'use strict';

const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { spawn, spawnSync } = require('node:child_process');

const REPO_ROOT = path.join(__dirname, '..', '..', '..');
const PANEL_DIR = path.join(REPO_ROOT, 'dashboard', 'Orbital-hebergeur');
const PANEL_PREFIX = '/hebergement';
const PANEL_PORT = Number(process.env.SYNKRONE_PANEL_PORT || 3000);

const STARTING_HTML = `<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta http-equiv="refresh" content="2">
  <title>Synkrone — hébergement</title>
  <style>
    html,body{margin:0;min-height:100%;background:#1B211E;color:#EEF0EA;font:16px/1.5 "IBM Plex Sans",system-ui,sans-serif}
    main{max-width:36rem;padding:3rem 1.5rem}
    h1{font-family:"Zilla Slab",Georgia,serif;font-weight:700;font-size:2.6rem;letter-spacing:-.01em;margin:0 0 .75rem}
    p{color:#8FA096;margin:0;max-width:46ch}
  </style>
</head>
<body>
  <main>
    <h1>Synkrone</h1>
    <p>Le panel d’hébergement démarre. Rechargement automatique dans deux secondes.</p>
  </main>
</body>
</html>`;

function panelPublicOrigin(publicPort) {
    const fromEnv = String(process.env.SYNKRONE_PANEL_ORIGIN || process.env.ORBITAL_PUBLIC_ORIGIN || '')
        .trim()
        .replace(/\/$/, '');
    if (fromEnv) {
        return fromEnv.endsWith(PANEL_PREFIX) ? fromEnv : `${fromEnv}${PANEL_PREFIX}`;
    }
    return `http://127.0.0.1:${publicPort}${PANEL_PREFIX}`;
}

function nextBin() {
    return path.join(PANEL_DIR, 'node_modules', 'next', 'dist', 'bin', 'next');
}

function ensurePanelInstalled() {
    if (fs.existsSync(nextBin())) return true;
    if (!fs.existsSync(path.join(PANEL_DIR, 'package.json'))) {
        console.warn('[panel] dossier introuvable:', PANEL_DIR);
        return false;
    }
    console.warn('[panel] npm install (première fois)…');
    const result = spawnSync('npm', ['install'], { cwd: PANEL_DIR, stdio: 'inherit' });
    return result.status === 0 && fs.existsSync(nextBin());
}

function forwardedProto(req) {
    const raw = req.headers['x-forwarded-proto'] || req.headers['x-forwarded-protocol'];
    if (raw) return String(raw).split(',')[0].trim() || 'http';
    if (req.secure) return 'https';
    return 'http';
}

function proxyHeaders(req) {
    const headers = { ...req.headers };
    headers['x-forwarded-host'] = req.headers.host || '';
    headers['x-forwarded-proto'] = forwardedProto(req);
    headers['x-forwarded-for'] = req.socket?.remoteAddress || '';
    delete headers.connection;
    return headers;
}

function proxyWeb(req, res) {
    const pReq = http.request({
        hostname: '127.0.0.1',
        port: PANEL_PORT,
        path: req.originalUrl || req.url,
        method: req.method,
        headers: proxyHeaders(req)
    }, (pRes) => {
        res.writeHead(pRes.statusCode || 502, pRes.headers);
        pRes.pipe(res);
    });
    pReq.on('error', () => {
        if (res.headersSent) return;
        res.statusCode = 503;
        res.setHeader('Content-Type', 'text/html; charset=utf-8');
        res.setHeader('Retry-After', '2');
        res.end(STARTING_HTML);
    });
    req.pipe(pReq);
}

function isPanelUrl(url) {
    const pathOnly = String(url || '').split('?')[0];
    return pathOnly === PANEL_PREFIX || pathOnly.startsWith(`${PANEL_PREFIX}/`);
}

function mountPanelProxy(app) {
    const handle = (req, res) => {
        proxyWeb(req, res);
    };
    // Express 5 : splat nommé + regex, pour ne jamais laisser le SPA public gagner.
    app.use('/hebergement{/*path}', handle);
    app.use(/^\/hebergement(\/|$)/, handle);
}

function panelHostName(hostHeader) {
    return String(hostHeader || '').split(':')[0].trim().toLowerCase();
}

function isPanelShortcutHost(hostHeader) {
    const host = panelHostName(hostHeader);
    return host === 'panel.synkrone.app' || host === 'pannel.synkrone.app';
}

function requestSearch(req) {
    const url = String(req.url || '');
    const q = url.indexOf('?');
    return q >= 0 ? url.slice(q) : '';
}

