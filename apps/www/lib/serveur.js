'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs/promises');
const path = require('node:path');
const { panelAdmin, readPanelEnvValue } = require('./admin-ops');

const REPO_ROOT = path.join(__dirname, '..', '..');
const OVERLAY_ROOT = path.join(__dirname, '..', 'data', 'serveur-config');
const DISCORD_API = 'https://discord.com/api/v10';

const OFFICIAL_BOTS = [
    { slug: 'vax', name: 'Vax', applicationId: '1367891720871874560', dir: 'bots/synkrone/py/Vax', tokenEnv: 'BOT_TOKEN_VAX' },
    { slug: 'arceus', name: 'Arceus', applicationId: '1492591949792940183', dir: 'bots/synkrone/py/Arceus', tokenEnv: 'BOT_TOKEN_ARCEUS' },
    { slug: 'asuna', name: 'Asuna', applicationId: '1428865683986452640', dir: 'bots/synkrone/py/Asuna', tokenEnv: 'BOT_TOKEN_ASUNA' },
    { slug: 'kayaba', name: 'Kayaba', applicationId: '1385913159717621780', dir: 'bots/synkrone/py/Kayaba', tokenEnv: 'BOT_TOKEN_KAYABA' },
    { slug: 'yui', name: 'Yui', applicationId: '1460012999912853810', dir: 'bots/synkrone/py/Yui', tokenEnv: 'BOT_TOKEN_YUI' }
];

const WELCOME_DEFAULT = {
    channel_id: null,
    embed_title: 'Bienvenue sur {guild}',
    embed_description: '{user.mention} nous a rejoint !',
    content_message: 'On acclame tous {user.mention} !\nNous sommes désormais {guild.count}.'
};
const GOODBYE_DEFAULT = {
    channel_id: null,
    embed_title: 'Départ de {user}',
    embed_description: 'Triste de te voir partir...',
    content_message: '{user.mention} nous a quitté.\nNous sommes désormais {guild.count}.'
};
const EMBED_DEFAULT = { color: 0x660099, footer: '', author: '', thumbnail: '', image: '' };

function secrets() {
    const seen = new Set();
    const out = [];
    for (const raw of [
        process.env.SESSION_SECRET,
        process.env.BOT_CONFIG_SECRET,
        process.env.PLATFORM_SECRET_KEY,
        readPanelEnvValue('PLATFORM_SECRET_KEY'),
        readPanelEnvValue('BOT_CONFIG_SECRET'),
        readPanelEnvValue('SESSION_SECRET')
    ]) {
        const value = String(raw || '').trim();
        if (value.length < 8 || seen.has(value)) continue;
        seen.add(value);
        out.push(value);
    }
    return out;
}

function discordUserId(user) {
    if (!user || user.isGuest) return null;
    const id = String(user.id || '');
    if (/^\d{15,22}$/.test(id)) return id;
    const fromProviders = user.providers && user.providers.discord;
    if (fromProviders && /^\d{15,22}$/.test(String(fromProviders))) return String(fromProviders);
    return null;
}

function verifyToken(raw) {
    const token = String(raw || '').trim();
    const parts = token.split('.');
    if (parts.length !== 2) return null;
    const [b64, sig] = parts;
    if (!/^[A-Za-z0-9_-]+$/.test(b64) || !/^[a-f0-9]{32}$/.test(sig)) return null;
    for (const secret of secrets()) {
        const expected = crypto.createHmac('sha256', secret).update(b64).digest('hex').slice(0, 32);
        const a = Buffer.from(sig);
        const b = Buffer.from(expected);
        if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) continue;
        try {
            const padded = b64 + '='.repeat((4 - (b64.length % 4)) % 4);
            const payload = JSON.parse(Buffer.from(padded, 'base64').toString('utf8'));
            if (!payload || Number(payload.exp) < Date.now() / 1000) return null;
            if (!payload.g || !payload.u || !payload.a) return null;
            return { guildId: String(payload.g), userId: String(payload.u), applicationId: String(payload.a) };
        } catch {
            return null;
        }
    }
    return null;
}

function officialByApp(applicationId) {
    return OFFICIAL_BOTS.find((b) => b.applicationId === String(applicationId)) || null;
}

function tokenForOfficial(bot) {
    return String(process.env[bot.tokenEnv] || process.env.DISCORD_BOT_TOKEN || '').trim();
}

function overlayPath(applicationId, guildId) {
    return path.join(OVERLAY_ROOT, String(applicationId), `${guildId}.json`);
}

function welcomeRel(guildId) {
    return `cogs/ADMIN/configuration/joinleave/bienvenue/data/${guildId}/config.json`;
}
function goodbyeRel(guildId) {
    return `cogs/ADMIN/configuration/joinleave/aurevoir/data_leave/${guildId}/config.json`;
}
function embedRel(guildId) {
    return `data/addons/data_embed_type/${guildId}.json`;
}

