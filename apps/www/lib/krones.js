'use strict';

const fs = require('node:fs/promises');
const path = require('node:path');
const { applyHostingDiscount, readPlatform } = require('./platform');

const DATA_PATH = path.join(__dirname, '..', 'data', 'krones.json');
const LOCK_PATH = `${DATA_PATH}.lock`;
const USERS_DB_PATH = path.join(
    __dirname,
    '..',
    '..',
    '..',
    'Synkrone',
    'test',
    'synkrone_authdiscord',
    'data',
    'users.json'
);

const DEMO_ACCOUNT_ID = 'demo';
const DEMO_BALANCE = 2000;
const LEDGER_CAP = 200;
const LOCK_STALE_MS = 15000;
const LOCK_WAIT_MS = 10000;
const GRADE_ORDER = ['Aucun', 'Kronium', 'Synkral', 'Kronalloy', 'Synkronite', 'Kronix'];
const DEV_PLAN = 'Synkral';
const LOW_BALANCE = 300;
const KRONES_PER_EURO = 150;
const JOIN_BONUS = 100;
const JOIN_BONUS_REASON = 'discord:join';
const VAT_RATE = 0.2;

const DEFAULT_PACKS = [
    { id: 'pack-s', label: 'Pack S', krones: 600, eurCents: 400 },
    { id: 'pack-m', label: 'Pack M', krones: 1250, eurCents: 800 },
    { id: 'pack-l', label: 'Pack L', krones: 2600, eurCents: 1600 },
    { id: 'pack-xl', label: 'Pack XL', krones: 4000, eurCents: 2500 },
    { id: 'pack-xxl', label: 'Pack XXL', krones: 5500, eurCents: 3500 }
];

const GRADE_META = {
    Kronium: {
        id: 'kronium',
        name: 'Kronium',
        krones: 150,
        period: 'unique',
        tagline: 'Soutien',
        discount: '0,5 %',
        discord: 'Soutien',
        highlights: [
            'Réduction de 0,5 % sur l’hébergement et la boutique',
            'Rôle Discord Soutien',
            'Salons dédiés',
            'Giveaways'
        ]
    },
    Synkral: {
        id: 'synkral',
        name: 'Synkral',
        krones: 750,
        period: 'unique',
        tagline: 'Communauté',
        discount: '3 %',
        discord: 'Soutien',
        highlights: [
            'Réduction de 3 %',
            'Tout Kronium',
            'Rôle Discord visible / remerciements'
        ]
    },
    Kronalloy: {
        id: 'kronalloy',
        name: 'Kronalloy',
        krones: 1500,
        period: 'unique',
        tagline: 'Équilibre',
        discount: '7 %',
        discord: 'VIP',
        highlights: [
            'Réduction de 7 %',
            'Tout Synkral',
            'Rôle Discord VIP',
            'Kits Minecraft',
            'Avantages Me et Bump',
            'Options Dashbot'
        ]
    },
    Synkronite: {
        id: 'synkronite',
        name: 'Synkronite',
        krones: 3000,
        period: 'unique',
        tagline: 'Prioritaire',
        discount: '15 %',
        discord: 'VIP',
        highlights: [
            'Réduction de 15 %',
            'Tout Kronalloy',
            'Support prioritaire'
        ]
    },
    Kronix: {
        id: 'kronix',
        name: 'Kronix',
        krones: 6000,
        period: 'unique',
        tagline: 'Complet',
        discount: '30 %',
        discord: 'Premium',
        highlights: [
            'Réduction de 30 %',
            'Tout Synkronite',
            'Rôle Discord Premium',
            'Tous les avantages de la grille'
        ]
    }
};

const DEFAULT_SUBSCRIPTIONS = GRADE_ORDER.filter((name) => name !== 'Aucun').map((name) => {
    const meta = GRADE_META[name];
    return {
        ...meta,
        perk: meta.highlights.join(' · ')
    };
});

