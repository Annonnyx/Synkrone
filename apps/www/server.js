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

const app = express();
const PORT = Number(process.env.PORT || 3668);
const SESSION_MAX_AGE_MS = 365 * 24 * 60 * 60 * 1000;

if (!process.env.PASSWORD) {
    console.warn('[local] PASSWORD manquant (apps/ui/.env ou apps/www/.env) — /ui/ refuse les connexions');
}
if (!process.env.MDP) {
    console.warn('[local] MDP manquant (apps/sharing/.env ou apps/www/.env) — /sharing/ refuse les connexions');
}
if (!isDiscordOAuthConfigured()) {
    console.warn('[local] Discord OAuth non configuré — le site se parcourt sans login');
}

app.use(express.json({ limit: '500mb' }));
app.use(express.urlencoded({ limit: '500mb', extended: true }));
app.use(session({
    secret: process.env.SESSION_SECRET || 'synkrone_secret',
    resave: false,
    saveUninitialized: false,
    rolling: true,
    cookie: { maxAge: SESSION_MAX_AGE_MS, httpOnly: true, sameSite: 'lax' }
}));

mountUi(app);
mountSharing(app);
mountVux(app);

app.get('/hub', (req, res) => {
    res.sendFile(path.join(WWW_DIR, 'index.html'));
});

app.get(['/ui', '/ui/'], (req, res) => {
    res.sendFile(path.join(UI_DIR, 'index.html'));
});

app.get(['/sharing', '/sharing/'], (req, res) => {
    res.sendFile(path.join(SHARING_DIR, 'index.html'));
});

app.use('/ui', express.static(UI_DIR));
app.use('/sharing', express.static(SHARING_DIR));
app.use('/logo', express.static(path.join(WWW_DIR, 'logo')));
app.use('/design', express.static(path.join(WWW_DIR, 'design')));

mountPublic(app, { skipBodyParser: true, skipSession: true });

app.listen(PORT, '127.0.0.1', () => {
    console.log(`local (JSON + SQLite disque, aucune base distante)`);
    console.log(`  site     : http://127.0.0.1:${PORT}/`);
    console.log(`  vux      : http://127.0.0.1:${PORT}/vux/`);
    console.log(`  hub      : http://127.0.0.1:${PORT}/hub`);
    console.log(`  ui       : http://127.0.0.1:${PORT}/ui/`);
    console.log(`  sharing  : http://127.0.0.1:${PORT}/sharing/`);
    console.log(`  catalogue: ${DATA_DIR}`);
});
