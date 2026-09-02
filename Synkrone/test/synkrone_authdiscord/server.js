const express = require('express');
const session = require('express-session');
const axios = require('axios');
const path = require('node:path');
const fs = require('node:fs/promises');
const os = require('node:os');
const { exec, execFile } = require('node:child_process');
const { promisify } = require('node:util');

const registerCloudRoutes = require('./routes/cloudRoutes');
const registerMeRoutes = require('./routes/meRoutes');
const registerPublicbotRoutes = require('./routes/publicbotRoutes');
const registerBumpRoutes = require('./routes/bumpRoutes');

const execAsync = promisify(exec);
const execFileAsync = promisify(execFile);

const DEFAULT_PORT = 3668;
const RESERVED_PATH_PREFIXES = ['/hub', '/ui', '/sharing', '/vux', '/uploads', '/design'];
const DISCORD_API_BASE = 'https://discord.com/api/v10';
const CONTACT_COOLDOWN_MS = 10 * 60 * 1000;
const DEFAULT_SUPPORT_GUILD_ID = '1368235294192570520';
const DEFAULT_TICKET_CATEGORY_ID = '1465825775231176717';
const DEFAULT_SUPPORT_ROLE_ID = '1465825778771034236';
const BOT_OWNER_CACHE_TTL_MS = 5 * 60 * 1000;
const SESSION_MAX_AGE_MS = 365 * 24 * 60 * 60 * 1000;

const USERS_DB_PATH = path.join(__dirname, 'data', 'users.json');
const ROULETTE_DB_PATH = path.join(__dirname, 'data', 'roulette.json');
const WORKSPACE_DB_PATH = path.join(__dirname, 'data', 'workspace.json');
const CLOUD_DB_PATH = path.join(__dirname, 'data', 'cloud.json');
const ONLINE_WINDOW_MS = 5 * 60 * 1000;

const ALLOWED_USER_GRADES = new Set(['Aucun', 'Kronium', 'Synkral', 'Kronalloy', 'Synkronite', 'Kronix']);
const ROULETTE_DEV_MODE = String(process.env.ROULETTE_DEV_MODE || 'false').toLowerCase() === 'true';

const ROULETTE_PRIZES = [
    { label: '50', amount: 50, color: '#ef4444', textColor: '#ffffff', weight: 1 },
    { label: '40', amount: 40, color: '#f97316', textColor: '#ffffff', weight: 5 },
    { label: '30', amount: 30, color: '#f59e0b', textColor: '#202225', weight: 9 },
    { label: '20', amount: 20, color: '#22c55e', textColor: '#ffffff', weight: 15 },
    { label: '10', amount: 10, color: '#3b82f6', textColor: '#ffffff', weight: 20 },
    { label: '5', amount: 5, color: '#6366f1', textColor: '#ffffff', weight: 25 },
    { label: '1', amount: 1, color: '#374151', textColor: '#ffffff', weight: 25 }
];

const ALLOWED_MANUAL_ROLES = new Set(['Initié', 'Krobi', 'Équipe', 'Admin']);
const BASE_MEMBER_ROLES = new Set(['Initié', 'Krobi']);
const GRADE_KRONE_COSTS = {
    Aucun: 0,
    Kronium: 160,
    Synkral: 780,
    Kronalloy: 1450,
    Synkronite: 2800,
    Kronix: 6500
};

const contactCooldownByUser = new Map();
let botOwnerCache = {
    ownerIds: new Set(),
    expiresAt: 0
};

function isManualStaffRole(roleValue) {
    const normalized = String(roleValue || '').trim().toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    return ['staff', 'equipe', 'equipes', 'admin'].includes(normalized);
}

async function ensureDbFile(filePath, defaultContent) {
    const dirPath = path.dirname(filePath);
    await fs.mkdir(dirPath, { recursive: true });
    try {
        await fs.access(filePath);
    } catch {
        await fs.writeFile(filePath, JSON.stringify(defaultContent, null, 2), 'utf8');
    }
}

async function readCloudDb() {
    const defaultCloud = { items: [], history: [] };
    await ensureDbFile(CLOUD_DB_PATH, defaultCloud);
    try {
        const raw = await fs.readFile(CLOUD_DB_PATH, 'utf8');
        return JSON.parse(raw);
    } catch {
        return defaultCloud;
    }
}

async function writeCloudDb(db) {
    await fs.writeFile(CLOUD_DB_PATH, JSON.stringify(db), 'utf8');
}

async function readWorkspaceDb() {
    const defaultWorkspace = {
        projects: [], versions: [],
        columns: [
            { id: 'todo', title: '  faire', color: '#eab308', collapsed: false },
            { id: 'doing', title: 'En cours', color: '#3b82f6', collapsed: false },
            { id: 'done', title: 'Termin ', color: '#22c55e', collapsed: false }
        ],
        tasks: [], notes: [], polls: [], chat: [], projectRoles: {}
    };
    await ensureDbFile(WORKSPACE_DB_PATH, defaultWorkspace);
    try {
        const raw = await fs.readFile(WORKSPACE_DB_PATH, 'utf8');
        return JSON.parse(raw);
    } catch {
        return defaultWorkspace;
    }
}

async function readRouletteDb() {
    await ensureDbFile(ROULETTE_DB_PATH, { entries: [] });
    try {
        const raw = await fs.readFile(ROULETTE_DB_PATH, 'utf8');
        const parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== 'object' || !Array.isArray(parsed.entries)) return { entries: [] };
        return { entries: parsed.entries };
    } catch {
        return { entries: [] };
    }
}

async function writeRouletteDb(db) {
    await fs.writeFile(ROULETTE_DB_PATH, JSON.stringify(db, null, 2), 'utf8');
}

function startOfDay(timestamp = Date.now()) {
    const value = new Date(timestamp);
    value.setHours(0, 0, 0, 0);
    return value.getTime();
}

function startOfRouletteWindow(timestamp = Date.now()) {
    const value = new Date(timestamp);
    value.setMinutes(0, 0, 0);
    if (value.getHours() < 8) value.setDate(value.getDate() - 1);
    value.setHours(8, 0, 0, 0);
    return value.getTime();
}

function startOfWeek(timestamp = Date.now()) {
    const value = new Date(timestamp);
    const day = value.getDay();
    const diff = day === 0 ? -6 : 1 - day;
    value.setDate(value.getDate() + diff);
    value.setHours(0, 0, 0, 0);
    return value.getTime();
}

function startOfMonth(timestamp = Date.now()) {
    const value = new Date(timestamp);
    value.setDate(1);
    value.setHours(0, 0, 0, 0);
    return value.getTime();
}

