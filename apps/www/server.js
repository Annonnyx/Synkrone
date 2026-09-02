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

app.listen(PORT, () => {
    console.log(`synkrone.app : http://localhost:${PORT}/hub`);
    console.log(`  ui       : http://localhost:${PORT}/ui/`);
    console.log(`  sharing  : http://localhost:${PORT}/sharing/`);
    console.log(`  catalogue: ${DATA_DIR}`);
});
