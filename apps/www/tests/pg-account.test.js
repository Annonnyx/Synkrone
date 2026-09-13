'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { mergeWalletState, pickPlan } = require('../lib/pg-account');

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