function selectRoulettePrize() {
    const pool = [];
    for (const prize of ROULETTE_PRIZES) {
        for (let index = 0; index < prize.weight; index += 1) pool.push(prize);
    }
    return pool[Math.floor(Math.random() * pool.length)] || ROULETTE_PRIZES[0];
}

function computeRouletteStats(entries) {
    const sortedEntries = [...entries].sort((a, b) => Number(b.createdAt || 0) - Number(a.createdAt || 0));
    const now = Date.now();
    const totalGenerated = sortedEntries.reduce((sum, entry) => sum + Number(entry.amount || 0), 0);
    const thisMonthGenerated = sortedEntries.filter(e => Number(e.createdAt || 0) >= startOfMonth(now)).reduce((sum, e) => sum + Number(e.amount || 0), 0);
    const thisWeekGenerated = sortedEntries.filter(e => Number(e.createdAt || 0) >= startOfWeek(now)).reduce((sum, e) => sum + Number(e.amount || 0), 0);
    const todayGenerated = sortedEntries.filter(e => Number(e.createdAt || 0) >= startOfDay(now)).reduce((sum, e) => sum + Number(e.amount || 0), 0);
    const uniqueUsers = new Set(sortedEntries.map(e => String(e.userId || '').trim()).filter(Boolean)).size;
    
    const monthlyPlayersById = new Map();
    sortedEntries.filter(e => Number(e.createdAt || 0) >= startOfMonth(now)).forEach(entry => {
        const userId = String(entry.userId || '').trim();
        if (!userId) return;
        const player = monthlyPlayersById.get(userId) || { id: userId, username: String(entry.username || 'Utilisateur'), avatar: String(entry.avatar || '/assets/images/logo.jpg'), spinsCount: 0, totalKrones: 0, averageVoteTime: 0 };
        player.spinsCount += 1;
        player.totalKrones += Number(entry.amount || 0);
        player.averageVoteTime += Number(entry.createdAt || 0);
        monthlyPlayersById.set(userId, player);
    });
    
    const monthlyPlayers = [...monthlyPlayersById.values()]
        .map(p => ({ ...p, averageVoteTime: p.averageVoteTime / p.spinsCount }))
        .sort((a, b) => b.spinsCount - a.spinsCount || a.averageVoteTime - b.averageVoteTime);
        
    return { totalGenerated, thisMonthGenerated, thisWeekGenerated, todayGenerated, totalEntries: sortedEntries.length, uniqueUsers, monthlyPlayers };
}

function computeRouletteRanking(entries) {
    const playersById = new Map();
    entries.forEach(entry => {
        const userId = String(entry.userId || '').trim();
        if (!userId) return;
        const player = playersById.get(userId) || { id: userId, username: String(entry.username || 'Utilisateur'), avatar: String(entry.avatar || '/assets/images/logo.jpg'), spinsCount: 0, totalKrones: 0, firstSpinAt: Number(entry.createdAt || 0) };
        player.spinsCount += 1;
        player.totalKrones += Number(entry.amount || 0);
        player.firstSpinAt = Math.min(player.firstSpinAt, Number(entry.createdAt || 0));
        playersById.set(userId, player);
    });
    return [...playersById.values()].sort((a, b) => b.totalKrones - a.totalKrones || b.spinsCount - a.spinsCount || a.firstSpinAt - b.firstSpinAt).map((player, index) => ({ ...player, position: index + 1 }));
}

function normalizePm2Process(pmProcess) {
    const rawName = String(pmProcess?.name || `Processus ${pmProcess?.pm_id ?? ''}`).trim();
    const targetMatch = rawName.match(/\b(HTML|BOT|MINECRAFT)\b/i);
    const portMatch = rawName.match(/\b(\d{2,5})\b/);
    const displayName = rawName.replace(/\b(HTML|BOT|MINECRAFT)\b/gi, '').replace(/\b\d{2,5}\b/g, '').replace(/[|()[\]_-]+/g, ' ').replace(/\s+/g, ' ').trim() || rawName;
    const monit = pmProcess?.monit || pmProcess?.pm2_env?.monit || pmProcess?.pm2_env?.axm_monitor || {};
    const cpu = Number(monit.cpu ?? pmProcess?.cpu ?? pmProcess?.pm2_env?.cpu);
    const memory = Number(monit.memory ?? pmProcess?.memory ?? pmProcess?.pm2_env?.memory);
    const port = portMatch ? Number(portMatch[1]) : null;
    
    return {
        id: pmProcess?.pm_id, name: rawName, displayName,
        target: targetMatch ? targetMatch[1].toUpperCase() : 'AUTRE',
        port: Number.isInteger(port) && port >= 1 && port <= 65535 ? port : null,
        status: pmProcess?.pm2_env?.status || 'unknown', uptime: Number(pmProcess?.pm2_env?.pm_uptime) || 0, pid: Number(pmProcess?.pid) || 0,
        memory: Number.isFinite(memory) && memory >= 0 ? memory : null, cpu: Number.isFinite(cpu) && cpu >= 0 ? cpu : null
    };
}

async function readUsersDb() {
    await ensureDbFile(USERS_DB_PATH, { users: {} });
    try {
        const raw = await fs.readFile(USERS_DB_PATH, 'utf8');
        const parsed = JSON.parse(raw);
        if (!parsed || typeof parsed !== 'object' || typeof parsed.users !== 'object') return { users: {} };
        return { users: parsed.users };
    } catch { 
        return { users: {} }; 
    }
}

async function writeUsersDb(db) {
    await fs.writeFile(USERS_DB_PATH, JSON.stringify(db, null, 2), 'utf8');
}

