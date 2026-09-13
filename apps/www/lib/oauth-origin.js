'use strict';

const PRODUCTION_ORIGIN = 'https://synkrone.app';
const LOCAL_ORIGIN = 'http://127.0.0.1:3668';
const PANEL_SUFFIX = '/hebergement';

function trimSlash(value) {
    return String(value || '').trim().replace(/\/$/, '');
}

function stripPanelSuffix(origin) {
    return trimSlash(origin).replace(/\/hebergement$/i, '');
}

function isLoopbackOrigin(value) {
    const raw = String(value || '').trim();
    if (!raw) return false;
    try {
        const url = new URL(raw.includes('://') ? raw : `http://${raw}`);
        const host = String(url.hostname || '').toLowerCase();
        return host === 'localhost' || host === '127.0.0.1' || host === '::1' || host === '0.0.0.0';
    } catch {
        return /^(https?:\/\/)?(127\.0\.0\.1|localhost|\[::1\]|::1|0\.0\.0\.0)(:|\/|$)/i.test(raw);
    }
}

function isProductionEnv(env = process.env) {
    return String(env.NODE_ENV || '').trim() === 'production';
}

function envOriginCandidates(env = process.env) {
    return [
        env.PUBLIC_SITE_ORIGIN,
        env.PUBLIC_ORIGIN,
        env.SYNKRONE_PANEL_ORIGIN,
        env.ORBITAL_PUBLIC_ORIGIN
    ];
}

function pickPublicOrigin(candidates, env = process.env) {
    const list = (candidates || []).map(trimSlash).filter(Boolean);
    const publicOne = list.find((item) => !isLoopbackOrigin(item));
    if (publicOne) return stripPanelSuffix(publicOne);
    if (isProductionEnv(env)) return PRODUCTION_ORIGIN;
    const first = list[0];
    return first ? stripPanelSuffix(first) : '';
}

function headerValue(req, name) {
    if (!req) return '';
    if (typeof req.get === 'function') return String(req.get(name) || '').trim();
    const headers = req.headers || {};
    const raw = headers[name] || headers[String(name).toLowerCase()];
    return String(Array.isArray(raw) ? raw[0] : raw || '').trim();
}

function requestOrigin(req) {
    const host = (headerValue(req, 'x-forwarded-host') || headerValue(req, 'host')).split(',')[0].trim();
    if (!host) return '';
    const proto = (
        headerValue(req, 'x-forwarded-proto')
        || headerValue(req, 'x-forwarded-protocol')
        || req.protocol
        || 'http'
    ).split(',')[0].trim() || 'http';
    return `${proto}://${host}`;
}

function publicSiteOriginFromEnv(env = process.env) {
    return pickPublicOrigin(envOriginCandidates(env), env);
}

function publicSiteOrigin(req, env = process.env) {
    return pickPublicOrigin([...envOriginCandidates(env), requestOrigin(req)], env) || LOCAL_ORIGIN;
}

function siteOAuthRedirectUri(req, envKey, callbackPath, env = process.env) {
    const explicit = trimSlash(env[envKey]);
    const derived = `${publicSiteOrigin(req, env)}${callbackPath.startsWith('/') ? callbackPath : `/${callbackPath}`}`;
    if (explicit && !isLoopbackOrigin(explicit)) return explicit;
    return derived;
}

function discordRedirectUri(req, env = process.env) {
    return siteOAuthRedirectUri(req, 'DISCORD_REDIRECT_URI', '/auth/discord/callback', env);
}

function githubRedirectUri(req, env = process.env) {
    return siteOAuthRedirectUri(req, 'GITHUB_REDIRECT_URI', '/auth/github/callback', env);
}

function googleRedirectUri(req, env = process.env) {
    return siteOAuthRedirectUri(req, 'GOOGLE_REDIRECT_URI', '/auth/google/callback', env);
}

function withPanelOrigin(origin) {
    const clean = stripPanelSuffix(origin) || LOCAL_ORIGIN;
    return `${clean}${PANEL_SUFFIX}`;
}

function panelPublicOrigin(publicPort, env = process.env) {
    const origin = pickPublicOrigin(envOriginCandidates(env), env)
        || `http://127.0.0.1:${Number(publicPort) || 3668}`;
    return withPanelOrigin(origin);
}

function panelOAuthRedirectUri(provider, publicPort, env = process.env) {
    return `${panelPublicOrigin(publicPort, env)}/api/auth/oauth/${provider}/callback`;
}

module.exports = {
    PRODUCTION_ORIGIN,
    LOCAL_ORIGIN,
    isLoopbackOrigin,
    pickPublicOrigin,
    publicSiteOriginFromEnv,
    publicSiteOrigin,
    requestOrigin,
    discordRedirectUri,
    githubRedirectUri,
    googleRedirectUri,
    panelPublicOrigin,
    panelOAuthRedirectUri,
    withPanelOrigin
};
