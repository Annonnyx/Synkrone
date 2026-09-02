const express = require('express');
const path = require('path');

const PORT = Number(process.env.VUX_PORT || 2001);
const VUX_DIR = __dirname;
const EXE_PATH = path.join(VUX_DIR, 'Vux.exe');
const ICO_PATH = path.join(VUX_DIR, 'vux.ico');
const HTML_PATH = path.join(VUX_DIR, 'vux.html');
const ASSETS_DIR = path.join(VUX_DIR, 'assets');
const DB_PATH = path.join(VUX_DIR, 'vux_stats.db');

let db = null;
try {
    const sqlite3 = require('sqlite3').verbose();
    db = new sqlite3.Database(DB_PATH, (err) => {
        if (err) {
            console.warn('[vux] SQLite indisponible:', err.message);
            db = null;
        } else {
            console.log('[vux] SQLite local:', DB_PATH);
        }
    });
} catch (error) {
    console.warn('[vux] module sqlite3 absent — page et Vux.exe servis, stats désactivées');
}

function getWeekNumber(d) {
    const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
    const dayNum = date.getUTCDay() || 7;
    date.setUTCDate(date.getUTCDate() + 4 - dayNum);
    const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
    return Math.ceil((((date - yearStart) / 86400000) + 1) / 7);
}

function getMaxRecord(countsObj, formatLabel) {
    let maxCount = 0;
    let maxLabel = 'Aucun';
    for (const [key, value] of Object.entries(countsObj)) {
        if (value > maxCount) {
            maxCount = value;
            maxLabel = formatLabel ? formatLabel(key) : key;
        }
    }
    return { count: maxCount, label: maxLabel };
}

