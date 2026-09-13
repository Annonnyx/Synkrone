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
const registerAnnouncementRoutes = require('./routes/announcementRoutes');
const { renderShell } = require(path.join(__dirname, '..', '..', '..', 'apps', 'www', 'lib', 'leaf-pages'));
const {
    requestPanelSession,
    rememberIdentity,
    issueSiteSession,
    requireInternalAuth,
    panelCookieOptions,
    panelBridgeFromSiteUser
} = require(path.join(__dirname, '..', '..', '..', 'apps', 'www', 'lib', 'identity-bridge'));
const { mountTemoignages, addOptInQuote } = require(path.join(__dirname, '..', '..', '..', 'apps', 'www', 'lib', 'temoignages'));

const execAsync = promisify(exec);
const execFileAsync = promisify(execFile);

const DEFAULT_PORT = 3668;
const RESERVED_PATH_PREFIXES = ['/hub', '/ui', '/sharing', '/vux', '/uploads', '/me-media', '/serveur-media', '/design', '/api', '/hebergement', '/robots.txt', '/sitemap.xml'];
const DISCORD_API_BASE = 'https://discord.com/api/v10';
const CONTACT_COOLDOWN_MS = 10 * 60 * 1000;
const DEFAULT_SUPPORT_GUILD_ID = '1368235294192570520';
const DEFAULT_TICKET_CATEGORY_ID = '1465825775231176717';
const DEFAULT_SUPPORT_ROLE_ID = '1465825778771034236';
const BOT_OWNER_CACHE_TTL_MS = 5 * 60 * 1000;

const USERS_DB_PATH = path.join(__dirname, 'data', 'users.json');
const ME_UPLOADS_DIR = path.join(__dirname, 'data', 'uploads', 'me');
const BANNER_MAX_BYTES = 3 * 1024 * 1024;
const BANNER_TYPES = {
    'image/jpeg': 'jpg',
    'image/png': 'png',
    'image/webp': 'webp',
    'image/gif': 'gif'
};

function isCustomBanner(url) {
    return String(url || '').startsWith('/me-media/');
}

function bannerExtFromBuffer(buf) {
    if (!buf || buf.length < 12) return null;
    if (buf[0] === 0xff && buf[1] === 0xd8 && buf[2] === 0xff) return 'jpg';
    if (buf[0] === 0x89 && buf[1] === 0x50 && buf[2] === 0x4e && buf[3] === 0x47) return 'png';
    if (buf[0] === 0x47 && buf[1] === 0x49 && buf[2] === 0x46) return 'gif';
    if (buf[0] === 0x52 && buf[1] === 0x49 && buf[2] === 0x46 && buf[3] === 0x46
        && buf[8] === 0x57 && buf[9] === 0x45 && buf[10] === 0x42 && buf[11] === 0x50) return 'webp';
    return null;
}

async function removeOldMeBanners(userId) {
    const prefix = `${String(userId).replace(/[^a-zA-Z0-9_-]/g, '')}-`;
    let names = [];
    try {
        names = await fs.readdir(ME_UPLOADS_DIR);
    } catch {
        return;
    }
    await Promise.all(names
        .filter((name) => name.startsWith(prefix))
        .map((name) => fs.unlink(path.join(ME_UPLOADS_DIR, name)).catch(() => undefined)));
}
let kronesApi = null;
try {
    kronesApi = require(path.join(__dirname, '..', '..', '..', 'apps', 'www', 'lib', 'krones'));
} catch {
    kronesApi = null;
}

const { readPlatform, writePlatform } = require(path.join(__dirname, '..', '..', '..', 'apps', 'www', 'lib', 'platform'));
const { panelAdmin, pm2Logs, listTickets } = require(path.join(__dirname, '..', '..', '..', 'apps', 'www', 'lib', 'admin-ops'));
const pgAccount = require(path.join(__dirname, '..', '..', '..', 'apps', 'www', 'lib', 'pg-account'));
const {
    COOKIE_NAME,
    createFileSessionStore,
    sessionCookieOptions
} = require(path.join(__dirname, '..', '..', '..', 'apps', 'www', 'lib', 'session-store'));

function safeReturnTo(value) {
    const raw = String(value || '').trim();
    if (!raw.startsWith('/') || raw.startsWith('//') || raw.includes('\\') || raw.includes('://')) return '';
    if (raw.length > 1024) return '';
    if (/^\/(auth|logout|api)(\/|$)/i.test(raw)) return '';
    return raw;
}

function safePanelReturnTo(value) {
    const raw = safeReturnTo(value);
    if (!raw) return '';
    const pathOnly = raw.split('?')[0];
    if (pathOnly === '/hebergement/login' || pathOnly.startsWith('/hebergement/login/')) return '';
    if (pathOnly === '/hebergement' || pathOnly.startsWith('/hebergement/')) return raw;
    return '';
}

function rememberReturnTo(req) {
    const dest = safeReturnTo(req.query.returnTo);
    if (dest) req.session.returnTo = dest;
}

function consumeReturnTo(req) {
    const dest = safeReturnTo(req.session?.returnTo) || '/';
    if (req.session) delete req.session.returnTo;
    return dest;
}

async function overlayWalletOnUser(user) {
    if (!kronesApi || !user || user.isGuest) return user;
    const id = String(user.id || '').trim();
    if (!id || id === 'guest') return user;
    try {
        const wallet = await kronesApi.peekWallet(id);
        user.krone = wallet.balance;
        if (wallet.plan) user.grade = wallet.plan;
    } catch {
        /* keep cached krone */
    }
    return user;
}
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

const ALLOWED_MANUAL_ROLES = new Set(['Initié', 'Krobi', 'Dev', 'Équipe', 'Admin']);
const BASE_MEMBER_ROLES = new Set(['Initié', 'Krobi']);
const GRADE_KRONE_COSTS = {
    Aucun: 0,
    Kronium: 150,
    Synkral: 750,
    Kronalloy: 1500,
    Synkronite: 3000,
    Kronix: 6000
};

const contactCooldownByUser = new Map();
let botOwnerCache = {
    ownerIds: new Set(),
    expiresAt: 0,
    status: 'unknown'
};

