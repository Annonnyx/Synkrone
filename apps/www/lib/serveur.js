'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs/promises');
const path = require('node:path');
const { panelAdmin, readPanelEnvValue } = require('./admin-ops');
const custom = require('./bot-custom');

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

const WELCOME_DEFAULT = custom.WELCOME_DEFAULT;
const GOODBYE_DEFAULT = custom.GOODBYE_DEFAULT;
const EMBED_DEFAULT = custom.EMBED_DEFAULT;

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

function defaultPath(applicationId) {
    return path.join(OVERLAY_ROOT, String(applicationId), '_default.json');
}

function serveurPathFromQuery(query) {
    const q = new URLSearchParams();
    const src = query || {};
    for (const key of ['t', 'guild', 'application']) {
        const value = String(src[key] || '').trim();
        if (value) q.set(key, value);
    }
    const qs = q.toString();
    return qs ? `/serveur?${qs}` : '/serveur';
}

function rememberServeurLink(req, claims) {
    if (!req.session || !claims) return;
    req.session.serveurLink = {
        guildId: claims.guildId,
        userId: claims.userId,
        applicationId: claims.applicationId
    };
}

function sessionServeurLink(req, discordId) {
    const link = req.session?.serveurLink;
    if (!link) return null;
    if (discordId && String(link.userId) !== String(discordId)) return null;
    if (!link.guildId || !link.applicationId) return null;
    return link;
}

async function listHostedGuilds(discordId, email) {
    const query = new URLSearchParams();
    if (discordId) query.set('discordUserId', discordId);
    if (email) query.set('email', String(email).trim().toLowerCase());
    if (!query.toString()) return [];
    try {
        const data = await panelAdmin(`/discord?${query.toString()}`);
        const guilds = [];
        const seen = new Set();
        for (const svc of data.services || []) {
            for (const g of svc.guilds || []) {
                const key = `${g.id}:${svc.applicationId || svc.id}`;
                if (seen.has(key)) continue;
                seen.add(key);
                guilds.push({
                    id: g.id,
                    name: g.name,
                    bot: svc.name,
                    applicationId: svc.applicationId,
                    href: svc.applicationId ? `/serveur?guild=${g.id}&application=${svc.applicationId}` : '/serveur'
                });
            }
        }
        return guilds;
    } catch {
        return [];
    }
}

function welcomeRel(guildId) {
    return `cogs/ADMIN/configuration/joinleave/bienvenue/data/${guildId}/config.json`;
}
function welcomeRelStaff(guildId) {
    return `cogs/staff/configuration/joinleave/bienvenue/data/${guildId}/config.json`;
}
function goodbyeRel(guildId) {
    return `cogs/ADMIN/configuration/joinleave/aurevoir/data_leave/${guildId}/config.json`;
}
function goodbyeRelStaff(guildId) {
    return `cogs/staff/configuration/joinleave/aurevoir/data_leave/${guildId}/config.json`;
}
function embedRel(guildId) {
    return `data/addons/data_embed_type/${guildId}.json`;
}
function embedGlobalRel() {
    return 'data/addons/data_embed_type/global_config.json';
}
function customRel(guildId) {
    return `data/synkrone_custom/${guildId}.json`;
}
function defaultsRel() {
    return 'config/defaults.json';
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
    return custom.parseColor(value, fallback);
}

async function loadDefault(applicationId) {
    const raw = (await readJson(defaultPath(applicationId))) || {};
    return custom.normalizeDefault(raw);
}

async function loadServer(applicationId, guildId) {
    const raw = (await readJson(overlayPath(applicationId, guildId))) || {};
    return custom.normalizeServer(raw);
}

function botFileJobs({ guildId, defaults, resolved }) {
    const bundle = custom.legacyBundle(resolved);
    const jobs = [
        [defaultsRel(), defaults],
        [embedGlobalRel(), {
            color: custom.parseColor(defaults.identity.embedColor),
            footer: defaults.identity.embedFooter,
            thumbnail: defaults.identity.embedThumbnail
        }]
    ];
    if (guildId && resolved) {
        jobs.push(
            [welcomeRel(guildId), bundle.welcome],
            [welcomeRelStaff(guildId), bundle.welcome],
            [goodbyeRel(guildId), bundle.goodbye],
            [goodbyeRelStaff(guildId), bundle.goodbye],
            [embedRel(guildId), bundle.embed],
            [customRel(guildId), resolved]
        );
    }
    return jobs;
}

async function writeHosted(serviceId, jobs) {
    for (const [rel, body] of jobs) {
        await panelAdmin(`/services/${encodeURIComponent(serviceId)}/file`, {
            method: 'POST',
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify({ path: rel, content: `${JSON.stringify(body, null, 4)}\n` })
        });
    }
}

async function writeOfficialDisk(bot, jobs) {
    const root = path.join(REPO_ROOT, bot.dir);
    for (const [rel, body] of jobs) {
        await writeJson(path.join(root, rel), body).catch(() => undefined);
    }
}

