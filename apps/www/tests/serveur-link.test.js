'use strict';

const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const test = require('node:test');
const { verifyToken, serveurPathFromQuery } = require('../lib/serveur');

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