const COMPARE_ROWS = [
    { id: 'price', label: 'Prix (achat unique)', kind: 'krones' },
    { id: 'price_eur', label: 'Équivalent euros TTC', kind: 'eur' },
    { id: 'discount', label: 'Réduction hébergement et boutique', kind: 'text', values: {
        Kronium: '0,5 %', Synkral: '3 %', Kronalloy: '7 %', Synkronite: '15 %', Kronix: '30 %'
    } },
    { id: 'previous', label: 'Inclut le rang inférieur', kind: 'from', from: 'Synkral' },
    { id: 'discord_support', label: 'Discord — salons soutien et giveaways', kind: 'from', from: 'Kronium' },
    { id: 'discord_thanks', label: 'Discord — rôle visible / remerciements', kind: 'from', from: 'Synkral' },
    { id: 'discord_vip', label: 'Discord — rôle VIP', kind: 'from', from: 'Kronalloy' },
    { id: 'discord_premium', label: 'Discord — rôle Premium', kind: 'from', from: 'Kronix' },
    { id: 'mc_kits', label: 'Kits Minecraft', kind: 'from', from: 'Kronalloy' },
    { id: 'me_bump', label: 'Avantages profil Me et listing Bump', kind: 'from', from: 'Kronalloy' },
    { id: 'dashbot', label: 'Options Dashbot', kind: 'from', from: 'Kronalloy' },
    { id: 'priority', label: 'Support prioritaire', kind: 'from', from: 'Synkronite' }
];

function gradeUnlocked(plan, from) {
    return GRADE_ORDER.indexOf(plan) >= GRADE_ORDER.indexOf(from);
}

function compareCell(row, plan) {
    if (row.kind === 'krones') {
        return { type: 'text', value: GRADE_META[plan]?.krones ?? 0 };
    }
    if (row.kind === 'eur') {
        const krones = GRADE_META[plan]?.krones ?? 0;
        return { type: 'text', value: Math.round((krones / KRONES_PER_EURO) * 100) };
    }
    if (row.kind === 'text') {
        return { type: 'text', value: row.values?.[plan] || '—' };
    }
    if (row.kind === 'from') {
        const yes = gradeUnlocked(plan, row.from);
        return { type: 'bool', value: yes, label: yes ? 'Oui' : '—' };
    }
    return { type: 'text', value: '—' };
}

const MC_COEFF = {
    unit: 'Krônes/mois',
    base: 80,
    ramGb: 40,
    cpu: 25,
    storagePer10Gb: 15,
    db: 60,
    formula: '80 + ramGb*40 + cpu*25 + Math.ceil(storageGb/10)*15 + (db?60:0)'
};

const DISCORD_COEFF = { unit: 'Krônes/mois', base: 40, ramGb: 20, cpu: 15, storagePer10Gb: 8 };
const WEB_COEFF = { unit: 'Krônes/mois', base: 50, ramGb: 25, cpu: 20, storagePer10Gb: 10 };

let writeChain = Promise.resolve();

function withProcessLock(fn) {
    const run = writeChain.then(fn, fn);
    writeChain = run.then(() => undefined, () => undefined);
    return run;
}

function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
}

async function acquireFileLock() {
    const started = Date.now();
    while (true) {
        try {
            const handle = await fs.open(LOCK_PATH, 'wx');
            await handle.writeFile(JSON.stringify({ pid: process.pid, at: Date.now() }));
            return handle;
        } catch (err) {
            if (err.code !== 'EEXIST') throw err;
            try {
                const raw = await fs.readFile(LOCK_PATH, 'utf8');
                const meta = JSON.parse(raw);
                if (Date.now() - Number(meta.at || 0) > LOCK_STALE_MS) {
                    await fs.unlink(LOCK_PATH).catch(() => undefined);
                    continue;
                }
            } catch {
                await fs.unlink(LOCK_PATH).catch(() => undefined);
                continue;
            }
            if (Date.now() - started > LOCK_WAIT_MS) {
                throw new Error('Krônes: verrou indisponible.');
            }
            await sleep(25);
        }
    }
}

async function withFileLock(fn) {
    return withProcessLock(async () => {
        const handle = await acquireFileLock();
        try {
            return await fn();
        } finally {
            await handle.close().catch(() => undefined);
            await fs.unlink(LOCK_PATH).catch(() => undefined);
        }
    });
}

function asInt(value, fallback = 0) {
    const n = Number(value);
    if (!Number.isFinite(n)) return fallback;
    return Math.trunc(n);
}

