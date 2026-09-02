const express = require('express');
const sqlite3 = require('sqlite3').verbose();
const cors = require('cors');
const path = require('path');

const app = express();
const PORT = 2001;

app.use(cors());
app.use(express.json());

// 1. Rendre le dossier actuel public pour servir index.html, vux.ico et le dossier assets/
app.use(express.static(path.join(__dirname)));

// 2. Route principale pour afficher la page web
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'vux.html'));
});

// Initialisation de la base de données SQLite
const db = new sqlite3.Database(path.join(__dirname, 'vux_stats.db'), (err) => {
    if (err) console.error("Erreur de base de données:", err.message);
    else console.log("Connecté à la base de données SQLite.");
});

// Création des tables
db.serialize(() => {
    db.run(`CREATE TABLE IF NOT EXISTS downloads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ip TEXT,
        timestamp TEXT
    )`);
    db.run(`CREATE TABLE IF NOT EXISTS likes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ip TEXT,
        timestamp TEXT
    )`);
});

// Fonctions utilitaires
function getWeekNumber(d) {
    const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
    const dayNum = date.getUTCDay() || 7;
    date.setUTCDate(date.getUTCDate() + 4 - dayNum);
    const yearStart = new Date(Date.UTC(date.getUTCFullYear(),0,1));
    return Math.ceil((((date - yearStart) / 86400000) + 1)/7);
}

function getMaxRecord(countsObj, formatLabel) {
    let maxCount = 0;
    let maxLabel = "Aucun";
    for (const [key, value] of Object.entries(countsObj)) {
        if (value > maxCount) { 
            maxCount = value; 
            maxLabel = formatLabel ? formatLabel(key) : key; 
        }
    }
    return { count: maxCount, label: maxLabel };
}

// API : Téléchargement (Max 1/Heure par IP)
app.post('/api/download', (req, res) => {
    const ip = req.headers['x-forwarded-for'] || req.socket.remoteAddress;
    const now = new Date();
    const oneHourAgo = new Date(now.getTime() - 60 * 60 * 1000).toISOString();

    db.get(`SELECT COUNT(*) as count FROM downloads WHERE ip = ? AND timestamp >= ?`, [ip, oneHourAgo], (err, row) => {
        if (err) return res.status(500).json({ error: "Erreur DB" });
        if (row.count > 0) {
            return res.status(429).json({ error: "Limite de 1 téléchargement par heure atteinte pour cette IP." });
        }

        db.run(`INSERT INTO downloads (ip, timestamp) VALUES (?, ?)`, [ip, now.toISOString()], function(err) {
            if (err) return res.status(500).json({ error: "Erreur d'insertion" });
            db.get(`SELECT COUNT(*) as total FROM downloads`, [], (err, rowTotal) => {
                res.json({ success: true, total: rowTotal.total });
            });
        });
    });
});

// API : Like (Max 1 par IP total)
app.post('/api/like', (req, res) => {
    const ip = req.headers['x-forwarded-for'] || req.socket.remoteAddress;
    const now = new Date();

    db.get(`SELECT COUNT(*) as count FROM likes WHERE ip = ?`, [ip], (err, row) => {
        if (err) return res.status(500).json({ error: "Erreur DB" });
        if (row.count > 0) {
            return res.status(429).json({ error: "Vous avez déjà aimé l'application." });
        }

        db.run(`INSERT INTO likes (ip, timestamp) VALUES (?, ?)`, [ip, now.toISOString()], function(err) {
            if (err) return res.status(500).json({ error: "Erreur d'insertion" });
            db.get(`SELECT COUNT(*) as total FROM likes`, [], (err, rowTotal) => {
                res.json({ success: true, totalLikes: rowTotal.total });
            });
        });
    });
});