function isManualStaffRole(roleValue) {
    const normalized = String(roleValue || '').trim().toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    return ['staff', 'equipe', 'equipes', 'admin', 'dev'].includes(normalized);
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
    if (pgAccount.isConfigured()) {
        try {
            return await pgAccount.loadSiteUsers();
        } catch (err) {
            console.error('[account] lecture postgres:', err.message);
        }
    }
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
    if (pgAccount.isConfigured()) {
        try {
            await pgAccount.saveSiteUsers(db.users);
            return;
        } catch (err) {
            console.error('[account] écriture postgres:', err.message);
        }
    }
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
    } else if (rawRole.toLowerCase() === 'dev') {
        safeRole = 'Dev';
    } else if (isManualStaffRole(rawRole)) {
        safeRole = 'Équipe';
    } else {
        safeRole = rawRole || 'Krobi';
    }
    
    return {
        id: safeId,
        dbId: String(user?.dbId || ''),
        username: String(user?.username || `Utilisateur ${safeId.slice(-4) || safeId}`),
        avatar: String(user?.avatar || '/assets/images/logo.jpg'), role: safeRole, grade: safeGrade, krone: safeKrone,
        isTeamOwner: safeOwner, isGuest: false, createdAt: Number(user?.createdAt) || now,
        updatedAt: Number(user?.updatedAt) || now, lastSeenAt: Number(user?.lastSeenAt) || now, lastLoginAt: Number(user?.lastLoginAt) || now,
        customUrl: String(user?.customUrl || ''),
        name: String(user?.name || user?.username || `Utilisateur ${safeId.slice(-4) || safeId}`),
        subtitle: String(user?.subtitle || 'Nouveau membre.'),
        banner: isCustomBanner(user?.banner) || String(user?.banner || '').startsWith('http')
            ? String(user.banner)
            : '',
        bannerCustom: Boolean(user?.bannerCustom) || isCustomBanner(user?.banner),
        privacy: String(user?.privacy || 'private'),
        unlockedPrivacies: Array.isArray(user?.unlockedPrivacies) ? user.unlockedPrivacies : ['private'],
        links: Array.isArray(user?.links) ? user.links : [],
        customTheme: typeof user?.customTheme === 'object' ? user.customTheme : { active: false, bg: '#eef0ea', text: '#1b211e', border: '#3f6b52', panelBg: '#ffffff' },
        extraLinkSlots: Number.isFinite(Number(user?.extraLinkSlots)) ? Math.max(0, Number(user.extraLinkSlots)) : 0,
        hasCustomization: Boolean(user?.hasCustomization),
        featuredUntil: Number(user?.featuredUntil) || 0,
        autoRenewFeatured: Boolean(user?.autoRenewFeatured),
        likedProfiles: Array.isArray(user?.likedProfiles) ? user.likedProfiles : [],
        stats: typeof user?.stats === 'object' ? user.stats : { visitsTotal: 0, visitsMonth: 0, likesTotal: 0, likesMonth: 0 },
        providers: (() => {
            const providers = user?.providers && typeof user.providers === 'object' ? { ...user.providers } : {};
            if (/^\d{15,22}$/.test(safeId) && !providers.discord) providers.discord = safeId;
            const prefixed = safeId.match(/^(discord|github|google):(.+)$/);
            if (prefixed && !providers[prefixed[1]]) providers[prefixed[1]] = prefixed[2];
            return providers;
        })(),
        email: String(user?.email || '').trim().toLowerCase()
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

function providersOf(user) {
    return user?.providers && typeof user.providers === 'object' ? { ...user.providers } : {};
}

function findUserByProvider(db, provider, providerId) {
    const id = String(providerId || '').trim();
    if (!id) return null;
    return Object.values(db.users || {}).find((u) => {
        if (!u) return false;
        if (provider === 'discord' && String(u.id) === id) return true;
        if (String(u.id) === `${provider}:${id}`) return true;
        return String(providersOf(u)[provider] || '') === id;
    }) || null;
}

function attachTargetId(req) {
    const user = req.session?.user;
    if (!user || user.isGuest) return null;
    const id = String(user.id || '').trim();
    return id && id !== 'guest' ? id : null;
}

function sessionFromPersisted(persisted) {
    return {
        id: persisted.id,
        dbId: persisted.dbId || '',
        username: persisted.username,
        avatar: persisted.avatar,
        role: persisted.role,
        grade: persisted.grade,
        krone: persisted.krone,
        isGuest: false,
        isTeamOwner: Boolean(persisted.isTeamOwner),
        providers: providersOf(persisted),
        email: String(persisted.email || '')
    };
}

function providerTakenError() {
    const err = new Error('Ce compte est déjà lié à un autre profil Synkrone.');
    err.code = 'PROVIDER_TAKEN';
    return err;
}

async function migrateUserId(db, fromId, toId) {
    if (!fromId || !toId || fromId === toId) return;
    const fromUser = db.users[fromId];
    if (!fromUser) return;
    const dest = db.users[toId] || {};
    db.users[toId] = normalizeStoredUser({
        ...fromUser,
        ...dest,
        id: toId,
        providers: { ...providersOf(fromUser), ...providersOf(dest) },
        krone: Math.max(Number(fromUser.krone) || 0, Number(dest.krone) || 0)
    }, toId);
    delete db.users[fromId];
    if (kronesApi?.migrateWallet) {
        await kronesApi.migrateWallet(fromId, toId).catch(() => undefined);
    }
}

async function upsertUserFromDiscordAuth(discordUser, isTeamOwner, attachToId) {
    const db = await readUsersDb();
    const discordId = String(discordUser?.id || '').trim();
    if (!discordId) return null;
    const byDiscord = findUserByProvider(db, 'discord', discordId);
    if (attachToId && db.users[attachToId] && byDiscord && String(byDiscord.id) !== String(attachToId)) {
        throw providerTakenError();
    }
    let existing = (attachToId && db.users[attachToId]) || byDiscord || db.users[discordId] || null;
    if (existing && String(existing.id) !== discordId) {
        await migrateUserId(db, existing.id, discordId);
        existing = db.users[discordId];
    }
    const now = Date.now();
    const keepBanner = Boolean(existing?.bannerCustom) || isCustomBanner(existing?.banner);
    const discordBanner = discordUser.banner
        ? `https://cdn.discordapp.com/banners/${discordId}/${discordUser.banner}.png?size=512`
        : '';
    const bannerUrl = keepBanner
        ? existing.banner
        : (discordBanner || existing?.banner || '');
    const nextUser = {
        ...(existing || {}),
        id: discordId,
        dbId: String(existing?.dbId || ''),
        username: String(discordUser?.global_name || discordUser?.username || existing?.username || `Utilisateur ${discordId.slice(-4)}`),
        name: String(existing?.name || discordUser?.global_name || discordUser?.username || existing?.username || `Utilisateur ${discordId.slice(-4)}`),
        avatar: discordUser?.avatar ? `https://cdn.discordapp.com/avatars/${discordId}/${discordUser.avatar}.png` : String(existing?.avatar || '/assets/images/logo.jpg'),
        banner: bannerUrl,
        bannerCustom: keepBanner,
        role: isTeamOwner === true ? 'Admin' : (existing ? existing.role : 'Krobi'),
        grade: ALLOWED_USER_GRADES.has(String(existing?.grade || '')) ? String(existing.grade) : 'Aucun',
        krone: Number.isFinite(Number(existing?.krone)) ? Math.max(0, Math.trunc(Number(existing.krone))) : 0,
        isTeamOwner: isTeamOwner === null ? Boolean(existing?.isTeamOwner) : Boolean(isTeamOwner),
        isGuest: false,
        providers: { ...providersOf(existing), discord: discordId },
        createdAt: Number(existing?.createdAt) || now,
        updatedAt: now,
        lastSeenAt: now,
        lastLoginAt: now
    };
    db.users[discordId] = normalizeStoredUser(nextUser, discordId);
    await writeUsersDb(db);
    return db.users[discordId];
}

async function upsertUserFromOAuth(provider, profile, attachToId) {
    const providerId = String(profile.id || '').trim();
    if (!providerId) return null;
    const db = await readUsersDb();
    const byProvider = findUserByProvider(db, provider, providerId);
    if (attachToId && db.users[attachToId] && byProvider && String(byProvider.id) !== String(attachToId)) {
        throw providerTakenError();
    }
    const existing = (attachToId && db.users[attachToId]) || byProvider || null;
    const now = Date.now();
    const id = existing?.id || `${provider}:${providerId}`;
    const nextUser = {
        ...(existing || {}),
        id,
        dbId: String(existing?.dbId || ''),
        username: String(existing?.username || profile.username || `Utilisateur ${providerId.slice(-4)}`),
        avatar: String(existing?.avatar || profile.avatar || '/assets/images/logo.jpg'),
        email: String(profile.email || existing?.email || '').trim().toLowerCase(),
        role: existing?.role || 'Krobi',
        grade: ALLOWED_USER_GRADES.has(String(existing?.grade || '')) ? String(existing.grade) : 'Aucun',
        krone: Number.isFinite(Number(existing?.krone)) ? Math.max(0, Math.trunc(Number(existing.krone))) : 0,
        isTeamOwner: Boolean(existing?.isTeamOwner),
        isGuest: false,
        providers: { ...providersOf(existing), [provider]: providerId },
        createdAt: Number(existing?.createdAt) || now,
        updatedAt: now,
        lastSeenAt: now,
        lastLoginAt: now
    };
    db.users[id] = normalizeStoredUser(nextUser, id);
    await writeUsersDb(db);
    return db.users[id];
}

function isProdCookie() {
    return process.env.NODE_ENV === 'production';
}

async function persistPanelUserId(siteUserId, panelUserId) {
    const siteId = String(siteUserId || '').trim();
    const panelId = String(panelUserId || '').trim();
    if (!siteId || !panelId) return;
    const db = await readUsersDb();
    const user = db.users[siteId];
    if (!user || String(user.dbId || '') === panelId) return;
    user.dbId = panelId;
    await writeUsersDb(db);
}

async function attachPanelFromSite(res, persisted, provider, profile, options = {}) {
    const required = Boolean(options.required);
    try {
        const panel = await requestPanelSession({
            provider,
            userId: persisted.dbId || undefined,
            profile: {
                id: String(profile.id || persisted.id),
                name: persisted.username,
                login: profile.username || persisted.username,
                email: persisted.email || profile.email || '',
                avatarUrl: persisted.avatar
            }
        });
        if (!panel?.token) throw new Error('Panel session missing');
        persisted.dbId = panel.userId;
        res.cookie('synkrone_session', panel.token, panelCookieOptions(isProdCookie()));
        await rememberIdentity({
            siteUserId: persisted.id,
            panelUserId: panel.userId,
            discordId: provider === 'discord' ? String(profile.id || persisted.id) : (panel.discordId || ''),
            email: persisted.email || profile.email || ''
        });
        await persistPanelUserId(persisted.id, panel.userId).catch(() => undefined);
        if (provider === 'discord' && panel.userId && kronesApi?.migrateWallet) {
            await kronesApi.migrateWallet(`panel:${panel.userId}`, String(profile.id || persisted.id)).catch(() => undefined);
        }
        return true;
    } catch (err) {
        if (required) throw err;
        return false;
    }
}

async function attachPanelFromSiteUser(res, user, options = {}) {
    const bridge = panelBridgeFromSiteUser(user);
    if (!bridge) {
        const err = new Error('Connectez-vous avec Discord, Google ou GitHub.');
        err.code = 'NO_OAUTH';
        throw err;
    }
    return attachPanelFromSite(res, user, bridge.provider, {
        id: bridge.profile.id,
        username: bridge.profile.login,
        email: bridge.profile.email,
        avatar: bridge.profile.avatarUrl
    }, options);
}

function panelLoginRedirect(returnTo, oauthError) {
    const qs = new URLSearchParams({ intent: 'panel' });
    if (returnTo) qs.set('returnTo', returnTo);
    if (oauthError) qs.set('oauth_error', oauthError);
    return `/login?${qs.toString()}`;
}

async function sendShell(res, pathname) {
    const html = await renderShell({
        shellPath: path.join(__dirname, 'public', 'index.html'),
        publicDir: path.join(__dirname, 'public'),
        pathname
    });
    res.set('Cache-Control', 'no-store');
    res.type('html').send(html);
}

async function syncSessionUserWithDb(sessionUser, options = {}) {
    const { markLogin = false } = options;
    if (!sessionUser || sessionUser.isGuest) return sessionUser;
    const userId = String(sessionUser.id || '').trim();
    if (!userId) return sessionUser;
    const db = await readUsersDb();
    const existing = normalizeStoredUser(db.users[userId], userId);
    const now = Date.now();
    
    const providers = providersOf(existing);
    if (/^\d{15,22}$/.test(userId)) providers.discord = userId;
    const nextUser = normalizeStoredUser({
        ...(existing || {}),
        id: userId,
        username: String(sessionUser.username || existing?.username || `Utilisateur ${userId.slice(-4)}`),
        avatar: String(sessionUser.avatar || existing?.avatar || '/assets/images/logo.jpg'),
        role: String(existing?.role || sessionUser.role || 'Krobi'),
        grade: ALLOWED_USER_GRADES.has(String(existing?.grade || sessionUser.grade || '')) ? String(existing?.grade || sessionUser.grade) : 'Aucun',
        krone: Number.isFinite(Number(existing?.krone)) ? Math.max(0, Math.trunc(Number(existing.krone))) : Number.isFinite(Number(sessionUser.krone)) ? Math.max(0, Math.trunc(Number(sessionUser.krone))) : 0,
        isTeamOwner: Boolean(sessionUser.isTeamOwner || existing?.isTeamOwner),
        isGuest: false,
        providers,
        email: String(existing?.email || sessionUser.email || ''),
        createdAt: Number(existing?.createdAt) || now,
        updatedAt: now,
        lastSeenAt: now,
        lastLoginAt: markLogin ? now : Number(existing?.lastLoginAt || now)
    }, userId);
    await overlayWalletOnUser(nextUser);
    db.users[userId] = nextUser;
    await writeUsersDb(db);

    sessionUser.username = nextUser.username;
    sessionUser.avatar = nextUser.avatar;
    sessionUser.role = nextUser.role;
    sessionUser.grade = nextUser.grade;
    sessionUser.krone = nextUser.krone;
    sessionUser.isTeamOwner = nextUser.isTeamOwner;
    sessionUser.providers = nextUser.providers;
    sessionUser.email = nextUser.email;
    return sessionUser;
}

function isDiscordOAuthConfigured() {
    return Boolean(
        String(process.env.DISCORD_CLIENT_ID || '').trim()
        && String(process.env.DISCORD_CLIENT_SECRET || '').trim()
        && String(process.env.DISCORD_REDIRECT_URI || '').trim()
    );
}

function isGithubOAuthConfigured() {
    return Boolean(
        String(process.env.GITHUB_CLIENT_ID || '').trim()
        && String(process.env.GITHUB_CLIENT_SECRET || '').trim()
    );
}

function isGoogleOAuthConfigured() {
    return Boolean(
        String(process.env.GOOGLE_CLIENT_ID || '').trim()
        && String(process.env.GOOGLE_CLIENT_SECRET || '').trim()
    );
}

function publicSiteOrigin(req) {
    const fromEnv = String(process.env.PUBLIC_ORIGIN || '').trim().replace(/\/$/, '');
    if (fromEnv) return fromEnv;
    const host = req?.get?.('host');
    if (host) return `${req.protocol || 'http'}://${host}`;
    return 'http://127.0.0.1:3668';
}

function githubRedirectUri(req) {
    return String(process.env.GITHUB_REDIRECT_URI || '').trim() || `${publicSiteOrigin(req)}/auth/github/callback`;
}

function googleRedirectUri(req) {
    return String(process.env.GOOGLE_REDIRECT_URI || '').trim() || `${publicSiteOrigin(req)}/auth/google/callback`;
}

function oauthFailRedirect(req, err) {
    if (err?.code === 'PROVIDER_TAKEN') return '/compte?linkError=taken';
    return safeReturnTo(req.session?.returnTo) || '/login';
}

function oauthStatus() {
    return {
        oauthConfigured: isDiscordOAuthConfigured() || isGithubOAuthConfigured() || isGoogleOAuthConfigured(),
        providers: {
            discord: isDiscordOAuthConfigured(),
            github: isGithubOAuthConfigured(),
            google: isGoogleOAuthConfigured()
        }
    };
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
            name: COOKIE_NAME,
            secret: process.env.SESSION_SECRET || 'synkrone_secret',
            resave: false,
            saveUninitialized: false,
            rolling: false,
            store: createFileSessionStore(path.join(__dirname, '..', '..', '..', 'apps', 'www', 'data', 'sessions')),
            cookie: sessionCookieOptions(process.env.NODE_ENV === 'production')
        }));
    }

    const designDir = path.join(__dirname, '..', '..', '..', 'apps', 'www', 'design');
    app.use('/design', express.static(designDir, {
        etag: true,
        setHeaders(res, filePath) {
            if (String(filePath).endsWith('.html')) res.setHeader('Cache-Control', 'no-store');
            else res.setHeader('Cache-Control', 'public, max-age=86400');
        }
    }));
    app.use('/me-media', express.static(ME_UPLOADS_DIR, { fallthrough: true, maxAge: '7d' }));
    void fs.mkdir(ME_UPLOADS_DIR, { recursive: true }).catch(() => undefined);