function normalizeStoredUser(user, userId) {
    const safeId = String(userId || user?.id || '').trim();
    if (!safeId) return null;
    const now = Date.now();
    const safeKrone = Number.isFinite(Number(user?.krone)) ? Math.max(0, Math.trunc(Number(user.krone))) : 0;
    const safeGrade = ALLOWED_USER_GRADES.has(String(user?.grade || '')) ? String(user.grade) : 'Aucun';
    const safeOwner = Boolean(user?.isTeamOwner);
    
    let rawRole = String(user?.role || '').trim();
    let safeRole = 'Krobi';
    if (safeOwner || rawRole.toLowerCase() === 'admin') {
        safeRole = 'Admin';
    } else if (isManualStaffRole(rawRole)) {
        safeRole = 'Équipe';
    } else {
        safeRole = rawRole || 'Krobi';
    }
    
    return {
        id: safeId, username: String(user?.username || `Utilisateur ${safeId.slice(-4) || safeId}`),
        avatar: String(user?.avatar || '/assets/images/logo.jpg'), role: safeRole, grade: safeGrade, krone: safeKrone,
        isTeamOwner: safeOwner, isGuest: false, createdAt: Number(user?.createdAt) || now,
        updatedAt: Number(user?.updatedAt) || now, lastSeenAt: Number(user?.lastSeenAt) || now, lastLoginAt: Number(user?.lastLoginAt) || now,
        customUrl: String(user?.customUrl || ''),
        subtitle: String(user?.subtitle || 'Nouveau membre.'),
        banner: String(user?.banner || 'https://placehold.co/800x200/181a1b/2d3033?text=Ma+Banni re'),
        privacy: String(user?.privacy || 'private'),
        unlockedPrivacies: Array.isArray(user?.unlockedPrivacies) ? user.unlockedPrivacies : ['private'],
        links: Array.isArray(user?.links) ? user.links : [],
        customTheme: typeof user?.customTheme === 'object' ? user.customTheme : { active: false, bg: '#181a1b', text: '#ffffff', border: '#e14f4f', panelBg: 'rgba(0,0,0,0.2)' },
        extraLinkSlots: Number.isFinite(Number(user?.extraLinkSlots)) ? Math.max(0, Number(user.extraLinkSlots)) : 0,
        hasCustomization: Boolean(user?.hasCustomization),
        likedProfiles: Array.isArray(user?.likedProfiles) ? user.likedProfiles : [],
        stats: typeof user?.stats === 'object' ? user.stats : { visitsTotal: 0, visitsMonth: 0, likesTotal: 0, likesMonth: 0 }
    };
}

function toAdminUserDto(user) {
    const now = Date.now();
    const lastSeenAt = Number(user?.lastSeenAt) || 0;
    return {
        id: String(user?.id || ''), username: String(user?.username || 'Utilisateur inconnu'),
        avatar: String(user?.avatar || '/assets/images/logo.jpg'), role: String(user?.role || 'Krobi'),
        grade: ALLOWED_USER_GRADES.has(String(user?.grade || '')) ? String(user.grade) : 'Aucun',
        krone: Number(user?.krone || 0), isTeamOwner: Boolean(user?.isTeamOwner),
        lastSeenAt, lastLoginAt: Number(user?.lastLoginAt) || 0, createdAt: Number(user?.createdAt) || 0,
        status: now - lastSeenAt <= ONLINE_WINDOW_MS ? 'online' : 'offline'
    };
}

async function upsertUserFromDiscordAuth(discordUser, isTeamOwner) {
    const db = await readUsersDb();
    const userId = String(discordUser?.id || '').trim();
    if (!userId) return null;
    const existing = normalizeStoredUser(db.users[userId], userId);
    const now = Date.now();
    
    const bannerUrl = discordUser.banner 
        ? `https://cdn.discordapp.com/banners/${userId}/${discordUser.banner}.png?size=512` 
        : existing?.banner || 'https://placehold.co/800x200/181a1b/2d3033?text=Ma+Banni re';
        
    const nextUser = {
        ...(existing || {}),
        id: userId, username: String(discordUser?.global_name || discordUser?.username || existing?.username || `Utilisateur ${userId.slice(-4)}`),
        avatar: discordUser?.avatar ? `https://cdn.discordapp.com/avatars/${userId}/${discordUser.avatar}.png` : String(existing?.avatar || '/assets/images/logo.jpg'),
        banner: bannerUrl,
        role: isTeamOwner ? 'Admin' : (existing ? existing.role : 'Krobi'),
        grade: ALLOWED_USER_GRADES.has(String(existing?.grade || '')) ? String(existing.grade) : 'Aucun',
        krone: Number.isFinite(Number(existing?.krone)) ? Math.max(0, Math.trunc(Number(existing.krone))) : 0,
        isTeamOwner: Boolean(isTeamOwner), isGuest: false, createdAt: Number(existing?.createdAt) || now, updatedAt: now, lastSeenAt: now, lastLoginAt: now
    };
    db.users[userId] = nextUser;
    await writeUsersDb(db);
    return nextUser;
}

async function syncSessionUserWithDb(sessionUser, options = {}) {
    const { markLogin = false } = options;
    if (!sessionUser || sessionUser.isGuest) return sessionUser;
    const userId = String(sessionUser.id || '').trim();
    if (!userId) return sessionUser;
    const db = await readUsersDb();
    const existing = normalizeStoredUser(db.users[userId], userId);
    const now = Date.now();
    
    const nextUser = {
        ...(existing || {}),
        id: userId, username: String(sessionUser.username || existing?.username || `Utilisateur ${userId.slice(-4)}`),
        avatar: String(sessionUser.avatar || existing?.avatar || '/assets/images/logo.jpg'),
        role: String(existing?.role || sessionUser.role || 'Krobi'),
        grade: ALLOWED_USER_GRADES.has(String(existing?.grade || sessionUser.grade || '')) ? String(existing?.grade || sessionUser.grade) : 'Aucun',
        krone: Number.isFinite(Number(existing?.krone)) ? Math.max(0, Math.trunc(Number(existing.krone))) : Number.isFinite(Number(sessionUser.krone)) ? Math.max(0, Math.trunc(Number(sessionUser.krone))) : 0,
        isTeamOwner: Boolean(sessionUser.isTeamOwner || existing?.isTeamOwner),
        isGuest: false, createdAt: Number(existing?.createdAt) || now, updatedAt: now, lastSeenAt: now, lastLoginAt: markLogin ? now : Number(existing?.lastLoginAt || now)
    };
    db.users[userId] = nextUser;
    await writeUsersDb(db);
    
    sessionUser.username = nextUser.username;
    sessionUser.avatar = nextUser.avatar;
    sessionUser.role = nextUser.role;
    sessionUser.grade = nextUser.grade;
    sessionUser.krone = nextUser.krone;
    sessionUser.isTeamOwner = nextUser.isTeamOwner;
    return sessionUser;
}

function isDiscordOAuthConfigured() {
    return Boolean(
        String(process.env.DISCORD_CLIENT_ID || '').trim()
        && String(process.env.DISCORD_CLIENT_SECRET || '').trim()
        && String(process.env.DISCORD_REDIRECT_URI || '').trim()
    );
}

function isReservedPublicPath(pathname) {
    const normalized = pathname.length > 1 && pathname.endsWith('/') ? pathname.slice(0, -1) : pathname;
    return RESERVED_PATH_PREFIXES.some((prefix) => normalized === prefix || normalized.startsWith(`${prefix}/`));
}