/** Si Next perd le basePath (/dashboard) ou si on ouvre panel.synkrone.app/, ne pas servir l'accueil. */
function mountPanelFallbacks(app) {
    app.use((req, res, next) => {
        const pathOnly = String(req.path || '/');
        const search = requestSearch(req);
        if (isPanelShortcutHost(req.headers.host) && (pathOnly === '/' || pathOnly === '/accueil')) {
            return res.redirect(302, `${PANEL_PREFIX}${search}`);
        }
        if (pathOnly === '/dashboard' || pathOnly.startsWith('/dashboard/')) {
            return res.redirect(302, `${PANEL_PREFIX}${pathOnly}${search}`);
        }
        return next();
    });
}

function attachUpgrade(server) {
    if (server.__synkronePanelWrapped) return;
    server.__synkronePanelWrapped = true;
    const requestListeners = server.listeners('request').slice();
    server.removeAllListeners('request');
    server.on('request', (req, res) => {
        if (isPanelUrl(req.url)) {
            proxyWeb(req, res);
            return;
        }
        for (const listener of requestListeners) listener.call(server, req, res);
    });
    server.on('upgrade', (req, socket, head) => {
        const url = String(req.url || '');
        if (!isPanelUrl(url)) return;
        const pReq = http.request({
            hostname: '127.0.0.1',
            port: PANEL_PORT,
            path: url,
            method: 'GET',
            headers: req.headers
        });
        pReq.on('upgrade', (pRes, pSocket, pHead) => {
            const lines = [`HTTP/1.1 ${pRes.statusCode} Switching Protocols`];
            for (const [key, value] of Object.entries(pRes.headers)) {
                if (value === undefined) continue;
                lines.push(`${key}: ${Array.isArray(value) ? value.join(', ') : value}`);
            }
            socket.write(`${lines.join('\r\n')}\r\n\r\n`);
            if (head?.length) pSocket.write(head);
            if (pHead?.length) socket.write(pHead);
            pSocket.pipe(socket);
            socket.pipe(pSocket);
        });
        pReq.on('error', () => socket.destroy());
        pReq.end();
    });
}

function panelBuilt() {
    return fs.existsSync(path.join(PANEL_DIR, '.next', 'BUILD_ID'));
}

function loadPanelEnvFile() {
    const file = path.join(PANEL_DIR, '.env');
    const out = {};
    if (!fs.existsSync(file)) return out;
    for (const line of fs.readFileSync(file, 'utf8').split(/\r?\n/)) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith('#')) continue;
        const eq = trimmed.indexOf('=');
        if (eq <= 0) continue;
        const key = trimmed.slice(0, eq).trim();
        let value = trimmed.slice(eq + 1).trim();
        if (
            (value.startsWith('"') && value.endsWith('"'))
            || (value.startsWith("'") && value.endsWith("'"))
        ) {
            value = value.slice(1, -1);
        }
        if (!key || value === '') continue;
        out[key] = value;
    }
    return out;
}

function spawnPanel({ publicPort }) {
    if (String(process.env.SYNKRONE_SKIP_PANEL || '') === '1') {
        console.warn('[panel] SYNKRONE_SKIP_PANEL=1 — panel non lancé');
        return null;
    }
    if (!ensurePanelInstalled()) {
        console.warn('[panel] Next.js absent. Le site tourne, /hebergement restera en attente.');
        return null;
    }
    const production = process.env.NODE_ENV === 'production';
    if (production && !panelBuilt()) {
        console.error('[panel] Build manquant. Lancer `npm run build` avant `npm start`.');
        return null;
    }
    const origin = panelPublicOrigin(publicPort);
    const inherited = { ...process.env };
    // An empty PLATFORM_SECRET_KEY inherited from the site blocks Next from
    // loading dashboard/.env (dotenv does not override existing keys). Tokens
    // then get encrypted with a fallback and become unreadable later.
    delete inherited.PLATFORM_SECRET_KEY;
    const child = spawn(process.execPath, [
        nextBin(),
        production ? 'start' : 'dev',
        '--hostname',
        '127.0.0.1',
        '--port',
        String(PANEL_PORT)
    ], {
        cwd: PANEL_DIR,
        stdio: ['ignore', 'inherit', 'inherit'],
        env: {
            ...inherited,
            ...loadPanelEnvFile(),
            PORT: String(PANEL_PORT),
            SYNKRONE_PANEL_ORIGIN: origin
        }
    });
    child.on('exit', (code, signal) => {
        if (signal === 'SIGTERM' || signal === 'SIGINT') return;
        console.warn(`[panel] Next s'est arrêté (${signal || code}). Relancer le process.`);
    });
    console.log(`[panel] Next ${production ? 'start' : 'dev'} http://127.0.0.1:${PANEL_PORT}${PANEL_PREFIX} → ${origin}`);
    return child;
}

function shutdownPanel(child) {
    if (!child || child.killed) return;
    child.kill('SIGTERM');
}

module.exports = {
    PANEL_PREFIX,
    PANEL_PORT,
    panelPublicOrigin,
    mountPanelProxy,
    mountPanelFallbacks,
    attachUpgrade,
    spawnPanel,
    shutdownPanel
};
