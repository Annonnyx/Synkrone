const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const DATA_DIR = path.join(__dirname, '..', 'data');
const CATALOG_PATH = path.join(DATA_DIR, 'command-catalog.json');
const BUILDS_PATH = path.join(DATA_DIR, 'command-builds.json');

const INVOCATIONS = new Set(['slash', 'prefix', 'both']);
const PREFIX_RE = /^[^\s]{1,8}$/;

function readJson(filePath, fallback) {
    try {
        return JSON.parse(fs.readFileSync(filePath, 'utf8'));
    } catch {
        return fallback;
    }
}

function writeJson(filePath, data) {
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    const tmp = `${filePath}.${process.pid}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify(data, null, 2) + '\n', 'utf8');
    fs.renameSync(tmp, filePath);
}

function loadCatalog() {
    const catalog = readJson(CATALOG_PATH, { categories: [], count: 0, cost: { base: 2, perCommand: 1 } });
    const categories = Array.isArray(catalog.categories) ? catalog.categories : [];
    const count = categories.reduce((n, cat) => n + (Array.isArray(cat.commands) ? cat.commands.length : 0), 0);
    return { ...catalog, categories, count };
}

function catalogIds(catalog) {
    const ids = new Set();
    for (const cat of catalog.categories) {
        for (const cmd of cat.commands || []) {
            if (cmd && cmd.id) ids.add(String(cmd.id));
        }
    }
    return ids;
}

function loadBuilds() {
    const data = readJson(BUILDS_PATH, { builds: [] });
    const builds = Array.isArray(data) ? data : (Array.isArray(data.builds) ? data.builds : []);
    return { builds };
}

function saveBuilds(store) {
    writeJson(BUILDS_PATH, { builds: store.builds });
}

function ownerId(req) {
    const user = req.session && req.session.user;
    if (user && (user.id || user.discordId)) return String(user.id || user.discordId);
    return 'local';
}

function computeCost(commandIds, catalog) {
    const cost = catalog.cost || {};
    const base = Number.isFinite(Number(cost.base)) ? Number(cost.base) : 2;
    const per = Number.isFinite(Number(cost.perCommand)) ? Number(cost.perCommand) : 1;
    const n = Array.isArray(commandIds) ? commandIds.length : 0;
    return Math.max(0, Math.trunc(base + per * n));
}

function sanitizeBuild(body, catalog, existing) {
    const known = catalogIds(catalog);
    const name = String(body && body.name != null ? body.name : (existing && existing.name) || 'Pack commandes').trim().slice(0, 64) || 'Pack commandes';
    const invocation = String(body && body.invocation != null ? body.invocation : (existing && existing.invocation) || 'both').toLowerCase();
    if (!INVOCATIONS.has(invocation)) {
        return { error: 'Invocation invalide (slash, prefix ou both).' };
    }
    const defaultPrefix = catalog.defaultPrefix || '*';
    const prefix = String(body && body.prefix != null ? body.prefix : (existing && existing.prefix) || defaultPrefix).trim();
    if ((invocation === 'prefix' || invocation === 'both') && !PREFIX_RE.test(prefix)) {
        return { error: 'Préfixe invalide (1 à 8 caractères, sans espace).' };
    }
    const raw = Array.isArray(body && body.commands) ? body.commands : (existing && existing.commands) || [];
    const commands = [...new Set(raw.map((id) => String(id || '').trim()).filter((id) => known.has(id)))];
    return {
        name,
        invocation,
        prefix: prefix || defaultPrefix,
        commands,
        cost: computeCost(commands, catalog)
    };
}

function publicBuild(build) {
    return {
        id: build.id,
        name: build.name,
        invocation: build.invocation,
        prefix: build.prefix,
        commands: build.commands,
        cost: build.cost,
        charged: Number(build.charged || 0),
        createdAt: build.createdAt,
        updatedAt: build.updatedAt
    };
}

function mountCommands(app) {
    app.get('/api/commands/catalog', (req, res) => {
        const catalog = loadCatalog();
        return res.json(catalog);
    });

    app.get('/api/commands/builds', (req, res) => {
        const uid = ownerId(req);
        const { builds } = loadBuilds();
        return res.json({ builds: builds.filter((b) => b.userId === uid).map(publicBuild) });
    });

    app.get('/api/commands/builds/:id', (req, res) => {
        const uid = ownerId(req);
        const { builds } = loadBuilds();
        const build = builds.find((b) => b.id === req.params.id && b.userId === uid);
        if (!build) return res.status(404).json({ error: 'Build introuvable.' });
        return res.json({ build: publicBuild(build) });
    });

    app.post('/api/commands/builds', (req, res) => {
        const catalog = loadCatalog();
        const parsed = sanitizeBuild(req.body || {}, catalog, null);
        if (parsed.error) return res.status(400).json({ error: parsed.error });
        const now = Date.now();
        const build = {
            id: crypto.randomBytes(8).toString('hex'),
            userId: ownerId(req),
            name: parsed.name,
            invocation: parsed.invocation,
            prefix: parsed.prefix,
            commands: parsed.commands,
            cost: parsed.cost,
            charged: 0,
            createdAt: now,
            updatedAt: now
        };
        const store = loadBuilds();
        store.builds.push(build);
        saveBuilds(store);
        return res.status(201).json({ build: publicBuild(build), isNew: true });
    });

    app.put('/api/commands/builds/:id', (req, res) => {
        const uid = ownerId(req);
        const store = loadBuilds();
        const idx = store.builds.findIndex((b) => b.id === req.params.id && b.userId === uid);
        if (idx < 0) return res.status(404).json({ error: 'Build introuvable.' });
        const catalog = loadCatalog();
        const parsed = sanitizeBuild(req.body || {}, catalog, store.builds[idx]);
        if (parsed.error) return res.status(400).json({ error: parsed.error });
        const prev = store.builds[idx];
        store.builds[idx] = {
            ...prev,
            name: parsed.name,
            invocation: parsed.invocation,
            prefix: parsed.prefix,
            commands: parsed.commands,
            cost: parsed.cost,
            updatedAt: Date.now()
        };
        saveBuilds(store);
        return res.json({ build: publicBuild(store.builds[idx]), isNew: false });
    });

    app.post('/api/commands/builds/:id/charged', (req, res) => {
        const uid = ownerId(req);
        const store = loadBuilds();
        const idx = store.builds.findIndex((b) => b.id === req.params.id && b.userId === uid);
        if (idx < 0) return res.status(404).json({ error: 'Build introuvable.' });
        const amount = Math.max(0, Math.trunc(Number(req.body && req.body.amount)));
        store.builds[idx].charged = amount;
        store.builds[idx].updatedAt = Date.now();
        saveBuilds(store);
        return res.json({ build: publicBuild(store.builds[idx]) });
    });

    app.delete('/api/commands/builds/:id', (req, res) => {
        const uid = ownerId(req);
        const store = loadBuilds();
        const next = store.builds.filter((b) => !(b.id === req.params.id && b.userId === uid));
        if (next.length === store.builds.length) return res.status(404).json({ error: 'Build introuvable.' });
        store.builds = next;
        saveBuilds(store);
        return res.json({ ok: true });
    });
}

module.exports = { mountCommands };
