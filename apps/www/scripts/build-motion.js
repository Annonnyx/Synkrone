'use strict';

/**
 * Émet les deux bundles navigateur de la vitrine dans
 * `Synkrone/test/synkrone_authdiscord/public/assets/` :
 *   - motion.js        : gsap, ScrollTrigger, SplitText, lenis, anime.js v4 (imports nommés)
 *                        + motion.css (lenis/dist/lenis.css). Chargé si data-motion="story".
 *   - status-chart.js  : ECharts tree-shaké (imports profonds). Chargé sur /stats.
 *
 * Voisin de build-tw-local.js. La racine du dépôt ne dépend pas d'echarts :
 * les dépendances vivent dans apps/www (npm install --prefix apps/www).
 */
const fs = require('node:fs');
const path = require('node:path');
const esbuild = require('esbuild');

const ROOT = path.join(__dirname, '..', '..', '..');
const WWW = path.join(__dirname, '..');
const PUBLIC = path.join(ROOT, 'Synkrone', 'test', 'synkrone_authdiscord', 'public');
const OUT = path.join(PUBLIC, 'assets');

if (!fs.existsSync(path.join(WWW, 'node_modules'))) {
    console.error('build-motion: node_modules absent dans apps/www — lancer `npm install --prefix apps/www`.');
    process.exit(1);
}
if (!fs.existsSync(PUBLIC)) {
    console.error(`build-motion: dossier public introuvable (${PUBLIC}).`);
    process.exit(1);
}

fs.mkdirSync(OUT, { recursive: true });

const COMMON = {
    bundle: true,
    format: 'iife',
    target: ['es2019'],
    minify: true,
    legalComments: 'none',
    logLevel: 'silent',
    absWorkingDir: WWW,
    define: { 'process.env.NODE_ENV': '"production"' }
};

function build(name, entry) {
    const result = esbuild.buildSync({
        ...COMMON,
        entryPoints: [path.join(WWW, 'scripts', entry)],
        outfile: path.join(OUT, name),
        metafile: true
    });
    const bytes = fs.statSync(path.join(OUT, name)).size;
    console.log(`${name}: ${(bytes / 1024).toFixed(1)} Ko`);
    return result;
}

build('motion.js', 'motion.entry.js');
build('status-chart.js', 'chart.entry.js');

// CSS Lenis (lenis/dist/lenis.css) — copié tel quel à côté du bundle.
const lenisCss = path.join(WWW, 'node_modules', 'lenis', 'dist', 'lenis.css');
const cssOut = path.join(OUT, 'motion.css');
if (fs.existsSync(lenisCss)) {
    fs.copyFileSync(lenisCss, cssOut);
    console.log(`motion.css: ${(fs.statSync(cssOut).size / 1024).toFixed(1)} Ko (lenis/dist/lenis.css)`);
} else {
    console.warn('build-motion: lenis/dist/lenis.css introuvable dans apps/www/node_modules');
}