async function fetchBotOwnerIds() {
    const token = String(process.env.DISCORD_BOT_TOKEN || '').trim();
    if (!token) return { status: 'unavailable', ownerIds: botOwnerCache.ownerIds };
    if (botOwnerCache.status === 'ok' && Date.now() < botOwnerCache.expiresAt) {
        return { status: 'ok', ownerIds: botOwnerCache.ownerIds };
    }
    try {
        const response = await axios.get(`${DISCORD_API_BASE}/oauth2/applications/@me`, {
            headers: { Authorization: `Bot ${token}` },
            timeout: 2500
        });
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
        botOwnerCache = { ownerIds, expiresAt: Date.now() + BOT_OWNER_CACHE_TTL_MS, status: 'ok' };
        return { status: 'ok', ownerIds };
    } catch {
        if (botOwnerCache.status === 'ok' && botOwnerCache.ownerIds.size) {
            botOwnerCache.expiresAt = Date.now() + 30_000;
            return { status: 'ok', ownerIds: botOwnerCache.ownerIds };
        }
        botOwnerCache = {
            ownerIds: botOwnerCache.ownerIds || new Set(),
            expiresAt: Date.now() + 30_000,
            status: 'unavailable'
        };
        return { status: 'unavailable', ownerIds: botOwnerCache.ownerIds };
    }
}

