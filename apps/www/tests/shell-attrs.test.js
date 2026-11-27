'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { shellAttrsForPath, renderShell, STORY_PATHS } = require('../lib/leaf-pages');

const PUBLIC_DIR = require('node:path').join(
    __dirname, '..', '..', '..', 'Synkrone', 'test', 'synkrone_authdiscord', 'public'
);
const SHELL_PATH = require('node:path').join(PUBLIC_DIR, 'index.html');

test('les routes récit reçoivent le scroll document et le mode story', () => {
    for (const route of ['/', '/accueil', '/discord', '/discord/bots', '/minecraft', '/minecraft/serveur']) {
        assert.deepEqual(shellAttrsForPath(route), { scroll: 'doc', motion: 'story' }, route);
    }
});

test('les feuilles outil restent en scroll natif, sans Lenis', () => {
    for (const route of ['/faq', '/stats', '/krones', '/login', '/contact', '/compte', '/serveur', '/cgu']) {
        assert.deepEqual(shellAttrsForPath(route), { scroll: 'doc', motion: 'off' }, route);
    }
});

test('les routes cadre et les chemins inconnus restent une scène viewport', () => {
    for (const route of [
        '/discord/bump', '/discord/me', '/discord/publicbot', '/discord/dashbot',
        '/discord/commandes', '/discord/bots/vax', '/minecraft/modpack/xenus',
        '/hebergement', '/equipe/cloud'
    ]) {
        assert.deepEqual(shellAttrsForPath(route), { scroll: 'stage', motion: 'off' }, route);
    }
});

test('aucun chemin à un seul segment n\'est traité comme une scène par défaut', () => {
    for (const route of ['/accueil', '/faq', '/stats', '/krones', '/login']) {
        assert.equal(shellAttrsForPath(route).scroll, 'doc', route);
    }
});

test('renderShell pose data-scroll et data-motion sur <html> sans toucher aux meta', async () => {
    const html = await renderShell({ shellPath: SHELL_PATH, publicDir: PUBLIC_DIR, pathname: '/krones' });
    assert.match(html, /<html[^>]*data-scroll="doc"/);
    assert.match(html, /<html[^>]*data-motion="off"/);
    assert.match(html, /<title>Synkrone — Krônes<\/title>/);
    assert.match(html, /rel="canonical" href="https:\/\/synkrone.app\/krones"/);

    const frame = await renderShell({ shellPath: SHELL_PATH, publicDir: PUBLIC_DIR, pathname: '/discord/bots/vax' });
    assert.match(frame, /<html[^>]*data-scroll="stage"/);
    assert.match(frame, /<html[^>]*data-motion="off"/);
    assert.match(frame, /<iframe id="content-frame"[^>]*src="\/discord\/bots\/vax\.html"/);

    const home = await renderShell({ shellPath: SHELL_PATH, publicDir: PUBLIC_DIR, pathname: '/' });
    assert.match(home, /<html[^>]*data-motion="story"/);
    assert.match(home, /<title>Synkrone — Accueil<\/title>/);
});

test('STORY_PATHS ne contient que les six routes récit', () => {
    assert.deepEqual([...STORY_PATHS].sort(), ['/accueil', '/discord', '/discord/bots', '/minecraft', '/minecraft/serveur', '/'].sort());
});