function computeMcMonthly({ ramGb = 0, cpu = 0, storageGb = 0, db = false, discounts } = {}) {
    const ram = Math.max(0, Number(ramGb) || 0);
    const cpuN = Math.max(0, Number(cpu) || 0);
    const storage = Math.max(0, Number(storageGb) || 0);
    const hasDb = db === true || db === 1 || db === '1' || String(db).toLowerCase() === 'true';
    const parts = {
        base: MC_COEFF.base,
        ram: ram * MC_COEFF.ramGb,
        cpu: cpuN * MC_COEFF.cpu,
        storage: Math.ceil(storage / 10) * MC_COEFF.storagePer10Gb,
        db: hasDb ? MC_COEFF.db : 0
    };
    return applyHostingDiscount(parts, 'minecraft', discounts);
}

function defaultStore() {
    return {
        wallets: {
            [DEMO_ACCOUNT_ID]: {
                balance: DEMO_BALANCE,
                plan: 'Aucun',
                ledger: []
            }
        },
        packs: DEFAULT_PACKS,
        subscriptions: DEFAULT_SUBSCRIPTIONS,
        minecraft: { ...MC_COEFF },
        discord: { ...DISCORD_COEFF },
        web: { ...WEB_COEFF },
        joinBonus: {}
    };
}

function normalizeWallet(raw, fallbackBalance = 0) {
    const balance = Math.max(0, asInt(raw?.balance, fallbackBalance));
    const plan = GRADE_ORDER.includes(String(raw?.plan || '')) ? String(raw.plan) : 'Aucun';
    const ledger = Array.isArray(raw?.ledger) ? raw.ledger.slice(0, LEDGER_CAP) : [];
    return { balance, plan, ledger };
}

function normalizeStore(parsed) {
    const base = defaultStore();
    if (!parsed || typeof parsed !== 'object') return base;
    const walletsIn = parsed.wallets && typeof parsed.wallets === 'object' ? parsed.wallets : null;
    const wallets = {};
    if (walletsIn) {
        for (const [id, wallet] of Object.entries(walletsIn)) {
            wallets[id] = normalizeWallet(wallet, id === DEMO_ACCOUNT_ID ? DEMO_BALANCE : 0);
        }
    } else if (parsed.balance !== undefined) {
        wallets[DEMO_ACCOUNT_ID] = normalizeWallet(parsed, DEMO_BALANCE);
    }
    if (!wallets[DEMO_ACCOUNT_ID]) {
        wallets[DEMO_ACCOUNT_ID] = normalizeWallet(null, DEMO_BALANCE);
    }
    const packs = Array.isArray(parsed.packs) && parsed.packs.length ? parsed.packs : base.packs;
    const subscriptions = Array.isArray(parsed.subscriptions) && parsed.subscriptions.length
        ? parsed.subscriptions
        : (Array.isArray(parsed.abonnements) && parsed.abonnements.length ? parsed.abonnements : base.subscriptions);
    return {
        wallets,
        packs,
        subscriptions,
        minecraft: { ...MC_COEFF, ...(parsed.minecraft || {}) },
        discord: { ...DISCORD_COEFF, ...(parsed.discord || {}) },
        web: { ...WEB_COEFF, ...(parsed.web || {}) },
        joinBonus: parsed.joinBonus && typeof parsed.joinBonus === 'object' ? parsed.joinBonus : {}
    };
}

async function readStore() {
    try {
        const raw = await fs.readFile(DATA_PATH, 'utf8');
        return normalizeStore(JSON.parse(raw));
    } catch (err) {
        if (err.code !== 'ENOENT') throw err;
        return defaultStore();
    }
}

async function persistStore(store) {
    await fs.mkdir(path.dirname(DATA_PATH), { recursive: true });
    const payload = {
        wallets: store.wallets,
        packs: store.packs,
        subscriptions: store.subscriptions,
        minecraft: { ...MC_COEFF, ...(store.minecraft || {}) },
        discord: { ...DISCORD_COEFF, ...(store.discord || {}) },
        web: { ...WEB_COEFF, ...(store.web || {}) },
        joinBonus: store.joinBonus && typeof store.joinBonus === 'object' ? store.joinBonus : {}
    };
    const tmp = `${DATA_PATH}.${process.pid}.tmp`;
    await fs.writeFile(tmp, JSON.stringify(payload, null, 2), 'utf8');
    await fs.rename(tmp, DATA_PATH);
}

