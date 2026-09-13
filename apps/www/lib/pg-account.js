'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs');
const fsp = require('node:fs/promises');
const path = require('node:path');
const { readPanelEnvValue } = require('./admin-ops');

const REPO_ROOT = path.join(__dirname, '..', '..');
const USERS_JSON = path.join(
    REPO_ROOT,
    'Synkrone',
    'test',
    'synkrone_authdiscord',
    'data',
    'users.json'
);
const KRONES_JSON = path.join(__dirname, '..', 'data', 'krones.json');
const IDENTITY_JSON = path.join(
    REPO_ROOT,
    'Synkrone',
    'test',
    'synkrone_authdiscord',
    'data',
    'identity-map.json'
);
const IMPORTED_MARK = path.join(__dirname, '..', 'data', '.pg-account-imported');

const GRADE_ORDER = ['Aucun', 'Kronium', 'Synkral', 'Kronalloy', 'Synkronite', 'Kronix'];
const LEDGER_CAP = 200;
const PROFILE_KEYS = [
    'customUrl',
    'name',
    'subtitle',
    'banner',
    'bannerCustom',
    'privacy',
    'unlockedPrivacies',
    'links',
    'customTheme',
    'extraLinkSlots',
    'hasCustomization',
    'featuredUntil',
    'autoRenewFeatured',
    'likedProfiles',
    'stats'
];

const SCHEMA_SQL = `
CREATE TABLE IF NOT EXISTS site_profiles (
  user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  public_id TEXT NOT NULL UNIQUE,
  role TEXT NOT NULL DEFAULT 'Krobi',
  is_team_owner BOOLEAN NOT NULL DEFAULT FALSE,
  last_seen_at TIMESTAMPTZ,
  last_login_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  profile JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS wallets (
  user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  balance INTEGER NOT NULL DEFAULT 0,
  plan TEXT NOT NULL DEFAULT 'Aucun',
  join_bonus_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS wallet_ledger (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  type TEXT NOT NULL,
  amount INTEGER NOT NULL,
  reason TEXT NOT NULL DEFAULT '',
  at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  balance_after INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS wallet_ledger_user_at_idx ON wallet_ledger (user_id, at DESC);
`;

let pool = null;
let ready = null;

function loadPg() {
    try {
        return require('pg');
    } catch {
        return require(path.join(
            REPO_ROOT,
            'dashboard',
            'Orbital-hebergeur',
            'node_modules',
            'pg'
        ));
    }
}

function databaseUrl() {
    return String(process.env.DATABASE_URL || readPanelEnvValue('DATABASE_URL') || '').trim();
}

function isConfigured() {
    return /^postgres(ql)?:\/\//i.test(databaseUrl());
}

function placeholderEmail(provider, providerId) {
    return `${provider}-${providerId}@oauth.synkrone.local`;
}

function isPlaceholderEmail(email) {
    return /@oauth\.synkrone\.local$/i.test(String(email || ''));
}

function ms(value) {
    if (!value) return 0;
    const t = value instanceof Date ? value.getTime() : Date.parse(String(value));
    return Number.isFinite(t) ? t : 0;
}

function toDate(msValue) {
    const n = Number(msValue);
    if (!Number.isFinite(n) || n <= 0) return null;
    return new Date(n);
}

function pickPlan(a, b) {
    const ia = GRADE_ORDER.indexOf(String(a || 'Aucun'));
    const ib = GRADE_ORDER.indexOf(String(b || 'Aucun'));
    return GRADE_ORDER[Math.max(ia, ib, 0)] || 'Aucun';
}

function mergeWalletState(a, b) {
    if (!a) return b || { balance: 0, plan: 'Aucun', ledger: [], joinBonusAt: null };
    if (!b) return a;
    const primary = Number(a.balance || 0) >= Number(b.balance || 0) ? a : b;
    const secondary = primary === a ? b : a;
    const seen = new Set((primary.ledger || []).map((row) => String(row.id || '')));
    const ledger = [...(primary.ledger || [])];
    for (const row of secondary.ledger || []) {
        const id = String(row?.id || '');
        if (id && seen.has(id)) continue;
        if (id) seen.add(id);
        ledger.push(row);
    }
    ledger.sort((x, y) => Number(y.at || 0) - Number(x.at || 0));
    return {
        balance: Math.max(0, Math.trunc(Number(primary.balance) || 0)),
        plan: pickPlan(a.plan, b.plan),
        ledger: ledger.slice(0, LEDGER_CAP),
        joinBonusAt: primary.joinBonusAt || secondary.joinBonusAt || null
    };
}

function profileFromUser(user) {
    const out = {};
    for (const key of PROFILE_KEYS) {
        if (user[key] !== undefined) out[key] = user[key];
    }
    return out;
}

