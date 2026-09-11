const express = require('express');
const axios = require('axios');
const fs = require('node:fs/promises');
const path = require('node:path');

const PUBLICBOT_DB_PATH = path.join(__dirname, '../data', 'publicbot.json');

async function readPublicBotDb() {
    try {
        const raw = await fs.readFile(PUBLICBOT_DB_PATH, 'utf8');
        return JSON.parse(raw);
    } catch {
        return { bots: {} };
    }
}

async function writePublicBotDb(db) {
    await fs.mkdir(path.dirname(PUBLICBOT_DB_PATH), { recursive: true });
    await fs.writeFile(PUBLICBOT_DB_PATH, JSON.stringify(db, null, 2), 'utf8');
}

// Normalisation des mots-clés (tags)
function normalizeTags(tagString) {
    if (!tagString) return [];
    const rawTags = String(tagString).split(',').map(t => t.trim()).filter(Boolean);
    const uniqueTagsMap = new Map();
    
    rawTags.forEach(tag => {
        let norm = tag.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
        if (norm.endsWith('s') && norm.length > 3) norm = norm.slice(0, -1);
        if (!uniqueTagsMap.has(norm)) {
            const display = tag.charAt(0).toUpperCase() + tag.slice(1).toLowerCase();
            uniqueTagsMap.set(norm, display);
        }
    });
    
    return Array.from(uniqueTagsMap.values()).slice(0, 15);
}

