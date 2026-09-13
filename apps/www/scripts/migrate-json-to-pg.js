#!/usr/bin/env node
'use strict';

const pgAccount = require('../lib/pg-account');

if (!pgAccount.isConfigured()) {
    console.error('DATABASE_URL manquant (panel .env).');
    process.exit(1);
}

pgAccount.ensureReady()
    .then(() => {
        console.log('Postgres prêt : comptes et Krônes sont sur la même base que les services.');
    })
    .catch((err) => {
        console.error(err);
        process.exit(1);
    });