function userFromRow(row, providers) {
    const profile = row.profile && typeof row.profile === 'object' ? row.profile : {};
    const publicId = String(row.public_id);
    const email = isPlaceholderEmail(row.email) ? String(profile.email || '') : String(row.email || '');
    return {
        id: publicId,
        dbId: String(row.user_id),
        username: String(row.name || `Utilisateur ${publicId.slice(-4)}`),
        avatar: String(row.avatar_url || '/assets/images/logo.jpg'),
        role: String(row.site_role || 'Krobi'),
        grade: GRADE_ORDER.includes(String(row.plan || '')) ? String(row.plan) : 'Aucun',
        krone: Math.max(0, Math.trunc(Number(row.balance) || 0)),
        isTeamOwner: Boolean(row.is_team_owner),
        isGuest: false,
        createdAt: ms(row.created_at),
        updatedAt: ms(row.updated_at),
        lastSeenAt: ms(row.last_seen_at),
        lastLoginAt: ms(row.last_login_at),
        email: email.trim().toLowerCase(),
        providers: providers || {},
        ...profile
    };
}

async function getPool() {
    if (pool) return pool;
    if (!isConfigured()) {
        const err = new Error('DATABASE_URL manquant.');
        err.code = 'NO_DATABASE';
        throw err;
    }
    const { Pool } = loadPg();
    pool = new Pool({
        connectionString: databaseUrl(),
        max: 8,
        idleTimeoutMillis: 10_000,
        connectionTimeoutMillis: 5_000
    });
    pool.on('error', (err) => {
        console.error('[account] postgres idle client:', err.message);
    });
    return pool;
}

async function withClient(fn) {
    const db = await getPool();
    const client = await db.connect();
    try {
        return await fn(client);
    } finally {
        client.release();
    }
}

async function ensureSchema(client) {
    await client.query(SCHEMA_SQL);
}

async function ensureReady() {
    if (ready) return ready;
    ready = (async () => {
        await withClient(async (client) => {
            await ensureSchema(client);
            await maybeImportJson(client);
        });
    })().catch((err) => {
        ready = null;
        throw err;
    });
    return ready;
}

async function findUserIdByOAuth(client, provider, providerId) {
    const id = String(providerId || '').trim();
    if (!provider || !id) return null;
    const found = await client.query(
        `SELECT user_id FROM oauth_accounts WHERE provider = $1 AND provider_account_id = $2 LIMIT 1`,
        [provider, id]
    );
    return found.rows[0]?.user_id || null;
}

async function findUserIdByPublicId(client, publicId) {
    const id = String(publicId || '').trim();
    if (!id) return null;
    const found = await client.query(
        `SELECT user_id FROM site_profiles WHERE public_id = $1 LIMIT 1`,
        [id]
    );
    return found.rows[0]?.user_id || null;
}

async function upsertOAuthUser(client, { provider, providerId, name, email, avatarUrl, admin }) {
    const existing = await findUserIdByOAuth(client, provider, providerId);
    const nowName = String(name || provider).slice(0, 120);
    const avatar = avatarUrl ? String(avatarUrl) : null;
    const realEmail = String(email || '').trim().toLowerCase();
    if (existing) {
        await client.query(
            `UPDATE users SET
                name = COALESCE(NULLIF($2, ''), name),
                avatar_url = COALESCE($3, avatar_url),
                email = CASE WHEN $4 <> '' AND email LIKE '%@oauth.synkrone.local' THEN $4 ELSE email END,
                role = CASE WHEN $5 THEN 'admin' ELSE role END
             WHERE id = $1`,
            [existing, nowName, avatar, realEmail, Boolean(admin)]
        );
        return existing;
    }
    const userId = crypto.randomUUID();
    await client.query(
        `INSERT INTO users (id, email, name, avatar_url, password_hash, role)
         VALUES ($1, $2, $3, $4, NULL, $5)`,
        [
            userId,
            realEmail || placeholderEmail(provider, providerId),
            nowName,
            avatar,
            admin ? 'admin' : 'user'
        ]
    );
    await client.query(
        `INSERT INTO oauth_accounts (
            id, user_id, provider, provider_account_id, provider_login, email, avatar_url, created_at, updated_at
         ) VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), NOW())`,
        [
            crypto.randomUUID(),
            userId,
            provider,
            String(providerId),
            nowName,
            realEmail || null,
            avatar
        ]
    );
    return userId;
}

function providersOf(user) {
    const providers = user?.providers && typeof user.providers === 'object' ? { ...user.providers } : {};
    const id = String(user?.id || '').trim();
    if (/^\d{15,22}$/.test(id) && !providers.discord) providers.discord = id;
    const prefixed = id.match(/^(discord|github|google):(.+)$/);
    if (prefixed && !providers[prefixed[1]]) providers[prefixed[1]] = prefixed[2];
    return providers;
}