function mountPublic(app, options = {}) {
    const skipBodyParser = Boolean(options.skipBodyParser);
    const skipSession = Boolean(options.skipSession);

    if (!skipBodyParser) {
        app.use(express.json({ limit: '500mb' }));
        app.use(express.urlencoded({ limit: '500mb', extended: true }));
    }
    if (!skipSession) {
        app.use(session({
            secret: process.env.SESSION_SECRET || 'synkrone_secret',
            resave: false, saveUninitialized: false, rolling: true,
            cookie: { maxAge: SESSION_MAX_AGE_MS, httpOnly: true, sameSite: 'lax' }
        }));
    }

    const designDir = path.join(__dirname, '..', '..', '..', 'apps', 'www', 'design');
    app.use('/design', express.static(designDir));

async function getBotOwnerIds() {
    const token = String(process.env.DISCORD_BOT_TOKEN || '').trim();
    if (!token) return new Set();
    if (Date.now() < botOwnerCache.expiresAt) return botOwnerCache.ownerIds;
    
    const response = await axios.get(`${DISCORD_API_BASE}/oauth2/applications/@me`, { headers: { Authorization: `Bot ${token}` } });
    const application = response?.data || {};
    const ownerIds = new Set();
    const directOwnerId = String(application?.owner?.id || '').trim();
    if (directOwnerId) ownerIds.add(directOwnerId);
    
    const teamMembers = Array.isArray(application?.team?.members) ? application.team.members : [];
    for (const member of teamMembers) {
        const memberId = String(member?.user?.id || '').trim();
        if (!memberId) continue;
        const membershipState = Number(member?.membership_state || 0);
        if (!membershipState || membershipState === 2) ownerIds.add(memberId);
    }
    botOwnerCache = { ownerIds, expiresAt: Date.now() + BOT_OWNER_CACHE_TTL_MS };
    return ownerIds;
}

async function isBotOwnerUserId(userId) {
    const safeUserId = String(userId || '').trim();
    if (!safeUserId) return false;
    try {
        const ownerIds = await getBotOwnerIds();
        return ownerIds.has(safeUserId);
    } catch (error) { 
        return false; 
    }
}

async function resolveAdminAccessForSessionUser(user) {
    if (!user || user.isGuest) return false;
    const isTeamOwner = await isBotOwnerUserId(user.id);
    user.isTeamOwner = isTeamOwner;
    if (isTeamOwner && user.role !== 'Admin') {
        user.role = 'Admin';
    } else if (!isTeamOwner && user.role === 'Admin') {
        user.role = 'Équipe';
    }
    return isTeamOwner;
}

app.get('/auth/discord', (req, res) => {
    if (!isDiscordOAuthConfigured()) return res.redirect('/');
    const discordUrl = `https://discord.com/api/oauth2/authorize?client_id=${process.env.DISCORD_CLIENT_ID}&redirect_uri=${encodeURIComponent(process.env.DISCORD_REDIRECT_URI)}&response_type=code&scope=identify`;
    res.redirect(discordUrl);
});

app.get('/auth/discord/callback', async (req, res) => {
    if (!isDiscordOAuthConfigured()) return res.redirect('/');
    const code = req.query.code;
    if (!code) return res.redirect('/');
    try {
        const tokenResponse = await axios.post('https://discord.com/api/oauth2/token', new URLSearchParams({
            client_id: process.env.DISCORD_CLIENT_ID, client_secret: process.env.DISCORD_CLIENT_SECRET,
            grant_type: 'authorization_code', code: code, redirect_uri: process.env.DISCORD_REDIRECT_URI
        }), { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } });
        
        const userResponse = await axios.get('https://discord.com/api/users/@me', { headers: { Authorization: `Bearer ${tokenResponse.data.access_token}` } });
        const discordUser = userResponse.data;
        const isTeamOwner = await isBotOwnerUserId(discordUser.id);
        const persistedUser = await upsertUserFromDiscordAuth(discordUser, isTeamOwner);
        
        req.session.user = {
            id: discordUser.id, username: persistedUser?.username || discordUser.global_name || discordUser.username,
            avatar: persistedUser?.avatar || (discordUser.avatar ? `https://cdn.discordapp.com/avatars/${discordUser.id}/${discordUser.avatar}.png` : '/assets/images/logo.jpg'),
            role: persistedUser?.role || (isTeamOwner ? 'Admin' : 'Krobi'),
            grade: persistedUser?.grade || 'Aucun', krone: Number.isFinite(Number(persistedUser?.krone)) ? Number(persistedUser.krone) : 0,
            isGuest: false, isTeamOwner
        };
        res.redirect('/');
    } catch (err) { 
        res.redirect('/'); 
    }
});

app.get('/auth/guest', (req, res) => {
    req.session.user = { id: 'guest', username: 'Visiteur', isGuest: true };
    res.redirect('/');
});

app.get('/api/me', async (req, res) => {
    if (!req.session.user) return res.json({ authenticated: false, oauthConfigured: isDiscordOAuthConfigured() });
    await resolveAdminAccessForSessionUser(req.session.user);
    const syncedUser = await syncSessionUserWithDb(req.session.user);
    
    const db = await readUsersDb();
    const fullUser = db.users[syncedUser.id];
    return res.json({ authenticated: true, oauthConfigured: isDiscordOAuthConfigured(), user: fullUser || syncedUser });
});

app.post('/api/me/profile', async (req, res) => {
    const sessionUser = req.session?.user;
    if (!sessionUser || sessionUser.isGuest) return res.status(401).json({ ok: false, message: 'Non authentifi ' });
    const db = await readUsersDb();
    const existing = normalizeStoredUser(db.users[sessionUser.id], sessionUser.id);
    if (!existing) return res.status(404).json({ ok: false, message: 'Utilisateur introuvable' });
    const payload = req.body || {};
    
    if (payload.customUrl !== undefined) {
        const desiredUrl = String(payload.customUrl).trim().toLowerCase();
        if (desiredUrl !== existing.customUrl && desiredUrl !== '') {
            const isTaken = Object.values(db.users).some(u => String(u.customUrl).toLowerCase() === desiredUrl && u.id !== sessionUser.id);
            if (isTaken) return res.status(409).json({ ok: false, message: 'Ce pseudo est d  pris.' });
            existing.customUrl = desiredUrl;
        }
    }
    
    if (payload.subtitle !== undefined) existing.subtitle = String(payload.subtitle);
    if (payload.banner !== undefined) existing.banner = String(payload.banner);
    if (payload.privacy !== undefined) existing.privacy = String(payload.privacy);
    if (Array.isArray(payload.unlockedPrivacies)) existing.unlockedPrivacies = payload.unlockedPrivacies;
    if (Array.isArray(payload.links)) existing.links = payload.links;
    if (typeof payload.customTheme === 'object') existing.customTheme = payload.customTheme;
    if (payload.extraLinkSlots !== undefined) existing.extraLinkSlots = Number(payload.extraLinkSlots);
    if (payload.hasCustomization !== undefined) existing.hasCustomization = Boolean(payload.hasCustomization);
    if (Array.isArray(payload.likedProfiles)) existing.likedProfiles = payload.likedProfiles;
    if (typeof payload.stats === 'object') existing.stats = payload.stats;
    
    if (payload.krone !== undefined) {
        existing.krone = Math.max(0, Math.trunc(Number(payload.krone)));
        req.session.user.krone = existing.krone; 
    }
    existing.updatedAt = Date.now();
    db.users[sessionUser.id] = existing;
    await writeUsersDb(db);
    return res.json({ ok: true, user: existing });
});

