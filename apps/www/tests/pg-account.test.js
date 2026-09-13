'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { mergeWalletState, pickPlan, oauthProviderLinks, SCHEMA_SQL } = require('../lib/pg-account');

test('wallet merge keeps the higher balance instead of summing duplicates', () => {
    const merged = mergeWalletState(
        { balance: 400, plan: 'Kronium', ledger: [{ id: 'a', at: 2 }], joinBonusAt: null },
        { balance: 150, plan: 'Aucun', ledger: [{ id: 'b', at: 1 }, { id: 'a', at: 2 }], joinBonusAt: 1 }
    );
    assert.equal(merged.balance, 400);
    assert.equal(merged.plan, 'Kronium');
    assert.equal(merged.ledger.length, 2);
    assert.equal(merged.joinBonusAt, 1);
});

test('higher grade wins when merging plans', () => {
    assert.equal(pickPlan('Kronium', 'Kronix'), 'Kronix');
    assert.equal(pickPlan('Aucun', 'Synkral'), 'Synkral');
});

test('hosting aggregation counts RUNNING services without inventing types', () => {
    const { hostingFromServiceRows } = require('../lib/pg-account');
    const hosting = hostingFromServiceRows([
        { type: 'discord', state: 'RUNNING', n: 2 },
        { type: 'minecraft', state: 'STOPPED', n: 1 }
    ]);
    assert.equal(hosting.discord, 2);
    assert.equal(hosting.minecraft, 1);
    assert.equal(hosting.total, 3);
    assert.equal(hosting.running, 2);
});

test('a Discord snowflake still yields an oauth link when the panel UUID already exists', () => {
    const links = oauthProviderLinks({
        id: '1368235294192570520',
        dbId: '70f4f7f6-df0a-4d0c-99f2-1a1c97fd1f68',
        username: 'Onyx'
    });
    assert.deepEqual(links[0], ['discord', '1368235294192570520']);
});

test('canonical panel user prefers the Discord owner over a stale Google UUID', () => {
    const { pickCanonicalUserId } = require('../lib/pg-account');
    assert.equal(
        pickCanonicalUserId(
            ['aaaaaaa1-bbbb-4ccc-8ddd-eeeeeeeeeee1', '70f4f7f6-df0a-4d0c-99f2-1a1c97fd1f68'],
            {
                snowflakeOwnerId: '70f4f7f6-df0a-4d0c-99f2-1a1c97fd1f68',
                dbId: 'aaaaaaa1-bbbb-4ccc-8ddd-eeeeeeeeeee1'
            }
        ),
        '70f4f7f6-df0a-4d0c-99f2-1a1c97fd1f68'
    );
});

test('site schema SQL creates the same account tables as the panel', () => {
    assert.match(SCHEMA_SQL, /CREATE TABLE IF NOT EXISTS site_profiles/);
    assert.match(SCHEMA_SQL, /CREATE TABLE IF NOT EXISTS wallets/);
    assert.match(SCHEMA_SQL, /CREATE TABLE IF NOT EXISTS wallet_ledger/);
});

test('site user ensure merges oauth taken by another uuid instead of skipping the link', () => {
    const fs = require('node:fs');
    const path = require('node:path');
    const source = fs.readFileSync(path.join(__dirname, '../lib/pg-account.js'), 'utf8');
    assert.match(source, /async function mergeDuplicateUsers/);
    assert.match(source, /findUserIdByDiscord/);
    assert.match(source, /preferFromProviders/);
    assert.match(source, /UPDATE services SET owner_id/);
});
