 const express = require('express');
const multer = require('multer');
const archiver = require('archiver');
const fs = require('fs');
const path = require('path');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 3000;
const UPLOADS_DIR = path.join(__dirname, 'uploads');
const DEFAULT_FOLDER = 'Vrac';
const DATA_FILE = path.join(__dirname, 'data.json');

// Création du dossier d'upload s'il n'existe pas
if (!fs.existsSync(UPLOADS_DIR)) fs.mkdirSync(UPLOADS_DIR);

// Stockage en mémoire
let imagesDB = []; 
let foldersDB = [DEFAULT_FOLDER];

function saveData() {
    fs.writeFileSync(DATA_FILE, JSON.stringify({ images: imagesDB, folders: foldersDB }, null, 2), 'utf8');
}

function loadData() {
    if (!fs.existsSync(DATA_FILE)) {
        saveData();
        return;
    }

    try {
        const raw = fs.readFileSync(DATA_FILE, 'utf8');
        const parsed = JSON.parse(raw);
        imagesDB = Array.isArray(parsed.images) ? parsed.images : [];
        foldersDB = Array.isArray(parsed.folders) && parsed.folders.length ? parsed.folders : [DEFAULT_FOLDER];

        if (foldersDB.includes('General') && !foldersDB.includes(DEFAULT_FOLDER)) {
            foldersDB = foldersDB.map(folder => folder === 'General' ? DEFAULT_FOLDER : folder);
        }

        const now = Date.now();
        imagesDB = imagesDB.map(image => {
            const normalizedFolder = normalizeFolderName(image.folder);
            const createdAt = Number.isFinite(image.createdAt)
                ? image.createdAt
                : (Number.isFinite(image.timestamp) ? image.timestamp : now);
            const updatedAt = Number.isFinite(image.updatedAt) ? image.updatedAt : createdAt;
            const hasNote = typeof image.description === 'string' && image.description.trim() !== '';
            const noteUpdatedAt = Number.isFinite(image.noteUpdatedAt)
                ? image.noteUpdatedAt
                : (hasNote ? updatedAt : null);

            return {
                ...image,
                folder: normalizedFolder === 'General' || !normalizedFolder ? DEFAULT_FOLDER : normalizedFolder,
                createdAt,
                updatedAt,
                noteUpdatedAt,
                timestamp: Number.isFinite(image.timestamp) ? image.timestamp : createdAt
            };
        });

        ensureFolderExists(DEFAULT_FOLDER);
        
        // Créer les dossiers physiques pour tous les dossiers
        foldersDB.forEach(folder => {
            const folderPath = getImageFolderPath(folder);
            if (!fs.existsSync(folderPath)) {
                fs.mkdirSync(folderPath, { recursive: true });
            }
        });
        
        saveData();
    } catch {
        imagesDB = [];
        foldersDB = [DEFAULT_FOLDER];
        saveData();
    }
}

app.use(express.json());
app.use(express.static(__dirname)); // Sert le frontend (index.html)
app.use('/uploads', express.static(UPLOADS_DIR));

// Middleware d'authentification
const authenticate = (req, res, next) => {
    const token = req.headers['x-auth'] || req.query['x-auth'];
    if (token !== process.env.PASSWORD) {
        return res.status(401).json({ error: 'Accès refusé' });
    }
    next();
};

// Configuration Multer
const storage = multer.diskStorage({
    destination: (req, file, cb) => cb(null, UPLOADS_DIR),
    filename: (req, file, cb) => {
        const uniqueSuffix = Date.now() + '-' + Math.round(Math.random() * 1E9);
        cb(null, uniqueSuffix + path.extname(file.originalname));
    }
});
const upload = multer({ storage });

function normalizeFolderName(value) {
    return (value || '').trim();
}

function ensureFolderExists(folderName) {
    if (!foldersDB.includes(folderName)) {
        foldersDB.push(folderName);
    }
}

function getImageFolderPath(folderName) {
    return path.join(UPLOADS_DIR, sanitizeFileNamePart(folderName));
}

function getImageFilePath(folderName, filename) {
    return path.join(getImageFolderPath(folderName), filename);
}