function oauthProviderLinks(user) {
    const providers = providersOf(user);
    const links = [];
    if (providers.discord) links.push(['discord', String(providers.discord)]);
    if (providers.github) links.push(['github', String(providers.github)]);
    if (providers.google) links.push(['google', String(providers.google)]);
    return links;
}

async function linkOAuthAccount(client, userId, provider, providerId, meta = {}) {
    const id = String(providerId || '').trim();
    if (!provider || !id) return false;
    const taken = await findUserIdByOAuth(client, provider, id);
    if (taken && taken !== userId) return false;
    if (taken === userId) return true;
    const existing = await client.query(
        `SELECT id, provider_account_id FROM oauth_accounts WHERE user_id = $1 AND provider = $2 LIMIT 1`,
        [userId, provider]
    );
    if (existing.rows[0]) {
        if (existing.rows[0].provider_account_id !== id) {
            await client.query(
                `UPDATE oauth_accounts
                 SET provider_account_id = $2, provider_login = COALESCE($3, provider_login),
                     email = COALESCE($4, email), avatar_url = COALESCE($5, avatar_url), updated_at = NOW()
                 WHERE id = $1`,
                [
                    existing.rows[0].id,
                    id,
                    meta.name ? String(meta.name) : null,
                    meta.email ? String(meta.email) : null,
                    meta.avatarUrl || null
                ]
            );
        }
        return true;
    }
    await client.query(
        `INSERT INTO oauth_accounts (
            id, user_id, provider, provider_account_id, provider_login, email, avatar_url, created_at, updated_at
         ) VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), NOW())
         ON CONFLICT (provider, provider_account_id) DO NOTHING`,
        [
            crypto.randomUUID(),
            userId,
            provider,
            id,
            meta.name ? String(meta.name) : null,
            meta.email ? String(meta.email) : null,
            meta.avatarUrl || null
        ]
    );
    return true;
}

async function ensureUserFromSite(client, user) {
    const admin = Boolean(user.isTeamOwner) || String(user.role || '').toLowerCase() === 'admin';
    const order = oauthProviderLinks(user);
    let userId = null;
    if (user?.dbId) {
        const exists = await client.query(`SELECT id FROM users WHERE id = $1 LIMIT 1`, [user.dbId]);
        if (exists.rows[0]) userId = user.dbId;
    }
    if (!userId) {
        for (const [provider, providerId] of order) {
            userId = await upsertOAuthUser(client, {
                provider,
                providerId,
                name: user.username || user.name,
                email: user.email,
                avatarUrl: user.avatar,
                admin
            });
            break;
        }
    }
    if (!userId) userId = await findUserIdByPublicId(client, user.id);
    if (!userId && order.length) {
        userId = await findUserIdByOAuth(client, order[0][0], order[0][1]);
    }
    if (!userId) {
        const publicId = String(user.id || '').trim();
        const fakeProvider = /^\d{15,22}$/.test(publicId) ? 'discord' : 'google';
        const fakeId = /^\d{15,22}$/.test(publicId) ? publicId : `site-${publicId}`.slice(0, 80);
        userId = await upsertOAuthUser(client, {
            provider: fakeProvider,
            providerId: fakeId,
            name: user.username || user.name,
            email: user.email,
            avatarUrl: user.avatar,
            admin
        });
    }
    for (const [provider, providerId] of order) {
        await linkOAuthAccount(client, userId, provider, providerId, {
            name: user.username || user.name,
            email: user.email,
            avatarUrl: user.avatar
        });
    }
    return userId;
}

async function upsertSiteProfile(client, userId, user) {
    const publicId = String(user.id || '').trim();
    const profile = profileFromUser(user);
    await client.query(
        `INSERT INTO site_profiles (
            user_id, public_id, role, is_team_owner, last_seen_at, last_login_at, created_at, updated_at, profile
         ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
         ON CONFLICT (user_id) DO UPDATE SET
            public_id = EXCLUDED.public_id,
            role = EXCLUDED.role,
            is_team_owner = EXCLUDED.is_team_owner,
            last_seen_at = EXCLUDED.last_seen_at,
            last_login_at = EXCLUDED.last_login_at,
            updated_at = EXCLUDED.updated_at,
            profile = EXCLUDED.profile`,
        [
            userId,
            publicId,
            String(user.role || 'Krobi'),
            Boolean(user.isTeamOwner),
            toDate(user.lastSeenAt),
            toDate(user.lastLoginAt),
            toDate(user.createdAt) || new Date(),
            toDate(user.updatedAt) || new Date(),
            JSON.stringify(profile)
        ]
    );
}

