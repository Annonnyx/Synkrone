'use strict';

const fs = require('node:fs');
const path = require('node:path');
const esbuild = require('esbuild');

const ROOT = path.join(__dirname, '..', '..', '..');
const WWW = path.join(__dirname, '..');
const ASSETS = path.join(ROOT, 'Synkrone', 'test', 'synkrone_authdiscord', 'public', 'assets');

esbuild.build({
    absWorkingDir: WWW,
    entryPoints: ['motion/motion.js', 'motion/status-chart.js'],
    bundle: true,
    format: 'esm',
    platform: 'browser',
    target: 'es2020',
    minify: true,
    outdir: ASSETS,
    entryNames: '[name]',
    legalComments: 'none'
}).then(() => {
    fs.copyFileSync(
        path.join(WWW, 'node_modules', 'lenis', 'dist', 'lenis.css'),
        path.join(ASSETS, 'lenis.css')
    );
    console.log('motion assets written');
}).catch((error) => {
    console.error(error);
    process.exit(1);
});
