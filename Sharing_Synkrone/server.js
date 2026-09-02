require('dotenv').config();
const express = require('express');
const fs = require('fs');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 3000;
const EXPECTED_PWD = process.env.MDP || '2708';

app.use(express.json());
app.use(express.static(__dirname));

// API: Authentification
app.post('/api/auth', (req, res) => {
    const { password } = req.body;
    if (password === EXPECTED_PWD) {
        res.json({ success: true });
    } else {
        res.status(401).json({ success: false, message: "Accès refusé" });
    }
});

// Fonction récursive pour scanner et filtrer __pycache__
const getCleanFiles = (dir) => {
    const results = [];
    if (!fs.existsSync(dir)) return results;
    
    const list = fs.readdirSync(dir);
    list.forEach(file => {
        if (file === '__pycache__' || file.includes('__pycache__')) return;
        
        const filePath = path.join(dir, file);
        const stat = fs.statSync(filePath);
        if (stat && stat.isDirectory()) {
            results.push({
                name: file,
                type: 'directory',
                children: getCleanFiles(filePath)
            });
        } else {
            let content = "";
            try {
                content = fs.readFileSync(filePath, 'utf8');
            } catch (e) {
                content = "[Fichier binaire ou illisible]";
            }
            results.push({
                name: file,
                type: 'file',
                ext: path.extname(file),
                content: content
            });
        }
    });
    return results;
};

// API: Explorateur du dossier data
app.get('/api/explorer', (req, res) => {
    const authHeader = req.headers.authorization;
    if (authHeader !== EXPECTED_PWD) {
        return res.status(401).json({ error: "Non autorisé" });
    }

    const dataPath = path.join(__dirname, 'data');
    try {
        const tree = getCleanFiles(dataPath);
        res.json({ files: tree });
    } catch (err) {
        res.status(500).json({ error: "Erreur lors de la lecture du dossier data" });
    }
});

app.listen(PORT, () => {
    console.log(`[Synkrone Sharing] Serveur Node.js actif sur http://localhost:${PORT}`);
});