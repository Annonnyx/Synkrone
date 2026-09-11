'use strict';

const fs = require('node:fs');
const fsp = require('node:fs/promises');
const path = require('node:path');
const { execFile } = require('node:child_process');
const { promisify } = require('node:util');
const dotenv = require('dotenv');

const execFileAsync = promisify(execFile);
const PANEL_ENV = path.join(__dirname, '..', '..', 'dashboard', 'Orbital-hebergeur', '.env');

if (fs.existsSync(PANEL_ENV)) {
    dotenv.config({ path: PANEL_ENV, override: false });
}

function panelOrigin() {
    const port = Number(process.env.SYNKRONE_PANEL_PORT || 3000);
    return `http://127.0.0.1:${port}/hebergement`;
}

function adminToken() {
    return String(process.env.PLATFORM_SECRET_KEY || '').trim();
}

async function panelAdmin(pathname, init = {}) {
    const token = adminToken();
    if (token.length < 16) {
        const err = new Error('PLATFORM_SECRET_KEY manquant pour administrer le panel.');
        err.status = 503;
        throw err;
    }
    const url = `${panelOrigin()}/api/internal/admin${pathname}`;
    const headers = {
        accept: 'application/json',
        authorization: `Bearer ${token}`,
        ...(init.headers || {})
    };
    let res;
    try {
        res = await fetch(url, { ...init, headers });
    } catch (error) {
        const err = new Error('Panel d’hébergement injoignable.');
        err.status = 503;
        throw err;
    }
    const text = await res.text();
    let data = {};
    try {
        data = text ? JSON.parse(text) : {};
    } catch {
        data = { error: text.slice(0, 200) };
    }
    if (!res.ok) {
        const err = new Error(data.error || `Panel ${res.status}`);
        err.status = res.status;
        throw err;
    }
    return data;
}

async function tailFile(filePath, maxBytes = 80 * 1024) {
    try {
        const stat = await fsp.stat(filePath);
        const start = Math.max(0, stat.size - maxBytes);
        const handle = await fsp.open(filePath, 'r');
        try {
            const buf = Buffer.alloc(stat.size - start);
            await handle.read(buf, 0, buf.length, start);
            return buf.toString('utf8');
        } finally {
            await handle.close();
        }
    } catch {
        return '';
    }
}

async function pm2Logs(pmId, lines = 200) {
    const { stdout } = await execFileAsync('pm2', ['jlist'], { maxBuffer: 2 * 1024 * 1024 });
    const processes = JSON.parse(stdout);
    const row = processes.find((p) => String(p.pm_id) === String(pmId));
    if (!row) {
        const err = new Error('Processus introuvable.');
        err.status = 404;
        throw err;
    }
    const out = await tailFile(row.pm2_env?.pm_out_log_path);
    const err = await tailFile(row.pm2_env?.pm_err_log_path);
    const clip = (text) => text.split(/\r?\n/).slice(-Math.max(20, Math.min(500, Number(lines) || 200))).join('\n');
    return {
        id: row.pm_id,
        name: row.name,
        out: clip(out),
        err: clip(err)
    };
}

async function listTickets() {
    const token = String(process.env.DISCORD_BOT_TOKEN || '').trim();
    const guildId = String(process.env.DISCORD_GUILD_ID || '').trim();
    const categoryId = String(process.env.DISCORD_TICKET_CATEGORY_ID || '1465825775231176717').trim();
    if (!token || !guildId) {
        return { configured: false, tickets: [], hint: 'DISCORD_BOT_TOKEN et DISCORD_GUILD_ID requis.' };
    }
    const res = await fetch(`https://discord.com/api/v10/guilds/${guildId}/channels`, {
        headers: { Authorization: `Bot ${token}` }
    });
    if (!res.ok) {
        const err = new Error('Impossible de lire les salons Discord.');
        err.status = res.status;
        throw err;
    }
    const channels = await res.json();
    const tickets = (Array.isArray(channels) ? channels : [])
        .filter((ch) => {
            if (Number(ch.type) !== 0) return false;
            if (categoryId && String(ch.parent_id || '') !== categoryId) return false;
            return true;
        })
        .map((ch) => ({
            id: ch.id,
            name: ch.name,
            topic: ch.topic || '',
            createdAt: ch.id ? Number(BigInt(ch.id) >> 22n) + 1420070400000 : null,
            url: `https://discord.com/channels/${guildId}/${ch.id}`
        }))
        .sort((a, b) => (b.createdAt || 0) - (a.createdAt || 0));
    return {
        configured: true,
        categoryId: categoryId || null,
        tickets
    };
}

module.exports = {
    panelAdmin,
    pm2Logs,
    listTickets
};