function resolveImageAbsolutePath(image) {
    if (!image || !image.filename) return null;

    const expectedPath = getImageFilePath(image.folder, image.filename);
    if (fs.existsSync(expectedPath)) {
        return expectedPath;
    }

    if (typeof image.url === 'string' && image.url.startsWith('/uploads/')) {
        const relativeUrlPath = image.url.replace('/uploads/', '');
        const urlPath = path.join(UPLOADS_DIR, relativeUrlPath);
        if (fs.existsSync(urlPath)) {
            return urlPath;
        }
    }

    let foundPath = null;
    let foundCount = 0;
    for (const folder of foldersDB) {
        const candidatePath = getImageFilePath(folder, image.filename);
        if (fs.existsSync(candidatePath)) {
            foundPath = candidatePath;
            foundCount += 1;
            if (foundCount > 1) return null;
        }
    }

    return foundCount === 1 ? foundPath : null;
}

function sanitizeFileNamePart(value) {
    const raw = String(value || '').trim();
    const sanitized = raw.replace(/[<>:"/\\|?*\x00-\x1F]/g, '_').replace(/\s+/g, ' ');
    return sanitized || 'fichier';
}

function getImageExtension(image) {
    const ext = path.extname(image.filename || '').trim();
    if (ext) return ext;
    const extFromUrl = path.extname(image.url || '').trim();
    return extFromUrl || '.jpg';
}

function buildUniqueUploadFileName(baseName, ext, folderName, options = {}) {
    const safeBase = sanitizeFileNamePart(baseName);
    const extension = (ext || '').trim() || '.jpg';
    const ignoreImageId = options.ignoreImageId || null;
    const ignoreFilename = (options.ignoreFilename || '').toLowerCase();
    const folderPath = getImageFolderPath(folderName);
    let counter = 1;

    while (true) {
        const suffix = counter === 1 ? '' : ` (${counter})`;
        const candidate = `${safeBase}${suffix}${extension}`;
        const candidateLower = candidate.toLowerCase();
        const candidatePath = path.join(folderPath, candidate);

        const usedByDb = imagesDB.some((img) => img.id !== ignoreImageId && img.folder === folderName && (img.filename || '').toLowerCase() === candidateLower);
        const existsOnDisk = fs.existsSync(candidatePath);
        const isIgnoredCurrentFile = ignoreFilename && candidateLower === ignoreFilename;

        if (!usedByDb && (!existsOnDisk || isIgnoredCurrentFile)) {
            return candidate;
        }

        counter += 1;
    }

}


function buildUniqueFileName(baseName, ext, usedNames) {
    let candidate = `${baseName}${ext}`;
    let counter = 2;

    while (usedNames.has(candidate.toLowerCase())) {
        candidate = `${baseName} (${counter})${ext}`;
        counter += 1;
    }

    usedNames.add(candidate.toLowerCase());
    return candidate;
}

function getImageFolderPath(folderName) {
    return path.join(UPLOADS_DIR, sanitizeFileNamePart(folderName));
}

function getImageFilePath(folderName, filename) {
    return path.join(getImageFolderPath(folderName), filename);
}

function appendImagesToArchive(archive, images, includeFolderPath) {
    const usedNames = new Set();

    images.forEach((image) => {
        if (!image.filename) return;

        const absolutePath = resolveImageAbsolutePath(image);
        if (!absolutePath) return;

        const safeBaseName = sanitizeFileNamePart(image.name);
        const ext = getImageExtension(image);
        const uniqueFileName = buildUniqueFileName(safeBaseName, ext, usedNames);
        const targetName = includeFolderPath
            ? `${sanitizeFileNamePart(image.folder)}/${uniqueFileName}`
            : uniqueFileName;

        archive.file(absolutePath, { name: targetName });
    });
}

function createZipArchive() {
    if (typeof archiver === 'function') {
        return archiver('zip', { zlib: { level: 9 } });
    }

    if (archiver && typeof archiver.ZipArchive === 'function') {
        return new archiver.ZipArchive({ zlib: { level: 9 } });
    }

    throw new Error('Module archiver incompatible');
}

loadData();

// Routes API
app.post('/api/login', (req, res) => {
    const { password } = req.body;
    if (password === process.env.PASSWORD) res.json({ success: true });
    else res.status(401).json({ success: false });
});

app.get('/api/images', authenticate, (req, res) => {
    res.json(imagesDB);
});

app.get('/api/folders', authenticate, (req, res) => {
    res.json(foldersDB);
});

app.post('/api/folders', authenticate, (req, res) => {
    const folderName = normalizeFolderName(req.body.name);

    if (!folderName) {
        return res.status(400).json({ error: 'Nom de dossier invalide' });
    }
    if (foldersDB.includes(folderName)) {
        return res.status(409).json({ error: 'Le dossier existe deja' });
    }

    // Créer le dossier physique
    const folderPath = getImageFolderPath(folderName);
    if (!fs.existsSync(folderPath)) {
        fs.mkdirSync(folderPath, { recursive: true });
    }

    foldersDB.push(folderName);
    saveData();
    res.status(201).json({ success: true, folder: folderName });
});

app.patch('/api/folders/:name', authenticate, (req, res) => {
    const oldName = normalizeFolderName(req.params.name);
    const newName = normalizeFolderName(req.body.newName);

    if (!oldName || !newName) {
        return res.status(400).json({ error: 'Nom de dossier invalide' });
    }
    if (oldName === DEFAULT_FOLDER) {
        return res.status(400).json({ error: 'Impossible de renommer le dossier par defaut' });
    }

    const folderIndex = foldersDB.findIndex(folder => folder === oldName);
    if (folderIndex === -1) {
        return res.status(404).json({ error: 'Dossier introuvable' });
    }
    if (foldersDB.includes(newName)) {
        return res.status(409).json({ error: 'Un dossier avec ce nom existe deja' });
    }

    // Renommer le dossier physique dans uploads/
    const oldFolderPath = getImageFolderPath(oldName);
    const newFolderPath = getImageFolderPath(newName);
    if (fs.existsSync(oldFolderPath)) {
        fs.renameSync(oldFolderPath, newFolderPath);
    } else {
        fs.mkdirSync(newFolderPath, { recursive: true });
    }

    foldersDB[folderIndex] = newName;
    imagesDB = imagesDB.map(image => {
        if (image.folder !== oldName) return image;
        return {
            ...image,
            folder: newName,
            url: `/uploads/${sanitizeFileNamePart(newName)}/${image.filename}`
        };
    });
    saveData();

    res.json({ success: true, folder: newName });
});

app.delete('/api/folders/:name', authenticate, (req, res) => {
    const folderName = normalizeFolderName(req.params.name);
    const mode = req.body && req.body.mode === 'delete' ? 'delete' : 'move';

    if (!folderName) {
        return res.status(400).json({ error: 'Nom de dossier invalide' });
    }
    if (folderName === DEFAULT_FOLDER) {
        return res.status(400).json({ error: 'Impossible de supprimer le dossier par defaut' });
    }

    const folderIndex = foldersDB.findIndex(folder => folder === folderName);
    if (folderIndex === -1) {
        return res.status(404).json({ error: 'Dossier introuvable' });
    }

    foldersDB.splice(folderIndex, 1);

    if (mode === 'delete') {
        const imagesToDelete = imagesDB.filter(image => image.folder === folderName);
        imagesToDelete.forEach(image => {
            const filePath = getImageFilePath(folderName, image.filename || '');
            if (image.filename && fs.existsSync(filePath)) {
                fs.unlinkSync(filePath);
            }
        });
        imagesDB = imagesDB.filter(image => image.folder !== folderName);
        
        // Supprimer le dossier physique
        const folderPath = getImageFolderPath(folderName);
        if (fs.existsSync(folderPath)) {
            fs.rmSync(folderPath, { recursive: true, force: true });
        }
    } else {
        // Mode move : déplacer les fichiers vers Vrac physiquement
        const destFolderPath = getImageFolderPath(DEFAULT_FOLDER);
        if (!fs.existsSync(destFolderPath)) {
            fs.mkdirSync(destFolderPath, { recursive: true });
        }

        imagesDB = imagesDB.map(image => {
            if (image.folder !== folderName) return image;

            if (image.filename) {
                const srcPath = getImageFilePath(folderName, image.filename);
                const destPath = getImageFilePath(DEFAULT_FOLDER, image.filename);
                if (fs.existsSync(srcPath)) {
                    fs.renameSync(srcPath, destPath);
                }
            }

            return {
                ...image,
                folder: DEFAULT_FOLDER,
                url: `/uploads/${sanitizeFileNamePart(DEFAULT_FOLDER)}/${image.filename}`
            };
        });

        // Supprimer le dossier physique maintenant vide
        const folderPath = getImageFolderPath(folderName);
        if (fs.existsSync(folderPath)) {
            fs.rmSync(folderPath, { recursive: true, force: true });
        }
    }

    saveData();

    res.json({ success: true, mode });
});

app.post('/api/images', authenticate, upload.array('images', 50), (req, res) => {
    const files = req.files || [];
    if (!files.length) {
        return res.status(400).json({ error: 'Fichier manquant' });
    }

    const folder = normalizeFolderName(req.body.folder) || DEFAULT_FOLDER;
    const baseName = (req.body.name || '').trim();
    const description = req.body.description || '';

    ensureFolderExists(folder);
    
    // Créer le dossier physique s'il n'existe pas
    const folderPath = getImageFolderPath(folder);
    if (!fs.existsSync(folderPath)) {
        fs.mkdirSync(folderPath, { recursive: true });
    }

    const createdImages = files.map((file, index) => {
        const autoName = path.parse(file.originalname).name || 'Sans nom';
        const requestedName = baseName
            ? (files.length > 1 ? `${baseName} ${index + 1}` : baseName)
            : autoName;

        const sourcePath = path.join(UPLOADS_DIR, file.filename);
        const extension = path.extname(file.originalname) || path.extname(file.filename) || '.jpg';
        const finalFilename = buildUniqueUploadFileName(requestedName, extension, folder);
        const targetPath = getImageFilePath(folder, finalFilename);

        if (sourcePath !== targetPath) {
            fs.renameSync(sourcePath, targetPath);
        }

        const finalName = path.parse(finalFilename).name;

        const now = Date.now();
        const newImage = {
            id: `${Date.now()}-${Math.round(Math.random() * 1E9)}`,
            name: finalName,
            description,
            folder,
            url: `/uploads/${sanitizeFileNamePart(folder)}/${finalFilename}`,
            filename: finalFilename,
            createdAt: now,
            updatedAt: now,
            noteUpdatedAt: description && description.trim() !== '' ? now : null,
            timestamp: now
        };

        imagesDB.push(newImage);
        return newImage;
    });

    saveData();

    res.status(201).json(createdImages);
});

app.patch('/api/images/:id', authenticate, (req, res) => {
    const image = imagesDB.find(img => img.id === req.params.id);
    if (!image) {
        return res.status(404).json({ error: 'Image introuvable' });
    }

    const nextName = typeof req.body.name === 'string' ? req.body.name.trim() : image.name;
    const nextDescription = typeof req.body.description === 'string' ? req.body.description : image.description;
    const requestedFolder = typeof req.body.folder === 'string' ? normalizeFolderName(req.body.folder) : image.folder;

    if (!nextName) {
        return res.status(400).json({ error: 'Nom invalide' });
    }

    if (!requestedFolder || !foldersDB.includes(requestedFolder)) {
        return res.status(400).json({ error: 'Dossier invalide' });
    }

    const oldAbsolutePath = getImageFilePath(image.folder, image.filename || '');
    const currentExt = path.extname(image.filename || '') || '.jpg';
    const targetFilename = buildUniqueUploadFileName(nextName, currentExt, requestedFolder, {
        ignoreImageId: image.id,
        ignoreFilename: image.filename
    });

    let folderChanged = image.folder !== requestedFolder;
    let targetAbsolutePath = getImageFilePath(requestedFolder, targetFilename);

    if (targetFilename !== image.filename || folderChanged) {
        if (!image.filename || !fs.existsSync(oldAbsolutePath)) {
            return res.status(404).json({ error: 'Fichier image introuvable pour renommage' });
        }

        // Créer le dossier de destination s'il n'existe pas
        const destFolderPath = getImageFolderPath(requestedFolder);
        if (!fs.existsSync(destFolderPath)) {
            fs.mkdirSync(destFolderPath, { recursive: true });
        }

        fs.renameSync(oldAbsolutePath, targetAbsolutePath);
        image.filename = targetFilename;
        image.url = `/uploads/${sanitizeFileNamePart(requestedFolder)}/${targetFilename}`;
    }

    const previousDescription = typeof image.description === 'string' ? image.description : '';
    const nameChanged = image.name !== path.parse(targetFilename).name;
    const descriptionChanged = previousDescription !== nextDescription;

    image.name = path.parse(image.filename).name;
    image.description = nextDescription;
    image.folder = requestedFolder;

    if (nameChanged || folderChanged || descriptionChanged) {
        image.updatedAt = Date.now();
    }
    if (descriptionChanged) {
        image.noteUpdatedAt = nextDescription && nextDescription.trim() !== '' ? Date.now() : null;
    }

    saveData();
    res.json({ success: true, image });
});

app.delete('/api/images/:id', authenticate, (req, res) => {
    const index = imagesDB.findIndex(img => img.id === req.params.id);
    if (index === -1) return res.status(404).json({ error: 'Introuvable' });
    
    const img = imagesDB[index];
    const filePath = getImageFilePath(img.folder, img.filename);
    
    // Suppression physique et mémoire
    if (fs.existsSync(filePath)) fs.unlinkSync(filePath);
    imagesDB.splice(index, 1);
    saveData();
    
    res.json({ success: true });
});

app.patch('/api/images/:id/move', authenticate, (req, res) => {
    const targetFolder = normalizeFolderName(req.body.folder);
    if (!targetFolder) {
        return res.status(400).json({ error: 'Dossier cible invalide' });
    }
    if (!foldersDB.includes(targetFolder)) {
        return res.status(404).json({ error: 'Dossier cible introuvable' });
    }

    const image = imagesDB.find(img => img.id === req.params.id);
    if (!image) {
        return res.status(404).json({ error: 'Image introuvable' });
    }

    const sourcePath = resolveImageAbsolutePath(image);
    if (!sourcePath) {
        return res.status(404).json({ error: 'Fichier image introuvable' });
    }

    const destFolderPath = getImageFolderPath(targetFolder);
    if (!fs.existsSync(destFolderPath)) {
        fs.mkdirSync(destFolderPath, { recursive: true });
    }

    const targetFilename = buildUniqueUploadFileName(image.name || path.parse(image.filename).name, getImageExtension(image), targetFolder, {
        ignoreImageId: image.id,
        ignoreFilename: image.filename
    });
    const destPath = getImageFilePath(targetFolder, targetFilename);

    if (sourcePath !== destPath) {
        fs.renameSync(sourcePath, destPath);
    }

    image.filename = targetFilename;
    image.folder = targetFolder;
    image.url = `/uploads/${sanitizeFileNamePart(targetFolder)}/${targetFilename}`;
    image.updatedAt = Date.now();
    saveData();
    res.json({ success: true, image });
});

app.get('/api/images/:id/download', authenticate, (req, res) => {
    const image = imagesDB.find((img) => img.id === req.params.id);
    if (!image) {
        return res.status(404).json({ error: 'Image introuvable' });
    }

    const absolutePath = resolveImageAbsolutePath(image);
    if (!absolutePath) {
        return res.status(404).json({ error: 'Fichier image introuvable' });
    }

    const displayedName = String(image.name || path.parse(image.filename || '').name || 'image').trim();
    const downloadName = `${displayedName}${getImageExtension(image)}`;
    res.download(absolutePath, downloadName);
});

app.get('/api/download/folders/:name', authenticate, (req, res) => {
    const folderName = normalizeFolderName(req.params.name);
    if (!folderName) {
        return res.status(400).json({ error: 'Nom de dossier invalide' });
    }
    if (!foldersDB.includes(folderName)) {
        return res.status(404).json({ error: 'Dossier introuvable' });
    }

    const images = imagesDB.filter((image) => image.folder === folderName);
    const zipName = `${sanitizeFileNamePart(folderName)}.zip`;

    res.attachment(zipName);
    const archive = createZipArchive();

    archive.on('error', () => {
        if (!res.headersSent) {
            res.status(500).json({ error: 'Erreur de creation de l archive' });
        } else {
            res.end();
        }
    });

    archive.pipe(res);
    appendImagesToArchive(archive, images, false);
    archive.finalize();
});

app.get('/api/download/all', authenticate, (req, res) => {
    const zipName = 'ui.Synkrone.app-all-dossiers.zip';

    res.attachment(zipName);
    const archive = createZipArchive();

    archive.on('error', () => {
        if (!res.headersSent) {
            res.status(500).json({ error: 'Erreur de creation de l archive' });
        } else {
            res.end();
        }
    });

    archive.pipe(res);
    appendImagesToArchive(archive, imagesDB, true);
    archive.finalize();
});

app.listen(PORT, () => console.log(`Synkrone App sur le port ${PORT}`));