async function ensureWalletRow(client, userId, seed = {}) {
    await client.query(
        `INSERT INTO wallets (user_id, balance, plan, join_bonus_at, updated_at)
         VALUES ($1, $2, $3, $4, NOW())
         ON CONFLICT (user_id) DO NOTHING`,
        [
            userId,
            Math.max(0, Math.trunc(Number(seed.balance) || 0)),
            GRADE_ORDER.includes(String(seed.plan || '')) ? String(seed.plan) : 'Aucun',
            seed.joinBonusAt ? new Date(seed.joinBonusAt) : null
        ]
    );
}

async function loadLedger(client, userId) {
    const rows = await client.query(
        `SELECT id, type, amount, reason, at, balance_after
         FROM wallet_ledger WHERE user_id = $1
         ORDER BY at DESC LIMIT $2`,
        [userId, LEDGER_CAP]
    );
    return rows.rows.map((row) => ({
        id: row.id,
        type: row.type,
        amount: Number(row.amount) || 0,
        reason: row.reason || '',
        at: ms(row.at),
        balanceAfter: Number(row.balance_after) || 0
    }));
}

async function trimLedger(client, userId) {
    await client.query(
        `DELETE FROM wallet_ledger
         WHERE user_id = $1 AND id NOT IN (
            SELECT id FROM wallet_ledger WHERE user_id = $1 ORDER BY at DESC LIMIT $2
         )`,
        [userId, LEDGER_CAP]
    );
}

async function resolveUserId(client, publicId) {
    const raw = String(publicId || '').trim();
    if (!raw || raw === 'demo' || raw === 'guest') return null;
    if (raw.startsWith('panel:')) {
        const id = raw.slice(6);
        const exists = await client.query(`SELECT id FROM users WHERE id = $1 LIMIT 1`, [id]);
        return exists.rows[0]?.id || null;
    }
    const byPublic = await findUserIdByPublicId(client, raw);
    if (byPublic) return byPublic;
    if (/^\d{15,22}$/.test(raw)) return findUserIdByOAuth(client, 'discord', raw);
    const prefixed = raw.match(/^(github|google|discord):(.+)$/);
    if (prefixed) return findUserIdByOAuth(client, prefixed[1], prefixed[2]);
    const asUuid = await client.query(`SELECT id FROM users WHERE id = $1 LIMIT 1`, [raw]);
    return asUuid.rows[0]?.id || null;
}

async function loadOauthMap(client) {
    const rows = await client.query(
        `SELECT user_id, provider, provider_account_id FROM oauth_accounts`
    );
    const map = {};
    for (const row of rows.rows) {
        const uid = row.user_id;
        if (!map[uid]) map[uid] = {};
        map[uid][row.provider] = row.provider_account_id;
    }
    return map;
}

async function loadSiteUsers() {
    await ensureReady();
    return withClient(async (client) => {
        const oauth = await loadOauthMap(client);
        const rows = await client.query(
            `SELECT
                u.id AS user_id,
                u.email,
                u.name,
                u.avatar_url,
                p.public_id,
                p.role AS site_role,
                p.is_team_owner,
                p.last_seen_at,
                p.last_login_at,
                p.created_at,
                p.updated_at,
                p.profile,
                w.balance,
                w.plan
             FROM site_profiles p
             JOIN users u ON u.id = p.user_id
             LEFT JOIN wallets w ON w.user_id = u.id`
        );
        const users = {};
        for (const row of rows.rows) {
            const user = userFromRow(row, oauth[row.user_id] || {});
            users[user.id] = user;
        }
        return { users };
    });
}

async function saveSiteUsers(usersMap) {
    await ensureReady();
    const entries = Object.values(usersMap || {}).filter((user) => user && user.id && !user.isGuest);
    return withClient(async (client) => {
        await client.query('BEGIN');
        try {
            for (const user of entries) {
                const userId = await ensureUserFromSite(client, user);
                user.dbId = userId;
                await upsertSiteProfile(client, userId, user);
                await ensureWalletRow(client, userId);
            }
            await client.query('COMMIT');
        } catch (err) {
            await client.query('ROLLBACK');
            throw err;
        }
    });
}

function walletDto(row, ledger, meta = {}) {
    const privilege = meta.privilege || null;
    const unlimited = privilege === 'admin';
    return {
        id: meta.publicId || row.user_id,
        dbId: row.user_id,
        balance: Math.max(0, Math.trunc(Number(row.balance) || 0)),
        plan: GRADE_ORDER.includes(String(row.plan || '')) ? String(row.plan) : 'Aucun',
        ledger,
        unlimited,
        privilege,
        linkedDiscord: Boolean(meta.discordId),
        shopUrl: '/krones',
        lowBalance: !unlimited && Math.max(0, Math.trunc(Number(row.balance) || 0)) < 300,
        authenticated: meta.authenticated !== false
    };
}

