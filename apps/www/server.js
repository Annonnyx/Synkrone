const os = require('os');
const path = require('path');
const Module = require('module');

const WWW_DIR = __dirname;
const UI_DIR = path.join(__dirname, '..', 'ui');
const SHARING_DIR = path.join(__dirname, '..', 'sharing');
const REPO_ROOT = path.join(__dirname, '..', '..');
const PUBLIC_DIR = path.join(REPO_ROOT, 'Synkrone', 'test', 'synkrone_authdiscord');
const VUX_DIR = path.join(REPO_ROOT, 'Synkrone', 'html', 'vux');
const WWW_MODULES = path.join(WWW_DIR, 'node_modules');

process.env.NODE_PATH = [WWW_MODULES, process.env.NODE_PATH].filter(Boolean).join(path.delimiter);
Module._initPaths();

require('dotenv').config({ path: path.join(UI_DIR, '.env') });
require('dotenv').config({ path: path.join(SHARING_DIR, '.env') });
require('dotenv').config({ path: path.join(PUBLIC_DIR, '.env') });
delete process.env.PORT;
require('dotenv').config({ path: path.join(WWW_DIR, '.env') });

const express = require('express');
const session = require('express-session');
const { mountUi } = require('../ui/server');
const { mountSharing, DATA_DIR } = require('../sharing/server');
const { mountPublic, isDiscordOAuthConfigured } = require(path.join(PUBLIC_DIR, 'server.js'));
const { mountVux } = require(path.join(VUX_DIR, 'server.js'));
// krones-api: wallet JSON (pas Stripe) — module Krônes
const { mountKrones } = require('./lib/krones');
const { mountDashbot } = require('./lib/dashbot');
const { mountCommands } = require('./lib/commands');
const { mountStatus } = require('./lib/status');
const { billingPublicDto } = require('./lib/billing');
const { mountServeur } = require('./lib/serveur');
const { mountCompte } = require('./lib/compte');
const {
    COOKIE_NAME,
    createFileSessionStore,
    sessionCookieOptions
} = require('./lib/session-store');
const {
    PANEL_PREFIX,
    panelPublicOrigin,
    mountPanelProxy,
    mountPanelFallbacks,
    attachUpgrade,
    spawnPanel,
    shutdownPanel
} = require('./lib/panel');

const app = express();
const PORT = Number(process.env.PORT || 3668);
const LISTEN_HOST = String(process.env.SYNKRONE_LISTEN_HOST || '127.0.0.1').trim() || '127.0.0.1';
const IS_PROD = process.env.NODE_ENV === 'production';
const INTERNAL_TOOLS = process.env.SYNKRONE_INTERNAL === '1' || !IS_PROD;
const HUB_ENABLED = process.env.SYNKRONE_HUB === '0' ? false : true;

function lanUrls(port) {
    const urls = [];
    for (const addrs of Object.values(os.networkInterfaces())) {
        for (const a of addrs || []) {
            const v4 = a.family === 'IPv4' || a.family === 4;
            if (v4 && !a.internal) urls.push(`http://${a.address}:${port}/`);
        }
    }
    return urls;
}

// Avant le parser JSON : le body du panel Next ne doit pas être consommé ici.
mountPanelProxy(app);

if (!process.env.PASSWORD) {
    console.warn('[local] PASSWORD manquant (apps/ui/.env ou apps/www/.env) — /ui/ refuse les connexions');
}
if (!process.env.MDP) {
    console.warn('[local] MDP manquant (apps/sharing/.env ou apps/www/.env) — /sharing/ refuse les connexions');
}
if (!isDiscordOAuthConfigured()) {
    console.warn('[local] Discord OAuth non configuré — le site se parcourt sans login');
}

if (IS_PROD) {
    const secret = String(process.env.SESSION_SECRET || '').trim();
    if (!secret || secret === 'synkrone_secret' || secret === 'change-me-local') {
        console.error('[prod] SESSION_SECRET manquant ou trop faible — refus de démarrer');
        process.exit(1);
    }
}

app.set('trust proxy', 1);
app.use(express.json({ limit: '500mb' }));
app.use(express.urlencoded({ limit: '500mb', extended: true }));
app.use(session({
    name: COOKIE_NAME,
    secret: process.env.SESSION_SECRET || 'synkrone_secret',
    resave: false,
    saveUninitialized: false,
    rolling: false,
    store: createFileSessionStore(path.join(WWW_DIR, 'data', 'sessions')),
    cookie: sessionCookieOptions(IS_PROD)
}));

