const fs = require('node:fs/promises');
const path = require('node:path');

const FILE = path.join(__dirname, '../data', 'announcements.json');
const DEFAULT_TYPES = ['maj', 'nerf', 'event', 'boutique'];
const SCOPES = new Set(['synkrone', 'bots', 'bump', 'me', 'dashbot', 'serveur', 'modpack']);

async function readStore() {
    try {
        const parsed = JSON.parse(await fs.readFile(FILE, 'utf8'));
        const types = Array.isArray(parsed.types) && parsed.types.length ? parsed.types : DEFAULT_TYPES;
        const items = Array.isArray(parsed.items) ? parsed.items : [];
        return { types, items };
    } catch {
        return { types: DEFAULT_TYPES, items: [] };
    }
}

async function writeStore(store) {
    await fs.mkdir(path.dirname(FILE), { recursive: true });
    await fs.writeFile(FILE, JSON.stringify(store, null, 2), 'utf8');
}

function publicItem(item) {
    const types = Array.isArray(item.types) && item.types.length ? item.types : [item.type].filter(Boolean);
    return {
        id: item.id,
        scope: item.scope || item.menu || 'synkrone',
        types,
        type: types[0] || 'maj',
        title: String(item.title || ''),
        summary: String(item.summary || ''),
        content: String(item.content || ''),
        date: String(item.date || ''),
        createdAt: Number(item.createdAt) || 0,
        published: item.published !== false
    };
}

module.exports = function registerAnnouncementRoutes(app, deps) {
    const resolveAdmin = deps.resolveAdminAccessForSessionUser;

    async function requireAdmin(req, res) {
        const user = req.session?.user;
        if (!user || user.isGuest) {
            res.status(401).json({ ok: false, error: 'Non autorisé' });
            return null;
        }
        const allowed = await resolveAdmin(user);
        if (!allowed) {
            res.status(403).json({ ok: false, error: 'Accès refusé' });
            return null;
        }
        return user;
    }

    app.get('/api/announcements', async (req, res) => {
        const store = await readStore();
        const admin = req.query.admin === '1' && req.session?.user
            ? await resolveAdmin(req.session.user)
            : false;
        const items = store.items
            .filter((item) => admin || item.published !== false)
            .map(publicItem)
            .sort((a, b) => (b.createdAt || 0) - (a.createdAt || 0));
        res.json({ ok: true, types: store.types, items });
    });

    app.post('/api/announcements', async (req, res) => {
        const user = await requireAdmin(req, res);
        if (!user) return;
        const title = String(req.body?.title || '').trim();
        const summary = String(req.body?.summary || '').trim();
        const content = String(req.body?.content || '').trim();
        const scope = SCOPES.has(req.body?.scope) ? req.body.scope : 'synkrone';
        const types = (Array.isArray(req.body?.types) ? req.body.types : [])
            .map((type) => String(type || '').trim().toLowerCase())
            .filter(Boolean);
        if (!title || !summary || !content || !types.length) {
            return res.status(400).json({ ok: false, error: 'Titre, types, résumé et contenu requis.' });
        }
        const now = new Date();
        const item = {
            id: Date.now(),
            scope,
            menu: scope,
            types,
            type: types[0],
            title,
            summary,
            content,
            date: now.toLocaleDateString('fr-FR', { day: '2-digit', month: 'short', year: 'numeric' }),
            createdAt: now.getTime(),
            published: req.body?.published !== false,
            authorId: String(user.id || '')
        };
        const store = await readStore();
        store.items.push(item);
        await writeStore(store);
        res.json({ ok: true, item: publicItem(item) });
    });

    app.patch('/api/announcements/:id', async (req, res) => {
        const user = await requireAdmin(req, res);
        if (!user) return;
        const id = Number(req.params.id);
        const store = await readStore();
        const item = store.items.find((entry) => Number(entry.id) === id);
        if (!item) return res.status(404).json({ ok: false, error: 'Introuvable' });
        if (req.body.title !== undefined) item.title = String(req.body.title).trim();
        if (req.body.summary !== undefined) item.summary = String(req.body.summary).trim();
        if (req.body.content !== undefined) item.content = String(req.body.content).trim();
        if (req.body.scope && SCOPES.has(req.body.scope)) {
            item.scope = req.body.scope;
            item.menu = req.body.scope;
        }
        if (Array.isArray(req.body.types) && req.body.types.length) {
            item.types = req.body.types.map((type) => String(type).trim().toLowerCase()).filter(Boolean);
            item.type = item.types[0];
        }
        if (req.body.published !== undefined) item.published = Boolean(req.body.published);
        await writeStore(store);
        res.json({ ok: true, item: publicItem(item) });
    });

    app.delete('/api/announcements/:id', async (req, res) => {
        const user = await requireAdmin(req, res);
        if (!user) return;
        const id = Number(req.params.id);
        const store = await readStore();
        store.items = store.items.filter((entry) => Number(entry.id) !== id);
        await writeStore(store);
        res.json({ ok: true });
    });

    app.put('/api/announcement-types', async (req, res) => {
        const user = await requireAdmin(req, res);
        if (!user) return;
        const types = (Array.isArray(req.body?.types) ? req.body.types : [])
            .map((type) => String(type || '').trim().toLowerCase())
            .filter(Boolean);
        if (!types.length) return res.status(400).json({ ok: false, error: 'Au moins un type.' });
        const store = await readStore();
        store.types = types;
        await writeStore(store);
        res.json({ ok: true, types });
    });
};