/** true / false si Discord a répondu ; null si le lookup a échoué. */
async function isBotOwnerUserId(userId) {
    const safeUserId = String(userId || '').trim();
    if (!safeUserId) return false;
    try {
        const lookup = await fetchBotOwnerIds();
        if (lookup.status !== 'ok') return null;
        return lookup.ownerIds.has(safeUserId);
    } catch {
        return null;
    }
}

async function persistedAdminAccess(userId) {
    const safeUserId = String(userId || '').trim();
    if (!safeUserId) return false;
    try {
        const db = await readUsersDb();
        const stored = normalizeStoredUser(db.users[safeUserId], safeUserId);
        if (!stored) return false;
        return Boolean(stored.isTeamOwner || stored.role === 'Admin');
    } catch {
        return false;
    }
}

async function resolveAdminAccessForSessionUser(user) {
    if (!user || user.isGuest) return false;
    const discordOwner = await isBotOwnerUserId(user.id);
    if (discordOwner === true) {
        user.isTeamOwner = true;
        if (user.role !== 'Admin') user.role = 'Admin';
        return true;
    }
    if (discordOwner === false) {
        user.isTeamOwner = false;
        if (user.role === 'Admin') user.role = 'Équipe';
        return false;
    }
    if (user.isTeamOwner || user.role === 'Admin') return true;
    const storedAdmin = await persistedAdminAccess(user.id);
    if (storedAdmin) {
        user.isTeamOwner = true;
        user.role = 'Admin';
        return true;
    }
    return false;
}

