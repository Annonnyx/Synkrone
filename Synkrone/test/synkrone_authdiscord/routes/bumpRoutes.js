const express = require('express');
const axios = require('axios');
const fs = require('node:fs/promises');
const path = require('node:path');

const BUMP_DB_PATH = path.join(__dirname, '../data', 'bump.json');

async function readBumpDb() {
    try {
        const raw = await fs.readFile(BUMP_DB_PATH, 'utf8');
        return JSON.parse(raw);
    } catch {
        return { servers: {} };
    }
}

async function writeBumpDb(db) {
    await fs.mkdir(path.dirname(BUMP_DB_PATH), { recursive: true });
    await fs.writeFile(BUMP_DB_PATH, JSON.stringify(db, null, 2), 'utf8');
}

module.exports = function registerBumpRoutes(app, deps) {
    const DISCORD_API_BASE = 'https://discord.com/api/v10';

    app.get('/api/discord/bump/public', async (req, res) => {
        const db = await readBumpDb();
        const botToken = process.env.DISCORD_BOT_TOKEN;
        const entries = Object.entries(db.servers || {}).filter(([, data]) => data && data.visibilityLevel !== 'hidden');
        const servers = [];
        for (const [id, data] of entries) {
            let name = `Serveur ${id.slice(-4)}`;
            let icon = '/assets/images/logo.jpg';
            if (botToken) {
                try {
                    const guildRes = await axios.get(`${DISCORD_API_BASE}/guilds/${id}?with_counts=true`, {
                        headers: { Authorization: `Bot ${botToken}` }
                    });
                    const guild = guildRes.data;
                    name = guild.name || name;
                    if (guild.icon) icon = `https://cdn.discordapp.com/icons/${id}/${guild.icon}.png`;
                    servers.push({
                        id,
                        name,
                        icon,
                        featuredUntil: data.featuredUntil || null,
                        visibilityLevel: data.visibilityLevel || 'public',
                        members: guild.approximate_member_count || 0
                    });
                    continue;
                } catch {
                    /* keep fallback */
                }
            }
            servers.push({
                id,
                name,
                icon,
                featuredUntil: data.featuredUntil || null,
                visibilityLevel: data.visibilityLevel || 'public',
                members: 0
            });
        }
        servers.sort((a, b) => Number(b.featuredUntil || 0) - Number(a.featuredUntil || 0));
        res.json({ ok: true, servers });
    });

    // 1. Récupération des serveurs de l'utilisateur
    app.get('/api/discord/bump/servers', async (req, res) => {
        const user = req.session?.user;
        if (!user || user.isGuest) return res.status(401).json({ error: 'Non autorisé' });
        
        try {
            const botToken = process.env.DISCORD_BOT_TOKEN;
            if (!botToken) return res.status(500).json({ error: 'Bot token missing' });
            
            const botGuildsReq = await axios.get(`${DISCORD_API_BASE}/users/@me/guilds`, {
                headers: { Authorization: `Bot ${botToken}` }
            });
            const botGuilds = botGuildsReq.data;
            
            const userServers = [];
            for (const guild of botGuilds) {
                try {
                    const memberReq = await axios.get(`${DISCORD_API_BASE}/guilds/${guild.id}/members/${user.id}`, {
                        headers: { Authorization: `Bot ${botToken}` }
                    });
                    const member = memberReq.data;
                    
                    const guildDataReq = await axios.get(`${DISCORD_API_BASE}/guilds/${guild.id}`, {
                        headers: { Authorization: `Bot ${botToken}` }
                    });
                    const guildData = guildDataReq.data;
                    
                    let isOwner = guildData.owner_id === user.id;
                    let isAdmin = false;
                    
                    if (!isOwner) {
                        for (const roleId of member.roles) {
                            const role = guildData.roles.find(r => r.id === roleId);
                            if (role && ((BigInt(role.permissions) & 8n) === 8n || (BigInt(role.permissions) & 32n) === 32n)) {
                                isAdmin = true;
                                break;
                            }
                        }
                    }
                    
                    if (isOwner || isAdmin) {
                        userServers.push({
                            id: guild.id,
                            name: guild.name,
                            icon: guild.icon,
                            role: isOwner ? 'owner' : 'admin'
                        });
                    }
                } catch (e) {
                    continue;
                }
            }
            res.json({ servers: userServers });
        } catch (error) {
            res.status(500).json({ error: 'Internal server error' });
        }
    });

    // 2. Base de données : Modules & Options du serveur
    app.get('/api/discord/bump/server/:id/modules', async (req, res) => {
        const serverId = req.params.id;
        const db = await readBumpDb();
        const serverData = db.servers[serverId] || { purchasedModules: [], disabledModules: [], featuredUntil: null };
        res.json(serverData);
    });

    // 3. Achat d'une option
    app.post('/api/discord/bump/server/:id/buy', async (req, res) => {
        const user = req.session?.user;
        if (!user || user.isGuest) return res.status(401).json({ error: 'Non autorisé' });
        
        const serverId = req.params.id;
        const { itemId, cost } = req.body;
        
        const db = await readBumpDb();
        if (!db.servers[serverId]) {
            db.servers[serverId] = { purchasedModules: [], disabledModules: [], featuredUntil: null };
        }

        if (itemId === 'featured') {
            // Mise en avant de 2 heures
            db.servers[serverId].featuredUntil = Date.now() + (2 * 60 * 60 * 1000); 
        } else {
            if (!db.servers[serverId].purchasedModules.includes(itemId)) {
                db.servers[serverId].purchasedModules.push(itemId);
            }
        }

        await writeBumpDb(db);
        res.json({ success: true, serverData: db.servers[serverId] });
    });

    // 4. Activer/Désactiver une option déjà achetée
    app.post('/api/discord/bump/server/:id/toggle', async (req, res) => {
        const serverId = req.params.id;
        const { itemId, action } = req.body;
        
        const db = await readBumpDb();
        if (!db.servers[serverId]) return res.json({ success: false });

        if (!db.servers[serverId].disabledModules) db.servers[serverId].disabledModules = [];

        if (action === 'disable') {
            if (!db.servers[serverId].disabledModules.includes(itemId)) {
                db.servers[serverId].disabledModules.push(itemId);
            }
        } else if (action === 'enable') {
            db.servers[serverId].disabledModules = db.servers[serverId].disabledModules.filter(id => id !== itemId);
        }

        await writeBumpDb(db);
        res.json({ success: true, serverData: db.servers[serverId] });
    });

    // 5. Récupération des détails réels du serveur via l'API Discord
    app.get('/api/discord/bump/server/:id/details', async (req, res) => {
        const botToken = process.env.DISCORD_BOT_TOKEN;
        const guildId = req.params.id;
        if (!botToken) return res.status(500).json({ error: 'Missing bot token' });

        try {
            // Requête principale
            const guildRes = await axios.get(`${DISCORD_API_BASE}/guilds/${guildId}?with_counts=true`, {
                headers: { Authorization: `Bot ${botToken}` }
            });
            const guild = guildRes.data;

            // Récupération des canaux
            const channelsRes = await axios.get(`${DISCORD_API_BASE}/guilds/${guildId}/channels`, {
                headers: { Authorization: `Bot ${botToken}` }
            });
            const channels = channelsRes.data.filter(c => c.type === 0).slice(0, 10).map(c => c.name);

            // Récupération du propriétaire
            const ownerRes = await axios.get(`${DISCORD_API_BASE}/users/${guild.owner_id}`, {
                headers: { Authorization: `Bot ${botToken}` }
            });
            const owner = ownerRes.data;

            // Extraction des rôles principaux
            const roles = guild.roles.filter(r => !r.managed && r.name !== '@everyone').slice(0, 10).map(r => r.name);

            // Fetch d'un panel de membres pour identifier bots et admins (limité à 100 pour éviter le spam API)
            const membersRes = await axios.get(`${DISCORD_API_BASE}/guilds/${guildId}/members?limit=100`, {
                headers: { Authorization: `Bot ${botToken}` }
            });
            const members = membersRes.data;
            
            const bots = members.filter(m => m.user.bot).map(m => ({
                name: m.user.username,
                avatar: m.user.avatar ? `https://cdn.discordapp.com/avatars/${m.user.id}/${m.user.avatar}.png` : '/assets/images/logo.jpg'
            }));

            const admins = members.filter(m => {
                if (m.user.bot) return false;
                if (m.user.id === guild.owner_id) return false;
                return m.roles.some(roleId => {
                    const r = guild.roles.find(gr => gr.id === roleId);
                    return r && ((BigInt(r.permissions) & 8n) === 8n);
                });
            }).map(m => ({
                name: m.user.username,
                avatar: m.user.avatar ? `https://cdn.discordapp.com/avatars/${m.user.id}/${m.user.avatar}.png` : '/assets/images/logo.jpg'
            }));

            res.json({
                members: guild.approximate_member_count || 0,
                online: guild.approximate_presence_count || 0,
                owner: {
                    name: owner.username,
                    avatar: owner.avatar ? `https://cdn.discordapp.com/avatars/${owner.id}/${owner.avatar}.png` : '/assets/images/logo.jpg'
                },
                admins: admins,
                bots: bots,
                roles: roles,
                channels: channels
            });
        } catch (error) {
            res.status(404).json({ error: 'Bot non présent ou permission insuffisante.' });
        }
    });
};