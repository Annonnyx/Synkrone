'use strict';

/** Two-layer Discord customization: Default (bot creator) vs Server (guild admin). */

const ACTIVITY_TYPES = ['playing', 'watching', 'listening', 'streaming', 'competing'];

const FONTS = [
    { id: 'ibm-plex-sans', label: 'IBM Plex Sans', google: 'IBM+Plex+Sans:wght@400;600' },
    { id: 'zilla-slab', label: 'Zilla Slab', google: 'Zilla+Slab:wght@400;600' },
    { id: 'source-serif-4', label: 'Source Serif 4', google: 'Source+Serif+4:wght@400;600' },
    { id: 'ibm-plex-mono', label: 'IBM Plex Mono', google: 'IBM+Plex+Mono:wght@400;500' },
    { id: 'fraunces', label: 'Fraunces', google: 'Fraunces:wght@400;600' }
];

const THEMES = {
    basalte: {
        label: 'Basalte',
        embedColor: '#1b211e',
        colors: { success: '#3f6b52', error: '#a8462f', warning: '#b8823d', info: '#5c6a66' }
    },
    pierre: {
        label: 'Pierre',
        embedColor: '#5c6a66',
        colors: { success: '#3f6b52', error: '#a8462f', warning: '#b8823d', info: '#1b211e' }
    },
    mousse: {
        label: 'Mousse',
        embedColor: '#3f6b52',
        colors: { success: '#2e5039', error: '#a8462f', warning: '#b8823d', info: '#5c6a66' }
    },
    ambre: {
        label: 'Ambre',
        embedColor: '#b8823d',
        colors: { success: '#3f6b52', error: '#a8462f', warning: '#8c6226', info: '#5c6a66' }
    }
};

const COLOR_PRESETS = ['#3f6b52', '#1b211e', '#b8823d', '#a8462f', '#5c6a66', '#660099', '#eef0ea'];

const MODULES = [
    { id: 'welcome', label: 'Bienvenue', needs: 'channel', autoName: 'bienvenue' },
    { id: 'goodbye', label: 'Au revoir', needs: 'channel', autoName: 'au-revoir' },
    { id: 'logs', label: 'Journaux', needs: 'channel', autoName: 'logs' },
    { id: 'tickets', label: 'Tickets', needs: 'channel', autoName: 'tickets' },
    { id: 'mute', label: 'Mute', needs: 'role', autoName: 'Muted' }
];

const ALLOW_KEYS = [
    'displayName',
    'avatar',
    'embedColor',
    'embedPalette',
    'embedLogo',
    'embedFooter',
    'font',
    'whiteLabel',
    'texts',
    'channels',
    'roles',
    'modules',
    'cooldowns',
    'commandPerms'
];

const FIELD_ALLOW = {
    'identity.displayName': 'displayName',
    'identity.avatarUrl': 'avatar',
    'identity.embedColor': 'embedColor',
    'identity.colors.success': 'embedPalette',
    'identity.colors.error': 'embedPalette',
    'identity.colors.warning': 'embedPalette',
    'identity.colors.info': 'embedPalette',
    'identity.logo': 'embedLogo',
    'identity.footerText': 'embedFooter',
    'identity.footerIcon': 'embedFooter',
    'identity.font': 'font',
    'identity.theme': 'embedColor',
    'texts.welcome': 'texts',
    'texts.welcomeTitle': 'texts',
    'texts.welcomeDescription': 'texts',
    'texts.goodbye': 'texts',
    'texts.goodbyeTitle': 'texts',
    'texts.goodbyeDescription': 'texts',
    'texts.buttonEmoji': 'texts',
    'channels.welcome': 'channels',
    'channels.goodbye': 'channels',
    'channels.logs': 'channels',
    'channels.tickets': 'channels',
    'channels.category': 'channels',
    'channels.autoNames': 'channels',
    'roles.mute': 'roles',
    'modules': 'modules',
    'cooldowns': 'cooldowns',
    'commandPerms': 'commandPerms'
};