app.get('/api/profiles', async (req, res) => {
    const db = await readUsersDb();
    const profiles = Object.values(db.users)
        .map(u => normalizeStoredUser(u, u.id))
        .filter(u => u && u.privacy === 'public'); 
    return res.json({ ok: true, profiles });
});

app.get('/logout', (req, res) => {
    req.session.destroy(() => res.redirect('/'));
});

// --- CLOUD ---
registerCloudRoutes(app, { readCloudDb, writeCloudDb, isManualStaffRole });
registerMeRoutes(app, { readUsersDb, writeUsersDb, isManualStaffRole });
registerPublicbotRoutes(app, { readUsersDb, writeUsersDb, isManualStaffRole });
registerBumpRoutes(app, { readUsersDb, writeUsersDb, isManualStaffRole });

// --- ESPACE DE TRAVAIL (WORKSPACE) ---
app.get('/api/workspace', async (req, res) => {
    const user = req.session?.user;
    if (!user || user.isGuest || (!user.isTeamOwner && !isManualStaffRole(user.role))) return res.status(403).json({ error: 'Acc s refus ' });
    const db = await readWorkspaceDb();
    if (user.isTeamOwner || user.role === 'Admin') return res.json(db);
    
    const myProjects = db.projects.filter(p => p.members.includes(user.id));
    const myProjectIds = new Set(myProjects.map(p => p.id));
    const myVersions = db.versions.filter(v => myProjectIds.has(v.projectId));
    const myVersionIds = new Set(myVersions.map(v => v.id));
    
    res.json({
        ...db, projects: myProjects, versions: myVersions,
        tasks: db.tasks.filter(t => myVersionIds.has(t.versionId)),
        notes: db.notes.filter(n => myVersionIds.has(n.versionId)),
        polls: db.polls.filter(p => myVersionIds.has(p.versionId)),
        chat: db.chat.filter(c => myVersionIds.has(c.versionId))
    });
});

app.post('/api/workspace', async (req, res) => {
    const user = req.session?.user;
    if (!user || user.isGuest || (!user.isTeamOwner && !isManualStaffRole(user.role))) return res.status(403).json({ error: 'Acc s refus ' });
    const db = await readWorkspaceDb();
    const incoming = req.body;
    
    if (user.isTeamOwner || user.role === 'Admin') {
        await fs.writeFile(WORKSPACE_DB_PATH, JSON.stringify({ ...db, ...incoming }, null, 2));
    } else {
        const myProjectIds = new Set(db.projects.filter(p => p.members.includes(user.id)).map(p => p.id));
        const myVersionIds = new Set(db.versions.filter(v => myProjectIds.has(v.projectId)).map(v => v.id));
        const otherProjects = db.projects.filter(p => !myProjectIds.has(p.id));
        const otherVersions = db.versions.filter(v => !myVersionIds.has(v.id));
        const otherTasks = db.tasks.filter(t => !myVersionIds.has(t.versionId));
        const otherNotes = db.notes.filter(n => !myVersionIds.has(n.versionId));
        const otherPolls = db.polls.filter(p => !myVersionIds.has(p.versionId));
        const otherChat = db.chat.filter(c => !myVersionIds.has(c.versionId));
        
        await fs.writeFile(WORKSPACE_DB_PATH, JSON.stringify({
            columns: incoming.columns || db.columns, projectRoles: incoming.projectRoles || db.projectRoles,
            projects: [...otherProjects, ...(incoming.projects || [])], versions: [...otherVersions, ...(incoming.versions || [])],
            tasks: [...otherTasks, ...(incoming.tasks || [])], notes: [...otherNotes, ...(incoming.notes || [])],
            polls: [...otherPolls, ...(incoming.polls || [])], chat: [...otherChat, ...(incoming.chat || [])],
        }, null, 2));
    }
    res.json({ ok: true });
});

// --- AUTRES ROUTES GLOBALES ---
const CONTACT_THEMES = { recrutement: 'Recrutement', achat: 'Lier a un achat', probleme: 'Probleme', bug: 'Bug / Erreur', performance: 'Performance / Latence', compte: 'Compte utilisateur', facturation: 'Facturation / Paiement', remboursement: 'Remboursement', securite: 'Securite / Signalement', moderation: 'Moderation / Sanction', suggestion: 'Suggestion', partenariat: 'Partenariat', evenement: 'Evenement / Communication', autre: 'Autre' };
const CONTACT_THEME_ALIASES = { recrutement: 'recrutement', achat: 'achat', lier_a_un_achat: 'achat', probleme: 'probleme', probleme_technique: 'probleme', bug: 'bug', bug_erreur: 'bug', performance: 'performance', performance_latence: 'performance', compte: 'compte', compte_utilisateur: 'compte', facturation: 'facturation', facturation_paiement: 'facturation', remboursement: 'remboursement', securite: 'securite', securite_signalement: 'securite', moderation: 'moderation', moderation_sanction: 'moderation', suggestion: 'suggestion', suggestion_idee: 'suggestion', partenariat: 'partenariat', evenement: 'evenement', evenement_communication: 'evenement', autre: 'autre' };

function normalizeThemeValue(value) {
    let normalized = String(value || '').trim().toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9]+/g, '_');
    while (normalized.startsWith('_')) normalized = normalized.slice(1);
    while (normalized.endsWith('_')) normalized = normalized.slice(0, -1);
    return normalized;
}

function resolveThemeKey(themeInput) {
    const normalized = normalizeThemeValue(themeInput);
    if (!normalized) return null;
    const alias = CONTACT_THEME_ALIASES[normalized];
    if (alias && Object.hasOwn(CONTACT_THEMES, alias)) return alias;
    return Object.hasOwn(CONTACT_THEMES, normalized) ? normalized : null;
}

function getContactInviteUrl() { return process.env.DISCORD_SUPPORT_INVITE_URL || 'https://discord.gg/p768u2Pgp3'; }