function accountId(req) {
    const user = req.session?.user;
    if (!user || user.isGuest) return DEMO_ACCOUNT_ID;
    const id = String(user.id || '').trim();
    return id || DEMO_ACCOUNT_ID;
}

function expressAccount(req) {
    const user = req.session?.user;
    if (!user || user.isGuest) return null;
    const id = String(user.id || '').trim();
    if (!id || id === 'guest' || id === DEMO_ACCOUNT_ID) return null;
    return {
        id,
        username: String(user.username || user.global_name || '').slice(0, 80),
        isTeamOwner: Boolean(user.isTeamOwner)
    };
}

const panelAccountCache = new Map();

async function panelAccountFromCookie(req) {
    const cookie = String(req.headers.cookie || '');
    if (!cookie.includes('synkrone_session=') && !cookie.includes('orbital_session=')) return null;
    const key = cookie.slice(0, 280);
    const hit = panelAccountCache.get(key);
    if (hit && Date.now() - hit.at < 4000) return hit.account;
    const port = Number(process.env.SYNKRONE_PANEL_PORT || 3000);
    try {
        const res = await fetch(`http://127.0.0.1:${port}/hebergement/api/krones`, {
            headers: { cookie, accept: 'application/json' }
        });
        if (!res.ok) {
            panelAccountCache.set(key, { at: Date.now(), account: null });
            return null;
        }
        const data = await res.json();
        const id = String(data.id || '').trim();
        const account = id
            ? { id, username: String(data.name || data.username || '').slice(0, 80), isTeamOwner: false }
            : null;
        panelAccountCache.set(key, { at: Date.now(), account });
        return account;
    } catch {
        panelAccountCache.set(key, { at: Date.now(), account: null });
        return null;
    }
}

async function sessionAccount(req) {
    return expressAccount(req);
}

function normalizeRole(role) {
    return String(role || '').trim().toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
}

function privilegeFromUser(user) {
    if (!user) return null;
    if (user.isTeamOwner) return 'admin';
    const role = normalizeRole(user.role);
    if (role === 'admin') return 'admin';
    if (['dev', 'equipe', 'equipes', 'staff'].includes(role)) return 'dev';
    return null;
}

function applyPrivilegePlan(wallet, privilege) {
    if (!wallet || privilege !== 'dev') return false;
    const current = GRADE_ORDER.indexOf(String(wallet.plan || 'Aucun'));
    const mid = GRADE_ORDER.indexOf(DEV_PLAN);
    if (current < mid) {
        wallet.plan = DEV_PLAN;
        return true;
    }
    return false;
}

function walletDto(wallet, meta = {}) {
    const authenticated = meta.authenticated === true;
    const privilege = meta.privilege || null;
    const unlimited = privilege === 'admin';
    const balance = Math.max(0, asInt(wallet?.balance, 0));
    return {
        balance,
        plan: GRADE_ORDER.includes(String(wallet?.plan || '')) ? String(wallet.plan) : 'Aucun',
        ledger: Array.isArray(wallet?.ledger) ? wallet.ledger : [],
        authenticated,
        demo: !authenticated,
        unlimited,
        privilege,
        shopUrl: '/krones',
        lowBalance: authenticated && !unlimited && balance < LOW_BALANCE
    };
}

function splitVat(ttcCents, rate) {
    const ttc = Math.max(0, Math.trunc(Number(ttcCents) || 0));
    const ht = Math.round(ttc / (1 + rate));
    return { ttc, ht, vat: ttc - ht, rate };
}

function publicPack(pack) {
    const fallback = DEFAULT_PACKS.find((item) => item.id === pack?.id);
    const id = String(pack?.id || fallback?.id || '');
    const krones = asInt(pack?.krones, fallback?.krones || 0);
    const eurCents = asInt(pack?.eurCents, fallback?.eurCents || Math.round((krones / KRONES_PER_EURO) * 100));
    const vat = splitVat(eurCents, VAT_RATE);
    return {
        id,
        label: String(pack?.label || fallback?.label || id),
        krones,
        eurCents: vat.ttc,
        htCents: vat.ht,
        vatCents: vat.vat,
        vatRate: VAT_RATE,
        currency: 'EUR'
    };
}

