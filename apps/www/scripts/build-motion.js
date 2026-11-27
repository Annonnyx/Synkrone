'use strict';

const fs = require('node:fs');
const path = require('node:path');
const esbuild = require('esbuild');

const ROOT = path.join(__dirname, '..', '..', '..');
const PUBLIC = path.join(ROOT, 'Synkrone', 'test', 'synkrone_authdiscord', 'public');
const OUT_DIR = path.join(PUBLIC, 'assets');

async function build() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  await esbuild.build({
    entryPoints: [path.join(__dirname, '..', 'src', 'motion-entry.js')],
    bundle: true,
    format: 'iife',
    platform: 'browser',
    target: ['es2020'],
    minify: true,
    sourcemap: false,
    outfile: path.join(OUT_DIR, 'motion.js'),
    logLevel: 'info',
  });
  await esbuild.build({
    entryPoints: [path.join(__dirname, '..', 'src', 'status-chart-entry.js')],
    bundle: true,
    format: 'iife',
    platform: 'browser',
    target: ['es2020'],
    minify: true,
    sourcemap: false,
    outfile: path.join(OUT_DIR, 'status-chart.js'),
    logLevel: 'info',
  });
  console.log('motion.js + status-chart.js built');
}

build().catch((err) => {
  console.error(err);
  process.exit(1);
});
