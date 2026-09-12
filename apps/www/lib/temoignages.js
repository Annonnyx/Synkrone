'use strict';

const fs = require('node:fs/promises');
const path = require('node:path');

const FILE = path.join(
    __dirname,
    '..',
    '..',
    '..',
    'Synkrone',
    'test',
    'synkrone_authdiscord',
    'data',
    'temoignages.json'
);

async function readStore() {
    try {
        const parsed = JSON.parse(await fs.readFile(FILE, 'utf8'));
        return { items: Array.isArray(parsed.items) ? parsed.items : [] };
    } catch {
        return { items: [] };
    }
}

async function writeStore(store) {
    await fs.mkdir(path.dirname(FILE), { recursive: true });
    await fs.writeFile(FILE, JSON.stringify(store, null, 2), 'utf8');
}

function publicItem(item, admin) {
    const row = {
        id: item.id,
        quote: String(item.quote || ''),
        displayName: String(item.displayName || ''),
        published: Boolean(item.published),
        createdAt: Number(item.createdAt) || 0
    };
    if (admin) row.authorId = String(item.authorId || '');
    return row;
}

function mountTemoignages(app, deps) {
    const resolveAdmin = deps.resolveAdminAccessForSessionUser;

    app.get('/api/temoignages', async (req, res) => {
        const store = await readStore();
        const admin = req.query.admin === '1' && req.session?.user
            ? await resolveAdmin(req.session.user)
            : false;
        const items = store.items
            .filter((item) => admin || item.published)
            .map((item) => publicItem(item, admin))
            .sort((a, b) => (b.createdAt || 0) - (a.createdAt || 0));
        res.json({ ok: true, items });
    });

    app.patch('/api/temoignages/:id', async (req, res) => {
        const user = req.session?.user;
        if (!user || user.isGuest) return res.status(401).json({ ok: false, error: 'Non autorisé' });
        const allowed = await resolveAdmin(user);
        if (!allowed) return res.status(403).json({ ok: false, error: 'Accès refusé' });
        const id = Number(req.params.id);
        const store = await readStore();
        const item = store.items.find((entry) => Number(entry.id) === id);
        if (!item) return res.status(404).json({ ok: false, error: 'Introuvable' });
        if (req.body.published !== undefined) item.published = Boolean(req.body.published);
        await writeStore(store);
        res.json({ ok: true, item: publicItem(item, true) });
    });
}

async function addOptInQuote({ authorId, displayName, quote }) {
    const text = String(quote || '').trim().slice(0, 400);
    const name = String(displayName || '').trim().slice(0, 80);
    if (!text || !name) return null;
    const store = await readStore();
    const item = {
        id: Date.now(),
        quote: text,
        displayName: name,
        published: false,
        createdAt: Date.now(),
        authorId: String(authorId || '')
    };
    store.items.push(item);
    await writeStore(store);
    return item;
}

module.exports = { mountTemoignages, addOptInQuote };
