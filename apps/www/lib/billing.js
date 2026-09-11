'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs/promises');
const path = require('node:path');

const DATA_PATH = path.join(__dirname, '..', 'data', 'krones-orders.json');
const LOCK_PATH = `${DATA_PATH}.lock`;
const LOCK_STALE_MS = 15000;
const LOCK_WAIT_MS = 10000;
const ORDER_TTL_MS = 7 * 24 * 60 * 60 * 1000;
const LEDGER_REASON_MAX = 200;
const CHECKOUT_WINDOW_MS = 10 * 60 * 1000;
const CHECKOUT_MAX = 8;

let writeChain = Promise.resolve();
const checkoutHits = new Map();

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
                throw new Error('Commandes Krônes : verrou indisponible.');
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

function env(name) {
    return String(process.env[name] || '').trim();
}

function vatRate() {
    const n = Number(process.env.SYNKRONE_VAT_RATE);
    if (Number.isFinite(n) && n >= 0 && n < 1) return n;
    return 0.2;
}

function isProduction() {
    return process.env.NODE_ENV === 'production';
}

function simulateAllowed() {
    if (env('SYNKRONE_PAY_DEMO') === '1') return true;
    return !isProduction();
}

function sellerRecord() {
    return {
        name: env('SYNKRONE_SELLER_NAME') || 'Synkrone',
        legalForm: env('SYNKRONE_SELLER_LEGAL_FORM'),
        address: env('SYNKRONE_SELLER_ADDRESS'),
        siret: env('SYNKRONE_SELLER_SIRET'),
        vatNumber: env('SYNKRONE_SELLER_VAT_NUMBER'),
        email: env('SYNKRONE_SELLER_EMAIL'),
        rcs: env('SYNKRONE_SELLER_RCS'),
        iban: env('SYNKRONE_SELLER_IBAN'),
        bic: env('SYNKRONE_SELLER_BIC'),
        mediatorName: env('SYNKRONE_MEDIATOR_NAME'),
        mediatorUrl: env('SYNKRONE_MEDIATOR_URL')
    };
}

function sellerReady(seller) {
    return Boolean(seller.name && seller.address && seller.email);
}

function splitVat(ttcCents, rate) {
    const ttc = Math.max(0, Math.trunc(Number(ttcCents) || 0));
    const ht = Math.round(ttc / (1 + rate));
    return { ttc, ht, vat: ttc - ht, rate };
}

function clientIp(req) {
    const forwarded = String(req.headers['x-forwarded-for'] || '').split(',')[0].trim();
    return forwarded || String(req.socket?.remoteAddress || '').slice(0, 80);
}

function defaultStore() {
    return { year: new Date().getFullYear(), seq: 0, orders: {} };
}

