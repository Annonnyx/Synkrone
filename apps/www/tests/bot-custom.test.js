'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const {
    defaultConfig,
    normalizeDefault,
    normalizeServer,
    resolveConfig,
    applyServerPatch,
    lockedFields,
    isAllowed,
    legacyBundle,
    catalog
} = require('../lib/bot-custom');

test('each server option has a matching default allow toggle', () => {
    const locked = lockedFields(defaultConfig().allow);
    assert.equal(locked['identity.embedColor'], false);
    assert.equal(locked['identity.displayName'], true);
    assert.equal(locked['identity.avatarUrl'], true);
    assert.equal(locked['texts.welcome'], false);
    assert.equal(locked.modules, true);
});

test('whiteLabel unlocks branding fields', () => {
    assert.equal(isAllowed({ whiteLabel: true }, 'displayName'), true);
    assert.equal(isAllowed({ whiteLabel: true }, 'avatar'), true);
    assert.equal(isAllowed({ whiteLabel: false, displayName: false }, 'displayName'), false);
});

test('server color wins only when allowed', () => {
    const defaults = normalizeDefault({
        identity: { embedColor: '#3f6b52' },
        allow: { embedColor: true, texts: false }
    });
    const server = normalizeServer({
        identity: { embedColor: '#a8462f' },
        texts: { welcome: 'Salut {user}' }
    });
    const resolved = resolveConfig(defaults, server);
    assert.equal(resolved.identity.embedColor, '#a8462f');
    assert.match(resolved.texts.welcome, /On acclame/);
});

test('locked fields are restored when a server patch tries to change them', () => {
    const allow = { embedColor: false, texts: true };
    const existing = { identity: { embedColor: '#111111' }, texts: { welcome: 'a' } };
    const patched = applyServerPatch(existing, {
        identity: { embedColor: '#ffffff' },
        texts: { welcome: 'b' }
    }, allow);
    assert.equal(patched.identity.embedColor, '#111111');
    assert.equal(patched.texts.welcome, 'b');
});

test('legacy welcome files enable when a channel is set', () => {
    const resolved = resolveConfig(defaultConfig(), {
        channels: { welcome: '123456789012345678' },
        texts: { welcome: 'hello' }
    });
    const bundle = legacyBundle(resolved);
    assert.equal(bundle.welcome.enabled, true);
    assert.equal(bundle.welcome.channel_id, '123456789012345678');
    assert.equal(bundle.welcome.content_message, 'hello');
});

test('cooldowns and commandPerms follow allow toggles', () => {
    const open = resolveConfig(
        { allow: { cooldowns: true, commandPerms: true } },
        { cooldowns: { ban: 12 }, commandPerms: { ban: '99' } }
    );
    assert.equal(open.cooldowns.ban, 12);
    assert.equal(open.commandPerms.ban, '99');
    const closed = resolveConfig(
        { allow: { cooldowns: false, commandPerms: false } },
        { cooldowns: { ban: 12 }, commandPerms: { ban: '99' } }
    );
    assert.deepEqual(closed.cooldowns, {});
    assert.deepEqual(closed.commandPerms, {});
});

test('catalog lists command names for the server editor', () => {
    assert.ok(catalog().commandNames.includes('ban'));
});