// API : Récupérer toutes les statistiques
app.get('/api/stats', (req, res) => {
    const now = new Date();
    let current = { year: 0, month: 0, week: 0, day: 0, hour: 0 };
    let counts = { year: {}, month: {}, week: {}, day: {}, hour: {} };
    
    const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
    let chartTodayHours = new Array(24).fill(0);
    let chartWeekDays = new Array(7).fill(0);
    let chartMonthDays = new Array(daysInMonth).fill(0);
    let chartYearWeeks = new Array(53).fill(0);
    let chartYearMonths = new Array(12).fill(0);
    let chartGlobal = { [now.getFullYear()]: 0 };

    db.all(`SELECT timestamp FROM downloads`, [], (err, rows) => {
        if (err) return res.status(500).json({ error: "Erreur DB" });

        rows.forEach(row => {
            const d = new Date(row.timestamp);
            
            const y = d.getFullYear().toString();
            const m = `${y}-${(d.getMonth()+1).toString().padStart(2,'0')}`;
            const w = `${y}-S${getWeekNumber(d).toString().padStart(2,'0')}`;
            const day = `${m}-${d.getDate().toString().padStart(2,'0')}`;
            const h = `${day} ${d.getHours().toString().padStart(2,'0')}h`;

            counts.year[y] = (counts.year[y] || 0) + 1;
            counts.month[m] = (counts.month[m] || 0) + 1;
            counts.week[w] = (counts.week[w] || 0) + 1;
            counts.day[day] = (counts.day[day] || 0) + 1;
            counts.hour[h] = (counts.hour[h] || 0) + 1;

            const diffTime = now - d;
            const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
            const diffHours = Math.floor(diffTime / (1000 * 60 * 60));

            if (d.getFullYear() === now.getFullYear()) current.year++;
            if (d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear()) current.month++;
            if (diffDays <= 7) current.week++;
            if (d.getDate() === now.getDate() && d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear()) current.day++;
            if (diffHours < 1) current.hour++;

            chartGlobal[d.getFullYear()] = (chartGlobal[d.getFullYear()] || 0) + 1;

            if (d.getFullYear() === now.getFullYear()) {
                chartYearMonths[d.getMonth()]++;
                chartYearWeeks[getWeekNumber(d) - 1]++;
                if (d.getMonth() === now.getMonth()) {
                    chartMonthDays[d.getDate() - 1]++;
                    if (d.getDate() === now.getDate()) chartTodayHours[d.getHours()]++;
                }
                if (getWeekNumber(d) === getWeekNumber(now)) {
                    const dayIndex = d.getDay() === 0 ? 6 : d.getDay() - 1; 
                    chartWeekDays[dayIndex]++;
                }
            }
        });

        db.get(`SELECT COUNT(*) as totalLikes FROM likes`, [], (err, rowLikes) => {
            res.json({
                totalDownloads: rows.length,
                totalLikes: rowLikes ? rowLikes.totalLikes : 0,
                current: current,
                records: {
                    year: getMaxRecord(counts.year, k => `en ${k}`),
                    month: getMaxRecord(counts.month, k => `en ${k}`),
                    week: getMaxRecord(counts.week, k => k),
                    day: getMaxRecord(counts.day, k => `le ${k}`),
                    hour: getMaxRecord(counts.hour, k => `le ${k}`)
                },
                chartData: {
                    today: { labels: Array.from({length: 24}, (_, i) => `${i}h`), data: chartTodayHours, label: "Aujourd'hui (Heures)" },
                    week: { labels: ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'], data: chartWeekDays, label: "Cette semaine (Jours)" },
                    month: { labels: Array.from({length: daysInMonth}, (_, i) => `${i+1}`), data: chartMonthDays, label: "Ce mois (Jours)" },
                    yearWeeks: { labels: Array.from({length: 53}, (_, i) => `S${i+1}`), data: chartYearWeeks, label: "Cette année (Semaines)" },
                    yearMonths: { labels: ['Jan','Fév','Mar','Avr','Mai','Juin','Juil','Aoû','Sep','Oct','Nov','Déc'], data: chartYearMonths, label: "Cette année (Mois)" },
                    global: { labels: Object.keys(chartGlobal).sort(), data: Object.keys(chartGlobal).sort().map(k => chartGlobal[k]), label: "Global (Années)" }
                }
            });
        });
    });
});

app.listen(PORT, () => {
    console.log(`Serveur Vux démarré sur le port ${PORT} avec SQLite.`);
    console.log(`Page web accessible sur http://localhost:${PORT}`);
});