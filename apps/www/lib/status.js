'use strict';

const fs = require('node:fs/promises');
const path = require('node:path');
const http = require('node:http');

const STARTED_AT = Date.now();
const DATA_PATH = path.join(__dirname, '..', 'data', 'uptime.json');
const PUBLIC_DATA = path.join(
    __dirname,
    '..',
    '..',
    '..',
    'Synkrone',
    'test',
    'synkrone_authdiscord',
    'data'
);
const GAP_MS = 3 * 60 * 1000;
const KEEP_DAYS = 14;
const OFFICIAL_BOTS = 5;

function dayKey(ms) {
    return new Date(ms).toISOString().slice(0, 10);
}

function defaultStore() {
    return { lastBeat: null, days: {} };
}

async function readStore() {
    try {
        const raw = await fs.readFile(DATA_PATH, 'utf8');
        const parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== 'object') return defaultStore();
        return {
            lastBeat: Number(parsed.lastBeat) || null,
            days: parsed.days && typeof parsed.days === 'object' ? parsed.days : {}
        };
    } catch (err) {
        if (err.code !== 'ENOENT') throw err;
        return defaultStore();
    }
}

async function persistStore(store) {
    await fs.mkdir(path.dirname(DATA_PATH), { recursive: true });
    const tmp = `${DATA_PATH}.${process.pid}.tmp`;
    await fs.writeFile(tmp, JSON.stringify(store, null, 2), 'utf8');
    await fs.rename(tmp, DATA_PATH);
}

function addSpan(days, from, to, field) {
    let cursor = from;
    while (cursor < to) {
        const key = dayKey(cursor);
        const nextDay = Date.parse(`${key}T00:00:00.000Z`) + 24 * 60 * 60 * 1000;
        const end = Math.min(to, nextDay);
        if (!days[key]) days[key] = { up: 0, down: 0 };
        days[key][field] += end - cursor;
        cursor = end;
    }
}

function pruneDays(days) {
    const keys = Object.keys(days).sort();
    const cutoff = dayKey(Date.now() - KEEP_DAYS * 24 * 60 * 60 * 1000);
    for (const key of keys) {
        if (key < cutoff) delete days[key];
    }
}

async function beat() {
    const now = Date.now();
    const store = await readStore();
    if (store.lastBeat) {
        const gap = now - store.lastBeat;
        addSpan(store.days, store.lastBeat, now, gap > GAP_MS ? 'down' : 'up');
    } else {
        addSpan(store.days, now - 1000, now, 'up');
    }
    store.lastBeat = now;
    pruneDays(store.days);
    await persistStore(store);
    return store;
}

function summarize(store) {
    let up = 0;
    let down = 0;
    const bars = [];
    const keys = Object.keys(store.days || {}).sort().slice(-7);
    for (const key of keys) {
        const day = store.days[key] || { up: 0, down: 0 };
        up += Number(day.up) || 0;
        down += Number(day.down) || 0;
        const total = (Number(day.up) || 0) + (Number(day.down) || 0);
        bars.push({
            date: key,
            up: Number(day.up) || 0,
            down: Number(day.down) || 0,
            pct: total ? Math.round((day.up / total) * 1000) / 10 : 100
        });
    }
    const total = up + down;
    return {
        pct: total ? Math.round((up / total) * 1000) / 10 : 100,
        upMs: up,
        downMs: down,
        bars
    };
}

async function countJsonMap(file, rootKey) {
    try {
        const raw = await fs.readFile(path.join(PUBLIC_DATA, file), 'utf8');
        const parsed = JSON.parse(raw);
        const bag = parsed?.[rootKey];
        if (!bag || typeof bag !== 'object') return 0;
        return Object.keys(bag).length;
    } catch {
        return 0;
    }
}

async function countApprovedBots() {
    try {
        const raw = await fs.readFile(path.join(PUBLIC_DATA, 'publicbot.json'), 'utf8');
        const parsed = JSON.parse(raw);
        const bots = parsed?.bots && typeof parsed.bots === 'object' ? Object.values(parsed.bots) : [];
        return bots.filter((bot) => String(bot?.status || '') === 'approved').length;
    } catch {
        return 0;
    }
}

function fetchPanelStatus() {
    const port = Number(process.env.SYNKRONE_PANEL_PORT || 3000);
    return new Promise((resolve) => {
        const req = http.get({
            hostname: '127.0.0.1',
            port,
            path: '/hebergement/api/status/public',
            timeout: 1500
        }, (res) => {
            let raw = '';
            res.on('data', (chunk) => { raw += chunk; });
            res.on('end', () => {
                try {
                    resolve(JSON.parse(raw));
                } catch {
                    resolve(null);
                }
            });
        });
        req.on('timeout', () => {
            req.destroy();
            resolve(null);
        });
        req.on('error', () => resolve(null));
    });
}

function formatUptime(seconds) {
    const s = Math.max(0, Math.trunc(seconds));
    const d = Math.floor(s / 86400);
    const h = Math.floor((s % 86400) / 3600);
    const m = Math.floor((s % 3600) / 60);
    if (d) return `${d} j ${h} h`;
    if (h) return `${h} h ${m} min`;
    if (m) return `${m} min`;
    return `${s} s`;
}

async function collect() {
    const store = await beat();
    const window = summarize(store);
    const [accounts, bump, catalog, panel] = await Promise.all([
        countJsonMap('users.json', 'users'),
        countJsonMap('bump.json', 'servers'),
        countApprovedBots(),
        fetchPanelStatus()
    ]);
    const hosting = panel?.hosting || { discord: 0, minecraft: 0, web: 0, total: 0, running: 0 };
    return {
        ok: true,
        at: Date.now(),
        live: true,
        process: {
            startedAt: STARTED_AT,
            uptimeSec: Math.trunc(process.uptime()),
            uptimeLabel: formatUptime(process.uptime())
        },
        uptime: {
            pct: window.pct,
            windowDays: 7,
            upMs: window.upMs,
            downMs: window.downMs,
            bars: window.bars
        },
        hosting: {
            docker: Boolean(panel?.docker),
            discord: hosting.discord || 0,
            minecraft: hosting.minecraft || 0,
            web: hosting.web || 0,
            total: hosting.total || 0,
            running: hosting.running || 0
        },
        platform: {
            officialBots: OFFICIAL_BOTS,
            catalog,
            bump,
            accounts
        }
    };
}

function mountStatus(app) {
    if (!app || typeof app.get !== 'function') {
        throw new Error('mountStatus(app) attend une app Express');
    }
    beat().catch(() => undefined);
    setInterval(() => {
        beat().catch(() => undefined);
    }, 60 * 1000).unref();

    app.get('/api/status', async (_req, res) => {
        try {
            return res.json(await collect());
        } catch {
            return res.status(500).json({ error: 'Statut indisponible.' });
        }
    });
}

module.exports = { mountStatus, collect };
