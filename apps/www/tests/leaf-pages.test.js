'use strict';

const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const assert = require('node:assert/strict');
const {
    LEAF_BY_PATH,
    FRAME_BY_PATH,
    leafForPath,
    frameSrcForPath,
    descriptionForPath,
    extractLeafParts,
    renderShell
} = require('../lib/leaf-pages');

const PUBLIC_DIR = path.join(__dirname, '..', '..', '..', 'Synkrone', 'test', 'synkrone_authdiscord', 'public');
const SHELL_PATH = path.join(PUBLIC_DIR, 'index.html');
const ISOLATED_MARKERS = /cdn\.tailwindcss|font-awesome|width:\s*100vw|html\s*,\s*body\s*\{[^}]{0,400}display\s*:\s*flex/i;

function walkHtml(dir, out = []) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) walkHtml(full, out);
        else if (entry.name.endsWith('.html')) out.push(full);
    }
    return out;
}

test('leafForPath maps canonical public URLs', () => {
    assert.equal(leafForPath('/'), '/accueil/index.html');
    assert.equal(leafForPath('/faq/'), '/faq/index.html');
    assert.equal(leafForPath('/discord/bots'), '/discord/bots/index.html');
    assert.equal(leafForPath('/discord/bots/vax'), null);
    assert.equal(leafForPath('/minecraft/modpack/xenus'), null);
    assert.equal(leafForPath('/discord/bump'), null);
    assert.equal(leafForPath('/discord/me'), null);
    assert.equal(leafForPath('/admin/annonce'), null);
});

test('frameSrcForPath keeps isolated apps in their own document', () => {
    assert.equal(frameSrcForPath('/discord/bump'), '/discord/bump/index.html');
    assert.equal(frameSrcForPath('/discord/me'), '/discord/me/index.html');
    assert.equal(frameSrcForPath('/discord/bots/vax'), '/discord/bots/vax.html');
    assert.equal(frameSrcForPath('/minecraft/modpack/xenus'), '/minecraft/modpack/index.html?tab=xenus');
    assert.equal(frameSrcForPath('/faq'), null);
    assert.equal(frameSrcForPath('/equipe/espace-travail/Projet/v1/kanban'), '/equipe/espace-travail/index.html');
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

test('shell keeps a content stage so accueil height survives iframe toggles', () => {
    const shell = fs.readFileSync(SHELL_PATH, 'utf8');
    assert.match(shell, /class="content-stage"/);
    assert.match(shell, /id="content-root"/);
    assert.match(shell, /id="content-frame"/);
});

test('renderShell injects accueil inside the leaf pane', async () => {
    const html = await renderShell({
        shellPath: SHELL_PATH,
        publicDir: PUBLIC_DIR,
        pathname: '/accueil'
    });
    const start = html.indexOf('id="content-root"');
    const end = html.indexOf('<!--LEAF_BODY-->');
    assert.ok(start > 0 && end > start);
    const pane = html.slice(start, end);
    assert.match(pane, /<h1>Synkrone<\/h1>/);
    assert.match(pane, /class="hero"/);
});

test('renderShell does not inject isolated app CSS into the chrome', async () => {
    const html = await renderShell({
        shellPath: SHELL_PATH,
        publicDir: PUBLIC_DIR,
        pathname: '/discord/bump'
    });
    assert.match(html, /id="content-frame"[^>]*src="\/discord\/bump\/index\.html"/);
    assert.doesNotMatch(html, /width:\s*100vw/);
    assert.doesNotMatch(html, /cdn\.tailwindcss\.com/);
});

test('isolated documents are never mapped as leaves', () => {
    const leaves = new Set(Object.values(LEAF_BY_PATH));
    const isolated = [];
    for (const file of walkHtml(PUBLIC_DIR)) {
        const rel = `/${path.relative(PUBLIC_DIR, file).replace(/\\/g, '/')}`;
        if (rel === '/index.html') continue;
        const html = fs.readFileSync(file, 'utf8');
        if (!ISOLATED_MARKERS.test(html)) continue;
        isolated.push(rel);
        assert.equal(leaves.has(rel), false, `${rel} casse le chrome si elle est injectée`);
    }
    assert.ok(isolated.includes('/discord/bump/index.html'));
});

test('public pages do not load the Tailwind Play CDN', () => {
    const hits = [];
    for (const file of walkHtml(PUBLIC_DIR)) {
        const html = fs.readFileSync(file, 'utf8');
        if (/cdn\.tailwindcss\.com/.test(html)) hits.push(path.relative(PUBLIC_DIR, file));
    }
    assert.deepEqual(hits, []);
});

test('every framed route stays framed and keeps Tailwind out of the shell', async () => {
    for (const pathname of Object.keys(FRAME_BY_PATH)) {
        assert.equal(leafForPath(pathname), null, pathname);
        assert.ok(frameSrcForPath(pathname), pathname);
        const html = await renderShell({
            shellPath: SHELL_PATH,
            publicDir: PUBLIC_DIR,
            pathname
        });
        assert.match(html, /id="content-frame"[^>]*src="/);
        assert.doesNotMatch(html, /cdn\.tailwindcss\.com/);
        assert.doesNotMatch(html, /font-awesome\/6/);
        assert.doesNotMatch(html, /width:\s*100vw/);
    }
});

test('extractLeafParts drops chrome-breaking CSS and scripts', () => {
    const html = `<!DOCTYPE html><html><head><title>X</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>html, body { width: 100vw; display: flex; } * { margin: 0; padding: 0; }</style>
        <style>.ok{color:green}</style></head>
        <body><h1>X</h1><script src="https://cdn.tailwindcss.com"></script></body></html>`;
    const parts = extractLeafParts(html);
    assert.match(parts.headExtras, /\.ok/);
    assert.doesNotMatch(parts.headExtras, /100vw/);
    assert.doesNotMatch(parts.headExtras, /font-awesome/);
    assert.doesNotMatch(parts.body, /tailwindcss/);
});

test('tw-local w-screen is a width, not a height', () => {
    const css = fs.readFileSync(path.join(PUBLIC_DIR, 'assets', 'tw-local.css'), 'utf8');
    const match = css.match(/\.w-screen\{[^}]+\}/);
    assert.ok(match, 'w-screen rule missing');
    assert.match(match[0], /width:\s*100%/);
    assert.doesNotMatch(match[0], /100vh/);
});

test('login is oauth-only and not a hosting-account split', () => {
    const html = fs.readFileSync(path.join(PUBLIC_DIR, 'login.html'), 'utf8');
    assert.doesNotMatch(html, /compte hébergement/i);
    assert.doesNotMatch(html, /panel-form/);
    assert.doesNotMatch(html, /\/hebergement\/api\/auth\/(login|register)/);
    assert.doesNotMatch(html, /sync-panel/);
    assert.match(html, /\/api\/auth\/attach-panel/);
    const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((row) => row[1]);
    assert.ok(scripts.length);
    for (const code of scripts) {
        assert.doesNotThrow(() => new Function(code));
    }
});

test('stats page script parses', () => {
    const html = fs.readFileSync(path.join(PUBLIC_DIR, 'stats', 'index.html'), 'utf8');
    const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((row) => row[1]);
    assert.ok(scripts.length);
    for (const code of scripts) {
        assert.doesNotThrow(() => new Function(code));
    }
});
