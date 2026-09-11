const fs = require('node:fs/promises');
const path = require('node:path');
const axios = require('axios');

const DATA_PATH = path.join(__dirname, '..', 'data', 'dashbot.json');
const DISCORD_API = 'https://discord.com/api/v10';
const SLOT_COST = 10;
const MAX_ACTIONS = 40;
const GUILD_CACHE_TTL_MS = 45 * 1000;
const GUILD_FETCH_LIMIT = 40;
const MEMBER_CONCURRENCY = 4;

const BOTS = [
    { id: '1367891720871874560', slug: 'vax', name: 'Vax', role: 'Modération', prefix: '!', icon: '/assets/images/vax.png' },
    { id: '1492591949792940183', slug: 'arceus', name: 'Arceus', role: 'Pokémon', prefix: "'", icon: '/assets/images/arceus.png' },
    { id: '1428865683986452640', slug: 'asuna', name: 'Asuna', role: 'Jeux', prefix: '$', icon: '/assets/images/asuna.png' },
    { id: '1385913159717621780', slug: 'kayaba', name: 'Kayaba', role: 'Combat', prefix: '.', icon: '/assets/images/kayaba.png' },
    { id: '1460012999912853810', slug: 'yui', name: 'Yui', role: 'Architecture', prefix: '?', icon: '/assets/images/yui.png' }
];

const DEMO_GUILDS = [
    { id: 'demo-alpha', name: 'Atelier Kronium', icon: '/assets/images/logo.jpg', role: 'owner', memberCount: 128 },
    { id: 'demo-beta', name: 'Guilde Synkral', icon: '/assets/images/logo.jpg', role: 'admin', memberCount: 42 },
    { id: 'demo-gamma', name: 'Salon Test', icon: '/assets/images/logo.jpg', role: 'owner', memberCount: 8 }
];

const guildCache = new Map();
let writeChain = Promise.resolve();

function isDiscordOAuthConfigured() {
    return Boolean(
        String(process.env.DISCORD_CLIENT_ID || '').trim()
        && String(process.env.DISCORD_CLIENT_SECRET || '').trim()
        && String(process.env.DISCORD_REDIRECT_URI || '').trim()
    );
}

function sessionUser(req) {
    const user = req.session?.user;
    if (!user || user.isGuest || String(user.id || '') === 'guest') return null;
    return user;
}

function isDemoId(id) {
    return String(id || '').startsWith('demo-');
}

function inviteUrl(botId, guildId) {
    const url = new URL('https://discord.com/oauth2/authorize');
    url.searchParams.set('client_id', String(botId));
    url.searchParams.set('scope', 'bot applications.commands');
    if (guildId && !isDemoId(guildId)) {
        url.searchParams.set('guild_id', String(guildId));
    }
    return url.toString();
}

function publicBots(guildId) {
    return BOTS.map((bot) => ({
        ...bot,
        inviteUrl: inviteUrl(bot.id, guildId)
    }));
}

function emptyBucket() {
    return {
        slotCount: 1,
        selectedGuildId: DEMO_GUILDS[0].id,
        invites: {
            [DEMO_GUILDS[0].id]: {
                [BOTS[0].id]: { invited: true, at: Date.now() }
            }
        },
        actions: [
            {
                at: Date.now(),
                type: 'seed',
                message: 'Vax marqué présent sur Atelier Kronium (démo).'
            }
        ]
    };
}

function defaultDb() {
    return {
        slotCost: SLOT_COST,
        demo: {
            ...emptyBucket(),
            guilds: DEMO_GUILDS
        },
        users: {}
    };
}

function normalizeBucket(raw, { demo } = { demo: false }) {
    const src = raw && typeof raw === 'object' ? raw : {};
    const slotCount = Math.max(1, Number(src.slotCount) || 1);
    const invites = src.invites && typeof src.invites === 'object' ? src.invites : {};
    const actions = Array.isArray(src.actions) ? src.actions.slice(0, MAX_ACTIONS) : [];
    const bucket = {
        slotCount,
        selectedGuildId: src.selectedGuildId || null,
        invites,
        actions
    };
    if (demo) {
        bucket.guilds = Array.isArray(src.guilds) && src.guilds.length
            ? src.guilds
            : DEMO_GUILDS;
        if (!bucket.selectedGuildId) bucket.selectedGuildId = bucket.guilds[0]?.id || null;
    }
    return bucket;
}

function normalizeDb(raw) {
    const db = raw && typeof raw === 'object' ? raw : {};
    return {
        slotCost: Number(db.slotCost) > 0 ? Number(db.slotCost) : SLOT_COST,
        demo: normalizeBucket(db.demo, { demo: true }),
        users: db.users && typeof db.users === 'object' ? db.users : {}
    };
}

async function readDb() {
    try {
        const raw = await fs.readFile(DATA_PATH, 'utf8');
        return normalizeDb(JSON.parse(raw));
    } catch {
        const fresh = defaultDb();
        await persistDb(fresh);
        return fresh;
    }
}