async function peekWallet(publicId, extra = {}) {
    await ensureReady();
    return withClient(async (client) => {
        const userId = await resolveUserId(client, publicId);
        if (!userId) return null;
        await ensureWalletRow(client, userId);
        const row = await client.query(`SELECT * FROM wallets WHERE user_id = $1 LIMIT 1`, [userId]);
        const ledger = await loadLedger(client, userId);
        const discord = await findDiscordId(client, userId);
        const profile = await client.query(
            `SELECT public_id, role, is_team_owner FROM site_profiles WHERE user_id = $1 LIMIT 1`,
            [userId]
        );
        const privilege = privilegeFromProfile(profile.rows[0], extra.privilege);
        if (privilege === 'dev') {
            const current = GRADE_ORDER.indexOf(String(row.rows[0].plan || 'Aucun'));
            const mid = GRADE_ORDER.indexOf('Synkral');
            if (current < mid) {
                await client.query(
                    `UPDATE wallets SET plan = $2, updated_at = NOW() WHERE user_id = $1`,
                    [userId, 'Synkral']
                );
                row.rows[0].plan = 'Synkral';
            }
        }
        return walletDto(row.rows[0], ledger, {
            publicId: profile.rows[0]?.public_id || publicId,
            discordId: discord,
            privilege,
            authenticated: true
        });
    });
}

function privilegeFromProfile(profile, fallback) {
    if (fallback) return fallback;
    if (!profile) return null;
    if (profile.is_team_owner) return 'admin';
    const role = String(profile.role || '')
        .trim()
        .toLowerCase()
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '');
    if (role === 'admin') return 'admin';
    if (['dev', 'equipe', 'equipes', 'staff'].includes(role)) return 'dev';
    return null;
}

async function findDiscordId(client, userId) {
    const row = await client.query(
        `SELECT provider_account_id FROM oauth_accounts
         WHERE user_id = $1 AND provider = 'discord' LIMIT 1`,
        [userId]
    );
    if (row.rows[0]?.provider_account_id) return row.rows[0].provider_account_id;
    const profile = await client.query(
        `SELECT public_id FROM site_profiles WHERE user_id = $1 LIMIT 1`,
        [userId]
    );
    const publicId = String(profile.rows[0]?.public_id || '').trim();
    if (!/^\d{15,22}$/.test(publicId)) return null;
    await linkOAuthAccount(client, userId, 'discord', publicId);
    return publicId;
}

async function mutateWallet(publicId, fn) {
    await ensureReady();
    return withClient(async (client) => {
        const userId = await resolveUserId(client, publicId);
        if (!userId) {
            return { ok: false, error: 'Compte introuvable.' };
        }
        await client.query('BEGIN');
        try {
            await ensureWalletRow(client, userId);
            const locked = await client.query(
                `SELECT * FROM wallets WHERE user_id = $1 FOR UPDATE`,
                [userId]
            );
            const wallet = locked.rows[0];
            const result = await fn(client, userId, wallet);
            await client.query('COMMIT');
            return result;
        } catch (err) {
            await client.query('ROLLBACK');
            throw err;
        }
    });
}

async function appendLedgerRow(client, userId, type, amount, reason, balanceAfter) {
    const id = `${Date.now()}-${crypto.randomBytes(4).toString('hex')}`;
    await client.query(
        `INSERT INTO wallet_ledger (id, user_id, type, amount, reason, at, balance_after)
         VALUES ($1, $2, $3, $4, $5, NOW(), $6)`,
        [id, userId, type, amount, String(reason || '').slice(0, 200), balanceAfter]
    );
    await trimLedger(client, userId);
}

async function creditAccount(publicId, amount, reason) {
    const parsed = Math.trunc(Number(amount));
    if (!Number.isFinite(parsed) || parsed <= 0) return { ok: false, error: 'Montant invalide.' };
    return mutateWallet(publicId, async (client, userId, wallet) => {
        const balance = Math.max(0, Math.trunc(Number(wallet.balance) || 0)) + parsed;
        await client.query(
            `UPDATE wallets SET balance = $2, updated_at = NOW() WHERE user_id = $1`,
            [userId, balance]
        );
        await appendLedgerRow(client, userId, 'credit', parsed, reason, balance);
        const dto = await peekAfter(client, userId, publicId);
        return { ok: true, wallet: dto };
    });
}