module.exports = function registerPublicbotRoutes(app, deps) {
    const { readUsersDb, writeUsersDb, isManualStaffRole, krones } = deps;
    const DISCORD_API_BASE = 'https://discord.com/api/v10';
    const COST_NEW_BOT = 60;
    const COST_FEATURED = 50;

    function isUserAdmin(user) {
        return user && !user.isGuest && (user.isTeamOwner || isManualStaffRole(user.role));
    }

    async function enrichBotsWithOwners(botsArray) {
        const usersDb = await readUsersDb();
        return botsArray.map(bot => {
            const owner = usersDb.users[bot.ownerId];
            return {
                ...bot,
                ownerName: owner ? (owner.username || 'Utilisateur') : 'Utilisateur inconnu',
                ownerAvatar: owner ? (owner.avatar || '/assets/images/logo.jpg') : '/assets/images/logo.jpg',
                likesCount: Array.isArray(bot.likes) ? bot.likes.length : 0,
                visits: bot.visits || 0,
                invites: bot.invites || 0
            };
        });
    }

    // 1. Liste de tous les bots validés
    app.get('/api/discord/publicbot/list', async (req, res) => {
        const db = await readPublicBotDb();
        const approvedBots = Object.values(db.bots).filter(b => b.status === 'approved');
        const enrichedBots = await enrichBotsWithOwners(approvedBots);
        res.json({ bots: enrichedBots });
    });

    // 2. Liste des bots de l'utilisateur
    app.get('/api/discord/publicbot/mybots', async (req, res) => {
        const user = req.session?.user;
        if (!user || user.isGuest) return res.status(401).json({ error: 'Non autorisé' });
        
        const db = await readPublicBotDb();
        const myBots = Object.values(db.bots).filter(b => b.ownerId === user.id);
        const enrichedBots = await enrichBotsWithOwners(myBots);
        res.json({ bots: enrichedBots });
    });

    // 3. Soumettre un nouveau bot
    app.post('/api/discord/publicbot/submit', async (req, res) => {
        const user = req.session?.user;
        if (!user || user.isGuest) return res.status(401).json({ error: 'Non autorisé' });

        const { botId, prefix, description, longDescription, customUrl, tags } = req.body;
        if (!botId || !description || !prefix) return res.status(400).json({ error: 'Champs obligatoires manquants' });

        const db = await readPublicBotDb();
        if (db.bots[botId]) return res.status(400).json({ error: 'Ce bot est déjà enregistré ou en attente.' });

        const cleanCustomUrl = String(customUrl || '').trim().toLowerCase().replace(/[^a-z0-9-]/g, '-');
        if (cleanCustomUrl && Object.values(db.bots).some(b => b.customUrl === cleanCustomUrl)) {
            return res.status(400).json({ error: 'Cette URL personnalisée est déjà utilisée.' });
        }

        const myBotsCount = Object.values(db.bots).filter(b => b.ownerId === user.id).length;
        const cost = myBotsCount === 0 ? 0 : COST_NEW_BOT;

        const usersDb = await readUsersDb();
        const userData = usersDb.users[user.id];
        if (!userData) return res.status(400).json({ error: 'Krones insuffisants.' });
        if (!krones && userData.krone < cost) return res.status(400).json({ error: 'Krones insuffisants.' });

        const botToken = process.env.DISCORD_BOT_TOKEN;
        let botName = "Bot " + botId.slice(-4);
        let botAvatar = "/assets/images/logo.jpg";
        
        try {
            if (botToken) {
                const discordRes = await axios.get(`${DISCORD_API_BASE}/users/${botId}`, { headers: { Authorization: `Bot ${botToken}` } });
                if (!discordRes.data.bot) return res.status(400).json({ error: "L'ID fourni n'appartient pas à un bot." });
                botName = discordRes.data.username;
                botAvatar = discordRes.data.avatar ? `https://cdn.discordapp.com/avatars/${botId}/${discordRes.data.avatar}.png` : botAvatar;
            }
        } catch (e) {
            return res.status(404).json({ error: 'Bot introuvable sur Discord. Vérifiez l\'ID.' });
        }

        if (cost > 0 && krones) {
            const spent = await krones.debitAccount(user.id, cost, 'publicbot:create');
            if (!spent.ok) return res.status(400).json({ error: spent.error || 'Krones insuffisants.' });
            userData.krone = spent.wallet.balance;
        } else {
            userData.krone -= cost;
        }
        await writeUsersDb(usersDb);
        req.session.user.krone = userData.krone;

        db.bots[botId] = {
            id: botId,
            ownerId: user.id,
            status: 'pending',
            name: botName,
            avatar: botAvatar,
            banner: '', // Vide par défaut
            prefix: prefix,
            description,
            longDescription: longDescription || '',
            customUrl: cleanCustomUrl || botId,
            tags: normalizeTags(tags),
            servers: 0,
            featured: false,
            addedAt: Date.now(),
            lastBump: 0,
            views: 0,
            invites: 0,
            likes: [],
            feedback: null
        };

        await writePublicBotDb(db);
        res.json({ success: true, message: 'Bot soumis avec succès. En attente de validation.', krone: userData.krone });
    });

    // 4. Mettre à jour un bot existant (et le renvoyer en validation si besoin)
    app.post('/api/discord/publicbot/update', async (req, res) => {
        const user = req.session?.user;
        if (!user || user.isGuest) return res.status(401).json({ error: 'Non autorisé' });

        const { botId, prefix, description, longDescription, customUrl, tags, banner, resubmit } = req.body;
        const db = await readPublicBotDb();
        const bot = db.bots[botId];

        if (!bot || (bot.ownerId !== user.id && !isUserAdmin(user))) return res.status(403).json({ error: 'Bot invalide ou non autorisé.' });

        const cleanCustomUrl = String(customUrl || '').trim().toLowerCase().replace(/[^a-z0-9-]/g, '-');
        if (cleanCustomUrl && cleanCustomUrl !== bot.customUrl && Object.values(db.bots).some(b => b.customUrl === cleanCustomUrl)) {
            return res.status(400).json({ error: 'Cette URL personnalisée est déjà utilisée.' });
        }

        bot.prefix = prefix || bot.prefix;
        bot.description = description || bot.description;
        bot.longDescription = longDescription || bot.longDescription;
        bot.customUrl = cleanCustomUrl || bot.customUrl;
        bot.tags = normalizeTags(tags);
        if (banner !== undefined) bot.banner = banner;

        // Si le bot était refusé et que l'utilisateur le renvoie
        if (resubmit && bot.status === 'needs_edit') {
            bot.status = 'pending';
            bot.feedback = null;
        }

        await writePublicBotDb(db);
        res.json({ success: true, message: 'Profil du bot mis à jour avec succès !' });
    });

    // 5. Supprimer un bot
    app.post('/api/discord/publicbot/delete', async (req, res) => {
        const user = req.session?.user;
        if (!user || user.isGuest) return res.status(401).json({ error: 'Non autorisé' });

        const { botId } = req.body;
        const db = await readPublicBotDb();
        const bot = db.bots[botId];

        if (!bot) return res.status(404).json({ error: 'Bot introuvable' });
        
        if (bot.ownerId !== user.id && !isUserAdmin(user)) {
            return res.status(403).json({ error: 'Vous ne pouvez pas supprimer ce bot.' });
        }

        delete db.bots[botId];
        await writePublicBotDb(db);
        res.json({ success: true, message: 'Bot supprimé avec succès.' });
    });

    // 6. Actions Utilisateurs : Voir, Inviter, Liker
    app.post('/api/discord/publicbot/view', async (req, res) => {
        const { botId } = req.body;
        const db = await readPublicBotDb();
        if (db.bots[botId]) {
            db.bots[botId].visits = (db.bots[botId].visits || 0) + 1;
            await writePublicBotDb(db);
        }
        res.json({ success: true });
    });

    app.post('/api/discord/publicbot/invite', async (req, res) => {
        const { botId } = req.body;
        const db = await readPublicBotDb();
        if (db.bots[botId]) {
            db.bots[botId].invites = (db.bots[botId].invites || 0) + 1;
            await writePublicBotDb(db);
        }
        res.json({ success: true });
    });

    app.post('/api/discord/publicbot/like', async (req, res) => {
        const user = req.session?.user;
        if (!user || user.isGuest) return res.status(401).json({ error: 'Non autorisé' });

        const { botId } = req.body;
        const db = await readPublicBotDb();
        const bot = db.bots[botId];

        if (!bot) return res.status(404).json({ error: 'Bot introuvable' });

        if (!bot.likes) bot.likes = [];
        const likeIndex = bot.likes.indexOf(user.id);
        
        let isLiked = false;
        if (likeIndex === -1) {
            bot.likes.push(user.id);
            isLiked = true;
        } else {
            bot.likes.splice(likeIndex, 1);
        }

        await writePublicBotDb(db);
        res.json({ success: true, isLiked, likesCount: bot.likes.length });
    });

    // 7. Mettre en avant
    app.post('/api/discord/publicbot/feature', async (req, res) => {
        const user = req.session?.user;
        if (!user || user.isGuest) return res.status(401).json({ error: 'Non autorisé' });

        const { botId } = req.body;
        const db = await readPublicBotDb();
        const bot = db.bots[botId];

        if (!bot || bot.ownerId !== user.id) return res.status(403).json({ error: 'Bot invalide.' });
        if (bot.featured) return res.status(400).json({ error: 'Le bot est déjà mis en avant.' });

        const usersDb = await readUsersDb();
        const userData = usersDb.users[user.id];
        if (!userData) return res.status(400).json({ error: 'Krones insuffisants.' });
        if (krones) {
            const spent = await krones.debitAccount(user.id, COST_FEATURED, 'publicbot:feature');
            if (!spent.ok) return res.status(400).json({ error: spent.error || 'Krones insuffisants.' });
            userData.krone = spent.wallet.balance;
        } else {
            if (userData.krone < COST_FEATURED) return res.status(400).json({ error: 'Krones insuffisants.' });
            userData.krone -= COST_FEATURED;
        }
        await writeUsersDb(usersDb);
        req.session.user.krone = userData.krone;

        bot.featured = true;
        await writePublicBotDb(db);

        res.json({ success: true, message: 'Bot mis en avant avec succès !', krone: userData.krone });
    });

    // 8. Bumper
    app.post('/api/discord/publicbot/trigger-bump', async (req, res) => {
        const user = req.session?.user;
        if (!user || user.isGuest) return res.status(401).json({ error: 'Non autorisé' });

        const { botId } = req.body;
        const db = await readPublicBotDb();
        const bot = db.bots[botId];

        if (!bot || bot.status !== 'approved') return res.status(404).json({ error: 'Bot introuvable ou non approuvé.' });

        const now = Date.now();
        const COOLDOWN = 2 * 60 * 60 * 1000;

        if (bot.lastBump && (now - bot.lastBump < COOLDOWN)) {
            const remaining = Math.ceil((COOLDOWN - (now - bot.lastBump)) / 60000);
            return res.status(429).json({ error: `Veuillez patienter ${remaining} minute(s) avant de bumper.` });
        }

        bot.lastBump = now;
        await writePublicBotDb(db);
        res.json({ success: true, message: 'Le bot a été bumpé ! Sa visibilité a augmenté.' });
    });

    // 9. Admin
    app.get('/api/discord/publicbot/admin/pending', async (req, res) => {
        const user = req.session?.user;
        if (!isUserAdmin(user)) return res.status(403).json({ error: 'Accès refusé' });

        const db = await readPublicBotDb();
        const pendingBots = Object.values(db.bots).filter(b => b.status === 'pending');
        const enrichedBots = await enrichBotsWithOwners(pendingBots);
        res.json({ pendingBots: enrichedBots });
    });

    app.post('/api/discord/publicbot/admin/action', async (req, res) => {
        const user = req.session?.user;
        if (!isUserAdmin(user)) return res.status(403).json({ error: 'Accès refusé' });

        const { botId, action, feedback } = req.body;
        const db = await readPublicBotDb();

        if (!db.bots[botId]) return res.status(404).json({ error: 'Bot introuvable' });

        if (action === 'approve') {
            db.bots[botId].status = 'approved';
            db.bots[botId].feedback = null;
            db.bots[botId].lastBump = Date.now();
        } else if (action === 'reject') {
            db.bots[botId].status = 'needs_edit';
            db.bots[botId].feedback = feedback || 'Votre bot ne respecte pas les critères de validation.';
        }

        await writePublicBotDb(db);
        res.json({ success: true, message: `Le bot a été ${action === 'approve' ? 'validé' : 'renvoyé à la correction'}.` });
    });
};