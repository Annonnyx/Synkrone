'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const {
    PRODUCTION_ORIGIN,
    isLoopbackOrigin,
    pickPublicOrigin,
    publicSiteOrigin,
    googleRedirectUri,
    githubRedirectUri,
    discordRedirectUri,
    panelOAuthRedirectUri
} = require('../lib/oauth-origin');

function withEnv(values, fn) {
    const prev = {};
    for (const key of Object.keys(values)) prev[key] = process.env[key];
    try {
        for (const [key, value] of Object.entries(values)) {
            if (value === undefined) delete process.env[key];
            else process.env[key] = value;
        }
        return fn();
    } finally {
        for (const [key, value] of Object.entries(prev)) {
            if (value === undefined) delete process.env[key];
            else process.env[key] = value;
        }
    }
}

const CLEAR = {
    PUBLIC_ORIGIN: undefined,
    PUBLIC_SITE_ORIGIN: undefined,
    SYNKRONE_PANEL_ORIGIN: undefined,
    ORBITAL_PUBLIC_ORIGIN: undefined,
    GOOGLE_REDIRECT_URI: undefined,
    GITHUB_REDIRECT_URI: undefined,
    DISCORD_REDIRECT_URI: undefined,
    NODE_ENV: 'development'
};

test('loopback OAuth URIs are ignored when a public origin exists', () => {
    withEnv({
        ...CLEAR,
        PUBLIC_ORIGIN: 'https://synkrone.app',
        GOOGLE_REDIRECT_URI: 'http://127.0.0.1:3668/auth/google/callback',
        GITHUB_REDIRECT_URI: 'http://127.0.0.1:3668/auth/github/callback',
        DISCORD_REDIRECT_URI: 'http://127.0.0.1:3668/auth/discord/callback',
        SYNKRONE_PANEL_ORIGIN: 'http://127.0.0.1:3668/hebergement'
    }, () => {
        assert.equal(googleRedirectUri(), 'https://synkrone.app/auth/google/callback');
        assert.equal(githubRedirectUri(), 'https://synkrone.app/auth/github/callback');
        assert.equal(discordRedirectUri(), 'https://synkrone.app/auth/discord/callback');
        assert.equal(
            panelOAuthRedirectUri('github', 3668),
            'https://synkrone.app/hebergement/api/auth/oauth/github/callback'
        );
        assert.equal(
            panelOAuthRedirectUri('google', 3668),
            'https://synkrone.app/hebergement/api/auth/oauth/google/callback'
        );
    });
});

test('a leftover localhost Google URI still yields synkrone.app in production', () => {
    withEnv({
        ...CLEAR,
        NODE_ENV: 'production',
        GOOGLE_REDIRECT_URI: 'http://127.0.0.1:3668/auth/google/callback',
        SYNKRONE_PANEL_ORIGIN: 'http://127.0.0.1:3668/hebergement'
    }, () => {
        assert.equal(googleRedirectUri(), `${PRODUCTION_ORIGIN}/auth/google/callback`);
        assert.equal(isLoopbackOrigin(googleRedirectUri()), false);
    });
});

test('SYNKRONE_PANEL_ORIGIN on synkrone.app is enough even without PUBLIC_ORIGIN', () => {
    withEnv({
        ...CLEAR,
        SYNKRONE_PANEL_ORIGIN: 'https://synkrone.app/hebergement',
        GOOGLE_REDIRECT_URI: 'http://127.0.0.1:3668/auth/google/callback'
    }, () => {
        assert.equal(publicSiteOrigin(), 'https://synkrone.app');
        assert.equal(googleRedirectUri(), 'https://synkrone.app/auth/google/callback');
    });
});

test('forwarded Host wins over a loopback listen address', () => {
    withEnv({
        ...CLEAR,
        GOOGLE_REDIRECT_URI: 'http://127.0.0.1:3668/auth/google/callback'
    }, () => {
        const req = {
            get(name) {
                if (name === 'x-forwarded-host') return 'synkrone.app';
                if (name === 'x-forwarded-proto') return 'https';
                if (name === 'host') return '127.0.0.1:3668';
                return '';
            }
        };
        assert.equal(googleRedirectUri(req), 'https://synkrone.app/auth/google/callback');
    });
});

test('local development still uses loopback when that is all that exists', () => {
    withEnv({
        ...CLEAR,
        GOOGLE_REDIRECT_URI: 'http://127.0.0.1:3668/auth/google/callback'
    }, () => {
        assert.equal(pickPublicOrigin(['http://127.0.0.1:3668'], { NODE_ENV: 'development' }), 'http://127.0.0.1:3668');
        assert.equal(googleRedirectUri(), 'http://127.0.0.1:3668/auth/google/callback');
    });
});