app.get('/auth/discord', (req, res) => {
    if (!isDiscordOAuthConfigured()) return res.redirect(safeReturnTo(req.query.returnTo) || '/login');
    rememberReturnTo(req);
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
        const persistedUser = await upsertUserFromDiscordAuth(discordUser, isTeamOwner, attachTargetId(req));
        if (!persistedUser) return res.redirect('/');
        req.session.user = sessionFromPersisted(persistedUser);
        const dest = consumeReturnTo(req);
        req.session.save(async (err) => {
            if (err) return res.redirect('/login');
            await attachPanelFromSite(res, persistedUser, 'discord', discordUser);
            res.redirect(dest);
        });
    } catch (err) {
        res.redirect(oauthFailRedirect(req, err));
    }
});

app.get('/auth/github', (req, res) => {
    if (!isGithubOAuthConfigured()) return res.redirect(safeReturnTo(req.query.returnTo) || '/login');
    rememberReturnTo(req);
    const url = new URL('https://github.com/login/oauth/authorize');
    url.searchParams.set('client_id', process.env.GITHUB_CLIENT_ID);
    url.searchParams.set('redirect_uri', githubRedirectUri(req));
    url.searchParams.set('scope', 'read:user user:email');
    url.searchParams.set('allow_signup', 'true');
    res.redirect(url.toString());
});

app.get('/auth/github/callback', async (req, res) => {
    if (!isGithubOAuthConfigured()) return res.redirect('/');
    const code = req.query.code;
    if (!code) return res.redirect('/');
    try {
        const tokenResponse = await axios.post('https://github.com/login/oauth/access_token', {
            client_id: process.env.GITHUB_CLIENT_ID,
            client_secret: process.env.GITHUB_CLIENT_SECRET,
            code,
            redirect_uri: githubRedirectUri(req)
        }, { headers: { Accept: 'application/json' } });
        const access = tokenResponse.data?.access_token;
        if (!access) return res.redirect('/');
        const userResponse = await axios.get('https://api.github.com/user', {
            headers: { Authorization: `Bearer ${access}`, 'User-Agent': 'Synkrone' }
        });
        const gh = userResponse.data || {};
        const persistedUser = await upsertUserFromOAuth('github', {
            id: gh.id,
            username: gh.login || gh.name,
            avatar: gh.avatar_url
        }, attachTargetId(req));
        if (!persistedUser) return res.redirect('/');
        req.session.user = sessionFromPersisted(persistedUser);
        const dest = consumeReturnTo(req);
        req.session.save(async (err) => {
            if (err) return res.redirect('/login');
            await attachPanelFromSite(res, persistedUser, 'github', {
                id: gh.id,
                username: gh.login || gh.name,
                email: '',
                avatar: gh.avatar_url
            });
            res.redirect(dest);
        });
    } catch (err) {
        res.redirect(oauthFailRedirect(req, err));
    }
});

app.get('/auth/google', (req, res) => {
    if (!isGoogleOAuthConfigured()) return res.redirect(safeReturnTo(req.query.returnTo) || '/login');
    rememberReturnTo(req);
    const url = new URL('https://accounts.google.com/o/oauth2/v2/auth');
    url.searchParams.set('client_id', process.env.GOOGLE_CLIENT_ID);
    url.searchParams.set('redirect_uri', googleRedirectUri(req));
    url.searchParams.set('response_type', 'code');
    url.searchParams.set('scope', 'openid email profile');
    url.searchParams.set('prompt', 'select_account');
    res.redirect(url.toString());
});

app.get('/auth/google/callback', async (req, res) => {
    if (!isGoogleOAuthConfigured()) return res.redirect('/');
    const code = req.query.code;
    if (!code) return res.redirect('/');
    try {
        const tokenResponse = await axios.post('https://oauth2.googleapis.com/token', {
            client_id: process.env.GOOGLE_CLIENT_ID,
            client_secret: process.env.GOOGLE_CLIENT_SECRET,
            code,
            grant_type: 'authorization_code',
            redirect_uri: googleRedirectUri(req)
        });
        const access = tokenResponse.data?.access_token;
        if (!access) return res.redirect('/');
        const userResponse = await axios.get('https://openidconnect.googleapis.com/v1/userinfo', {
            headers: { Authorization: `Bearer ${access}` }
        });
        const g = userResponse.data || {};
        const persistedUser = await upsertUserFromOAuth('google', {
            id: g.sub,
            username: g.name || g.email,
            avatar: g.picture,
            email: g.email
        }, attachTargetId(req));
        if (!persistedUser) return res.redirect('/');
        req.session.user = sessionFromPersisted(persistedUser);
        const dest = consumeReturnTo(req);
        req.session.save(async (err) => {
            if (err) return res.redirect('/login');
            await attachPanelFromSite(res, persistedUser, 'google', {
                id: g.sub,
                username: g.name || g.email,
                email: g.email,
                avatar: g.picture
            });
            res.redirect(dest);
        });
    } catch (err) {
        res.redirect(oauthFailRedirect(req, err));
    }
});

app.get('/auth/guest', (req, res) => {
    rememberReturnTo(req);
    req.session.user = { id: 'guest', username: 'Visiteur', isGuest: true };
    const dest = consumeReturnTo(req);
    req.session.save((err) => {
        if (err) return res.redirect('/');
        res.redirect(dest);
    });
});

