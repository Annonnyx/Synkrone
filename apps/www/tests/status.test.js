'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { summarize, mergeHosting, formatUptime } = require('../lib/status');
const { hostingFromServiceRows } = require('../lib/pg-account');

test('uptime summary uses real day spans and 100% when the window is empty', () => {
    assert.equal(summarize({ days: {} }).pct, 100);
    const window = summarize({
        days: {
            '2026-09-11': { up: 86_400_000, down: 0 },
            '2026-09-12': { up: 86_000_000, down: 400_000 }
        }
    });
    assert.equal(window.bars.length, 2);
    assert.ok(window.pct < 100);
    assert.ok(window.pct > 99);
});

test('hosting rows from postgres fill discord/minecraft/web without inventing extras', () => {
    const hosting = hostingFromServiceRows([
        { type: 'discord', state: 'RUNNING', n: 2 },
        { type: 'minecraft', state: 'STOPPED', n: 1 },
        { type: 'web', state: 'RUNNING', n: 3 },
        { type: 'other', state: 'RUNNING', n: 1 }
    ]);
    assert.equal(hosting.discord, 2);
    assert.equal(hosting.minecraft, 1);
    assert.equal(hosting.web, 3);
    assert.equal(hosting.total, 7);
    assert.equal(hosting.running, 6);
});

test('hosting merge keeps the source that actually has services', () => {
    const empty = mergeHosting(null, { discord: 0, minecraft: 0, web: 0, total: 0, running: 0 });
    assert.equal(empty.total, 0);
    const picked = mergeHosting(
        { discord: 0, minecraft: 0, web: 0, total: 0, running: 0 },
        { discord: 4, minecraft: 1, web: 2, total: 7, running: 3 }
    );
    assert.equal(picked.discord, 4);
    assert.equal(picked.total, 7);
    assert.equal(picked.running, 3);
});

test('process uptime labels stay human', () => {
    assert.equal(formatUptime(45), '45 s');
    assert.equal(formatUptime(120), '2 min');
    assert.match(formatUptime(90000), /j/);
});