async function persistDb(db) {
    await fs.mkdir(path.dirname(DATA_PATH), { recursive: true });
    const tmp = `${DATA_PATH}.tmp`;
    await fs.writeFile(tmp, JSON.stringify(db, null, 2), 'utf8');
    await fs.rename(tmp, DATA_PATH);
}

function withLock(fn) {
    const run = writeChain.then(fn, fn);
    writeChain = run.then(() => undefined, () => undefined);
    return run;
}

function managedGuildIds(bucket) {
    const ids = [];
    for (const [guildId, bots] of Object.entries(bucket.invites || {})) {
        if (!bots || typeof bots !== 'object') continue;
        if (Object.values(bots).some((entry) => entry && entry.invited)) ids.push(guildId);
    }
    return ids;
}

function canTrackGuild(bucket, guildId) {
    const managed = managedGuildIds(bucket);
    if (managed.includes(String(guildId))) return true;
    return managed.length < (bucket.slotCount || 1);
}

function pushAction(bucket, type, message) {
    bucket.actions = [
        { at: Date.now(), type, message },
        ...(bucket.actions || [])
    ].slice(0, MAX_ACTIONS);
}

function publicUser(user) {
    if (!user) return null;
    return {
        id: String(user.id),
        username: user.username || 'Discord',
        avatar: user.avatar || '/assets/images/logo.jpg'
    };
}

async function mapPool(items, limit, mapper) {
    const out = new Array(items.length);
    let index = 0;
    async function worker() {
        while (index < items.length) {
            const current = index;
            index += 1;
            out[current] = await mapper(items[current], current);
        }
    }
    const workers = Array.from(
        { length: Math.min(Math.max(1, limit), Math.max(1, items.length)) },
        () => worker()
    );
    await Promise.all(workers);
    return out;
}

function guildIconUrl(guild) {
    if (!guild?.id || !guild?.icon) return '/assets/images/logo.jpg';
    return `https://cdn.discordapp.com/icons/${guild.id}/${guild.icon}.png`;
}

async function fetchRealGuilds(user) {
    const token = String(process.env.DISCORD_BOT_TOKEN || '').trim();
    const userId = String(user.id);
    if (!token) {
        return { guilds: [], source: 'none', hint: 'bot-token-missing' };
    }

    const cached = guildCache.get(userId);
    if (cached && Date.now() - cached.at < GUILD_CACHE_TTL_MS) {
        return cached;
    }

    try {
        const { data } = await axios.get(`${DISCORD_API}/users/@me/guilds`, {
            headers: { Authorization: `Bot ${token}` },
            timeout: 8000
        });
        const list = Array.isArray(data) ? data.slice(0, GUILD_FETCH_LIMIT) : [];
        const checked = await mapPool(list, MEMBER_CONCURRENCY, async (guild) => {
            try {
                await axios.get(`${DISCORD_API}/guilds/${guild.id}/members/${userId}`, {
                    headers: { Authorization: `Bot ${token}` },
                    timeout: 5000
                });
                return {
                    id: String(guild.id),
                    name: guild.name || 'Serveur',
                    icon: guildIconUrl(guild),
                    role: 'membre',
                    memberCount: guild.approximate_member_count || null
                };
            } catch {
                return null;
            }
        });
        const memberGuilds = checked.filter(Boolean);
        let payload;
        if (memberGuilds.length) {
            payload = { guilds: memberGuilds, source: 'bot', hint: 'member', at: Date.now() };
        } else if (list.length) {
            payload = {
                guilds: list.map((guild) => ({
                    id: String(guild.id),
                    name: guild.name || 'Serveur',
                    icon: guildIconUrl(guild),
                    role: 'bot',
                    memberCount: guild.approximate_member_count || null
                })),
                source: 'bot-unverified',
                hint: 'members-intent',
                at: Date.now()
            };
        } else {
            payload = { guilds: [], source: 'bot', hint: 'empty', at: Date.now() };
        }
        guildCache.set(userId, payload);
        return payload;
    } catch {
        const failed = { guilds: [], source: 'error', hint: 'discord-unreachable', at: Date.now() };
        guildCache.set(userId, failed);
        return failed;
    }
}

function guildHintText(mode, source, hint) {
    if (mode === 'demo') {
        return 'Serveurs fictifs persistés dans dashbot.json. Inviter ne parle pas à Discord.';
    }
    if (source === 'none' || hint === 'bot-token-missing') {
        return 'Pas de DISCORD_BOT_TOKEN : Inviter ouvre Discord, à vous de choisir le serveur.';
    }
    if (source === 'bot-unverified') {
        return 'Liste des serveurs où le bot support est présent (adhésion non vérifiée).';
    }
    if (hint === 'empty') {
        return 'Le bot support n’est sur aucun serveur commun. Inviter ouvre le sélecteur Discord.';
    }
    if (source === 'error') {
        return 'Discord injoignable pour lister les serveurs. Les invites restent disponibles.';
    }
    return 'Serveurs Discord où vous et le bot support êtes présents.';
}