function normalizeStore(parsed) {
    if (!parsed || typeof parsed !== 'object') return defaultStore();
    const ordersIn = parsed.orders && typeof parsed.orders === 'object' ? parsed.orders : {};
    const orders = {};
    for (const [id, order] of Object.entries(ordersIn)) {
        if (order && typeof order === 'object' && order.id) orders[id] = order;
    }
    return {
        year: Number(parsed.year) || new Date().getFullYear(),
        seq: Math.max(0, Math.trunc(Number(parsed.seq) || 0)),
        orders
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
    const tmp = `${DATA_PATH}.${process.pid}.tmp`;
    await fs.writeFile(tmp, JSON.stringify(store, null, 2), 'utf8');
    await fs.rename(tmp, DATA_PATH);
}

function nextInvoiceNumber(store) {
    const year = new Date().getFullYear();
    if (store.year !== year) {
        store.year = year;
        store.seq = 0;
    }
    store.seq += 1;
    return `SK-${year}-${String(store.seq).padStart(6, '0')}`;
}

function expireIfNeeded(order) {
    if (!order) return order;
    const pending = order.status === 'awaiting_payment' || order.status === 'awaiting_transfer';
    if (pending && Date.now() - Number(order.createdAt || 0) > ORDER_TTL_MS) {
        order.status = 'expired';
        order.expiredAt = Date.now();
    }
    return order;
}

function publicSeller(seller) {
    return {
        name: seller.name,
        legalForm: seller.legalForm || null,
        address: seller.address || null,
        siret: seller.siret || null,
        vatNumber: seller.vatNumber || null,
        email: seller.email || null,
        rcs: seller.rcs || null,
        hasIban: Boolean(seller.iban),
        mediatorName: seller.mediatorName || null,
        mediatorUrl: seller.mediatorUrl || null
    };
}

function paymentMethods(seller) {
    return [
        {
            id: 'sepa',
            label: 'Virement SEPA',
            available: Boolean(seller.iban),
            hint: seller.iban
                ? 'Crédit après réception du virement (référence = n° de facture).'
                : 'IBAN à renseigner (SYNKRONE_SELLER_IBAN) pour activer le virement.'
        },
        {
            id: 'paypal',
            label: 'PayPal',
            available: false,
            soon: true,
            hint: 'Prestataire à brancher. La commande et la facture sont déjà prêtes.'
        },
        {
            id: 'apple_pay',
            label: 'Apple Pay',
            available: false,
            soon: true,
            hint: 'Prestataire à brancher. Même flux de commande.'
        },
        {
            id: 'card',
            label: 'Carte bancaire',
            available: false,
            soon: true,
            hint: 'Prestataire à brancher.'
        },
        {
            id: 'demo',
            label: 'Paiement de test',
            available: simulateAllowed(),
            hint: 'Aucun prélèvement. Valide le parcours commande → facture → crédit du portefeuille.'
        }
    ];
}

function billingPublicDto(account) {
    const seller = sellerRecord();
    return {
        authenticated: Boolean(account),
        loginUrl: '/hebergement/login',
        currency: 'EUR',
        vatRate: vatRate(),
        vatLabel: `${Math.round(vatRate() * 100)} %`,
        country: 'FR',
        simulateAllowed: simulateAllowed(),
        sellerReady: sellerReady(seller),
        production: isProduction(),
        seller: publicSeller(seller),
        methods: paymentMethods(seller),
        legal: {
            cguUrl: '/cgu',
            cgvUrl: '/cgv',
            withdrawal: 'Les Krônes sont un contenu numérique fourni immédiatement. Le droit de rétractation est perdu si vous le demandez expressément (art. L. 221-28 C. conso.).',
            nonRedeemable: 'Les Krônes n’ont pas de valeur fiduciaire et ne sont pas convertibles en euros.'
        }
    };
}

function orderDto(order, { includeTransfer = false } = {}) {
    if (!order) return null;
    const seller = sellerRecord();
    const dto = {
        id: order.id,
        invoiceNumber: order.invoiceNumber,
        status: order.status,
        packId: order.packId,
        packLabel: order.packLabel,
        kind: order.kind || 'pack',
        grade: order.grade || null,
        krones: order.krones,
        currency: order.currency,
        amountTtcCents: order.amountTtcCents,
        amountHtCents: order.amountHtCents,
        vatCents: order.vatCents,
        vatRate: order.vatRate,
        method: order.method || null,
        providerRef: order.providerRef || null,
        createdAt: order.createdAt,
        paidAt: order.paidAt || null,
        fulfilledAt: order.fulfilledAt || null,
        expiredAt: order.expiredAt || null,
        cancelledAt: order.cancelledAt || null,
        seller: publicSeller(seller)
    };
    if (includeTransfer && order.method === 'sepa' && seller.iban && (order.status === 'awaiting_transfer' || order.status === 'awaiting_payment')) {
        dto.transfer = {
            iban: seller.iban,
            bic: seller.bic || null,
            reference: order.invoiceNumber,
            beneficiary: seller.name
        };
    }
    return dto;
}

function rateLimitCheckout(userId) {
    const now = Date.now();
    const hits = (checkoutHits.get(userId) || []).filter((t) => now - t < CHECKOUT_WINDOW_MS);
    if (hits.length >= CHECKOUT_MAX) return false;
    hits.push(now);
    checkoutHits.set(userId, hits);
    return true;
}

function consentsOk(body) {
    const c = body?.consents && typeof body.consents === 'object' ? body.consents : {};
    return Boolean(c.age) && Boolean(c.cgv) && Boolean(c.withdrawalWaiver);
}

function findPack(catalog, packId) {
    const packs = Array.isArray(catalog?.packs) ? catalog.packs : [];
    return packs.find((pack) => String(pack.id) === String(packId)) || null;
}

function findGrade(catalog, name) {
    const subs = Array.isArray(catalog?.subscriptions) ? catalog.subscriptions : [];
    const wanted = String(name || '').trim();
    return subs.find((sub) => sub.name === wanted || sub.id === wanted.toLowerCase()) || null;
}

function gradeTotals(catalog, plan) {
    if (!plan || plan === 'Aucun') return { krones: 0, eurCents: 0 };
    const sub = findGrade(catalog, plan);
    return {
        krones: Math.max(0, Math.trunc(Number(sub?.krones) || 0)),
        eurCents: Math.max(0, Math.trunc(Number(sub?.eurCents) || 0))
    };
}

function ownsOrder(order, account) {
    return order && account && String(order.userId) === String(account.id);
}

async function fulfillLocked(store, order, deps, meta) {
    if (order.status === 'fulfilled') {
        return { ok: true, already: true, order };
    }
    if (order.status === 'expired' || order.status === 'cancelled' || order.status === 'refunded') {
        return { ok: false, error: 'Commande close.', order };
    }
    if (order.kind === 'grade') {
        const planned = await deps.setAccountPlan(order.userId, order.grade);
        if (!planned?.ok) {
            return { ok: false, error: planned?.error || 'Rang impossible à attribuer.', order };
        }
        order.status = 'fulfilled';
        order.paidAt = order.paidAt || Date.now();
        order.fulfilledAt = Date.now();
        order.method = meta.method || order.method;
        order.providerRef = meta.providerRef || order.providerRef || null;
        store.orders[order.id] = order;
        await persistStore(store);
        return { ok: true, order, wallet: planned.wallet };
    }
    const credited = await deps.creditAccount(order.userId, order.krones, `commande:${order.invoiceNumber}`.slice(0, LEDGER_REASON_MAX));
    if (!credited.ok) {
        return { ok: false, error: credited.error || 'Crédit du portefeuille impossible.', order };
    }
    order.status = 'fulfilled';
    order.paidAt = order.paidAt || Date.now();
    order.fulfilledAt = Date.now();
    order.method = meta.method || order.method;
    order.providerRef = meta.providerRef || order.providerRef || null;
    order.ledgerEntryId = credited.wallet?.ledger?.[0]?.id || null;
    store.orders[order.id] = order;
    await persistStore(store);
    return { ok: true, order, wallet: credited.wallet };
}

function mountBilling(app, deps) {
    if (!app || typeof app.get !== 'function') {
        throw new Error('mountBilling(app) attend une app Express');
    }
    const sessionAccount = deps.sessionAccount;
    const getCatalog = deps.getCatalog;
    const applySession = deps.applySession;
    const creditAccount = deps.creditAccount;
    const peekWallet = deps.peekWallet;
    const setAccountPlan = deps.setAccountPlan;

    app.get('/api/krones/billing', async (req, res) => {
        return res.json(billingPublicDto(await sessionAccount(req)));
    });

    app.get('/api/krones/orders', async (req, res) => {
        const account = await sessionAccount(req);
        if (!account) return res.status(401).json({ error: 'Connectez-vous pour voir vos commandes.', loginUrl: '/hebergement/login' });
        try {
            const list = await withFileLock(async () => {
                const store = await readStore();
                let dirty = false;
                const mine = [];
                for (const order of Object.values(store.orders)) {
                    if (!ownsOrder(order, account)) continue;
                    const before = order.status;
                    expireIfNeeded(order);
                    if (order.status !== before) dirty = true;
                    mine.push(order);
                }
                if (dirty) await persistStore(store);
                mine.sort((a, b) => Number(b.createdAt || 0) - Number(a.createdAt || 0));
                return mine.slice(0, 50).map((order) => orderDto(order, { includeTransfer: true }));
            });
            return res.json({ orders: list });
        } catch {
            return res.status(500).json({ error: 'Commandes indisponibles.' });
        }
    });

    app.get('/api/krones/orders/:id', async (req, res) => {
        const account = await sessionAccount(req);
        if (!account) return res.status(401).json({ error: 'Connectez-vous.', loginUrl: '/hebergement/login' });
        try {
            const dto = await withFileLock(async () => {
                const store = await readStore();
                const order = store.orders[String(req.params.id || '')];
                if (!order) return { missing: true };
                if (!ownsOrder(order, account) && !account.isTeamOwner) return { forbidden: true };
                expireIfNeeded(order);
                await persistStore(store);
                return { order: orderDto(order, { includeTransfer: true }) };
            });
            if (dto.missing) return res.status(404).json({ error: 'Commande introuvable.' });
            if (dto.forbidden) return res.status(403).json({ error: 'Commande d’un autre compte.' });
            return res.json(dto.order);
        } catch {
            return res.status(500).json({ error: 'Commande indisponible.' });
        }
    });

    app.post('/api/krones/checkout', async (req, res) => {
        const account = await sessionAccount(req);
        if (!account) {
            return res.status(401).json({ error: 'Un compte est obligatoire pour acheter.', loginUrl: '/hebergement/login' });
        }
        if (!consentsOk(req.body)) {
            return res.status(400).json({
                error: 'Cochez l’âge, les CGV et la renonciation au droit de rétractation.'
            });
        }
        const seller = sellerRecord();
        if (isProduction() && !sellerReady(seller)) {
            return res.status(503).json({
                error: 'Vente indisponible : identité du vendeur incomplète (nom, adresse, e-mail).'
            });
        }
        if (!rateLimitCheckout(account.id)) {
            return res.status(429).json({ error: 'Trop de tentatives. Réessayez dans quelques minutes.' });
        }
        const packId = String(req.body?.packId || '').trim();
        const gradeName = String(req.body?.grade || '').trim();
        let catalog;
        try {
            catalog = await getCatalog();
        } catch {
            return res.status(500).json({ error: 'Catalogue indisponible.' });
        }
        let kind = 'pack';
        let packIdOut = packId;
        let packLabel = '';
        let krones = 0;
        let eurCents = 0;
        let grade = null;
        if (gradeName) {
            const target = findGrade(catalog, gradeName);
            if (!target) return res.status(400).json({ error: 'Rang invalide.' });
            let currentPlan = 'Aucun';
            if (peekWallet) {
                try {
                    const wallet = await peekWallet(account.id);
                    currentPlan = wallet?.plan || 'Aucun';
                } catch { /* Aucun */ }
            }
            const current = gradeTotals(catalog, currentPlan);
            const next = gradeTotals(catalog, target.name);
            krones = Math.max(0, next.krones - current.krones);
            eurCents = Math.max(0, next.eurCents - current.eurCents);
            if (krones <= 0 || eurCents <= 0) {
                return res.status(400).json({ error: 'Rang déjà possédé.' });
            }
            kind = 'grade';
            packIdOut = `grade:${target.id}`;
            packLabel = current.krones ? `Complément ${target.name}` : `Rang ${target.name}`;
            grade = target.name;
        } else {
            const pack = findPack(catalog, packId);
            krones = Math.trunc(Number(pack?.krones) || 0);
            eurCents = Math.trunc(Number(pack?.eurCents) || 0);
            if (!pack || krones <= 0 || eurCents <= 0) {
                return res.status(400).json({ error: 'Pack invalide.' });
            }
            packLabel = pack.label;
        }
        const vat = splitVat(eurCents, vatRate());
        try {
            const created = await withFileLock(async () => {
                const store = await readStore();
                const id = `ord_${Date.now().toString(36)}_${crypto.randomBytes(4).toString('hex')}`;
                const order = {
                    id,
                    invoiceNumber: nextInvoiceNumber(store),
                    status: 'awaiting_payment',
                    userId: account.id,
                    username: account.username,
                    packId: packIdOut,
                    packLabel,
                    kind,
                    grade,
                    krones,
                    currency: 'EUR',
                    amountTtcCents: vat.ttc,
                    amountHtCents: vat.ht,
                    vatCents: vat.vat,
                    vatRate: vat.rate,
                    method: null,
                    providerRef: null,
                    consents: {
                        age: true,
                        cgv: true,
                        withdrawalWaiver: true,
                        at: Date.now()
                    },
                    ip: clientIp(req),
                    userAgent: String(req.get('user-agent') || '').slice(0, 240),
                    createdAt: Date.now()
                };
                store.orders[id] = order;
                await persistStore(store);
                return order;
            });
            return res.status(201).json(orderDto(created));
        } catch {
            return res.status(500).json({ error: 'Impossible d’enregistrer la commande.' });
        }
    });

    app.post('/api/krones/orders/:id/pay', async (req, res) => {
        const account = await sessionAccount(req);
        if (!account) return res.status(401).json({ error: 'Connectez-vous.', loginUrl: '/hebergement/login' });
        const method = String(req.body?.method || '').trim();
        const seller = sellerRecord();
        const methods = paymentMethods(seller);
        const chosen = methods.find((item) => item.id === method);
        if (!chosen) return res.status(400).json({ error: 'Moyen de paiement inconnu.' });
        if (!chosen.available) {
            const status = chosen.soon ? 503 : 400;
            return res.status(status).json({
                error: chosen.soon
                    ? `${chosen.label} n’est pas encore branché. La commande reste en attente.`
                    : chosen.hint || 'Moyen de paiement indisponible.',
                method
            });
        }
        try {
            const result = await withFileLock(async () => {
                const store = await readStore();
                const order = store.orders[String(req.params.id || '')];
                if (!order) return { missing: true };
                if (!ownsOrder(order, account)) return { forbidden: true };
                expireIfNeeded(order);
                if (order.status === 'fulfilled') {
                    return { ok: true, already: true, order };
                }
                if (order.status !== 'awaiting_payment' && !(order.status === 'awaiting_transfer' && method === 'sepa')) {
                    return { closed: true, order };
                }
                if (method === 'demo') {
                    return fulfillLocked(store, order, { creditAccount, setAccountPlan }, {
                        method: 'demo',
                        providerRef: `demo:${order.id}`
                    });
                }
                if (method === 'sepa') {
                    order.status = 'awaiting_transfer';
                    order.method = 'sepa';
                    store.orders[order.id] = order;
                    await persistStore(store);
                    return { ok: true, order };
                }
                return { ok: false, error: 'Moyen de paiement non géré.' };
            });
            if (result.missing) return res.status(404).json({ error: 'Commande introuvable.' });
            if (result.forbidden) return res.status(403).json({ error: 'Commande d’un autre compte.' });
            if (result.closed) {
                return res.status(409).json({ error: 'Cette commande n’est plus payable.', order: orderDto(result.order) });
            }
            if (!result.ok) return res.status(400).json({ error: result.error || 'Paiement refusé.' });
            if (result.wallet) applySession(req, result.wallet);
            return res.json({
                ...orderDto(result.order, { includeTransfer: true }),
                already: Boolean(result.already),
                wallet: result.wallet || undefined
            });
        } catch {
            return res.status(500).json({ error: 'Paiement impossible.' });
        }
    });

    app.post('/api/krones/orders/:id/cancel', async (req, res) => {
        const account = await sessionAccount(req);
        if (!account) return res.status(401).json({ error: 'Connectez-vous.', loginUrl: '/hebergement/login' });
        try {
            const result = await withFileLock(async () => {
                const store = await readStore();
                const order = store.orders[String(req.params.id || '')];
                if (!order) return { missing: true };
                if (!ownsOrder(order, account)) return { forbidden: true };
                if (order.status === 'fulfilled' || order.status === 'refunded') {
                    return { closed: true, order };
                }
                order.status = 'cancelled';
                order.cancelledAt = Date.now();
                store.orders[order.id] = order;
                await persistStore(store);
                return { ok: true, order };
            });
            if (result.missing) return res.status(404).json({ error: 'Commande introuvable.' });
            if (result.forbidden) return res.status(403).json({ error: 'Commande d’un autre compte.' });
            if (result.closed) return res.status(409).json({ error: 'Commande déjà soldée.', order: orderDto(result.order) });
            return res.json(orderDto(result.order));
        } catch {
            return res.status(500).json({ error: 'Annulation impossible.' });
        }
    });

    app.post('/api/krones/orders/:id/fulfill', async (req, res) => {
        const account = await sessionAccount(req);
        if (!account?.isTeamOwner) {
            return res.status(403).json({ error: 'Réservé à l’équipe : confirmer un virement reçu.' });
        }
        try {
            const result = await withFileLock(async () => {
                const store = await readStore();
                const order = store.orders[String(req.params.id || '')];
                if (!order) return { missing: true };
                expireIfNeeded(order);
                return fulfillLocked(store, order, { creditAccount, setAccountPlan }, {
                    method: order.method || 'sepa',
                    providerRef: String(req.body?.providerRef || `staff:${account.id}`).slice(0, 120)
                });
            });
            if (result.missing) return res.status(404).json({ error: 'Commande introuvable.' });
            if (!result.ok) return res.status(409).json({ error: result.error, order: orderDto(result.order) });
            return res.json({ ...orderDto(result.order), already: Boolean(result.already) });
        } catch {
            return res.status(500).json({ error: 'Confirmation impossible.' });
        }
    });

    app.post('/api/krones/webhooks/:provider', async (req, res) => {
        const provider = String(req.params.provider || '').trim().toLowerCase();
        const allowed = new Set(['paypal', 'apple_pay', 'card', 'stripe']);
        if (!allowed.has(provider)) {
            return res.status(404).json({ error: 'Prestataire inconnu.' });
        }
        const secret = env('SYNKRONE_PAY_WEBHOOK_SECRET');
        if (!secret) {
            return res.status(503).json({
                error: 'Webhook inactif. Définir SYNKRONE_PAY_WEBHOOK_SECRET puis vérifier la signature du prestataire avant de créditer.'
            });
        }
        const header = String(req.get('x-synkrone-webhook') || '');
        const expected = crypto.createHmac('sha256', secret).update(JSON.stringify(req.body || {})).digest('hex');
        const a = Buffer.from(header);
        const b = Buffer.from(expected);
        if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) {
            return res.status(401).json({ error: 'Signature webhook invalide.' });
        }
        const orderId = String(req.body?.orderId || req.body?.id || '').trim();
        const providerRef = String(req.body?.providerRef || req.body?.transactionId || '').slice(0, 120);
        if (!orderId) return res.status(400).json({ error: 'orderId manquant.' });
        try {
            const result = await withFileLock(async () => {
                const store = await readStore();
                const order = store.orders[orderId];
                if (!order) return { missing: true };
                return fulfillLocked(store, order, { creditAccount, setAccountPlan }, { method: provider, providerRef });
            });
            if (result.missing) return res.status(404).json({ error: 'Commande introuvable.' });
            if (!result.ok) return res.status(409).json({ error: result.error });
            return res.json({ ok: true, id: result.order.id, status: result.order.status, already: Boolean(result.already) });
        } catch {
            return res.status(500).json({ error: 'Webhook impossible à traiter.' });
        }
    });
}

module.exports = {
    mountBilling,
    billingPublicDto,
    vatRate,
    splitVat,
    DATA_PATH
};