function emptyStats() {
    const now = new Date();
    const daysInMonth = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
    return {
        totalDownloads: 0,
        totalLikes: 0,
        current: { year: 0, month: 0, week: 0, day: 0, hour: 0 },
        records: {
            year: { count: 0, label: 'Aucun' },
            month: { count: 0, label: 'Aucun' },
            week: { count: 0, label: 'Aucun' },
            day: { count: 0, label: 'Aucun' },
            hour: { count: 0, label: 'Aucun' }
        },
        chartData: {
            today: { labels: Array.from({ length: 24 }, (_, i) => `${i}h`), data: new Array(24).fill(0), label: "Aujourd'hui (Heures)" },
            week: { labels: ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'], data: new Array(7).fill(0), label: 'Cette semaine (Jours)' },
            month: { labels: Array.from({ length: daysInMonth }, (_, i) => `${i + 1}`), data: new Array(daysInMonth).fill(0), label: 'Ce mois (Jours)' },
            yearWeeks: { labels: Array.from({ length: 53 }, (_, i) => `S${i + 1}`), data: new Array(53).fill(0), label: 'Cette année (Semaines)' },
            yearMonths: { labels: ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Aoû', 'Sep', 'Oct', 'Nov', 'Déc'], data: new Array(12).fill(0), label: 'Cette année (Mois)' },
            global: { labels: [String(now.getFullYear())], data: [0], label: 'Global (Années)' }
        }
    };
}

function ensureTables() {
    if (!db) return;
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
}

function clientIp(req) {
    return req.headers['x-forwarded-for'] || req.socket.remoteAddress;
}

function mountVux(app) {
    ensureTables();

    app.post('/vux/api/download', (req, res) => {
        if (!db) return res.json({ success: true, total: 0 });
        const ip = clientIp(req);
        const now = new Date();
        const oneHourAgo = new Date(now.getTime() - 60 * 60 * 1000).toISOString();

        db.get(`SELECT COUNT(*) as count FROM downloads WHERE ip = ? AND timestamp >= ?`, [ip, oneHourAgo], (err, row) => {
            if (err) return res.status(500).json({ error: 'Erreur DB' });
            if (row.count > 0) {
                return res.status(429).json({ error: 'Limite de 1 téléchargement par heure atteinte pour cette IP.' });
            }

            db.run(`INSERT INTO downloads (ip, timestamp) VALUES (?, ?)`, [ip, now.toISOString()], function insertDownload(insertErr) {
                if (insertErr) return res.status(500).json({ error: "Erreur d'insertion" });
                db.get(`SELECT COUNT(*) as total FROM downloads`, [], (countErr, rowTotal) => {
                    if (countErr) return res.status(500).json({ error: 'Erreur DB' });
                    res.json({ success: true, total: rowTotal.total });
                });
            });
        });
    });

    app.post('/vux/api/like', (req, res) => {
        if (!db) return res.json({ success: true, totalLikes: 0 });
        const ip = clientIp(req);
        const now = new Date();

        db.get(`SELECT COUNT(*) as count FROM likes WHERE ip = ?`, [ip], (err, row) => {
            if (err) return res.status(500).json({ error: 'Erreur DB' });
            if (row.count > 0) {
                return res.status(429).json({ error: "Vous avez déjà aimé l'application." });
            }

            db.run(`INSERT INTO likes (ip, timestamp) VALUES (?, ?)`, [ip, now.toISOString()], function insertLike(insertErr) {
                if (insertErr) return res.status(500).json({ error: "Erreur d'insertion" });
                db.get(`SELECT COUNT(*) as total FROM likes`, [], (countErr, rowLikes) => {
                    if (countErr) return res.status(500).json({ error: 'Erreur DB' });
                    res.json({ success: true, totalLikes: rowLikes.total });
                });
            });
        });
    });

    app.get('/vux/api/stats', (req, res) => {
        if (!db) return res.json(emptyStats());
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
            if (err) return res.status(500).json({ error: 'Erreur DB' });

            rows.forEach((row) => {
                const d = new Date(row.timestamp);

                const y = d.getFullYear().toString();
                const m = `${y}-${(d.getMonth() + 1).toString().padStart(2, '0')}`;
                const w = `${y}-S${getWeekNumber(d).toString().padStart(2, '0')}`;
                const day = `${m}-${d.getDate().toString().padStart(2, '0')}`;
                const h = `${day} ${d.getHours().toString().padStart(2, '0')}h`;

                counts.year[y] = (counts.year[y] || 0) + 1;
                counts.month[m] = (counts.month[m] || 0) + 1;
                counts.week[w] = (counts.week[w] || 0) + 1;
                counts.day[day] = (counts.day[day] || 0) + 1;
                counts.hour[h] = (counts.hour[h] || 0) + 1;

                const diffTime = now - d;
                const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));
                const diffHours = Math.floor(diffTime / (1000 * 60 * 60));

                if (d.getFullYear() === now.getFullYear()) current.year += 1;
                if (d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear()) current.month += 1;
                if (diffDays <= 7) current.week += 1;
                if (d.getDate() === now.getDate() && d.getMonth() === now.getMonth() && d.getFullYear() === now.getFullYear()) current.day += 1;
                if (diffHours < 1) current.hour += 1;

                chartGlobal[d.getFullYear()] = (chartGlobal[d.getFullYear()] || 0) + 1;

                if (d.getFullYear() === now.getFullYear()) {
                    chartYearMonths[d.getMonth()] += 1;
                    chartYearWeeks[getWeekNumber(d) - 1] += 1;
                    if (d.getMonth() === now.getMonth()) {
                        chartMonthDays[d.getDate() - 1] += 1;
                        if (d.getDate() === now.getDate()) chartTodayHours[d.getHours()] += 1;
                    }
                    if (getWeekNumber(d) === getWeekNumber(now)) {
                        const dayIndex = d.getDay() === 0 ? 6 : d.getDay() - 1;
                        chartWeekDays[dayIndex] += 1;
                    }
                }
            });

            db.get(`SELECT COUNT(*) as totalLikes FROM likes`, [], (likeErr, rowLikes) => {
                if (likeErr) return res.status(500).json({ error: 'Erreur DB' });
                res.json({
                    totalDownloads: rows.length,
                    totalLikes: rowLikes ? rowLikes.totalLikes : 0,
                    current,
                    records: {
                        year: getMaxRecord(counts.year, (k) => `en ${k}`),
                        month: getMaxRecord(counts.month, (k) => `en ${k}`),
                        week: getMaxRecord(counts.week, (k) => k),
                        day: getMaxRecord(counts.day, (k) => `le ${k}`),
                        hour: getMaxRecord(counts.hour, (k) => `le ${k}`)
                    },
                    chartData: {
                        today: { labels: Array.from({ length: 24 }, (_, i) => `${i}h`), data: chartTodayHours, label: "Aujourd'hui (Heures)" },
                        week: { labels: ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim'], data: chartWeekDays, label: 'Cette semaine (Jours)' },
                        month: { labels: Array.from({ length: daysInMonth }, (_, i) => `${i + 1}`), data: chartMonthDays, label: 'Ce mois (Jours)' },
                        yearWeeks: { labels: Array.from({ length: 53 }, (_, i) => `S${i + 1}`), data: chartYearWeeks, label: 'Cette année (Semaines)' },
                        yearMonths: { labels: ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Aoû', 'Sep', 'Oct', 'Nov', 'Déc'], data: chartYearMonths, label: 'Cette année (Mois)' },
                        global: { labels: Object.keys(chartGlobal).sort(), data: Object.keys(chartGlobal).sort().map((k) => chartGlobal[k]), label: 'Global (Années)' }
                    }
                });
            });
        });
    });

    app.get(['/vux', '/vux/'], (req, res) => res.sendFile(HTML_PATH));
    app.get(['/vux/vux.exe', '/vux/Vux.exe'], (req, res) => {
        res.download(EXE_PATH, 'Vux.exe');
    });
    app.get('/vux/vux.ico', (req, res) => res.sendFile(ICO_PATH));
    app.use('/vux/assets', express.static(ASSETS_DIR));
}

module.exports = { mountVux };

if (require.main === module) {
    const standalone = express();
    standalone.use(express.json());
    mountVux(standalone);
    standalone.listen(PORT, '127.0.0.1', () => {
        console.log(`Serveur Vux http://127.0.0.1:${PORT}/vux/`);
    });
}
