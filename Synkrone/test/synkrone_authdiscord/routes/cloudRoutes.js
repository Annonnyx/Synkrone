const path = require('node:path');
const fs = require('node:fs/promises');

// File d'attente pour bloquer les écritures simultanées
let cloudMutex = Promise.resolve();

// Le bon chemin : on remonte d'un seul cran depuis "routes/" vers "data/cloud"
const CLOUD_DIR = path.join(__dirname, '../data/cloud');

function canAccessCloud(user, isManualStaffRole) {
    return Boolean(user && !user.isGuest && (user.isTeamOwner || isManualStaffRole(user.role)));
}

function toArrayOrDefault(value, fallback) {
    return Array.isArray(value) ? value : fallback;
}

function normalizeCloudPayload(payload, currentDb) {
    const safePayload = payload && typeof payload === 'object' ? payload : {};
    return {
        ...currentDb,
        items: toArrayOrDefault(safePayload.items, currentDb.items),
        history: toArrayOrDefault(safePayload.history, currentDb.history)
    };
}

function isObject(value) {
    return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

// Fonction pour écrire physiquement les fichiers sur le disque
async function syncPhysicalCloud(items) {
    function getFullPath(item) {
        const parts = [item.name.replace(/[<>:"/\\|?*]+/g, '_')];
        let current = item;
        while (current.parentId && current.parentId !== 'root') {
            const parent = items.find(i => i.id === current.parentId);
            if (!parent) break;
            parts.unshift(parent.name.replace(/[<>:"/\\|?*]+/g, '_'));
            current = parent;
        }
        return path.join(CLOUD_DIR, ...parts);
    }

    try {
        await fs.mkdir(CLOUD_DIR, { recursive: true });

        // 1. Création des dossiers
        const folders = items.filter(i => i.type === 'folder' && !i.deleted);
        for (const folder of folders) {
            await fs.mkdir(getFullPath(folder), { recursive: true }).catch(() => {});
        }

        // 2. Création des fichiers
        const files = items.filter(i => i.type !== 'folder' && !i.deleted);
        for (const file of files) {
            const filePath = getFullPath(file);
            await fs.mkdir(path.dirname(filePath), { recursive: true }).catch(() => {});
            
            if (file.content) {
                // Gestion des fichiers importés (base64)
                if (file.content.startsWith('data:')) {
                    const base64Data = file.content.split(',')[1];
                    if (base64Data) {
                        await fs.writeFile(filePath, Buffer.from(base64Data, 'base64')).catch(() => {});
                    }
                } else {
                    // Fichiers texte classiques
                    await fs.writeFile(filePath, file.content, 'utf8').catch(() => {});
                }
            } else {
                // Fichier vide
                await fs.writeFile(filePath, '', 'utf8').catch(() => {});
            }
        }
    } catch (err) {
        console.error("[Cloud] Erreur lors de la synchronisation physique :", err);
    }
}

module.exports = function registerCloudRoutes(app, deps) {
    const { readCloudDb, writeCloudDb, isManualStaffRole } = deps;

    app.get('/api/cloud', async (req, res) => {
        const user = req.session?.user;
        if (!canAccessCloud(user, isManualStaffRole)) return res.status(403).json({ error: 'Accès refusé' });
        
        const db = await readCloudDb();
        return res.json(db);
    });

    app.post('/api/cloud', async (req, res) => {
        const user = req.session?.user;
        if (!canAccessCloud(user, isManualStaffRole)) return res.status(403).json({ error: 'Accès refusé' });

        // On place la sauvegarde dans la file d'attente (Mutex)
        await (cloudMutex = cloudMutex.then(async () => {
            const currentDb = await readCloudDb();
            const nextDb = normalizeCloudPayload(req.body, currentDb);
            
            await writeCloudDb(nextDb);
            
            // Lancement de la synchronisation physique sans bloquer la réponse HTTP
            syncPhysicalCloud(nextDb.items);
        }).catch(err => console.error('[Cloud] Erreur de sauvegarde globale:', err)));

        return res.json({ ok: true });
    });

    app.post('/api/cloud/import-item', async (req, res) => {
        const user = req.session?.user;
        if (!canAccessCloud(user, isManualStaffRole)) return res.status(403).json({ error: 'Accès refusé' });

        const payload = isObject(req.body) ? req.body : {};
        const item = isObject(payload.item) ? payload.item : null;
        const historyEntry = isObject(payload.historyEntry) ? payload.historyEntry : null;

        if (!item || !String(item.id || '').trim()) {
            return res.status(400).json({ error: 'Item invalide.' });
        }
        if (!historyEntry || !String(historyEntry.id || '').trim()) {
            return res.status(400).json({ error: 'Entrée historique invalide.' });
        }

        // On place l'import dans la file d'attente
        await (cloudMutex = cloudMutex.then(async () => {
            const db = await readCloudDb();
            db.items = Array.isArray(db.items) ? db.items : [];
            db.history = Array.isArray(db.history) ? db.history : [];

            const existingIndex = db.items.findIndex((existingItem) => String(existingItem?.id || '') === String(item.id));
            if (existingIndex >= 0) db.items[existingIndex] = item;
            else db.items.push(item);

            const historyExists = db.history.some((entry) => String(entry?.id || '') === String(historyEntry.id));
            if (!historyExists) db.history.unshift(historyEntry);

            await writeCloudDb(db);
            
            syncPhysicalCloud(db.items);
        }).catch(err => console.error('[Cloud] Erreur d\'importation d\'item:', err)));

        return res.json({ ok: true });
    });
};