function publicSubscription(raw) {
    const name = GRADE_ORDER.includes(String(raw?.name || '')) ? String(raw.name) : null;
    const meta = (name && GRADE_META[name]) || DEFAULT_SUBSCRIPTIONS.find((item) => item.id === raw?.id) || null;
    if (!meta) return null;
    const krones = asInt(raw?.krones, meta.krones);
    return {
        id: meta.id,
        name: meta.name,
        krones,
        period: 'unique',
        tagline: meta.tagline,
        discount: meta.discount,
        discord: meta.discord,
        highlights: meta.highlights.slice(),
        perk: meta.highlights.join(' · '),
        eurCents: splitVat(Math.round((krones / KRONES_PER_EURO) * 100), VAT_RATE).ttc
    };
}

function compareTable() {
    const plans = GRADE_ORDER.filter((name) => name !== 'Aucun');
    return {
        plans,
        rows: COMPARE_ROWS.map((row) => ({
            id: row.id,
            label: row.label,
            cells: Object.fromEntries(plans.map((plan) => [plan, compareCell(row, plan)]))
        }))
    };
}

function buildCatalog(store) {
    const packSource = Array.isArray(store?.packs) && store.packs.length ? store.packs : DEFAULT_PACKS;
    const subSource = Array.isArray(store?.subscriptions) && store.subscriptions.length
        ? store.subscriptions
        : DEFAULT_SUBSCRIPTIONS;
    const packs = packSource.map(publicPack).filter((pack) => pack.id && pack.krones > 0);
    const subscriptions = subSource.map(publicSubscription).filter(Boolean);
    return {
        packs,
        subscriptions,
        abonnements: subscriptions,
        compare: compareTable(),
        pricing: {
            currency: 'EUR',
            vatRate: VAT_RATE,
            kronesPerEuro: KRONES_PER_EURO
        },
        minecraft: { ...MC_COEFF, ...(store.minecraft || {}) },
        discord: { ...DISCORD_COEFF, ...(store.discord || {}) },
        web: { ...WEB_COEFF, ...(store.web || {}) },
        computeMcMonthly
    };
}

function parseMcQuery(query) {
    if (!query || typeof query !== 'object') return null;
    const has = ['ramGb', 'cpu', 'storageGb', 'db'].some((key) => query[key] !== undefined);
    if (!has) return null;
    return {
        ramGb: Number(query.ramGb || 0),
        cpu: Number(query.cpu || 0),
        storageGb: Number(query.storageGb || 0),
        db: query.db
    };
}

function catalogDto(store, mcQuery, discounts) {
    const catalog = buildCatalog(store);
    const minecraft = { ...catalog.minecraft };
    const input = parseMcQuery(mcQuery);
    if (input) {
        minecraft.input = {
            ramGb: input.ramGb,
            cpu: input.cpu,
            storageGb: input.storageGb,
            db: input.db === true || input.db === 1 || input.db === '1' || String(input.db).toLowerCase() === 'true'
        };
        minecraft.monthly = computeMcMonthly({ ...minecraft.input, discounts });
    }
    return {
        unit: 'Krônes',
        packs: catalog.packs,
        subscriptions: catalog.subscriptions,
        abonnements: catalog.subscriptions,
        compare: catalog.compare,
        pricing: catalog.pricing,
        discounts: Array.isArray(discounts) ? discounts : [],
        minecraft,
        discord: catalog.discord,
        web: catalog.web
    };
}

async function readProfile(userId) {
    if (!userId || userId === DEMO_ACCOUNT_ID) return null;
    try {
        const raw = await fs.readFile(USERS_DB_PATH, 'utf8');
        const db = JSON.parse(raw);
        const existing = db?.users?.[userId];
        if (!existing || typeof existing !== 'object') return null;
        return existing;
    } catch {
        return null;
    }
}

async function syncProfile(userId, wallet) {
    if (!userId || userId === DEMO_ACCOUNT_ID) return null;
    try {
        const raw = await fs.readFile(USERS_DB_PATH, 'utf8');
        const db = JSON.parse(raw);
        if (!db || typeof db !== 'object' || !db.users || typeof db.users !== 'object') return null;
        const existing = db.users[userId];
        if (!existing || typeof existing !== 'object') return null;
        existing.krone = wallet.balance;
        if (GRADE_ORDER.includes(String(wallet.plan || ''))) existing.grade = wallet.plan;
        existing.updatedAt = Date.now();
        db.users[userId] = existing;
        const tmp = `${USERS_DB_PATH}.${process.pid}.tmp`;
        await fs.writeFile(tmp, JSON.stringify(db, null, 2), 'utf8');
        await fs.rename(tmp, USERS_DB_PATH);
        return existing;
    } catch {
        return null;
    }
}

