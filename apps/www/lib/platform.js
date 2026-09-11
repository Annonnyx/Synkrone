'use strict';

const fs = require('node:fs/promises');
const path = require('node:path');

const DATA_PATH = path.join(__dirname, '..', 'data', 'platform.json');

const DISCOUNT_TARGETS = new Set(['all', 'discord', 'minecraft', 'web', 'ram', 'cpu', 'storage']);

const DEFAULTS = {
    minecraftEnabled: true,
    maxCpuMillicores: 4000,
    maxMemoryMb: 8192,
    maxStorageMb: 51200,
    limits: {
        discord: { cpuMillicores: 2000, memoryMb: 2048, storageMb: 10240 },
        minecraft: { cpuMillicores: 4000, memoryMb: 8192, storageMb: 51200 },
        web: { cpuMillicores: 2000, memoryMb: 4096, storageMb: 20480 }
    },
    discounts: []
};

function normalizeDiscount(raw, index = 0) {
    if (!raw || typeof raw !== 'object') return null;
    const targets = (Array.isArray(raw.targets) ? raw.targets : [])
        .map((item) => String(item || '').trim().toLowerCase())
        .filter((item) => DISCOUNT_TARGETS.has(item));
    if (!targets.length) return null;
    const percent = Math.min(100, Math.max(0, asInt(raw.percent, 0, 0, 100)));
    const startsAt = Number.isFinite(Number(raw.startsAt)) ? Math.trunc(Number(raw.startsAt)) : Date.now();
    const endsAt = Number.isFinite(Number(raw.endsAt)) ? Math.trunc(Number(raw.endsAt)) : 0;
    if (!endsAt || endsAt <= startsAt) return null;
    return {
        id: String(raw.id || '').trim() || `promo-${Date.now().toString(36)}-${index}`,
        label: String(raw.label || 'Promo').trim().slice(0, 80) || 'Promo',
        targets,
        percent,
        startsAt,
        endsAt,
        enabled: raw.enabled !== false
    };
}

function activeDiscounts(discounts, at = Date.now()) {
    return (Array.isArray(discounts) ? discounts : []).filter((row) => (
        row && row.enabled !== false && Number(row.startsAt) <= at && at < Number(row.endsAt)
    ));
}

function discountFactor(discounts, keys) {
    const wanted = new Set(keys);
    return activeDiscounts(discounts).reduce((factor, row) => {
        if (!row.targets.some((target) => wanted.has(target))) return factor;
        return factor * Math.max(0, 1 - Number(row.percent || 0) / 100);
    }, 1);
}

function applyHostingDiscount(parts, type, discounts) {
    const ram = Number(parts.ram || 0) * discountFactor(discounts, ['ram']);
    const cpu = Number(parts.cpu || 0) * discountFactor(discounts, ['cpu']);
    const storage = Number(parts.storage || 0) * discountFactor(discounts, ['storage']);
    const subtotal = Number(parts.base || 0) + ram + cpu + storage + Number(parts.db || 0);
    return Math.max(0, Math.round(subtotal * discountFactor(discounts, [type, 'all'])));
}

function asInt(value, fallback, min, max) {
    const n = Number(value);
    if (!Number.isFinite(n)) return fallback;
    return Math.min(max, Math.max(min, Math.trunc(n)));
}

function normalize(raw) {
    const src = raw && typeof raw === 'object' ? raw : {};
    const limitsIn = src.limits && typeof src.limits === 'object' ? src.limits : {};
    const out = {
        minecraftEnabled: src.minecraftEnabled !== false,
        maxCpuMillicores: asInt(src.maxCpuMillicores, DEFAULTS.maxCpuMillicores, 100, 16000),
        maxMemoryMb: asInt(src.maxMemoryMb, DEFAULTS.maxMemoryMb, 64, 65536),
        maxStorageMb: asInt(src.maxStorageMb, DEFAULTS.maxStorageMb, 512, 204800),
        limits: {},
        discounts: []
    };
    for (const type of ['discord', 'minecraft', 'web']) {
        const row = limitsIn[type] && typeof limitsIn[type] === 'object' ? limitsIn[type] : {};
        const fallback = DEFAULTS.limits[type];
        out.limits[type] = {
            cpuMillicores: asInt(row.cpuMillicores, fallback.cpuMillicores, 100, out.maxCpuMillicores),
            memoryMb: asInt(row.memoryMb, fallback.memoryMb, 64, out.maxMemoryMb),
            storageMb: asInt(row.storageMb, fallback.storageMb, 512, out.maxStorageMb)
        };
    }
    if (process.env.SYNKRONE_DISABLE_MINECRAFT === '1') out.minecraftEnabled = false;
    const discountsIn = Array.isArray(src.discounts) ? src.discounts : [];
    out.discounts = discountsIn.map((row, index) => normalizeDiscount(row, index)).filter(Boolean);
    return out;
}

async function readPlatform() {
    try {
        const raw = JSON.parse(await fs.readFile(DATA_PATH, 'utf8'));
        return normalize(raw);
    } catch {
        return normalize(DEFAULTS);
    }
}

async function writePlatform(patch) {
    const current = await readPlatform();
    const next = normalize({
        ...current,
        ...patch,
        limits: {
            ...current.limits,
            ...(patch && patch.limits && typeof patch.limits === 'object' ? patch.limits : {})
        },
        discounts: Array.isArray(patch?.discounts) ? patch.discounts : current.discounts
    });
    await fs.mkdir(path.dirname(DATA_PATH), { recursive: true });
    const tmp = `${DATA_PATH}.${process.pid}.tmp`;
    await fs.writeFile(tmp, JSON.stringify(next, null, 2), 'utf8');
    await fs.rename(tmp, DATA_PATH);
    return next;
}

module.exports = {
    DATA_PATH,
    DEFAULTS,
    DISCOUNT_TARGETS: [...DISCOUNT_TARGETS],
    normalize,
    normalizeDiscount,
    activeDiscounts,
    applyHostingDiscount,
    readPlatform,
    writePlatform
};
