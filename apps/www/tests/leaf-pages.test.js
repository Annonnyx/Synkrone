'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { leafForPath, descriptionForPath, extractLeafParts } = require('../lib/leaf-pages');

test('leafForPath maps canonical public URLs', () => {
    assert.equal(leafForPath('/'), '/accueil/index.html');
    assert.equal(leafForPath('/faq/'), '/faq/index.html');
    assert.equal(leafForPath('/discord/bots/vax'), '/discord/bots/vax.html');
    assert.equal(leafForPath('/minecraft/modpack/xenus'), '/minecraft/modpack/xenus.html');
});

test('descriptionForPath is distinct per section', () => {
    assert.notEqual(descriptionForPath('/faq'), descriptionForPath('/stats'));
    assert.match(descriptionForPath('/krones'), /Krônes/);
});

test('extractLeafParts keeps body text and styles', () => {
    const html = `<!DOCTYPE html><html><head><title>Synkrone — FAQ</title>
        <meta name="description" content="Réponses courtes.">
        <link rel="stylesheet" href="/assets/accueil.css">
        <style>.x{color:red}</style></head>
        <body><h1>FAQ</h1><p>Compte</p></body></html>`;
    const parts = extractLeafParts(html);
    assert.match(parts.body, /<h1>FAQ<\/h1>/);
    assert.match(parts.headExtras, /accueil\.css/);
    assert.equal(parts.title, 'Synkrone — FAQ');
    assert.equal(parts.description, 'Réponses courtes.');
});