function applySession(req, wallet) {
    if (!req.session?.user || req.session.user.isGuest) return;
    req.session.user.krone = wallet.balance;
    if (GRADE_ORDER.includes(String(wallet.plan || ''))) {
        req.session.user.grade = wallet.plan;
    }
}

function ensureWalletInStore(store, id, seed) {
    if (store.wallets[id]) {
        return { wallet: store.wallets[id], created: false };
    }
    const fromSeed = seed && Number.isFinite(Number(seed.krone))
        ? Math.max(0, Math.trunc(Number(seed.krone)))
        : (id === DEMO_ACCOUNT_ID ? DEMO_BALANCE : 0);
    const plan = GRADE_ORDER.includes(String(seed?.grade || '')) ? String(seed.grade) : 'Aucun';
    store.wallets[id] = {
        balance: id === DEMO_ACCOUNT_ID ? DEMO_BALANCE : fromSeed,
        plan,
        ledger: []
    };
    return { wallet: store.wallets[id], created: true };
}

async function seedFor(id) {
    if (!id || id === DEMO_ACCOUNT_ID) return null;
    return readProfile(id);
}

async function ensureWallet(store, req) {
    const account = await sessionAccount(req);
    const id = account?.id || DEMO_ACCOUNT_ID;
    const seed = await seedFor(id);
    const { wallet, created } = ensureWalletInStore(store, id, seed);
    const privilege = privilegeFromUser({
        ...(seed || {}),
        isTeamOwner: Boolean(account?.isTeamOwner || seed?.isTeamOwner)
    });
    const planChanged = applyPrivilegePlan(wallet, privilege);
    return { id, wallet, created: created || planChanged, privilege };
}

function appendLedger(wallet, type, amount, reason) {
    const entry = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        type,
        amount,
        reason: String(reason || '').trim().slice(0, 200),
        at: Date.now(),
        balanceAfter: wallet.balance
    };
    wallet.ledger = [entry, ...(Array.isArray(wallet.ledger) ? wallet.ledger : [])].slice(0, LEDGER_CAP);
    return entry;
}

function parseAmount(body) {
    const amount = asInt(body?.amount, NaN);
    if (!Number.isFinite(amount) || amount <= 0) return null;
    return amount;
}

function allowOpenCredit() {
    return process.env.NODE_ENV !== 'production' || process.env.SYNKRONE_KRONES_DEMO === '1';
}

async function peekWallet(id) {
    const account = String(id || '').trim() || DEMO_ACCOUNT_ID;
    return withFileLock(async () => {
        const store = await readStore();
        const { wallet, created } = ensureWalletInStore(store, account, await seedFor(account));
        const privilege = privilegeFromUser(await seedFor(account));
        const planChanged = applyPrivilegePlan(wallet, privilege);
        if (created || planChanged) {
            await persistStore(store);
            await syncProfile(account, wallet);
        }
        return { id: account, ...walletDto(wallet, { authenticated: account !== DEMO_ACCOUNT_ID, privilege }) };
    });
}

async function snapshotWallets() {
    return withFileLock(async () => {
        const store = await readStore();
        const out = {};
        for (const [id, wallet] of Object.entries(store.wallets)) {
            out[id] = walletDto(wallet, { authenticated: id !== DEMO_ACCOUNT_ID });
        }
        return out;
    });
}

async function creditAccount(id, amount, reason) {
    const parsed = asInt(amount, NaN);
    if (!Number.isFinite(parsed) || parsed <= 0) {
        return { ok: false, error: 'Montant invalide.' };
    }
    const account = String(id || '').trim() || DEMO_ACCOUNT_ID;
    return withFileLock(async () => {
        const store = await readStore();
        const { wallet } = ensureWalletInStore(store, account, await seedFor(account));
        wallet.balance += parsed;
        appendLedger(wallet, 'credit', parsed, reason);
        store.wallets[account] = wallet;
        await persistStore(store);
        await syncProfile(account, wallet);
        return { ok: true, wallet: walletDto(wallet) };
    });
}

