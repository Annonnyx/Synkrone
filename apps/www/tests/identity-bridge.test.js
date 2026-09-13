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

test('panel UUID users still bridge Discord from providers', () => {
    const bridge = panelBridgeFromSiteUser({
        id: '70f4f7f6-df0a-4d0c-99f2-1a1c97fd1f68',
        dbId: '70f4f7f6-df0a-4d0c-99f2-1a1c97fd1f68',
        username: 'Onyx',
        providers: { discord: '1368235294192570520' }
    });
    assert.equal(bridge.provider, 'discord');
    assert.equal(bridge.profile.id, '1368235294192570520');
});

test('linking Google from a Discord site user still attaches the Discord panel user', () => {
    const { panelAttachPayload } = require('../lib/identity-bridge');
    const payload = panelAttachPayload(
        {
            id: '1368235294192570520',
            dbId: '70f4f7f6-df0a-4d0c-99f2-1a1c97fd1f68',
            username: 'Onyx',
            email: 'onyx@gmail.com',
            avatar: '/a.png',
            providers: { discord: '1368235294192570520' }
        },
        'google',
        { id: 'google-sub-1', username: 'Onyx', email: 'onyx@gmail.com' }
    );
    assert.equal(payload.provider, 'discord');
    assert.equal(payload.userId, '70f4f7f6-df0a-4d0c-99f2-1a1c97fd1f68');
    assert.equal(payload.profile.id, '1368235294192570520');
    assert.equal(payload.link.provider, 'google');
    assert.equal(payload.link.profile.id, 'google-sub-1');
});

test('a panel UUID without Discord is not invented as linked', () => {
    assert.equal(
        panelBridgeFromSiteUser({
            id: '70f4f7f6-df0a-4d0c-99f2-1a1c97fd1f68',
            username: 'Mail'
        }),
        null
    );
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