function getCooldownRemainingMs(userId) {
    const key = String(userId || '').trim();
    if (!key) return 0;
    const lastTicketAt = contactCooldownByUser.get(key);
    if (!lastTicketAt) return 0;
    const elapsed = Date.now() - lastTicketAt;
    if (elapsed >= CONTACT_COOLDOWN_MS) { contactCooldownByUser.delete(key); return 0; }
    return CONTACT_COOLDOWN_MS - elapsed;
}

function getTicketCategoryId() { return String(process.env.DISCORD_TICKET_CATEGORY_ID || DEFAULT_TICKET_CATEGORY_ID).trim(); }
function getSupportRoleId() { return String(process.env.DISCORD_SUPPORT_ROLE_ID || DEFAULT_SUPPORT_ROLE_ID).trim(); }

function sanitizeChannelSegment(value) { return String(value || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/[^a-z0-9-]/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, ''); }

function buildTicketChannelName(username, userId) {
    const base = sanitizeChannelSegment(username) || `user-${String(userId || '').slice(-4) || 'ticket'}`;
    const suffix = String(Date.now()).slice(-6);
    return `ticket-${base}-${suffix}`.slice(0, 90);
}

async function resolveGuildInfo(token, guildId) {
    if (!guildId) return null;
    const response = await axios.get(`${DISCORD_API_BASE}/guilds/${guildId}`, { headers: { Authorization: `Bot ${token}` } });
    const guild = response?.data || {};
    const iconHash = String(guild.icon || '').trim();
    const iconUrl = iconHash ? `https://cdn.discordapp.com/icons/${guildId}/${iconHash}.png?size=256` : '/assets/images/logo.jpg';
    return { id: guildId, name: String(guild.name || 'Serveur Discord Synkrone'), iconUrl };
}

async function resolveGuildId(token, channelId) {
    const configuredGuildId = String(process.env.DISCORD_GUILD_ID || '').trim() || DEFAULT_SUPPORT_GUILD_ID;
    if (configuredGuildId) return configuredGuildId;
    if (!channelId) return null;
    const response = await axios.get(`${DISCORD_API_BASE}/channels/${channelId}`, { headers: { Authorization: `Bot ${token}` } });
    return String(response?.data?.guild_id || '').trim() || null;
}

async function isDiscordMember(token, guildId, userId) {
    try {
        await axios.get(`${DISCORD_API_BASE}/guilds/${guildId}/members/${userId}`, { headers: { Authorization: `Bot ${token}` } });
        return true;
    } catch (error) { return false; }
}

app.get('/api/contact-state', async (req, res) => {
    const inviteUrl = getContactInviteUrl();
    const user = req.session?.user;
    const token = process.env.DISCORD_BOT_TOKEN;
    const categoryId = getTicketCategoryId();
    
    if (!token || !categoryId) return res.status(500).json({ ok: false, message: 'Config Discord manquante.', authenticated: Boolean(user && !user.isGuest), isMember: false, inviteUrl, loginUrl: '/auth/discord' });
    let guildId = null, guild = null;
    try {
        guildId = await resolveGuildId(token, categoryId);
        guild = await resolveGuildInfo(token, guildId);
    } catch (error) {}
    
    if (!user || user.isGuest) return res.json({ ok: true, authenticated: false, isMember: false, inviteUrl, loginUrl: '/auth/discord', guild });
    try {
        if (!guildId) return res.status(500).json({ ok: false, message: 'Serveur Discord introuvable.', authenticated: true, isMember: false, inviteUrl, loginUrl: '/auth/discord', guild });
        const member = await isDiscordMember(token, guildId, user.id);
        const cooldownRemainingMs = getCooldownRemainingMs(user.id);
        return res.json({ ok: true, authenticated: true, isMember: member, inviteUrl, loginUrl: '/auth/discord', guild, cooldownSecondsRemaining: Math.ceil(cooldownRemainingMs / 1000), user: { id: user.id, username: user.username, avatar: user.avatar || '/assets/images/logo.jpg' } });
    } catch (error) { return res.status(502).json({ ok: false, message: 'Impossible de verifier la presence Discord.', authenticated: true, isMember: false, inviteUrl, loginUrl: '/auth/discord', guild }); }
});

app.post('/api/contact-ticket', async (req, res) => {
    const token = process.env.DISCORD_BOT_TOKEN;
    const categoryId = getTicketCategoryId();
    const supportRoleId = getSupportRoleId();
    const inviteUrl = getContactInviteUrl();
    const sessionUser = req.session?.user;
    
    if (!sessionUser || sessionUser.isGuest) return res.status(401).json({ ok: false, message: 'Connectez-vous avec Discord.', inviteUrl, loginUrl: '/auth/discord' });
    if (!token || !categoryId || !supportRoleId) return res.status(500).json({ ok: false, message: 'Configuration Discord manquante.' });
    
    const rawTheme = String(req.body?.theme || '');
    const resolvedTheme = resolveThemeKey(rawTheme);
    const rawMessage = String(req.body?.message || '').trim();
    
    if (!rawTheme || !rawMessage) return res.status(400).json({ ok: false, message: 'Champs obligatoires.' });
    if (!resolvedTheme) return res.status(400).json({ ok: false, message: 'Th me invalide.' });
    
    try {
        const guildId = await resolveGuildId(token, categoryId);
        if (!guildId) return res.status(500).json({ ok: false, message: 'Serveur Discord introuvable.' });
        
        const cooldownRemainingMs = getCooldownRemainingMs(sessionUser.id);
        if (cooldownRemainingMs > 0) return res.status(429).json({ ok: false, message: `Patientez ${Math.ceil(cooldownRemainingMs / 60000)} min.` });
        
        const member = await isDiscordMember(token, guildId, sessionUser.id);
        if (!member) return res.status(403).json({ ok: false, message: 'Rejoignez le serveur Discord.', inviteUrl });
        
        const safeUsername = String(sessionUser.username || 'Utilisateur inconnu').slice(0, 100);
        const ticketChannelName = buildTicketChannelName(safeUsername, sessionUser.id);
        
        const createdChannelResponse = await axios.post(`${DISCORD_API_BASE}/guilds/${guildId}/channels`, {
            name: ticketChannelName, type: 0, parent_id: categoryId,
            permission_overwrites: [
                { id: String(guildId), type: 0, deny: '1024', allow: '0' },
                { id: supportRoleId, type: 0, allow: '68608', deny: '0' },
                { id: String(sessionUser.id), type: 1, allow: '68608', deny: '0' }
            ]
        }, { headers: { Authorization: `Bot ${token}` } });
        
        const createdChannelId = createdChannelResponse.data.id;
        
        await axios.post(`${DISCORD_API_BASE}/channels/${createdChannelId}/messages`, {
            content: `<@${sessionUser.id}> <@&${supportRoleId}>`,
            embeds: [{ title: `${safeUsername} - ${CONTACT_THEMES[resolvedTheme]}`, color: 5793266, description: `**D tail :**\n${rawMessage}` }]
        }, { headers: { Authorization: `Bot ${token}` } });
        
        contactCooldownByUser.set(String(sessionUser.id), Date.now());
        return res.json({ ok: true, message: 'Demande envoy e.' });
    } catch (error) { return res.status(502).json({ ok: false, message: 'Erreur lors de la cr ation du ticket.' }); }
});

