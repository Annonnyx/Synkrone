'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs/promises');
const path = require('node:path');
const { createFileSessionStore, SESSION_MAX_AGE_MS } = require('./session-store');
const { panelAdmin, readPanelEnvValue } = require('./admin-ops');

const MAP_PATH = path.join(
    __dirname,
    '..',
    '..',
    '..',
    'Synkrone',
    'test',
    'synkrone_authdiscord',
    'data',
    'identity-map.json'
);
const SESSIONS_DIR = path.join(__dirname, '..', 'data', 'sessions');

function platformSecret() {
    return String(readPanelEnvValue('PLATFORM_SECRET_KEY') || process.env.PLATFORM_SECRET_KEY || '').trim();
}

function requireInternalAuth(req) {
    const expected = platformSecret();
    const auth = String(req.headers.authorization || '');
    const token = auth.startsWith('Bearer ') ? auth.slice(7).trim() : '';
    if (expected.length < 16 || token.length !== expected.length) return false;
    try {
        return crypto.timingSafeEqual(Buffer.from(token), Buffer.from(expected));
    } catch {
        return false;
    }
}

async function readMap() {
    try {
        const parsed = JSON.parse(await fs.readFile(MAP_PATH, 'utf8'));
        return {
            bySiteId: parsed.bySiteId && typeof parsed.bySiteId === 'object' ? parsed.bySiteId : {},
            byPanelId: parsed.byPanelId && typeof parsed.byPanelId === 'object' ? parsed.byPanelId : {},
            byDiscordId: parsed.byDiscordId && typeof parsed.byDiscordId === 'object' ? parsed.byDiscordId : {}
        };
    } catch {
        return { bySiteId: {}, byPanelId: {}, byDiscordId: {} };
    }
}

async function writeMap(map) {
    await fs.mkdir(path.dirname(MAP_PATH), { recursive: true });
    await fs.writeFile(MAP_PATH, JSON.stringify(map, null, 2), 'utf8');
}

async function rememberIdentity({ siteUserId, panelUserId, discordId, email }) {
    const map = await readMap();
    const row = {
        siteUserId: siteUserId ? String(siteUserId) : '',
        panelUserId: panelUserId ? String(panelUserId) : '',
        discordId: discordId ? String(discordId) : '',
        email: email ? String(email).toLowerCase() : '',
        updatedAt: Date.now()
    };
    if (row.siteUserId) map.bySiteId[row.siteUserId] = row;
    if (row.panelUserId) map.byPanelId[row.panelUserId] = row;
    if (row.discordId) map.byDiscordId[row.discordId] = row;
    await writeMap(map);
    return row;
}

async function identityFor(kind, id) {
    const map = await readMap();
    const key = String(id || '');
    if (!key) return null;
    if (kind === 'site') return map.bySiteId[key] || null;
    if (kind === 'panel') return map.byPanelId[key] || null;
    if (kind === 'discord') return map.byDiscordId[key] || null;
    return null;
}

async function issueSiteSession(userPayload) {
    const sid = crypto.randomBytes(24).toString('base64url');
    const store = createFileSessionStore(SESSIONS_DIR);
    const sess = {
        cookie: {
            originalMaxAge: SESSION_MAX_AGE_MS,
            maxAge: SESSION_MAX_AGE_MS,
            httpOnly: true,
            path: '/',
            sameSite: 'lax'
        },
        user: userPayload
    };
    await new Promise((resolve, reject) => {
        store.set(sid, sess, (err) => (err ? reject(err) : resolve()));
    });
    return sid;
}

function panelBridgeFromSiteUser(user) {
    if (!user || user.isGuest) return null;
    const id = String(user.id || '').trim();
    if (!id || id === 'guest') return null;
    const providers = user.providers && typeof user.providers === 'object' ? user.providers : {};
    const discord = /^\d{15,22}$/.test(id) ? id : String(providers.discord || '').trim();
    if (/^\d{15,22}$/.test(discord)) {
        return {
            provider: 'discord',
            profile: {
                id: discord,
                name: user.username,
                login: user.username,
                email: user.email || '',
                avatarUrl: user.avatar
            }
        };
    }
    let github = String(providers.github || '').trim();
    if (!github && id.startsWith('github:')) github = id.slice(7);
    if (github && !github.startsWith('panel-')) {
        return {
            provider: 'github',
            profile: {
                id: github,
                name: user.username,
                login: user.username,
                email: user.email || '',
                avatarUrl: user.avatar
            }
        };
    }
    let google = String(providers.google || '').trim();
    if (!google && id.startsWith('google:')) google = id.slice(7);
    if (google && !google.startsWith('panel-')) {
        return {
            provider: 'google',
            profile: {
                id: google,
                name: user.username,
                login: user.username,
                email: user.email || '',
                avatarUrl: user.avatar
            }
        };
    }
    return null;
}

async function requestPanelSession(payload) {
    return panelAdmin('/session-bridge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });
}

function panelCookieOptions(isProd) {
    return {
        httpOnly: true,
        sameSite: 'lax',
        secure: Boolean(isProd),
        path: '/',
        maxAge: SESSION_MAX_AGE_MS
    };
}

function siteCookieOptions(isProd) {
    return {
        httpOnly: true,
        sameSite: 'lax',
        secure: Boolean(isProd),
        path: '/',
        maxAge: SESSION_MAX_AGE_MS
    };
}

module.exports = {
    platformSecret,
    requireInternalAuth,
    rememberIdentity,
    identityFor,
    issueSiteSession,
    panelBridgeFromSiteUser,
    requestPanelSession,
    panelCookieOptions,
    siteCookieOptions,
    SESSION_MAX_AGE_MS
};