app.post('/api/internal/session-bridge', async (req, res) => {
    if (!requireInternalAuth(req)) return res.status(401).json({ error: 'Unauthorized' });
    const provider = String(req.body?.provider || '');
    const profile = req.body?.profile || {};
    if (!profile.id) return res.status(400).json({ error: 'missing_profile' });
    try {
        let persisted = null;
        if (provider === 'discord') {
            persisted = await upsertUserFromDiscordAuth({
                id: String(profile.id),
                username: profile.login || profile.name,
                global_name: profile.name,
                avatar: null
            }, false, null);
            if (persisted && profile.avatarUrl) persisted.avatar = String(profile.avatarUrl);
        } else if (provider === 'github' || provider === 'google') {
            persisted = await upsertUserFromOAuth(provider, {
                id: profile.id,
                username: profile.login || profile.name,
                avatar: profile.avatarUrl,
                email: profile.email
            }, null);
        } else {
            return res.status(400).json({ error: 'unknown_provider' });
        }
        if (!persisted) return res.status(400).json({ error: 'user_failed' });
        const sid = await issueSiteSession(sessionFromPersisted(persisted));
        await rememberIdentity({
            siteUserId: persisted.id,
            discordId: provider === 'discord' ? String(profile.id) : '',
            email: persisted.email || profile.email || ''
        });
        return res.json({ ok: true, sid, siteUserId: persisted.id });
    } catch (err) {
        if (err.code === 'PROVIDER_TAKEN') return res.status(409).json({ error: 'PROVIDER_TAKEN' });
        return res.status(500).json({ error: 'bridge_failed' });
    }
});

app.post('/api/auth/attach-panel', async (req, res) => {
    const user = req.session?.user;
    if (!user || user.isGuest) {
        return res.status(401).json({ ok: false, error: 'Connexion requise.' });
    }
    try {
        await attachPanelFromSiteUser(res, user, { required: true });
        return res.json({ ok: true });
    } catch (err) {
        const status = err.code === 'NO_OAUTH' ? 400 : 502;
        return res.status(status).json({
            ok: false,
            error: err.code === 'NO_OAUTH'
                ? 'Connectez-vous avec Discord, Google ou GitHub.'
                : 'Pont panel indisponible.'
        });
    }
});

app.get('/api/auth/enter-panel', async (req, res) => {
    res.set('Cache-Control', 'no-store');
    const dest = safePanelReturnTo(req.query.returnTo) || '/hebergement/dashboard';
    const oauthError = String(req.query.oauth_error || '').trim();
    const user = req.session?.user;
    if (!user || user.isGuest) {
        return res.redirect(panelLoginRedirect(dest, oauthError || undefined));
    }
    try {
        await attachPanelFromSiteUser(res, user, { required: true });
        return res.redirect(dest);
    } catch (err) {
        const code = err.code === 'NO_OAUTH' ? 'no_oauth' : 'panel_bridge';
        return res.redirect(panelLoginRedirect(dest, oauthError || code));
    }
});

app.get('/api/me', async (req, res) => {
    if (!req.session.user) return res.json({ authenticated: false, ...oauthStatus() });
    await resolveAdminAccessForSessionUser(req.session.user);
    const syncedUser = await syncSessionUserWithDb(req.session.user);
    
    if (kronesApi && syncedUser && !syncedUser.isGuest) {
        void kronesApi.claimJoinBonus(syncedUser.id).catch(() => undefined);
    }
    const db = await readUsersDb();
    const fullUser = db.users[syncedUser.id];
    if (fullUser) await overlayWalletOnUser(fullUser);
    await overlayWalletOnUser(syncedUser);
    const out = fullUser || syncedUser;
    const discordId = /^\d{15,22}$/.test(String(out.id || ''))
        ? String(out.id)
        : String(out.providers?.discord || '');
    return res.json({
        authenticated: true,
        ...oauthStatus(),
        user: { ...out, discordId: discordId || null }
    });
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
    
    if (payload.name !== undefined) existing.name = String(payload.name).trim().slice(0, 40) || existing.username;
    if (payload.subtitle !== undefined) existing.subtitle = String(payload.subtitle).slice(0, 160);
    if (payload.banner !== undefined) {
        const nextBanner = String(payload.banner || '').trim();
        if (nextBanner && !isCustomBanner(nextBanner) && !/^https?:\/\//i.test(nextBanner)) {
            return res.status(400).json({ ok: false, message: 'Bannière invalide.' });
        }
        existing.banner = nextBanner;
        existing.bannerCustom = isCustomBanner(nextBanner);
    }
    if (payload.privacy !== undefined) existing.privacy = String(payload.privacy);
    if (Array.isArray(payload.unlockedPrivacies)) existing.unlockedPrivacies = payload.unlockedPrivacies;
    if (Array.isArray(payload.links)) existing.links = payload.links;
    if (typeof payload.customTheme === 'object') existing.customTheme = payload.customTheme;
    if (payload.extraLinkSlots !== undefined) existing.extraLinkSlots = Number(payload.extraLinkSlots);
    if (payload.hasCustomization !== undefined) existing.hasCustomization = Boolean(payload.hasCustomization);
    if (payload.autoRenewFeatured !== undefined) existing.autoRenewFeatured = Boolean(payload.autoRenewFeatured);
    if (Array.isArray(payload.likedProfiles)) existing.likedProfiles = payload.likedProfiles;
    if (typeof payload.stats === 'object') existing.stats = payload.stats;
    existing.updatedAt = Date.now();
    db.users[sessionUser.id] = existing;
    await writeUsersDb(db);
    return res.json({ ok: true, user: existing });
});