function serializeState(mode, user, bucket, guildsPayload, slotCost) {
    const selectedGuildId = bucket.selectedGuildId
        || guildsPayload.guilds[0]?.id
        || null;
    return {
        ok: true,
        mode,
        oauthConfigured: isDiscordOAuthConfigured(),
        loginUrl: '/auth/discord',
        user: publicUser(user),
        bots: publicBots(selectedGuildId),
        guilds: guildsPayload.guilds,
        guildsSource: guildsPayload.source,
        guildsHint: guildHintText(mode, guildsPayload.source, guildsPayload.hint),
        selectedGuildId,
        invites: bucket.invites || {},
        slotCount: bucket.slotCount,
        slotCost,
        managedCount: managedGuildIds(bucket).length,
        actions: bucket.actions || []
    };
}

async function loadState(req) {
    const user = sessionUser(req);
    const db = await readDb();
    if (!user) {
        return serializeState('demo', null, db.demo, {
            guilds: db.demo.guilds || DEMO_GUILDS,
            source: 'demo',
            hint: 'demo'
        }, db.slotCost);
    }
    const bucket = normalizeBucket(db.users[String(user.id)]);
    const guildsPayload = await fetchRealGuilds(user);
    return serializeState('real', user, bucket, guildsPayload, db.slotCost);
}

function mountDashbot(app) {
    app.get('/api/dashbot', async (req, res) => {
        try {
            return res.json(await loadState(req));
        } catch (error) {
            return res.status(500).json({ ok: false, error: 'dashbot-read' });
        }
    });

    app.post('/api/dashbot/select', async (req, res) => {
        try {
            const guildId = String(req.body?.guildId || '').trim();
            if (!guildId) return res.status(400).json({ ok: false, error: 'guildId' });
            const user = sessionUser(req);
            const state = await withLock(async () => {
                const db = await readDb();
                if (!user) {
                    db.demo.selectedGuildId = guildId;
                    await persistDb(db);
                } else {
                    const key = String(user.id);
                    db.users[key] = normalizeBucket(db.users[key]);
                    db.users[key].selectedGuildId = guildId;
                    await persistDb(db);
                }
                return true;
            });
            if (!state) return res.status(500).json({ ok: false });
            return res.json(await loadState(req));
        } catch {
            return res.status(500).json({ ok: false, error: 'dashbot-select' });
        }
    });

    app.post('/api/dashbot/invite', async (req, res) => {
        try {
            const guildId = String(req.body?.guildId || '').trim();
            const botId = String(req.body?.botId || '').trim();
            const invited = req.body?.invited !== false;
            const bot = BOTS.find((item) => item.id === botId);
            if (!guildId || !bot) return res.status(400).json({ ok: false, error: 'params' });

            const user = sessionUser(req);
            const result = await withLock(async () => {
                const db = await readDb();
                const bucket = user
                    ? (db.users[String(user.id)] = normalizeBucket(db.users[String(user.id)]))
                    : db.demo;

                if (invited && !canTrackGuild(bucket, guildId)) {
                    return { blocked: true, db };
                }

                if (!bucket.invites[guildId]) bucket.invites[guildId] = {};
                if (invited) {
                    bucket.invites[guildId][botId] = { invited: true, at: Date.now() };
                    pushAction(bucket, 'invite', `${bot.name} → ${guildId}`);
                } else {
                    delete bucket.invites[guildId][botId];
                    if (!Object.keys(bucket.invites[guildId]).length) delete bucket.invites[guildId];
                    pushAction(bucket, 'uninvite', `${bot.name} retiré de ${guildId}`);
                }
                bucket.selectedGuildId = guildId;
                await persistDb(db);
                return { blocked: false };
            });

            if (result.blocked) {
                return res.status(409).json({
                    ok: false,
                    error: 'slot',
                    message: 'Achetez un slot pour suivre un serveur de plus.',
                    slotCost: SLOT_COST
                });
            }

            const state = await loadState(req);
            return res.json({
                ...state,
                inviteUrl: user && !isDemoId(guildId) ? inviteUrl(botId, guildId) : null
            });
        } catch {
            return res.status(500).json({ ok: false, error: 'dashbot-invite' });
        }
    });

    app.post('/api/dashbot/slot', async (req, res) => {
        try {
            const user = sessionUser(req);
            await withLock(async () => {
                const db = await readDb();
                const bucket = user
                    ? (db.users[String(user.id)] = normalizeBucket(db.users[String(user.id)]))
                    : db.demo;
                bucket.slotCount = (bucket.slotCount || 1) + 1;
                pushAction(bucket, 'slot', `Slot +1 (${bucket.slotCount} au total)`);
                await persistDb(db);
            });
            return res.json(await loadState(req));
        } catch {
            return res.status(500).json({ ok: false, error: 'dashbot-slot' });
        }
    });

    app.post('/api/dashbot/demo/reset', async (req, res) => {
        try {
            if (sessionUser(req)) {
                return res.status(403).json({ ok: false, error: 'real-mode' });
            }
            await withLock(async () => {
                const db = await readDb();
                db.demo = defaultDb().demo;
                await persistDb(db);
            });
            return res.json(await loadState(req));
        } catch {
            return res.status(500).json({ ok: false, error: 'dashbot-reset' });
        }
    });
}

module.exports = { mountDashbot };