app.get('/api/contact-config', (req, res) => res.json({ ok: true, inviteUrl: getContactInviteUrl() }));

app.get('/api/roulette/config', async (req, res) => {
    const sessionUser = req.session?.user;
    const loggedIn = Boolean(sessionUser && !sessionUser.isGuest);
    const db = await readRouletteDb();
    let canSpin = true;
    let reason = 'Mode dev actif';
    
    if (loggedIn && !ROULETTE_DEV_MODE) {
        const rouletteWindowStart = startOfRouletteWindow();
        const alreadyPlayedToday = db.entries.some(e => String(e.userId || '') === String(sessionUser.id || '') && Number(e.createdAt || 0) >= rouletteWindowStart);
        canSpin = !alreadyPlayedToday;
        reason = canSpin ? 'Tu peux jouer (reset quotidien   08:00).' : 'Tu as d  jou  pour cette p riode (reset   08:00).';
    }
    return res.json({ ok: true, devMode: ROULETTE_DEV_MODE, authenticated: loggedIn, canSpin, reason, loginUrl: '/auth/discord' });
});

app.get('/api/roulette/history', async (req, res) => {
    const db = await readRouletteDb();
    return res.json({ ok: true, history: [...db.entries].sort((a, b) => Number(b.createdAt || 0) - Number(a.createdAt || 0)) });
});

app.get('/api/roulette/stats', async (req, res) => {
    const db = await readRouletteDb();
    return res.json({
        ok: true, stats: computeRouletteStats(db.entries), ranking: computeRouletteRanking(db.entries),
        currentUserId: req.session?.user && !req.session.user.isGuest ? String(req.session.user.id || '') : null, devMode: ROULETTE_DEV_MODE
    });
});

app.post('/api/roulette/spin', async (req, res) => {
    const sessionUser = req.session?.user;
    if (!sessionUser || sessionUser.isGuest) return res.status(401).json({ ok: false, message: 'Connecte-toi pour jouer   la roulette.' });
    
    const db = await readRouletteDb();
    if (!ROULETTE_DEV_MODE) {
        if (db.entries.some(e => String(e.userId || '') === String(sessionUser.id || '') && Number(e.createdAt || 0) >= startOfRouletteWindow())) {
            return res.status(429).json({ ok: false, message: 'Tu as d  jou  pour cette p riode.' });
        }
    }
    
    const prize = selectRoulettePrize();
    const now = Date.now();
    const userId = String(sessionUser.id || '').trim();
    
    const usersDb = await readUsersDb();
    const existing = normalizeStoredUser(usersDb.users[userId], userId);
    const nextKrone = Math.max(0, Number(existing?.krone || 0) + Number(prize.amount || 0));
    
    const nextUser = {
        ...(existing || {}), id: userId, username: String(sessionUser.username || existing?.username || `Utilisateur ${userId.slice(-4)}`),
        avatar: String(sessionUser.avatar || existing?.avatar || '/assets/images/logo.jpg'), role: String(sessionUser.role || existing?.role || 'Krobi'),
        grade: ALLOWED_USER_GRADES.has(String(existing?.grade || sessionUser.grade || '')) ? String(existing?.grade || sessionUser.grade) : 'Aucun',
        krone: nextKrone, isTeamOwner: Boolean(existing?.isTeamOwner || sessionUser.isTeamOwner), isGuest: false, updatedAt: now, lastSeenAt: now, lastLoginAt: Number(existing?.lastLoginAt || now)
    };
    
    usersDb.users[userId] = nextUser;
    await writeUsersDb(usersDb);
    
    const entry = { id: `${now}-${Math.random().toString(36).slice(2, 8)}`, userId, username: nextUser.username, avatar: nextUser.avatar, amount: Number(prize.amount || 0), prizeLabel: prize.label, createdAt: now };
    db.entries.push(entry);
    await writeRouletteDb(db);
    
    if (req.session?.user) req.session.user.krone = nextUser.krone;
    return res.json({ ok: true, message: `Tu as gagn  ${prize.amount} Kr nes.`, prize, amount: Number(prize.amount || 0), newKrone: nextUser.krone, entry, devMode: ROULETTE_DEV_MODE });
});

app.post('/api/grades/purchase', async (req, res) => {
    const sessionUser = req.session?.user;
    if (!sessionUser || sessionUser.isGuest) return res.status(401).json({ ok: false, message: 'Connectez-vous avec Discord.' });
    
    await resolveAdminAccessForSessionUser(sessionUser);
    await syncSessionUserWithDb(sessionUser);
    
    const userId = String(sessionUser.id || '').trim();
    if (!userId) return res.status(400).json({ ok: false, message: 'Session invalide.' });
    
    const targetGrade = String(req.body?.grade || '').trim();
    if (!ALLOWED_USER_GRADES.has(targetGrade) || targetGrade === 'Aucun') return res.status(400).json({ ok: false, message: 'Grade cible invalide.' });
    
    const db = await readUsersDb();
    const existing = normalizeStoredUser(db.users[userId], userId);
    if (!existing) return res.status(404).json({ ok: false, message: 'Utilisateur introuvable.' });
    
    const safeRole = String(existing.role || 'Krobi').trim() || 'Krobi';
    const isSupportLabel = Object.prototype.hasOwnProperty.call(GRADE_KRONE_COSTS, safeRole);
    if (Boolean(existing.isTeamOwner) || (!BASE_MEMBER_ROLES.has(safeRole) && !isSupportLabel)) {
        return res.status(409).json({ ok: false, message: 'Profil staff: grade inchangeable.', user: toAdminUserDto(existing) });
    }
    
    const currentCost = Number(GRADE_KRONE_COSTS[ALLOWED_USER_GRADES.has(String(existing.grade || '')) ? String(existing.grade) : 'Aucun'] || 0);
    const targetCost = Number(GRADE_KRONE_COSTS[targetGrade] || 0);
    if (targetCost <= currentCost) return res.status(400).json({ ok: false, message: 'Grade deja possede.' });
    
    const requiredKrone = targetCost - currentCost;
    if (Math.max(0, Math.trunc(Number(existing.krone || 0))) < requiredKrone) return res.status(409).json({ ok: false, message: 'Solde insuffisant.' });
    
    const nextUser = { ...existing, grade: targetGrade, krone: existing.krone - requiredKrone, updatedAt: Date.now(), lastSeenAt: Date.now() };
    db.users[userId] = nextUser;
    await writeUsersDb(db);
    sessionUser.grade = nextUser.grade; sessionUser.krone = nextUser.krone;
    
    return res.json({ ok: true, message: 'Achat valide.', user: toAdminUserDto(nextUser) });
});

