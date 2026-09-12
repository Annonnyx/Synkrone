'use strict';

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const test = require('node:test');
const { verifyToken, serveurPathFromQuery, isGuildAdminFromSnapshot } = require('../lib/serveur');

function sign(payload, secret) {
    const raw = Buffer.from(JSON.stringify(payload), 'utf8');
    const b64 = raw.toString('base64url');
    const sig = crypto.createHmac('sha256', secret).update(b64).digest('hex').slice(0, 32);
    return `${b64}.${sig}`;
}

test('serveur return path keeps the signed token', () => {
    assert.equal(serveurPathFromQuery({ t: 'abc.def' }), '/serveur?t=abc.def');
    assert.equal(serveurPathFromQuery({ guild: '1', application: '2' }), '/serveur?guild=1&application=2');
    assert.equal(serveurPathFromQuery({}), '/serveur');
});

test('verifyToken accepts a live HMAC payload', () => {
    const prev = process.env.SESSION_SECRET;
    process.env.SESSION_SECRET = 'unit-test-session-secret';
    const token = sign({
        a: '111',
        exp: Math.floor(Date.now() / 1000) + 3600,
        g: '222',
        u: '333'
    }, 'unit-test-session-secret');
    const claims = verifyToken(token);
    process.env.SESSION_SECRET = prev;
    assert.deepEqual(claims, { guildId: '222', userId: '333', applicationId: '111' });
});

test('expired tokens are rejected', () => {
    const prev = process.env.SESSION_SECRET;
    process.env.SESSION_SECRET = 'unit-test-session-secret';
    const token = sign({
        a: '111',
        exp: Math.floor(Date.now() / 1000) - 10,
        g: '222',
        u: '333'
    }, 'unit-test-session-secret');
    const claims = verifyToken(token);
    process.env.SESSION_SECRET = prev;
    assert.equal(claims, null);
});

test('guild owner and administrator can configure a server', () => {
    assert.equal(isGuildAdminFromSnapshot({
        ownerId: '1',
        userId: '1',
        memberRoleIds: [],
        roles: []
    }), true);
    assert.equal(isGuildAdminFromSnapshot({
        ownerId: '1',
        userId: '2',
        memberRoleIds: ['r-admin'],
        roles: [{ id: 'r-admin', permissions: String(0x8) }]
    }), true);
    assert.equal(isGuildAdminFromSnapshot({
        ownerId: '1',
        userId: '2',
        memberRoleIds: ['r-manage'],
        roles: [{ id: 'r-manage', permissions: String(0x20) }]
    }), true);
    assert.equal(isGuildAdminFromSnapshot({
        ownerId: '1',
        userId: '2',
        memberRoleIds: ['r-mod'],
        roles: [{ id: 'r-mod', permissions: String(0x4) }]
    }), false);
    assert.equal(isGuildAdminFromSnapshot({
        ownerId: '1',
        userId: '2',
        memberRoleIds: [],
        roles: [{ id: 'r-admin', permissions: String(0x8) }]
    }), false);
});
