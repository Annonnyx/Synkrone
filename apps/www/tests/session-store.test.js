'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const { FileSessionStore, SESSION_MAX_AGE_MS, safeSid } = require('../lib/session-store');

test('site session lasts three weeks', () => {
    assert.equal(SESSION_MAX_AGE_MS, 21 * 24 * 60 * 60 * 1000);
});

test('file store round-trips a session across get/set', async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sk-sess-'));
    const store = new FileSessionStore(dir);
    const sess = { user: { id: '1', username: 'A' }, cookie: { maxAge: SESSION_MAX_AGE_MS } };
    await new Promise((resolve, reject) => store.set('abc', sess, (err) => (err ? reject(err) : resolve())));
    const got = await new Promise((resolve, reject) => store.get('abc', (err, value) => (err ? reject(err) : resolve(value))));
    assert.equal(got.user.username, 'A');
    await new Promise((resolve, reject) => store.destroy('abc', (err) => (err ? reject(err) : resolve())));
    const missing = await new Promise((resolve, reject) => store.get('abc', (err, value) => (err ? reject(err) : resolve(value))));
    assert.equal(missing, null);
    fs.rmSync(dir, { recursive: true, force: true });
});

test('expired sessions are treated as missing', async () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sk-sess-'));
    const store = new FileSessionStore(dir);
    const file = path.join(dir, `${safeSid('old')}.json`);
    fs.writeFileSync(file, JSON.stringify({ sess: { user: { id: 'x' } }, expires: Date.now() - 1000 }));
    const got = await new Promise((resolve, reject) => store.get('old', (err, value) => (err ? reject(err) : resolve(value))));
    assert.equal(got, null);
    fs.rmSync(dir, { recursive: true, force: true });
});
