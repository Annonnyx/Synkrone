const express = require('express');
const path = require('path');
const app = express();
const PORT = process.env.PORT || 3668;

// Permet de servir tous les fichiers statiques (ton index.html, ton dossier logo/, etc.)
app.use(express.static(path.join(__dirname, '.')));

// Route spécifique pour accéder au hub via /hub
app.get('/hub', (req, res) => {
    res.sendFile(path.join(__dirname, 'index.html'));
});

// Redirection automatique de la racine ( / ) vers /hub
app.get('/', (req, res) => {
    res.redirect('/hub');
});

// Lancement du serveur
app.listen(PORT, () => {
    console.log(`Serveur démarré avec succès ! Accède à ton hub sur : http://localhost:${PORT}/hub`);
});