const WELCOME_DEFAULT = {
    channel_id: null,
    embed_title: 'Bienvenue sur {guild}',
    embed_description: '{user.mention} nous a rejoint !',
    content_message: 'On acclame tous {user.mention} !\nNous sommes désormais {guild.count}.',
    enabled: false
};
const GOODBYE_DEFAULT = {
    channel_id: null,
    embed_title: 'Départ de {user}',
    embed_description: 'Triste de te voir partir...',
    content_message: '{user.mention} nous a quitté.\nNous sommes désormais {guild.count}.',
    enabled: false
};
const EMBED_DEFAULT = { color: 0x660099, footer: '', author: '', thumbnail: '', image: '' };

function asBool(value, fallback) {
    if (value === true || value === false) return value;
    return fallback;
}

function asText(value, max = 500) {
    return String(value || '').slice(0, max);
}

function asId(value) {
    const raw = String(value || '').trim();
    return /^\d{15,22}$/.test(raw) ? raw : '';
}

function parseColor(value, fallback = EMBED_DEFAULT.color) {
    if (typeof value === 'number' && Number.isFinite(value)) return value >>> 0;
    const raw = String(value || '').trim().replace(/^#/, '');
    if (!raw) return fallback;
    const n = Number.parseInt(raw, 16);
    return Number.isFinite(n) ? n : fallback;
}

function colorToHex(value, fallback = EMBED_DEFAULT.color) {
    return `#${parseColor(value, fallback).toString(16).padStart(6, '0')}`;
}

function hexOrEmpty(value) {
    const raw = String(value || '').trim();
    if (!raw) return '';
    return colorToHex(raw, 0);
}

function emptyInstall() {
    const out = {};
    for (const mod of MODULES) {
        out[mod.id] = { provision: 'manual', autoName: mod.autoName };
    }
    return out;
}

function emptyAllow() {
    return {
        displayName: false,
        avatar: false,
        embedColor: true,
        embedPalette: true,
        embedLogo: true,
        embedFooter: true,
        font: true,
        whiteLabel: false,
        texts: true,
        channels: true,
        roles: true,
        modules: false,
        cooldowns: false,
        commandPerms: false
    };
}

function emptyModules(defaultOn = true) {
    const out = {};
    for (const mod of MODULES) out[mod.id] = { enabled: defaultOn };
    return out;
}

function defaultConfig() {
    return {
        version: 1,
        identity: {
            displayName: '',
            activityType: 'playing',
            activityText: '',
            embedColor: '#660099',
            embedFooter: '',
            embedThumbnail: ''
        },
        install: emptyInstall(),
        allow: emptyAllow(),
        modules: emptyModules(true),
        limits: {
            autoCreatedMax: 20,
            premiumFonts: false
        }
    };
}

function emptyServer() {
    const autoNames = {};
    for (const mod of MODULES) autoNames[mod.id] = '';
    const modules = {};
    for (const mod of MODULES) modules[mod.id] = null;
    return {
        version: 1,
        identity: {
            displayName: '',
            avatarUrl: '',
            embedColor: '',
            colors: { success: '', error: '', warning: '', info: '' },
            logo: '',
            footerText: '',
            footerIcon: '',
            font: '',
            theme: ''
        },
        channels: { welcome: '', goodbye: '', logs: '', tickets: '', category: '', autoNames },
        roles: { mute: '' },
        texts: {
            welcome: '',
            welcomeTitle: '',
            welcomeDescription: '',
            goodbye: '',
            goodbyeTitle: '',
            goodbyeDescription: '',
            buttonEmoji: ''
        },
        modules,
        cooldowns: {},
        commandPerms: {}
    };
}

function normalizeInstall(raw) {
    const base = emptyInstall();
    const src = raw && typeof raw === 'object' ? raw : {};
    for (const mod of MODULES) {
        const item = src[mod.id] && typeof src[mod.id] === 'object' ? src[mod.id] : {};
        base[mod.id] = {
            provision: item.provision === 'auto' ? 'auto' : 'manual',
            autoName: asText(item.autoName || mod.autoName, 80)
        };
    }
    return base;
}

function normalizeAllow(raw) {
    const base = emptyAllow();
    const src = raw && typeof raw === 'object' ? raw : {};
    for (const key of ALLOW_KEYS) base[key] = asBool(src[key], base[key]);
    return base;
}

function normalizeDefault(raw) {
    const base = defaultConfig();
    const src = raw && typeof raw === 'object' ? raw : {};
    const identity = src.identity && typeof src.identity === 'object' ? src.identity : {};
    const activity = ACTIVITY_TYPES.includes(String(identity.activityType || ''))
        ? String(identity.activityType)
        : 'playing';
    return {
        version: 1,
        identity: {
            displayName: asText(identity.displayName, 32),
            activityType: activity,
            activityText: asText(identity.activityText, 120),
            embedColor: colorToHex(identity.embedColor || src.embed?.color, EMBED_DEFAULT.color),
            embedFooter: asText(identity.embedFooter ?? src.embed?.footer, 200),
            embedThumbnail: asText(identity.embedThumbnail ?? src.embed?.thumbnail, 400)
        },
        install: normalizeInstall(src.install),
        allow: normalizeAllow(src.allow),
        modules: (() => {
            const next = emptyModules(true);
            const incoming = src.modules && typeof src.modules === 'object' ? src.modules : {};
            for (const mod of MODULES) {
                const item = incoming[mod.id];
                if (item && typeof item === 'object') next[mod.id] = { enabled: asBool(item.enabled, true) };
                else if (typeof item === 'boolean') next[mod.id] = { enabled: item };
            }
            return next;
        })(),
        limits: {
            autoCreatedMax: Math.max(0, Math.min(100, Number(src.limits?.autoCreatedMax) || 20)),
            premiumFonts: asBool(src.limits?.premiumFonts, false)
        }
    };
}

function normalizeServer(raw) {
    const base = emptyServer();
    const src = raw && typeof raw === 'object' ? raw : {};
    const identity = src.identity && typeof src.identity === 'object' ? src.identity : {};
    const colors = identity.colors && typeof identity.colors === 'object' ? identity.colors : {};
    const channels = src.channels && typeof src.channels === 'object' ? src.channels : {};
    const autoNames = channels.autoNames && typeof channels.autoNames === 'object' ? channels.autoNames : {};
    const roles = src.roles && typeof src.roles === 'object' ? src.roles : {};
    const texts = src.texts && typeof src.texts === 'object' ? src.texts : {};
    const modules = src.modules && typeof src.modules === 'object' ? src.modules : {};
    const fontIds = new Set(FONTS.map((f) => f.id));
    const themeIds = new Set(Object.keys(THEMES));

    for (const mod of MODULES) {
        base.channels.autoNames[mod.id] = asText(autoNames[mod.id], 80);
        if (modules[mod.id] === true || modules[mod.id] === false) base.modules[mod.id] = modules[mod.id];
        else if (modules[mod.id] && typeof modules[mod.id] === 'object' && typeof modules[mod.id].enabled === 'boolean') {
            base.modules[mod.id] = modules[mod.id].enabled;
        }
    }

    const legacyWelcome = src.welcome && typeof src.welcome === 'object' ? src.welcome : {};
    const legacyGoodbye = src.goodbye && typeof src.goodbye === 'object' ? src.goodbye : {};
    const legacyEmbed = src.embed && typeof src.embed === 'object' ? src.embed : {};

    base.identity = {
        displayName: asText(identity.displayName, 32),
        avatarUrl: asText(identity.avatarUrl, 400),
        embedColor: hexOrEmpty(identity.embedColor || legacyEmbed.color),
        colors: {
            success: hexOrEmpty(colors.success),
            error: hexOrEmpty(colors.error),
            warning: hexOrEmpty(colors.warning),
            info: hexOrEmpty(colors.info)
        },
        logo: asText(identity.logo || legacyEmbed.thumbnail, 500),
        footerText: asText(identity.footerText || legacyEmbed.footer, 200),
        footerIcon: asText(identity.footerIcon, 400),
        font: fontIds.has(String(identity.font || '')) ? String(identity.font) : '',
        theme: themeIds.has(String(identity.theme || '')) ? String(identity.theme) : ''
    };
    base.channels.welcome = asId(channels.welcome || legacyWelcome.channel_id);
    base.channels.goodbye = asId(channels.goodbye || legacyGoodbye.channel_id);
    base.channels.logs = asId(channels.logs);
    base.channels.tickets = asId(channels.tickets);
    base.channels.category = asId(channels.category);
    base.roles.mute = asId(roles.mute);
    base.texts = {
        welcome: asText(texts.welcome || legacyWelcome.content_message, 1000),
        welcomeTitle: asText(texts.welcomeTitle || legacyWelcome.embed_title, 250),
        welcomeDescription: asText(texts.welcomeDescription || legacyWelcome.embed_description, 1000),
        goodbye: asText(texts.goodbye || legacyGoodbye.content_message, 1000),
        goodbyeTitle: asText(texts.goodbyeTitle || legacyGoodbye.embed_title, 250),
        goodbyeDescription: asText(texts.goodbyeDescription || legacyGoodbye.embed_description, 1000),
        buttonEmoji: asText(texts.buttonEmoji, 80)
    };
    if (src.cooldowns && typeof src.cooldowns === 'object') {
        for (const [key, val] of Object.entries(src.cooldowns)) {
            const n = Number(val);
            if (key && Number.isFinite(n)) base.cooldowns[asText(key, 40)] = Math.max(0, Math.min(3600, Math.trunc(n)));
        }
    }
    if (src.commandPerms && typeof src.commandPerms === 'object') {
        for (const [key, val] of Object.entries(src.commandPerms)) {
            base.commandPerms[asText(key, 40)] = asText(val, 80);
        }
    }
    return base;
}

function isAllowed(allow, key) {
    const flags = normalizeAllow(allow);
    if (flags[key]) return true;
    if (flags.whiteLabel && ['displayName', 'avatar', 'embedLogo', 'embedFooter'].includes(key)) return true;
    return false;
}

function lockedFields(allow) {
    const flags = normalizeAllow(allow);
    const locked = {};
    for (const [field, key] of Object.entries(FIELD_ALLOW)) {
        locked[field] = !isAllowed(flags, key);
    }
    return locked;
}

function pick(serverValue, defaultValue, allowed) {
    if (!allowed) return defaultValue;
    if (serverValue === null || serverValue === undefined || serverValue === '') return defaultValue;
    return serverValue;
}

function resolveConfig(defaultsRaw, serverRaw) {
    const defaults = normalizeDefault(defaultsRaw);
    const server = normalizeServer(serverRaw);
    const allow = defaults.allow;
    const theme = THEMES[server.identity.theme] || null;
    const themeColor = theme?.embedColor || defaults.identity.embedColor;
    const themeColors = theme?.colors || { success: '#3f6b52', error: '#a8462f', warning: '#b8823d', info: '#5c6a66' };

    const modules = {};
    for (const mod of MODULES) {
        const fallback = defaults.modules[mod.id]?.enabled !== false;
        modules[mod.id] = pick(server.modules[mod.id], fallback, isAllowed(allow, 'modules'));
    }

    const autoNames = {};
    for (const mod of MODULES) {
        autoNames[mod.id] = pick(
            server.channels.autoNames[mod.id],
            defaults.install[mod.id].autoName,
            isAllowed(allow, 'channels')
        );
    }

    return {
        version: 1,
        identity: {
            displayName: pick(server.identity.displayName, defaults.identity.displayName, isAllowed(allow, 'displayName')),
            avatarUrl: pick(server.identity.avatarUrl, '', isAllowed(allow, 'avatar')),
            activityType: defaults.identity.activityType,
            activityText: defaults.identity.activityText,
            embedColor: pick(server.identity.embedColor, themeColor, isAllowed(allow, 'embedColor')),
            colors: {
                success: pick(server.identity.colors.success, themeColors.success, isAllowed(allow, 'embedPalette')),
                error: pick(server.identity.colors.error, themeColors.error, isAllowed(allow, 'embedPalette')),
                warning: pick(server.identity.colors.warning, themeColors.warning, isAllowed(allow, 'embedPalette')),
                info: pick(server.identity.colors.info, themeColors.info, isAllowed(allow, 'embedPalette'))
            },
            logo: pick(server.identity.logo, defaults.identity.embedThumbnail, isAllowed(allow, 'embedLogo')),
            footerText: pick(server.identity.footerText, defaults.identity.embedFooter, isAllowed(allow, 'embedFooter')),
            footerIcon: pick(server.identity.footerIcon, '', isAllowed(allow, 'embedFooter')),
            font: pick(server.identity.font, 'ibm-plex-sans', isAllowed(allow, 'font')),
            theme: server.identity.theme
        },
        install: defaults.install,
        channels: {
            welcome: pick(server.channels.welcome, '', isAllowed(allow, 'channels')),
            goodbye: pick(server.channels.goodbye, '', isAllowed(allow, 'channels')),
            logs: pick(server.channels.logs, '', isAllowed(allow, 'channels')),
            tickets: pick(server.channels.tickets, '', isAllowed(allow, 'channels')),
            category: pick(server.channels.category, '', isAllowed(allow, 'channels')),
            autoNames
        },
        roles: {
            mute: pick(server.roles.mute, '', isAllowed(allow, 'roles'))
        },
        texts: {
            welcome: pick(server.texts.welcome, WELCOME_DEFAULT.content_message, isAllowed(allow, 'texts')),
            welcomeTitle: pick(server.texts.welcomeTitle, WELCOME_DEFAULT.embed_title, isAllowed(allow, 'texts')),
            welcomeDescription: pick(server.texts.welcomeDescription, WELCOME_DEFAULT.embed_description, isAllowed(allow, 'texts')),
            goodbye: pick(server.texts.goodbye, GOODBYE_DEFAULT.content_message, isAllowed(allow, 'texts')),
            goodbyeTitle: pick(server.texts.goodbyeTitle, GOODBYE_DEFAULT.embed_title, isAllowed(allow, 'texts')),
            goodbyeDescription: pick(server.texts.goodbyeDescription, GOODBYE_DEFAULT.embed_description, isAllowed(allow, 'texts')),
            buttonEmoji: pick(server.texts.buttonEmoji, '', isAllowed(allow, 'texts'))
        },
        modules,
        cooldowns: isAllowed(allow, 'cooldowns') ? server.cooldowns : {},
        commandPerms: isAllowed(allow, 'commandPerms') ? server.commandPerms : {},
        allow,
        limits: defaults.limits
    };
}

function deepMerge(base, patch) {
    if (patch === undefined) return base;
    if (!patch || typeof patch !== 'object' || Array.isArray(patch)) return patch;
    if (!base || typeof base !== 'object' || Array.isArray(base)) return { ...patch };
    const out = { ...base };
    for (const [key, value] of Object.entries(patch)) {
        if (value && typeof value === 'object' && !Array.isArray(value)) {
            out[key] = deepMerge(base[key], value);
        } else if (value !== undefined) {
            out[key] = value;
        }
    }
    return out;
}

function getPath(obj, dotted) {
    return dotted.split('.').reduce((acc, key) => (acc == null ? acc : acc[key]), obj);
}

function setPath(obj, dotted, value) {
    const parts = dotted.split('.');
    let cur = obj;
    for (let i = 0; i < parts.length - 1; i += 1) {
        if (!cur[parts[i]] || typeof cur[parts[i]] !== 'object') cur[parts[i]] = {};
        cur = cur[parts[i]];
    }
    cur[parts[parts.length - 1]] = value;
}

function applyServerPatch(existingRaw, patchRaw, allowRaw) {
    const existing = normalizeServer(existingRaw);
    const merged = normalizeServer(deepMerge(existing, patchRaw && typeof patchRaw === 'object' ? patchRaw : {}));
    const locked = lockedFields(allowRaw);
    const next = structuredClone(merged);
    for (const [field, isLocked] of Object.entries(locked)) {
        if (!isLocked) continue;
        const prev = getPath(existing, field);
        if (prev !== undefined) setPath(next, field, prev);
    }
    return normalizeServer(next);
}

function legacyBundle(resolved) {
    const welcomeChannel = resolved.channels.welcome || null;
    const goodbyeChannel = resolved.channels.goodbye || null;
    return {
        welcome: {
            ...WELCOME_DEFAULT,
            channel_id: welcomeChannel,
            embed_title: resolved.texts.welcomeTitle,
            embed_description: resolved.texts.welcomeDescription,
            content_message: resolved.texts.welcome,
            enabled: Boolean(welcomeChannel) && resolved.modules.welcome !== false
        },
        goodbye: {
            ...GOODBYE_DEFAULT,
            channel_id: goodbyeChannel,
            embed_title: resolved.texts.goodbyeTitle,
            embed_description: resolved.texts.goodbyeDescription,
            content_message: resolved.texts.goodbye,
            enabled: Boolean(goodbyeChannel) && resolved.modules.goodbye !== false
        },
        embed: {
            ...EMBED_DEFAULT,
            color: parseColor(resolved.identity.embedColor),
            footer: resolved.identity.footerText,
            author: resolved.identity.displayName,
            thumbnail: resolved.identity.logo,
            image: ''
        }
    };
}

function persistServer(server, resolved) {
    const bundle = legacyBundle(resolved);
    return {
        ...normalizeServer(server),
        welcome: bundle.welcome,
        goodbye: bundle.goodbye,
        embed: bundle.embed
    };
}

function commandNames() {
    try {
        const fs = require('node:fs');
        const path = require('node:path');
        const file = path.join(__dirname, '..', 'data', 'command-catalog.json');
        const data = JSON.parse(fs.readFileSync(file, 'utf8'));
        const names = [];
        for (const cat of data.categories || []) {
            for (const cmd of cat.commands || []) {
                const name = String(cmd.name || cmd.id || '').trim();
                if (name) names.push(name);
            }
        }
        return [...new Set(names)].sort();
    } catch {
        return [];
    }
}

function catalog() {
    return {
        fonts: FONTS,
        themes: Object.entries(THEMES).map(([id, value]) => ({ id, ...value })),
        modules: MODULES,
        allowKeys: ALLOW_KEYS,
        colorPresets: COLOR_PRESETS,
        activityTypes: ACTIVITY_TYPES,
        commandNames: commandNames()
    };
}

module.exports = {
    ACTIVITY_TYPES,
    FONTS,
    THEMES,
    COLOR_PRESETS,
    MODULES,
    ALLOW_KEYS,
    FIELD_ALLOW,
    WELCOME_DEFAULT,
    GOODBYE_DEFAULT,
    EMBED_DEFAULT,
    defaultConfig,
    emptyServer,
    normalizeDefault,
    normalizeServer,
    normalizeAllow,
    isAllowed,
    lockedFields,
    resolveConfig,
    applyServerPatch,
    legacyBundle,
    persistServer,
    parseColor,
    colorToHex,
    catalog
};