async function debitAccount(publicId, amount, reason, privilege) {
    const parsed = Math.trunc(Number(amount));
    if (!Number.isFinite(parsed) || parsed <= 0) return { ok: false, error: 'Montant invalide.' };
    return mutateWallet(publicId, async (client, userId, wallet) => {
        const profile = await client.query(
            `SELECT public_id, role, is_team_owner FROM site_profiles WHERE user_id = $1 LIMIT 1`,
            [userId]
        );
        const priv = privilege || privilegeFromProfile(profile.rows[0]);
        if (priv !== 'admin') {
            const balance = Math.max(0, Math.trunc(Number(wallet.balance) || 0));
            if (balance < parsed) {
                const dto = await peekAfter(client, userId, publicId, priv);
                return { ok: false, error: 'Solde insuffisant.', wallet: dto };
            }
            const next = balance - parsed;
            await client.query(
                `UPDATE wallets SET balance = $2, updated_at = NOW() WHERE user_id = $1`,
                [userId, next]
            );
            await appendLedgerRow(client, userId, 'debit', parsed, reason, next);
        }
        return { ok: true, wallet: await peekAfter(client, userId, publicId, priv) };
    });
}

async function setAccountBalance(publicId, balance, reason) {
    const parsed = Math.max(0, Math.trunc(Number(balance) || 0));
    return mutateWallet(publicId, async (client, userId, wallet) => {
        const current = Math.max(0, Math.trunc(Number(wallet.balance) || 0));
        const delta = parsed - current;
        await client.query(
            `UPDATE wallets SET balance = $2, updated_at = NOW() WHERE user_id = $1`,
            [userId, parsed]
        );
        if (delta !== 0) {
            await appendLedgerRow(
                client,
                userId,
                delta >= 0 ? 'credit' : 'debit',
                Math.abs(delta),
                reason || 'admin:set',
                parsed
            );
        }
        return { ok: true, wallet: await peekAfter(client, userId, publicId) };
    });
}

async function setAccountPlan(publicId, plan) {
    const next = GRADE_ORDER.includes(String(plan || '')) ? String(plan) : 'Aucun';
    return mutateWallet(publicId, async (client, userId) => {
        await client.query(
            `UPDATE wallets SET plan = $2, updated_at = NOW() WHERE user_id = $1`,
            [userId, next]
        );
        return { ok: true, wallet: await peekAfter(client, userId, publicId) };
    });
}

async function peekAfter(client, userId, publicId, privilege) {
    const row = await client.query(`SELECT * FROM wallets WHERE user_id = $1 LIMIT 1`, [userId]);
    const ledger = await loadLedger(client, userId);
    const discord = await findDiscordId(client, userId);
    const profile = await client.query(
        `SELECT public_id FROM site_profiles WHERE user_id = $1 LIMIT 1`,
        [userId]
    );
    return walletDto(row.rows[0], ledger, {
        publicId: profile.rows[0]?.public_id || publicId,
        discordId: discord,
        privilege,
        authenticated: true
    });
}

async function claimJoinBonus(publicId, isMember) {
    const account = String(publicId || '').trim();
    if (!/^\d{15,22}$/.test(account)) {
        return { ok: false, claimed: false, reason: 'invalid' };
    }
    return mutateWallet(account, async (client, userId, wallet) => {
        if (wallet.join_bonus_at) {
            return { ok: true, claimed: false, reason: 'already' };
        }
        if (!isMember) return { ok: false, claimed: false, reason: 'not-member' };
        const next = Math.max(0, Math.trunc(Number(wallet.balance) || 0)) + 100;
        await client.query(
            `UPDATE wallets SET balance = $2, join_bonus_at = NOW(), updated_at = NOW() WHERE user_id = $1`,
            [userId, next]
        );
        await appendLedgerRow(client, userId, 'credit', 100, 'discord:join', next);
        return {
            ok: true,
            claimed: true,
            amount: 100,
            wallet: await peekAfter(client, userId, account)
        };
    });
}