async function debitAccount(id, amount, reason) {
    const parsed = asInt(amount, NaN);
    if (!Number.isFinite(parsed) || parsed <= 0) {
        return { ok: false, error: 'Montant invalide.' };
    }
    const account = String(id || '').trim() || DEMO_ACCOUNT_ID;
    return withFileLock(async () => {
        const store = await readStore();
        const seed = await seedFor(account);
        const { wallet } = ensureWalletInStore(store, account, seed);
        const privilege = privilegeFromUser(seed);
        applyPrivilegePlan(wallet, privilege);
        if (privilege === 'admin') {
            store.wallets[account] = wallet;
            await persistStore(store);
            await syncProfile(account, wallet);
            return { ok: true, wallet: walletDto(wallet, { privilege, authenticated: true }) };
        }
        if (wallet.balance < parsed) {
            return { ok: false, error: 'Solde insuffisant.', wallet: walletDto(wallet, { privilege, authenticated: true }) };
        }
        wallet.balance -= parsed;
        appendLedger(wallet, 'debit', parsed, reason);
        store.wallets[account] = wallet;
        await persistStore(store);
        await syncProfile(account, wallet);
        return { ok: true, wallet: walletDto(wallet, { privilege, authenticated: true }) };
    });
}

async function setAccountBalance(id, balance, reason) {
    const parsed = Math.max(0, asInt(balance, 0));
    const account = String(id || '').trim();
    if (!account || account === DEMO_ACCOUNT_ID) {
        return { ok: false, error: 'Compte invalide.' };
    }
    return withFileLock(async () => {
        const store = await readStore();
        const { wallet } = ensureWalletInStore(store, account, await seedFor(account));
        const delta = parsed - wallet.balance;
        wallet.balance = parsed;
        appendLedger(wallet, delta >= 0 ? 'credit' : 'debit', Math.abs(delta), reason || 'admin:set');
        store.wallets[account] = wallet;
        await persistStore(store);
        await syncProfile(account, wallet);
        return { ok: true, wallet: walletDto(wallet) };
    });
}

function isDiscordSnowflake(id) {
    return /^\d{15,22}$/.test(String(id || '').trim());
}

async function isGuildMember(discordId) {
    const token = String(process.env.DISCORD_BOT_TOKEN || '').trim();
    const guildId = String(process.env.DISCORD_GUILD_ID || '').trim();
    if (!token || !guildId || !isDiscordSnowflake(discordId)) return false;
    try {
        const res = await fetch(`https://discord.com/api/v10/guilds/${guildId}/members/${discordId}`, {
            headers: { Authorization: `Bot ${token}` },
            signal: AbortSignal.timeout(2000)
        });
        return res.ok;
    } catch {
        return false;
    }
}

async function alreadyClaimedJoinBonus(account) {
    try {
        const store = await readStore();
        return Boolean(store.joinBonus && store.joinBonus[account]);
    } catch {
        return false;
    }
}

async function claimJoinBonus(id) {
    const account = String(id || '').trim();
    if (!isDiscordSnowflake(account) || account === DEMO_ACCOUNT_ID) {
        return { ok: false, claimed: false, reason: 'invalid' };
    }
    if (await alreadyClaimedJoinBonus(account)) {
        return { ok: true, claimed: false, reason: 'already' };
    }
    const member = await isGuildMember(account);
    if (!member) return { ok: false, claimed: false, reason: 'not-member' };
    return withFileLock(async () => {
        const store = await readStore();
        if (!store.joinBonus || typeof store.joinBonus !== 'object') store.joinBonus = {};
        if (store.joinBonus[account]) {
            return { ok: true, claimed: false, reason: 'already' };
        }
        store.joinBonus[account] = Date.now();
        const { wallet } = ensureWalletInStore(store, account, await seedFor(account));
        wallet.balance += JOIN_BONUS;
        appendLedger(wallet, 'credit', JOIN_BONUS, JOIN_BONUS_REASON);
        store.wallets[account] = wallet;
        await persistStore(store);
        await syncProfile(account, wallet);
        return { ok: true, claimed: true, amount: JOIN_BONUS, wallet: walletDto(wallet, { authenticated: true }) };
    });
}