async function pushBotFiles(applicationId, { guildId, defaults, resolved }) {
    const jobs = botFileJobs({ guildId, defaults, resolved });
    const official = officialByApp(applicationId);
    if (official) await writeOfficialDisk(official, jobs);
    const hosted = await hostedLookup(applicationId);
    if (hosted.found && hosted.serviceId) await writeHosted(hosted.serviceId, jobs);
    return { official: Boolean(official), hosted: Boolean(hosted.found) };
}

async function ownedApplicationIds(discordId, email) {
    const query = new URLSearchParams();
    if (discordId) query.set('discordUserId', discordId);
    if (email) query.set('email', String(email).trim().toLowerCase());
    if (!query.toString()) return new Set();
    try {
        const data = await panelAdmin(`/discord?${query.toString()}`);
        return new Set((data.services || []).map((svc) => String(svc.applicationId || '')).filter(Boolean));
    } catch {
        return new Set();
    }
}

async function isBotCreator(user, applicationId) {
    if (!user || !applicationId) return false;
    if (officialByApp(applicationId) && (user.isTeamOwner || user.role === 'Admin')) return true;
    const owned = await ownedApplicationIds(discordUserId(user), user.email);
    return owned.has(String(applicationId));
}

function textChannels(list) {
    return (Array.isArray(list) ? list : [])
        .filter((ch) => ch.type === 0 || ch.type === 5 || ch.type == null)
        .map((ch) => ({ id: String(ch.id), name: String(ch.name || ch.id) }));
}

function guildRoles(list) {
    return (Array.isArray(list) ? list : [])
        .filter((role) => role.name !== '@everyone')
        .map((role) => ({ id: String(role.id), name: String(role.name || role.id) }));
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

const ADMINISTRATOR = 0x8n;
const MANAGE_GUILD = 0x20n;

function isGuildAdminFromSnapshot({ ownerId, userId, memberRoleIds, roles }) {
    if (String(ownerId || '') === String(userId || '')) return true;
    const mine = new Set(memberRoleIds || []);
    return (roles || []).some((role) => {
        if (!mine.has(role.id)) return false;
        const perms = BigInt(role.permissions || '0');
        return (perms & ADMINISTRATOR) === ADMINISTRATOR || (perms & MANAGE_GUILD) === MANAGE_GUILD;
    });
}

async function memberCanManage(token, guildId, userId) {
    if (!token) return false;
    const guild = await discordGet(token, `/guilds/${guildId}`);
    const member = await discordGet(token, `/guilds/${guildId}/members/${userId}`);
    const roles = await discordGet(token, `/guilds/${guildId}/roles`);
    return isGuildAdminFromSnapshot({
        ownerId: guild?.owner_id,
        userId,
        memberRoleIds: member?.roles,
        roles: Array.isArray(roles) ? roles : []
    });
}

async function assertConfigurer(discordId, guildId, applicationId) {
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
        try {
            return await getServeur(req, res);
        } catch (err) {
            return res.status(Number(err.status) || 503).json({
                ok: false,
                error: err.message || 'Configuration indisponible.'
            });
        }
    });
    mountServeurWrites(app);
}