if (HUB_ENABLED) {
    app.get('/hub', (req, res) => {
        res.sendFile(path.join(WWW_DIR, 'index.html'));
    });
}
if (INTERNAL_TOOLS) {
    mountUi(app);
    mountSharing(app);
    app.get(['/ui', '/ui/'], (req, res) => {
        res.sendFile(path.join(UI_DIR, 'index.html'));
    });
    app.get(['/sharing', '/sharing/'], (req, res) => {
        res.sendFile(path.join(SHARING_DIR, 'index.html'));
    });
    app.use('/ui', express.static(UI_DIR));
    app.use('/sharing', express.static(SHARING_DIR));
} else {
    console.log('[prod] /ui /sharing fermés (SYNKRONE_INTERNAL=1 pour les ouvrir)');
}

mountVux(app);
function staticAssetHeaders(res, filePath) {
    if (String(filePath).endsWith('.html')) {
        res.setHeader('Cache-Control', 'no-store');
        return;
    }
    res.setHeader('Cache-Control', 'public, max-age=86400');
}
const staticOpts = { etag: true, setHeaders: staticAssetHeaders };

app.use('/logo', express.static(path.join(WWW_DIR, 'logo'), { maxAge: '7d', etag: true }));
app.use('/design', express.static(path.join(WWW_DIR, 'design'), staticOpts));

app.get('/api/config', (_req, res) => {
    const billing = billingPublicDto(null);
    res.json({
        panelOrigin: panelPublicOrigin(PORT),
        internal: INTERNAL_TOOLS,
        hub: HUB_ENABLED,
        supportInvite: process.env.DISCORD_SUPPORT_INVITE_URL || 'https://discord.gg/p768u2Pgp3',
        sellerReady: billing.sellerReady,
        seller: billing.seller,
        methods: billing.methods,
        mediatorReady: Boolean(billing.seller?.mediatorReady),
        mediator: {
            name: billing.seller?.mediatorName || '',
            url: billing.seller?.mediatorUrl || '',
            address: billing.seller?.mediatorAddress || ''
        }
    });
});

mountKrones(app);
mountStatus(app);
mountDashbot(app);
mountCommands(app);
mountServeur(app);
mountCompte(app);
mountPanelFallbacks(app);
mountPublic(app, { skipBodyParser: true, skipSession: true });

function logOAuthRedirects(port) {
    const {
        discordRedirectUri,
        githubRedirectUri,
        googleRedirectUri,
        panelOAuthRedirectUri
    } = require('./lib/oauth-origin');
    console.log('  OAuth site');
    console.log(`    Discord     ${discordRedirectUri()}`);
    console.log(`    GitHub      ${githubRedirectUri()}`);
    console.log(`    Google      ${googleRedirectUri()}`);
    console.log('  OAuth panel');
    console.log(`    Discord     ${panelOAuthRedirectUri('discord', port)}`);
    console.log(`    GitHub      ${panelOAuthRedirectUri('github', port)}`);
    console.log(`    Google      ${panelOAuthRedirectUri('google', port)}`);
}

const panelChild = spawnPanel({ publicPort: PORT });
const server = app.listen(PORT, LISTEN_HOST, () => {
    attachUpgrade(server);
    console.log(`synkrone — un process, un port (écoute ${LISTEN_HOST}:${PORT}${IS_PROD ? ', production' : ''})`);
    console.log(`  site        : http://127.0.0.1:${PORT}/`);
    if (LISTEN_HOST === '0.0.0.0' || LISTEN_HOST === '::') {
        for (const url of lanUrls(PORT)) console.log(`  réseau      : ${url}`);
    }
    console.log(`  hébergement : http://127.0.0.1:${PORT}${PANEL_PREFIX}`);
    console.log(`  vux         : http://127.0.0.1:${PORT}/vux/`);
    if (HUB_ENABLED) {
        console.log(`  hub         : http://127.0.0.1:${PORT}/hub`);
    }
    if (INTERNAL_TOOLS) {
        console.log(`  ui          : http://127.0.0.1:${PORT}/ui/`);
        console.log(`  sharing     : http://127.0.0.1:${PORT}/sharing/`);
    }
    console.log(`  catalogue   : ${DATA_DIR}`);
    logOAuthRedirects(PORT);
});

function shutdown(signal) {
    shutdownPanel(panelChild);
    server.close(() => process.exit(0));
    setTimeout(() => process.exit(0), 4000).unref();
    if (signal) console.log(`[synkrone] arrêt (${signal})`);
}
process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));
