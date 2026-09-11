const express = require('express');

module.exports = function registerMeRoutes(app, deps) {
    const { readUsersDb, writeUsersDb, isManualStaffRole, krones } = deps;

    // Informations du Bot Bump
    app.get('/api/discord/me/bump-info', async (req, res) => {
        const user = req.session?.user;
        if (!user || user.isGuest) {
            return res.status(401).json({ error: 'Non autorisé' });
        }
        res.json({ message: "Bump info endpoint for Me Bot", data: {} });
    });

    // Action de Bump
    app.post('/api/discord/me/trigger-bump', async (req, res) => {
        const user = req.session?.user;
        if (!user || user.isGuest) {
            return res.status(401).json({ error: 'Non autorisé' });
        }
        
        try {
            const db = await readUsersDb();
            const userId = String(user.id);
            if (db.users[userId]) {
                db.users[userId].updatedAt = Date.now();
                await writeUsersDb(db);
            }
            res.json({ success: true, message: "Le Bump a été enregistré avec succès ! Votre profil gagne en visibilité." });
        } catch (error) {
            res.status(500).json({ error: 'Erreur technique lors du bump' });
        }
    });

    // Action de Mise en avant (Achat Krones)
    app.post('/api/discord/me/buy-featured', async (req, res) => {
        const user = req.session?.user;
        if (!user || user.isGuest) return res.status(401).json({ error: 'Non autorisé' });
        
        const { days, cost, autoRenew } = req.body;
        if (!days || !cost) return res.status(400).json({ error: 'Paramètres invalides' });

        try {
            const db = await readUsersDb();
            const userId = String(user.id);
            const existing = db.users[userId];
            
            if (!existing) return res.status(404).json({ error: 'Utilisateur introuvable' });
            if (krones) {
                const spent = await krones.debitAccount(userId, cost, 'me:featured');
                if (!spent.ok) return res.status(400).json({ error: spent.error || 'Fonds insuffisants' });
                existing.krone = spent.wallet.balance;
            } else {
                if (existing.krone < cost) return res.status(400).json({ error: 'Fonds insuffisants' });
                existing.krone -= cost;
            }
            const currentUntil = existing.featuredUntil || Date.now();
            existing.featuredUntil = Math.max(currentUntil, Date.now()) + (days * 24 * 60 * 60 * 1000);
            existing.featured = true;
            existing.autoRenewFeatured = Boolean(autoRenew);
            
            await writeUsersDb(db);
            
            // Mise à jour de la session
            req.session.user.krone = existing.krone;
            
            res.json({ 
                success: true, 
                featuredUntil: existing.featuredUntil, 
                krone: existing.krone 
            });
        } catch(e) {
            console.error('[MeRoutes] Erreur buy-featured:', e);
            res.status(500).json({ error: 'Erreur serveur' });
        }
    });
};