app.post('/api/me/banner', async (req, res) => {
    const sessionUser = req.session?.user;
    if (!sessionUser || sessionUser.isGuest) return res.status(401).json({ ok: false, message: 'Non authentifié' });
    const db = await readUsersDb();
    const existing = normalizeStoredUser(db.users[sessionUser.id], sessionUser.id);
    if (!existing) return res.status(404).json({ ok: false, message: 'Utilisateur introuvable' });

    if (req.body?.clear) {
        await removeOldMeBanners(sessionUser.id);
        existing.banner = '';
        existing.bannerCustom = false;
        existing.updatedAt = Date.now();
        db.users[sessionUser.id] = existing;
        await writeUsersDb(db);
        return res.json({ ok: true, banner: '', user: existing });
    }

    const raw = String(req.body?.image || '');
    const match = raw.match(/^data:(image\/(?:jpeg|png|webp|gif));base64,([A-Za-z0-9+/=\s]+)$/i);
    if (!match) return res.status(400).json({ ok: false, message: 'Choisissez une image JPEG, PNG, WebP ou GIF.' });
    const declared = BANNER_TYPES[match[1].toLowerCase()];
    if (!declared) return res.status(400).json({ ok: false, message: 'Format d’image non pris en charge.' });
    let buf;
    try {
        buf = Buffer.from(match[2].replace(/\s+/g, ''), 'base64');
    } catch {
        return res.status(400).json({ ok: false, message: 'Image illisible.' });
    }
    if (!buf.length) return res.status(400).json({ ok: false, message: 'Image vide.' });
    if (buf.length > BANNER_MAX_BYTES) return res.status(413).json({ ok: false, message: 'Image trop lourde (3 Mo max).' });
    const ext = bannerExtFromBuffer(buf);
    if (!ext) return res.status(400).json({ ok: false, message: 'Le fichier n’est pas une image valide.' });

    const safeId = String(sessionUser.id).replace(/[^a-zA-Z0-9_-]/g, '') || 'user';
    await fs.mkdir(ME_UPLOADS_DIR, { recursive: true });
    await removeOldMeBanners(safeId);
    const filename = `${safeId}-${Date.now().toString(36)}.${ext}`;
    await fs.writeFile(path.join(ME_UPLOADS_DIR, filename), buf);
    existing.banner = `/me-media/${filename}`;
    existing.bannerCustom = true;
    existing.updatedAt = Date.now();
    db.users[sessionUser.id] = existing;
    await writeUsersDb(db);
    return res.json({ ok: true, banner: existing.banner, user: existing });
});

app.get('/api/profiles', async (req, res) => {
    const db = await readUsersDb();
    const profiles = Object.values(db.users)
        .map(u => normalizeStoredUser(u, u.id))
        .filter(u => u && u.privacy === 'public'); 
    return res.json({ ok: true, profiles });
});

app.get('/logout', (req, res) => {
    const dest = safeReturnTo(req.query.returnTo) || '/';
    res.clearCookie('synkrone_session', { path: '/' });
    req.session.destroy(() => res.redirect(dest));
});

// --- CLOUD ---
registerCloudRoutes(app, { readCloudDb, writeCloudDb, isManualStaffRole });
registerMeRoutes(app, { readUsersDb, writeUsersDb, isManualStaffRole, krones: kronesApi });
registerPublicbotRoutes(app, { readUsersDb, writeUsersDb, isManualStaffRole, krones: kronesApi });
registerBumpRoutes(app, { readUsersDb, writeUsersDb, isManualStaffRole });
registerAnnouncementRoutes(app, { resolveAdminAccessForSessionUser });
mountTemoignages(app, { resolveAdminAccessForSessionUser });

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
        if (req.body?.publishQuote) {
            await addOptInQuote({
                authorId: sessionUser.id,
                displayName: safeUsername,
                quote: rawMessage
            }).catch(() => undefined);
        }
        return res.json({ ok: true, message: 'Demande envoyée.' });
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
    if (!sessionUser || sessionUser.isGuest) return res.status(401).json({ ok: false, message: 'Connectez-vous pour jouer à la roulette.' });
    
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
    let nextKrone = Math.max(0, Number(existing?.krone || 0) + Number(prize.amount || 0));
    if (kronesApi) {
        const credited = await kronesApi.creditAccount(userId, Number(prize.amount || 0), 'roulette');
        if (credited.ok) nextKrone = credited.wallet.balance;
    }
    
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
    if (kronesApi) {
        const spent = await kronesApi.debitAccount(userId, requiredKrone, `grade:${targetGrade}`);
        if (!spent.ok) return res.status(409).json({ ok: false, message: spent.error || 'Solde insuffisant.' });
        await kronesApi.setAccountPlan(userId, targetGrade);
        const nextUser = { ...existing, grade: targetGrade, krone: spent.wallet.balance, updatedAt: Date.now(), lastSeenAt: Date.now() };
        db.users[userId] = nextUser;
        await writeUsersDb(db);
        sessionUser.grade = nextUser.grade; sessionUser.krone = nextUser.krone;
        return res.json({ ok: true, message: 'Achat valide.', user: toAdminUserDto(nextUser) });
    }
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
    writeUsersDb,
    krones: kronesApi
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

app.get('/api/admin/pm2/servers/:id/logs', async (req, res) => {
    const hasAccess = await resolveAdminAccessForSessionUser(req.session?.user);
    if (!hasAccess) return res.status(403).json({ error: 'Acces refuse.' });
    try {
        const logs = await pm2Logs(req.params.id, req.query.lines);
        const text = [logs.out, logs.err ? `--- stderr ---\n${logs.err}` : ''].filter(Boolean).join('\n');
        return res.type('text/plain').send(text);
    } catch (error) {
        return res.status(error.status || 500).json({ error: error.message || 'Logs indisponibles.' });
    }
});

app.post('/api/admin/pm2/servers/:id/logs/clear', async (req, res) => {
    const hasAccess = await resolveAdminAccessForSessionUser(req.session?.user);
    if (!hasAccess) return res.status(403).json({ error: 'Acces refuse.' });
    try {
        const { stdout } = await execFileAsync('pm2', ['jlist'], { maxBuffer: 2 * 1024 * 1024 });
        const processes = JSON.parse(stdout);
        const row = processes.find((p) => String(p.pm_id) === String(req.params.id));
        if (!row) return res.status(404).json({ error: 'Processus introuvable.' });
        const fsSync = require('node:fs');
        for (const file of [row.pm2_env?.pm_out_log_path, row.pm2_env?.pm_err_log_path]) {
            if (file) fsSync.writeFileSync(file, '');
        }
        return res.json({ ok: true });
    } catch (error) {
        return res.status(500).json({ error: 'Impossible de vider les logs.' });
    }
});

app.get('/api/admin/platform', async (req, res) => {
    const hasAccess = await resolveAdminAccessForSessionUser(req.session?.user);
    if (!hasAccess) return res.status(403).json({ error: 'Acces refuse.' });
    return res.json(await readPlatform());
});

app.patch('/api/admin/platform', async (req, res) => {
    const hasAccess = await resolveAdminAccessForSessionUser(req.session?.user);
    if (!hasAccess) return res.status(403).json({ error: 'Acces refuse.' });
    return res.json(await writePlatform(req.body || {}));
});