async function getServeur(req, res) {
        const user = sessionUser(req);
        const discordId = discordUserId(user);
        const rawToken = String(req.query.t || '').trim();
        const claims = rawToken ? verifyToken(rawToken) : null;
        if (claims) rememberServeurLink(req, claims);
        const returnTo = serveurPathFromQuery(req.query);
        if (!discordId) {
            return res.status(401).json({
                ok: false,
                discordOnly: true,
                loginUrl: `/login?returnTo=${encodeURIComponent(returnTo)}`
            });
        }
        if (rawToken && !claims) {
            return res.status(403).json({
                ok: false,
                expired: true,
                error: 'Lien expiré. Relance /config sur Discord, puis Configurer sur le site.'
            });
        }
        const stored = sessionServeurLink(req, discordId);
        const guildId = String(claims?.guildId || req.query.guild || stored?.guildId || '').trim();
        const applicationId = String(claims?.applicationId || req.query.application || stored?.applicationId || '').trim();
        const layer = String(req.query.layer || '').trim() === 'default' ? 'default' : 'server';
        if (claims && claims.userId !== discordId) {
            return res.status(403).json({ ok: false, error: 'Ce lien Discord appartient à un autre compte.' });
        }
        const creator = applicationId ? await isBotCreator(user, applicationId) : false;
        if (applicationId && (layer === 'default' || !guildId) && creator) {
            const official = officialByApp(applicationId);
            const hosted = official ? { found: false } : await hostedLookup(applicationId);
            const defaults = await loadDefault(applicationId);
            return res.json({
                ok: true,
                layer: 'default',
                canEditDefaults: true,
                user: { id: discordId, username: user.username },
                applicationId,
                botName: official?.name || hosted.name || 'Bot custom',
                kind: official ? 'official' : hosted.found ? 'hosted' : 'unknown',
                defaults,
                catalog: custom.catalog()
            });
        }
        if (!guildId || !applicationId) {
            const guilds = await listHostedGuilds(discordId, user.email);
            return res.json({
                ok: true,
                needLink: true,
                user: { id: discordId, username: user.username },
                guilds,
                hint: guilds.length
                    ? 'Choisis un serveur, ou ouvre /config sur Discord pour un lien direct.'
                    : 'Ouvre /config sur le serveur Discord, puis Configurer sur le site.'
            });
        }
        const allowed = await assertConfigurer(discordId, guildId, applicationId);
        if (!allowed) {
            return res.status(403).json({
                ok: false,
                error: 'Il faut être propriétaire ou administrateur de ce serveur Discord.'
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
        let roles = [];
        if (hosted.found && hosted.serviceId) {
            try {
                const extra = await panelAdmin(
                    `/discord?applicationId=${encodeURIComponent(applicationId)}&guildId=${encodeURIComponent(guildId)}&memberId=${encodeURIComponent(discordId)}`
                );
                channels = textChannels(extra.channels || []);
                roles = guildRoles(extra.roles || []);
            } catch {
                channels = [];
            }
        } else if (official) {
            const token = tokenForOfficial(official);
            channels = textChannels(await discordGet(token, `/guilds/${guildId}/channels`));
            roles = guildRoles(await discordGet(token, `/guilds/${guildId}/roles`));
        }
        const defaults = await loadDefault(applicationId);
        const config = await loadServer(applicationId, guildId);
        const resolved = custom.resolveConfig(defaults, config);
        return res.json({
            ok: true,
            layer: 'server',
            canEditDefaults: creator,
            user: { id: discordId, username: user.username },
            guildId,
            applicationId,
            botName: official?.name || hosted.name || 'Bot custom',
            kind: official ? 'official' : hosted.found ? 'hosted' : 'unknown',
            channels,
            roles,
            defaults,
            allow: defaults.allow,
            locked: custom.lockedFields(defaults.allow),
            config,
            resolved,
            catalog: custom.catalog()
        });
}

function mountServeurWrites(app) {
    app.post('/api/serveur', async (req, res) => {
        const user = sessionUser(req);
        const discordId = discordUserId(user);
        if (!discordId) return res.status(401).json({ ok: false, discordOnly: true });
        const rawToken = String(req.body?.t || req.query.t || '').trim();
        const claims = rawToken ? verifyToken(rawToken) : null;
        if (claims) rememberServeurLink(req, claims);
        const stored = sessionServeurLink(req, discordId);
        const guildId = String(claims?.guildId || req.body?.guildId || stored?.guildId || '').trim();
        const applicationId = String(claims?.applicationId || req.body?.applicationId || stored?.applicationId || '').trim();
        if (!guildId || !applicationId) {
            return res.status(400).json({ ok: false, error: 'Serveur ou application manquant.' });
        }
        if (claims && claims.userId !== discordId) {
            return res.status(403).json({ ok: false, error: 'Ce lien Discord appartient à un autre compte.' });
        }
        const allowed = await assertConfigurer(discordId, guildId, applicationId);
        if (!allowed) {
            return res.status(403).json({ ok: false, error: 'Il faut être propriétaire ou administrateur de ce serveur Discord.' });
        }
        const defaults = await loadDefault(applicationId);
        const existing = await loadServer(applicationId, guildId);
        const body = req.body || {};
        const patch = body.config || body;
        const next = custom.applyServerPatch(existing, patch, defaults.allow);
        const resolved = custom.resolveConfig(defaults, next);
        const storedConfig = custom.persistServer(next, resolved);
        await writeJson(overlayPath(applicationId, guildId), storedConfig);
        try {
            await pushBotFiles(applicationId, { guildId, defaults, resolved });
        } catch (err) {
            if (!officialByApp(applicationId)) {
                return res.status(503).json({ ok: false, error: err.message || 'Volume hébergé injoignable.' });
            }
        }
        return res.json({ ok: true, config: next, resolved, locked: custom.lockedFields(defaults.allow) });
    });

    app.post('/api/serveur/defaults', async (req, res) => {
        const user = sessionUser(req);
        const discordId = discordUserId(user);
        if (!discordId) return res.status(401).json({ ok: false, discordOnly: true });
        const applicationId = String(req.body?.applicationId || req.query.application || '').trim();
        if (!applicationId) return res.status(400).json({ ok: false, error: 'Application manquante.' });
        if (!(await isBotCreator(user, applicationId))) {
            return res.status(403).json({ ok: false, error: 'Seul le créateur du bot règle la config défaut.' });
        }
        const defaults = custom.normalizeDefault(req.body?.defaults || req.body || {});
        await writeJson(defaultPath(applicationId), defaults);
        try {
            await pushBotFiles(applicationId, { defaults, resolved: null });
        } catch (err) {
            if (!officialByApp(applicationId)) {
                return res.status(503).json({ ok: false, error: err.message || 'Volume hébergé injoignable.' });
            }
        }
        return res.json({ ok: true, defaults });
    });
}

module.exports = {
    mountServeur,
    verifyToken,
    discordUserId,
    serveurPathFromQuery,
    isGuildAdminFromSnapshot,
    OFFICIAL_BOTS
};