async function setAccountPlan(id, plan) {
    const next = GRADE_ORDER.includes(String(plan || '')) ? String(plan) : 'Aucun';
    const account = String(id || '').trim();
    if (!account) return { ok: false, error: 'Compte invalide.' };
    return withFileLock(async () => {
        const store = await readStore();
        const { wallet } = ensureWalletInStore(store, account, await seedFor(account));
        wallet.plan = next;
        store.wallets[account] = wallet;
        await persistStore(store);
        await syncProfile(account, wallet);
        return { ok: true, wallet: walletDto(wallet) };
    });
}

function mountKrones(app) {
    if (!app || typeof app.get !== 'function') {
        throw new Error('mountKrones(app) attend une app Express');
    }

    mountKrones.catalog = buildCatalog(defaultStore());

    app.get('/api/krones', async (req, res) => {
        try {
            const dto = await withFileLock(async () => {
                const store = await readStore();
                const { id, wallet, created, privilege } = await ensureWallet(store, req);
                if (created) {
                    await persistStore(store);
                    if (id !== DEMO_ACCOUNT_ID) await syncProfile(id, wallet);
                }
                mountKrones.catalog = buildCatalog(store);
                return { id, privilege, dto: walletDto(wallet, { authenticated: id !== DEMO_ACCOUNT_ID, privilege }) };
            });
            if (dto.id && dto.id !== DEMO_ACCOUNT_ID) {
                void claimJoinBonus(dto.id).catch(() => undefined);
            }
            return res.json(dto.dto);
        } catch (error) {
            return res.status(500).json({ error: 'Krônes indisponibles.' });
        }
    });

    app.get('/api/krones/catalog', async (req, res) => {
        try {
            const store = await readStore();
            mountKrones.catalog = buildCatalog(store);
            const platform = await readPlatform().catch(() => ({ discounts: [] }));
            const dto = catalogDto(store, req.query, platform.discounts);
            try {
                const { billingPublicDto } = require('./billing');
                dto.billing = billingPublicDto(await sessionAccount(req));
            } catch {
                dto.billing = { authenticated: Boolean(await sessionAccount(req)), loginUrl: '/login?returnTo=/krones' };
            }
            return res.json(dto);
        } catch (error) {
            return res.status(500).json({ error: 'Catalogue Krônes indisponible.' });
        }
    });

    app.post('/api/krones/credit', async (req, res) => {
        if (!allowOpenCredit()) {
            return res.status(403).json({ error: 'Crédit démo désactivé.' });
        }
        const amount = parseAmount(req.body);
        if (amount === null) return res.status(400).json({ error: 'Montant invalide.' });
        try {
            const result = await creditAccount(accountId(req), amount, req.body?.reason);
            if (!result.ok) return res.status(400).json({ error: result.error });
            applySession(req, result.wallet);
            return res.json(result.wallet);
        } catch (error) {
            return res.status(500).json({ error: 'Crédit Krônes impossible.' });
        }
    });

    app.post('/api/krones/debit', async (req, res) => {
        const amount = parseAmount(req.body);
        if (amount === null) return res.status(400).json({ error: 'Montant invalide.' });
        try {
            const result = await debitAccount(accountId(req), amount, req.body?.reason);
            if (!result.ok) {
                const status = result.error === 'Solde insuffisant.' ? 403 : 400;
                return res.status(status).json({ ...(result.wallet || {}), error: result.error });
            }
            applySession(req, result.wallet);
            return res.json(result.wallet);
        } catch (error) {
            return res.status(500).json({ error: 'Débit Krônes impossible.' });
        }
    });

    try {
        const { mountBilling } = require('./billing');
        mountBilling(app, {
            sessionAccount,
            creditAccount,
            applySession,
            peekWallet,
            setAccountPlan,
            getCatalog: async () => {
                const store = await readStore();
                return buildCatalog(store);
            }
        });
    } catch (error) {
        console.warn('[krones] module facturation indisponible:', error.message);
    }
}

mountKrones.catalog = buildCatalog(defaultStore());

module.exports = {
    mountKrones,
    peekWallet,
    snapshotWallets,
    creditAccount,
    debitAccount,
    setAccountBalance,
    setAccountPlan,
    sessionAccount,
    claimJoinBonus,
    GRADE_ORDER,
    DATA_PATH
};