const utilisateurRoutes = require('./routes/utilisateurRoutes.js');
app.use('/api', utilisateurRoutes({
    resolveAdminAccessForSessionUser,
    readUsersDb,
    normalizeStoredUser,
    toAdminUserDto,
    isManualStaffRole,
    ALLOWED_USER_GRADES,
    ALLOWED_MANUAL_ROLES,
    writeUsersDb
}));

app.get('/api/admin/pm2/servers', async (req, res) => {
    const hasAccess = await resolveAdminAccessForSessionUser(req.session?.user);
    if (!hasAccess) return res.status(403).json({ error: 'Acces refuse.' });
    try {
        const { stdout } = await execAsync('pm2 jlist', { maxBuffer: 2 * 1024 * 1024 });
        const processes = JSON.parse(stdout);
        const servers = processes.map((pmProcess) => ({ ...normalizePm2Process(pmProcess), protected: String(pmProcess.pm_id) === (processes.find(p => Number(p.pid || 0) === process.pid) ? String(processes.find(p => Number(p.pid || 0) === process.pid).pm_id) : null) }));
        return res.json({ servers, vps: { totalMem: os.totalmem(), freeMem: os.freemem(), usedMem: os.totalmem() - os.freemem(), cpuCount: os.cpus().length, totalCpu: servers.reduce((tot, s) => tot + s.cpu, 0) } });
    } catch (error) { return res.status(500).json({ error: 'PM2 indisponible.' }); }
});

app.post(/^\/api\/admin\/pm2\/servers\/(all|\d+)\/(start|restart|stop)$/, async (req, res) => {
    const hasAccess = await resolveAdminAccessForSessionUser(req.session?.user);
    if (!hasAccess) return res.status(403).json({ error: 'Acces refuse.' });
    try {
        const { stdout } = await execFileAsync('pm2', ['jlist'], { maxBuffer: 1024 * 1024 });
        const processes = JSON.parse(stdout);
        const protectedId = processes.find(p => Number(p.pid || 0) === process.pid) ? String(processes.find(p => Number(p.pid || 0) === process.pid).pm_id) : null;
        if (String(req.params[0]).trim() === protectedId) return res.status(409).json({ error: 'Processus Synkrone protege.' });
        const targetIds = String(req.params[0]).trim() === 'all' ? processes.map(p => String(p.pm_id)).filter(id => id !== protectedId) : [String(req.params[0]).trim()];
        const results = [];
        for (const targetId of targetIds) results.push((await execFileAsync('pm2', [String(req.params[1]).trim(), targetId], { maxBuffer: 1024 * 1024 })).stdout || '');
        return res.json({ success: true, output: results.join('') });
    } catch (error) { return res.status(500).json({ error: 'PM2 impossible.' }); }
});

// -- ROUTES IFRAMES --
app.get(/^\/discord\/bots\/(discord|asuna|vax|yui|kayaba|arceus|bot)\.html$/i, (req, res) => res.sendFile(path.join(__dirname, 'public', 'discord', 'bots', `${String(req.params[0]).toLowerCase()}.html`)));
app.get(/^\/minecraft\/modpack\/(accueil|xenus|thefrenchbaguette|vanipack)\.html$/i, (req, res) => res.sendFile(path.join(__dirname, 'public', 'minecraft', 'modpack', `${String(req.params[0]).toLowerCase()}.html`)));
app.get('/discord/publicbot/index.html', (req, res) => res.sendFile(path.join(__dirname, 'public', 'discord', 'publicbot', 'index.html')));
app.get(/^\/equipe\/(espace-travail|cloud)\/index\.html$/i, (req, res) => {
    const page = String(req.params[0] || '').toLowerCase();
    res.sendFile(path.join(__dirname, 'public', 'equipe', page, 'index.html'));
});
app.get(/^\/admin\/(utilisateur|annonce|pm2)\/index\.html$/i, async (req, res) => {
    const hasAccess = await resolveAdminAccessForSessionUser(req.session?.user);
    if (!hasAccess) return res.status(403).send('Acces refuse');
    res.sendFile(path.join(__dirname, 'public', 'admin', String(req.params[0]).toLowerCase(), 'index.html'));
});

// -- ROUTES SHELL --
const SHELL_ROUTES = new Set(['/', '/accueil', '/discord', '/discord/bots', '/discord/publicbot', '/discord/dashbot', '/discord/me', '/discord/bump', '/minecraft', '/minecraft/serveur', '/minecraft/modpack', '/admin', '/admin/utilisateur', '/admin/annonce', '/admin/pm2', '/equipe', '/equipe/espace-travail', '/equipe/cloud', '/cgu', '/contact', '/parametre.html']);
const SHELL_PREFIXES = ['/discord/bots/', '/minecraft/modpack/', '/equipe/espace-travail/', '/equipe/cloud/'];

app.get(/^\/(.*)$/i, async (req, res, next) => {
    let normalizedPath = req.path;
    if (normalizedPath.length > 1 && normalizedPath.endsWith('/')) {
        normalizedPath = normalizedPath.slice(0, -1);
    }
    if (isReservedPublicPath(normalizedPath)) return next();
    if (normalizedPath.endsWith('.html') && !SHELL_ROUTES.has(normalizedPath)) {
        return next();
    }
    const isShellRoute = SHELL_ROUTES.has(normalizedPath) || SHELL_PREFIXES.some(prefix => normalizedPath.startsWith(prefix));
    if (!isShellRoute) return next();
    if (normalizedPath.startsWith('/admin')) {
        const hasAccess = await resolveAdminAccessForSessionUser(req.session?.user);
        if (!hasAccess) return res.redirect('/accueil');
    }
    return res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.use(express.static(path.join(__dirname, 'public')));
app.get(/^(.*)$/, (req, res, next) => {
    if (isReservedPublicPath(req.path)) return next();
    return res.sendFile(path.join(__dirname, 'public', 'index.html'));
});
}

module.exports = { mountPublic, isDiscordOAuthConfigured };

if (require.main === module) {
    require('dotenv').config();
    const standalone = express();
    mountPublic(standalone);
    const port = Number(process.env.PORT || DEFAULT_PORT);
    standalone.listen(port, '127.0.0.1', () => {
        console.log(`[Synkrone.app] Site public http://127.0.0.1:${port}/`);
    });
}