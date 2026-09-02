const fs = require('fs');
const path = require('path');

const DATA_DIR = process.env.DATA_DIR
    ? path.resolve(process.env.DATA_DIR)
    : path.join(__dirname, '..', '..', 'templates', 'discord');

const SKIP_NAMES = new Set(['__pycache__', '.env', 'node_modules', '.git']);

const getCleanFiles = (dir) => {
    const results = [];
    if (!fs.existsSync(dir)) return results;

    const list = fs.readdirSync(dir);
    list.forEach(file => {
        if (SKIP_NAMES.has(file) || file.includes('__pycache__')) return;

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

function mountSharing(app) {
    app.post('/api/auth', (req, res) => {
        const expected = process.env.MDP;
        if (!expected) {
            return res.status(503).json({ success: false, message: 'MDP manquant' });
        }
        const { password } = req.body;
        if (password === expected) {
            res.json({ success: true });
        } else {
            res.status(401).json({ success: false, message: 'Accès refusé' });
        }
    });

    app.get('/api/explorer', (req, res) => {
        const expected = process.env.MDP;
        if (!expected) {
            return res.status(503).json({ error: 'MDP manquant' });
        }
        if (req.headers.authorization !== expected) {
            return res.status(401).json({ error: 'Non autorisé' });
        }

        try {
            const tree = getCleanFiles(DATA_DIR);
            res.json({ files: tree });
        } catch (err) {
            res.status(500).json({ error: 'Erreur lors de la lecture du template Discord' });
        }
    });
}

module.exports = { mountSharing, DATA_DIR };
