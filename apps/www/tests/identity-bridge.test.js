'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { panelBridgeFromSiteUser } = require('../lib/identity-bridge');

test('discord snowflake site users bridge as discord', () => {
    const bridge = panelBridgeFromSiteUser({
        id: '1368235294192570520',
        username: 'Onyx',
        avatar: '/a.png',
        email: 'a@b.c'
    });
    assert.equal(bridge.provider, 'discord');
    assert.equal(bridge.profile.id, '1368235294192570520');
});

test('github and google prefixed ids bridge without a fake panel user', () => {
    assert.equal(panelBridgeFromSiteUser({ id: 'github:99', username: 'octo' }).provider, 'github');
    assert.equal(panelBridgeFromSiteUser({ id: 'google:abc', username: 'g' }).profile.id, 'abc');
});

test('guests and email-only panel shadows do not bridge', () => {
    assert.equal(panelBridgeFromSiteUser({ id: 'guest', isGuest: true, username: 'Visiteur' }), null);
    assert.equal(panelBridgeFromSiteUser({ id: 'google:panel-uuid', username: 'Mail' }), null);
    assert.equal(panelBridgeFromSiteUser(null), null);
});

test('express panel cookie lasts three weeks in milliseconds', () => {
    const { panelCookieOptions, SESSION_MAX_AGE_MS } = require('../lib/identity-bridge');
    assert.equal(panelCookieOptions(false).maxAge, SESSION_MAX_AGE_MS);
    assert.equal(SESSION_MAX_AGE_MS, 21 * 24 * 60 * 60 * 1000);
});