app.get('/api/admin/hosting/services', async (req, res) => {
    const hasAccess = await resolveAdminAccessForSessionUser(req.session?.user);
    if (!hasAccess) return res.status(403).json({ error: 'Acces refuse.' });
    try {
        return res.json(await panelAdmin('/services'));
    } catch (error) {
        return res.status(error.status || 500).json({ error: error.message || 'Services indisponibles.' });
    }
});

app.post('/api/admin/hosting/services/:id/:action', async (req, res) => {
    const hasAccess = await resolveAdminAccessForSessionUser(req.session?.user);
    if (!hasAccess) return res.status(403).json({ error: 'Acces refuse.' });
    const action = String(req.params.action || '').trim();
    if (!['start', 'stop', 'restart', 'kill', 'file', 'recreate'].includes(action)) {
        return res.status(400).json({ error: 'Action inconnue.' });
    }
    try {
        return res.json(await panelAdmin(`/services/${encodeURIComponent(req.params.id)}/${action}`, {
            method: 'POST',
            headers: { 'content-type': 'application/json' },
            body: JSON.stringify(req.body || {})
        }));
    } catch (error) {
        return res.status(error.status || 500).json({ error: error.message || 'Action impossible.' });
    }
});

app.get('/api/admin/hosting/services/:id/files', async (req, res) => {
    const hasAccess = await resolveAdminAccessForSessionUser(req.session?.user);
    if (!hasAccess) return res.status(403).json({ error: 'Acces refuse.' });
    try {
        const q = new URLSearchParams();
        if (req.query.path) q.set('path', String(req.query.path));
        return res.json(await panelAdmin(`/services/${encodeURIComponent(req.params.id)}/files?${q}`));
    } catch (error) {
        return res.status(error.status || 500).json({ error: error.message || 'Fichiers indisponibles.' });
    }
});

app.get('/api/admin/hosting/services/:id/file', async (req, res) => {
    const hasAccess = await resolveAdminAccessForSessionUser(req.session?.user);
    if (!hasAccess) return res.status(403).json({ error: 'Acces refuse.' });
    try {
        const q = new URLSearchParams();
        if (req.query.path) q.set('path', String(req.query.path));
        return res.json(await panelAdmin(`/services/${encodeURIComponent(req.params.id)}/file?${q}`));
    } catch (error) {
        return res.status(error.status || 500).json({ error: error.message || 'Lecture impossible.' });
    }
});

app.get('/api/admin/tickets', async (req, res) => {
    const hasAccess = await resolveAdminAccessForSessionUser(req.session?.user);
    if (!hasAccess) return res.status(403).json({ error: 'Acces refuse.' });
    try {
        return res.json(await listTickets());
    } catch (error) {
        return res.status(error.status || 500).json({ error: error.message || 'Tickets indisponibles.' });
    }
});

// -- ROUTES IFRAMES --
app.get(/^\/discord\/bots\/(discord|asuna|vax|yui|kayaba|arceus|bot)\.html$/i, (req, res) => res.sendFile(path.join(__dirname, 'public', 'discord', 'bots', `${String(req.params[0]).toLowerCase()}.html`)));
app.get(/^\/minecraft\/modpack\/(accueil|xenus|thefrenchbaguette|vanipack)\.html$/i, (req, res) => res.sendFile(path.join(__dirname, 'public', 'minecraft', 'modpack', `${String(req.params[0]).toLowerCase()}.html`)));
app.get('/discord/publicbot/index.html', (req, res) => res.sendFile(path.join(__dirname, 'public', 'discord', 'publicbot', 'index.html')));
app.get(/^\/equipe\/(espace-travail|cloud)\/index\.html$/i, (req, res) => {
    const page = String(req.params[0] || '').toLowerCase();
    res.sendFile(path.join(__dirname, 'public', 'equipe', page, 'index.html'));
});
app.get(/^\/admin\/(utilisateur|annonce|pm2|plateforme|services|tickets)\/index\.html$/i, async (req, res) => {
    const hasAccess = await resolveAdminAccessForSessionUser(req.session?.user);
    if (!hasAccess) return res.status(403).send('Acces refuse');
    res.sendFile(path.join(__dirname, 'public', 'admin', String(req.params[0]).toLowerCase(), 'index.html'));
});

app.get('/robots.txt', (_req, res) => {
    res.type('text/plain');
    res.sendFile(path.join(__dirname, 'public', 'robots.txt'));
});
app.get('/sitemap.xml', (_req, res) => {
    res.type('application/xml');
    res.sendFile(path.join(__dirname, 'public', 'sitemap.xml'));
});

app.get(['/faq', '/faq/', '/krones', '/krones/', '/cgv', '/cgv/', '/stats', '/stats/', '/login', '/login/', '/compte', '/compte/', '/serveur', '/serveur/'], (req, res) => {
    return sendShell(res, req.path);
});

// -- ROUTES SHELL --
const SHELL_ROUTES = new Set(['/', '/accueil', '/login', '/discord', '/discord/bots', '/discord/publicbot', '/discord/dashbot', '/discord/commandes', '/discord/me', '/discord/bump', '/minecraft', '/minecraft/serveur', '/minecraft/modpack', '/admin', '/admin/utilisateur', '/admin/annonce', '/admin/pm2', '/admin/plateforme', '/admin/services', '/admin/tickets', '/equipe', '/equipe/espace-travail', '/equipe/cloud', '/cgu', '/cgv', '/contact', '/faq', '/krones', '/stats', '/compte', '/serveur']);
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
        if (!req.session?.user || req.session.user.isGuest) {
            return res.redirect(`/login?returnTo=${encodeURIComponent(normalizedPath)}`);
        }
        const hasAccess = await resolveAdminAccessForSessionUser(req.session.user);
        if (!hasAccess) return res.redirect('/accueil');
    }
    return sendShell(res, normalizedPath);
});

app.use(express.static(path.join(__dirname, 'public'), {
        etag: true,
        setHeaders(res, filePath) {
            if (String(filePath).endsWith('.html')) res.setHeader('Cache-Control', 'no-store');
            else res.setHeader('Cache-Control', 'public, max-age=86400');
        }
    }));
app.get(/^(.*)$/, (req, res, next) => {
    if (isReservedPublicPath(req.path)) return next();
    return sendShell(res, req.path);
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