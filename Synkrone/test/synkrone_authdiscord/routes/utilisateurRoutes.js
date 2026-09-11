const express = require('express');

module.exports = function (dependencies) {
    const router = express.Router();
    const {
        resolveAdminAccessForSessionUser,
        readUsersDb,
        normalizeStoredUser,
        toAdminUserDto,
        isManualStaffRole,
        ALLOWED_USER_GRADES,
        ALLOWED_MANUAL_ROLES,
        writeUsersDb,
        krones
    } = dependencies;

    router.get('/admin/users', async (req, res) => {
        const hasAccess = await resolveAdminAccessForSessionUser(req.session?.user);
        if (!hasAccess) return res.status(403).json({ ok: false, message: 'Acces admin refuse.' });
        const db = await readUsersDb();
        const users = Object.entries(db.users)
            .map(([id, rawUser]) => normalizeStoredUser(rawUser, id))
            .filter(Boolean)
            .map(toAdminUserDto)
            .sort((a, b) => (b.lastSeenAt || 0) - (a.lastSeenAt || 0));
        return res.json({ ok: true, users });
    });

    router.get('/admin/users/:userId', async (req, res) => {
        const hasAccess = await resolveAdminAccessForSessionUser(req.session?.user);
        if (!hasAccess) return res.status(403).json({ ok: false, message: 'Acces admin refuse.' });
        const userId = String(req.params.userId || '').trim();
        if (!userId) return res.status(400).json({ ok: false, message: 'ID invalide.' });
        const db = await readUsersDb();
        const existing = normalizeStoredUser(db.users[userId], userId);
        if (!existing) return res.status(404).json({ ok: false, message: 'Utilisateur introuvable.' });
        return res.json({ ok: true, user: toAdminUserDto(existing) });
    });

    router.get('/staff/users', async (req, res) => {
        const user = req.session?.user;
        if (!user || user.isGuest) return res.status(401).json({ ok: false, message: 'Non authentifie' });
        const isStaff = user.isTeamOwner || isManualStaffRole(user.role);
        if (!isStaff) return res.status(403).json({ ok: false, message: 'Acces refuse' });
        const db = await readUsersDb();
        const users = Object.entries(db.users)
            .map(([id, rawUser]) => normalizeStoredUser(rawUser, id))
            .filter(u => u && (u.isTeamOwner || isManualStaffRole(u.role)))
            .map(toAdminUserDto)
            .sort((a, b) => (b.lastSeenAt || 0) - (a.lastSeenAt || 0));
        return res.json({ ok: true, users });
    });

    router.patch('/admin/users/:userId', async (req, res) => {
        const hasAccess = await resolveAdminAccessForSessionUser(req.session?.user);
        if (!hasAccess) return res.status(403).json({ ok: false, message: 'Acces admin refuse.' });
        const userId = String(req.params.userId || '').trim();
        if (!userId) return res.status(400).json({ ok: false, message: 'ID invalide.' });
        
        const db = await readUsersDb();
        const existing = normalizeStoredUser(db.users[userId], userId);
        if (!existing) return res.status(404).json({ ok: false, message: 'Utilisateur introuvable.' });
        
        const rawGrade = String(req.body?.grade || '').trim();
        if (!ALLOWED_USER_GRADES.has(rawGrade || existing.grade)) return res.status(400).json({ ok: false, message: 'Grade invalide.' });
        
        let nextRole = String(existing.role || 'Krobi').trim();
        if (Object.hasOwn(req.body || {}, 'role')) {
            const rawRole = String(req.body.role || '').trim();
            if (existing.isTeamOwner) nextRole = 'Admin';
            else if (ALLOWED_MANUAL_ROLES.has(rawRole)) nextRole = rawRole;
            else return res.status(400).json({ ok: false, message: 'Role invalide.' });
        }
        
        let nextKrone = existing.krone;
        if (Object.hasOwn(req.body || {}, 'krone')) {
            if (!Number.isFinite(Number(req.body.krone))) return res.status(400).json({ ok: false, message: 'Krone invalide.' });
            nextKrone = Math.max(0, Math.trunc(Number(req.body.krone)));
            if (krones) {
                const set = await krones.setAccountBalance(userId, nextKrone, 'admin:set');
                if (!set.ok) return res.status(400).json({ ok: false, message: set.error || 'Krone invalide.' });
                nextKrone = set.wallet.balance;
            }
        }
        if (krones && Object.hasOwn(req.body || {}, 'grade')) {
            await krones.setAccountPlan(userId, rawGrade || existing.grade);
        }
        
        const nextUser = { ...existing, role: nextRole, grade: rawGrade || existing.grade, krone: nextKrone, updatedAt: Date.now() };
        db.users[userId] = nextUser;
        await writeUsersDb(db);
        if (req.session?.user && String(req.session.user.id || '') === userId) { 
            req.session.user.role = nextUser.role; 
            req.session.user.grade = nextUser.grade; 
            req.session.user.krone = nextUser.krone; 
        }
        return res.json({ ok: true, user: toAdminUserDto(nextUser) });
    });

    return router;
};
