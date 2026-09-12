'use strict';

const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const path = require('node:path');
const test = require('node:test');

test('shell forwards login and serveur query strings into the iframe', () => {
    const source = readFileSync(
        path.join(__dirname, '..', '..', '..', 'Synkrone', 'test', 'synkrone_authdiscord', 'public', 'index.html'),
        'utf8'
    );
    assert.match(source, /QUERY_LEAF_SECTIONS/);
    assert.match(source, /withSearch/);
    assert.match(source, /window\.location\.search/);
});