async function migrateWallet(fromId, toId) {
    const from = String(fromId || '').trim();
    const to = String(toId || '').trim();
    if (!from || !to || from === to) return;
    await ensureReady();
    return withClient(async (client) => {
        await client.query('BEGIN');
        try {
            const fromUser = await resolveUserId(client, from);
            let toUser = await resolveUserId(client, to);
            if (!fromUser) {
                await client.query('COMMIT');
                return;
            }
            if (!toUser) toUser = fromUser;
            if (fromUser === toUser) {
                await client.query(
                    `UPDATE site_profiles SET public_id = $2, updated_at = NOW() WHERE user_id = $1`,
                    [fromUser, to]
                );
                await client.query('COMMIT');
                return;
            }
            await ensureWalletRow(client, fromUser);
            await ensureWalletRow(client, toUser);
            const a = await client.query(`SELECT * FROM wallets WHERE user_id = $1 FOR UPDATE`, [fromUser]);
            const b = await client.query(`SELECT * FROM wallets WHERE user_id = $1 FOR UPDATE`, [toUser]);
            const fromLedger = await loadLedger(client, fromUser);
            const toLedger = await loadLedger(client, toUser);
            const merged = mergeWalletState(
                {
                    balance: a.rows[0].balance,
                    plan: a.rows[0].plan,
                    ledger: fromLedger,
                    joinBonusAt: a.rows[0].join_bonus_at
                },
                {
                    balance: b.rows[0].balance,
                    plan: b.rows[0].plan,
                    ledger: toLedger,
                    joinBonusAt: b.rows[0].join_bonus_at
                }
            );
            await client.query(
                `UPDATE wallets SET balance = $2, plan = $3, join_bonus_at = $4, updated_at = NOW() WHERE user_id = $1`,
                [toUser, merged.balance, merged.plan, merged.joinBonusAt]
            );
            await client.query(`DELETE FROM wallets WHERE user_id = $1`, [fromUser]);
            await client.query(
                `UPDATE site_profiles SET public_id = $2, updated_at = NOW() WHERE user_id = $1`,
                [toUser, to]
            );
            await client.query('COMMIT');
        } catch (err) {
            await client.query('ROLLBACK');
            throw err;
        }
    });
}

async function snapshotWallets() {
    await ensureReady();
    return withClient(async (client) => {
        const rows = await client.query(
            `SELECT w.*, p.public_id
             FROM wallets w
             LEFT JOIN site_profiles p ON p.user_id = w.user_id`
        );
        const out = {};
        for (const row of rows.rows) {
            const ledger = await loadLedger(client, row.user_id);
            const key = row.public_id || row.user_id;
            out[key] = walletDto(row, ledger, { publicId: key, authenticated: true });
        }
        return out;
    });
}

async function readJson(file, fallback) {
    try {
        return JSON.parse(await fsp.readFile(file, 'utf8'));
    } catch {
        return fallback;
    }
}

async function maybeImportJson(client) {
    if (fs.existsSync(IMPORTED_MARK)) return;
    const existing = await client.query(`SELECT 1 FROM site_profiles LIMIT 1`);
    const walletsExisting = await client.query(`SELECT 1 FROM wallets LIMIT 1`);
    if (existing.rows.length && walletsExisting.rows.length) {
        await fsp.mkdir(path.dirname(IMPORTED_MARK), { recursive: true });
        await fsp.writeFile(IMPORTED_MARK, `${Date.now()}\n`, 'utf8');
        return;
    }
    const usersFile = await readJson(USERS_JSON, { users: {} });
    const kronesFile = await readJson(KRONES_JSON, { wallets: {}, joinBonus: {} });
    const identity = await readJson(IDENTITY_JSON, { bySiteId: {}, byPanelId: {}, byDiscordId: {} });
    const users = usersFile.users && typeof usersFile.users === 'object' ? usersFile.users : {};
    const imported = await importLegacy(client, {
        users,
        wallets: kronesFile.wallets && typeof kronesFile.wallets === 'object' ? kronesFile.wallets : {},
        joinBonus: kronesFile.joinBonus && typeof kronesFile.joinBonus === 'object' ? kronesFile.joinBonus : {},
        identity
    });
    await fsp.mkdir(path.dirname(IMPORTED_MARK), { recursive: true });
    await fsp.writeFile(IMPORTED_MARK, `${JSON.stringify({ at: Date.now(), ...imported })}\n`, 'utf8');
    console.log(`[account] import JSON → postgres: ${imported.users} comptes, ${imported.wallets} portefeuilles`);
}

function resolveLegacyWalletOwner(key, users, identity, created) {
    if (!key || key === 'demo') return null;
    if (key.startsWith('panel:')) return key.slice(6);
    if (identity.byDiscordId?.[key]?.panelUserId) return identity.byDiscordId[key].panelUserId;
    if (identity.bySiteId?.[key]?.panelUserId) return identity.bySiteId[key].panelUserId;
    if (created[key]) return created[key];
    const user = users[key];
    if (user?.providers?.discord && created[user.providers.discord]) {
        return created[user.providers.discord];
    }
    return created[key] || null;
}