async function readJson(file) {
    try {
        return JSON.parse(await fs.readFile(file, 'utf8'));
    } catch {
        return null;
    }
}

async function writeJson(file, data) {
    await fs.mkdir(path.dirname(file), { recursive: true });
    await fs.writeFile(file, `${JSON.stringify(data, null, 4)}\n`, 'utf8');
}

function parseColor(value, fallback = EMBED_DEFAULT.color) {
    if (typeof value === 'number' && Number.isFinite(value)) return value;
    const raw = String(value || '').trim().replace(/^#/, '');
    if (!raw) return fallback;
    const n = Number.parseInt(raw, 16);
    return Number.isFinite(n) ? n : fallback;
}

async function loadOverlay(applicationId, guildId) {
    const raw = (await readJson(overlayPath(applicationId, guildId))) || {};
    return {
        welcome: { ...WELCOME_DEFAULT, ...(raw.welcome || {}) },
        goodbye: { ...GOODBYE_DEFAULT, ...(raw.goodbye || {}) },
        embed: { ...EMBED_DEFAULT, ...(raw.embed || {}) }
    };
}

async function discordGet(token, pathname) {
    if (!token) return null;
    try {
        const res = await fetch(`${DISCORD_API}${pathname}`, {
            headers: { Authorization: `Bot ${token}` },
            signal: AbortSignal.timeout(4000)
        });
        if (!res.ok) return null;
        return await res.json();
    } catch {
        return null;
    }
}

async function writeHosted(serviceId, guildId, config) {
    const files = [
        [welcomeRel(guildId), { ...WELCOME_DEFAULT, ...config.welcome, channel_id: config.welcome.channel_id || null }],
        [goodbyeRel(guildId), { ...GOODBYE_DEFAULT, ...config.goodbye, channel_id: config.goodbye.channel_id || null }],
        [embedRel(guildId), { ...EMBED_DEFAULT, ...config.embed, color: parseColor(config.embed.color) }]
    ];
    for (const [rel, body] of files) {
        await panelAdmin(`/services/${encodeURIComponent(serviceId)}/file`, {
            method: 'POST',
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify({ path: rel, content: `${JSON.stringify(body, null, 4)}\n` })
        });
    }
}

async function writeOfficialDisk(bot, guildId, config) {
    const root = path.join(REPO_ROOT, bot.dir);
    const payload = {
        welcome: { ...WELCOME_DEFAULT, ...config.welcome },
        goodbye: { ...GOODBYE_DEFAULT, ...config.goodbye },
        embed: { ...EMBED_DEFAULT, ...config.embed, color: parseColor(config.embed.color) }
    };
    await writeJson(path.join(root, 'data', 'synkrone_guild', `${guildId}.json`), payload);
    const welcomeFile = path.join(root, welcomeRel(guildId));
    const goodbyeFile = path.join(root, goodbyeRel(guildId));
    const embedFile = path.join(root, embedRel(guildId));
    try {
        await fs.access(path.dirname(path.dirname(welcomeFile)));
        await writeJson(welcomeFile, payload.welcome);
    } catch {
        /* official tree without template welcome cog */
    }
    try {
        await fs.access(path.dirname(path.dirname(goodbyeFile)));
        await writeJson(goodbyeFile, payload.goodbye);
    } catch {
        /* skip */
    }
    await writeJson(embedFile, payload.embed).catch(() => undefined);
}

async function memberCanManage(token, guildId, userId) {
    if (!token) return false;
    const guild = await discordGet(token, `/guilds/${guildId}`);
    if (guild && String(guild.owner_id) === String(userId)) return true;
    const member = await discordGet(token, `/guilds/${guildId}/members/${userId}`);
    const roles = await discordGet(token, `/guilds/${guildId}/roles`);
    if (!member || !Array.isArray(roles)) return false;
    const mine = new Set(member.roles || []);
    const MANAGE_GUILD = 0x20n;
    return roles.some((role) => mine.has(role.id) && (BigInt(role.permissions || '0') & MANAGE_GUILD) === MANAGE_GUILD);
}

async function assertConfigurer(discordId, guildId, applicationId, claims) {
    if (claims && claims.userId === discordId && claims.guildId === guildId && claims.applicationId === applicationId) {
        return true;
    }
    const official = officialByApp(applicationId);
    if (official) {
        return memberCanManage(tokenForOfficial(official), guildId, discordId);
    }
    try {
        const extra = await panelAdmin(
            `/discord?applicationId=${encodeURIComponent(applicationId)}&guildId=${encodeURIComponent(guildId)}&memberId=${encodeURIComponent(discordId)}`
        );
        return Boolean(extra.manageGuild);
    } catch {
        return false;
    }
}

async function hostedLookup(applicationId) {
    try {
        return await panelAdmin(`/discord?applicationId=${encodeURIComponent(applicationId)}`);
    } catch {
        return { found: false };
    }
}

function sessionUser(req) {
    const user = req.session?.user;
    if (!user || user.isGuest) return null;
    return user;
}

function mountServeur(app) {
    app.get('/api/serveur', async (req, res) => {
        const user = sessionUser(req);
        const discordId = discordUserId(user);
        if (!discordId) {
            return res.status(401).json({
                ok: false,
                discordOnly: true,
                loginUrl: `/login?returnTo=${encodeURIComponent(`/serveur${req.url.includes('?') ? req.url.slice(req.url.indexOf('?')) : ''}`)}`
            });
        }
        const claims = verifyToken(req.query.t);
        const guildId = String(claims?.guildId || req.query.guild || '').trim();
        const applicationId = String(claims?.applicationId || req.query.application || '').trim();
        if (claims && claims.userId !== discordId) {
            return res.status(403).json({ ok: false, error: 'Ce lien Discord appartient à un autre compte.' });
        }
        if (!guildId || !applicationId) {
            return res.json({
                ok: true,
                needLink: true,
                user: { id: discordId, username: user.username },
                hint: 'Ouvre /config sur le serveur Discord, puis Configurer sur le site.'
            });
        }
        const official = officialByApp(applicationId);
        let hosted = { found: false };
        try {
            hosted = await hostedLookup(applicationId);
        } catch {
            hosted = { found: false };
        }
        let channels = [];
        if (hosted.found && hosted.serviceId) {
            try {
                const extra = await panelAdmin(
                    `/discord?applicationId=${encodeURIComponent(applicationId)}&guildId=${encodeURIComponent(guildId)}&memberId=${encodeURIComponent(discordId)}`
                );
                channels = extra.channels || [];
            } catch {
                channels = [];
            }
        } else if (official) {
            const token = tokenForOfficial(official);
            const remote = await discordGet(token, `/guilds/${guildId}/channels`);
            channels = Array.isArray(remote)
                ? remote.filter((ch) => ch.type === 0 || ch.type === 5).map((ch) => ({ id: ch.id, name: ch.name }))
                : [];
        }
        const config = await loadOverlay(applicationId, guildId);
        return res.json({
            ok: true,
            user: { id: discordId, username: user.username },
            guildId,
            applicationId,
            botName: official?.name || hosted.name || 'Bot custom',
            kind: official ? 'official' : hosted.found ? 'hosted' : 'unknown',
            channels,
            config: {
                welcome: {
                    ...config.welcome,
                    channel_id: config.welcome.channel_id ? String(config.welcome.channel_id) : ''
                },
                goodbye: {
                    ...config.goodbye,
                    channel_id: config.goodbye.channel_id ? String(config.goodbye.channel_id) : ''
                },
                embed: {
                    ...config.embed,
                    color: `#${parseColor(config.embed.color).toString(16).padStart(6, '0')}`
                }
            }
        });
    });

    app.post('/api/serveur', async (req, res) => {
        const user = sessionUser(req);
        const discordId = discordUserId(user);
        if (!discordId) return res.status(401).json({ ok: false, discordOnly: true });
        const claims = verifyToken(req.body?.t || req.query.t);
        const guildId = String(claims?.guildId || req.body?.guildId || '').trim();
        const applicationId = String(claims?.applicationId || req.body?.applicationId || '').trim();
        if (!guildId || !applicationId) {
            return res.status(400).json({ ok: false, error: 'Serveur ou application manquant.' });
        }
        if (claims && claims.userId !== discordId) {
            return res.status(403).json({ ok: false, error: 'Ce lien Discord appartient à un autre compte.' });
        }
        const allowed = await assertConfigurer(discordId, guildId, applicationId, claims);
        if (!allowed) {
            return res.status(403).json({ ok: false, error: 'Lien expiré ou permission insuffisante. Relance /config.' });
        }
        const body = req.body || {};
        const config = {
            welcome: { ...WELCOME_DEFAULT, ...(body.welcome || {}) },
            goodbye: { ...GOODBYE_DEFAULT, ...(body.goodbye || {}) },
            embed: { ...EMBED_DEFAULT, ...(body.embed || {}), color: parseColor(body.embed?.color) }
        };
        await writeJson(overlayPath(applicationId, guildId), config);
        const official = officialByApp(applicationId);
        if (official) {
            await writeOfficialDisk(official, guildId, config);
        }
        try {
            const hosted = await hostedLookup(applicationId);
            if (hosted.found && hosted.serviceId) {
                await writeHosted(hosted.serviceId, guildId, config);
            }
        } catch (err) {
            if (!official) {
                return res.status(503).json({ ok: false, error: err.message || 'Volume hébergé injoignable.' });
            }
        }
        return res.json({ ok: true });
    });
}

module.exports = {
    mountServeur,
    verifyToken,
    discordUserId,
    OFFICIAL_BOTS
};
