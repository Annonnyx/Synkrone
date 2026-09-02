const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '..', 'ui', '.env') });
require('dotenv').config({ path: path.join(__dirname, '..', 'sharing', '.env') });
delete process.env.PORT;
require('dotenv').config({ path: path.join(__dirname, '.env') });

const express = require('express');
const { mountUi } = require('../ui/server');
const { mountSharing, DATA_DIR } = require('../sharing/server');

const app = express();
const PORT = process.env.PORT || 3668;
const WWW_DIR = __dirname;
const UI_DIR = path.join(__dirname, '..', 'ui');
const SHARING_DIR = path.join(__dirname, '..', 'sharing');

if (!process.env.PASSWORD) {
    console.warn('[local] PASSWORD manquant (apps/ui/.env ou apps/www/.env) — /ui/ refuse les connexions');
}
if (!process.env.MDP) {
    console.warn('[local] MDP manquant (apps/sharing/.env ou apps/www/.env) — /sharing/ refuse les connexions');
}

app.use(express.json());

mountUi(app);
mountSharing(app);

app.get('/', (req, res) => {
    res.redirect('/hub');
});

app.get('/hub', (req, res) => {
    res.sendFile(path.join(WWW_DIR, 'index.html'));
});

app.get(['/ui', '/ui/'], (req, res) => {
    res.sendFile(path.join(UI_DIR, 'index.html'));
});

app.get(['/sharing', '/sharing/'], (req, res) => {
    res.sendFile(path.join(SHARING_DIR, 'index.html'));
});

app.use('/ui', express.static(UI_DIR));
app.use('/sharing', express.static(SHARING_DIR));
app.use(express.static(WWW_DIR));

app.listen(PORT, '127.0.0.1', () => {
    console.log(`local (fichiers JSON + disque, aucune base distante)`);
    console.log(`  hub      : http://127.0.0.1:${PORT}/hub`);
    console.log(`  ui       : http://127.0.0.1:${PORT}/ui/`);
    console.log(`  sharing  : http://127.0.0.1:${PORT}/sharing/`);
    console.log(`  catalogue: ${DATA_DIR}`);
});