async function importLegacy(client, { users, wallets, joinBonus, identity }) {
    const created = {};
    let userCount = 0;
    await client.query('BEGIN');
    try {
        for (const user of Object.values(users || {})) {
            if (!user || !user.id || user.isGuest) continue;
            const userId = await ensureUserFromSite(client, user);
            created[String(user.id)] = userId;
            if (user.providers?.discord) created[String(user.providers.discord)] = userId;
            await upsertSiteProfile(client, userId, user);
            userCount += 1;
        }
        const grouped = new Map();
        for (const [key, raw] of Object.entries(wallets || {})) {
            let userId = resolveLegacyWalletOwner(key, users, identity, created);
            if (!userId && /^\d{15,22}$/.test(key)) {
                userId = await upsertOAuthUser(client, {
                    provider: 'discord',
                    providerId: key,
                    name: users[key]?.username || `Utilisateur ${key.slice(-4)}`,
                    email: users[key]?.email,
                    avatarUrl: users[key]?.avatar
                });
                created[key] = userId;
            }
            if (!userId) continue;
            const joinAt = joinBonus[key] ? Number(joinBonus[key]) : null;
            const next = {
                balance: Math.max(0, Math.trunc(Number(raw?.balance) || 0)),
                plan: GRADE_ORDER.includes(String(raw?.plan || '')) ? String(raw.plan) : 'Aucun',
                ledger: Array.isArray(raw?.ledger) ? raw.ledger : [],
                joinBonusAt: Number.isFinite(joinAt) && joinAt > 0 ? joinAt : null
            };
            grouped.set(userId, mergeWalletState(grouped.get(userId), next));
        }
        for (const [userId, wallet] of grouped.entries()) {
            await client.query(
                `INSERT INTO wallets (user_id, balance, plan, join_bonus_at, updated_at)
                 VALUES ($1, $2, $3, $4, NOW())
                 ON CONFLICT (user_id) DO UPDATE SET
                    balance = GREATEST(wallets.balance, EXCLUDED.balance),
                    plan = EXCLUDED.plan,
                    join_bonus_at = COALESCE(wallets.join_bonus_at, EXCLUDED.join_bonus_at),
                    updated_at = NOW()`,
                [
                    userId,
                    wallet.balance,
                    wallet.plan,
                    wallet.joinBonusAt ? new Date(wallet.joinBonusAt) : null
                ]
            );
            for (const entry of (wallet.ledger || []).slice(0, LEDGER_CAP)) {
                const id = String(entry.id || `${Date.now()}-${crypto.randomBytes(3).toString('hex')}`);
                await client.query(
                    `INSERT INTO wallet_ledger (id, user_id, type, amount, reason, at, balance_after)
                     VALUES ($1, $2, $3, $4, $5, $6, $7)
                     ON CONFLICT (id) DO NOTHING`,
                    [
                        id,
                        userId,
                        entry.type === 'debit' ? 'debit' : 'credit',
                        Math.max(0, Math.trunc(Number(entry.amount) || 0)),
                        String(entry.reason || '').slice(0, 200),
                        toDate(entry.at) || new Date(),
                        Math.max(0, Math.trunc(Number(entry.balanceAfter) || 0))
                    ]
                );
            }
        }
        await client.query('COMMIT');
        return { users: userCount, wallets: grouped.size };
    } catch (err) {
        await client.query('ROLLBACK');
        throw err;
    }
}

async function countSiteAccounts() {
    if (!isConfigured()) return 0;
    try {
        await ensureReady();
        return withClient(async (client) => {
            let profiles = 0;
            let users = 0;
            try {
                const row = await client.query('SELECT COUNT(*)::int AS n FROM site_profiles');
                profiles = Number(row.rows[0]?.n) || 0;
            } catch {
                profiles = 0;
            }
            try {
                const row = await client.query('SELECT COUNT(*)::int AS n FROM users');
                users = Number(row.rows[0]?.n) || 0;
            } catch {
                users = 0;
            }
            return Math.max(profiles, users);
        });
    } catch {
        return 0;
    }
}

function hostingFromServiceRows(rows) {
    const hosting = { discord: 0, minecraft: 0, web: 0, total: 0, running: 0 };
    for (const row of rows || []) {
        const n = Number(row.n) || 0;
        hosting.total += n;
        if (row.type === 'discord' || row.type === 'minecraft' || row.type === 'web') {
            hosting[row.type] += n;
        }
        if (String(row.state || '') === 'RUNNING') hosting.running += n;
    }
    return hosting;
}

async function countHostingServices() {
    if (!isConfigured()) return null;
    try {
        await ensureReady();
        return withClient(async (client) => {
            const rows = await client.query(
                `SELECT type, state, COUNT(*)::int AS n FROM services GROUP BY type, state`
            );
            return hostingFromServiceRows(rows.rows);
        });
    } catch {
        return null;
    }
}

module.exports = {
    isConfigured,
    databaseUrl,
    ensureReady,
    loadSiteUsers,
    saveSiteUsers,
    peekWallet,
    creditAccount,
    debitAccount,
    setAccountBalance,
    setAccountPlan,
    claimJoinBonus,
    migrateWallet,
    snapshotWallets,
    mergeWalletState,
    pickPlan,
    oauthProviderLinks,
    SCHEMA_SQL,
    GRADE_ORDER,
    countSiteAccounts,
    countHostingServices,
    hostingFromServiceRows
};
