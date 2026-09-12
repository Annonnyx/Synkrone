'use strict';

const fs = require('node:fs/promises');
const path = require('node:path');

const SITE_ORIGIN = 'https://synkrone.app';

const PAGE_DESCRIPTIONS = {
    '/': 'Hébergement de bots Discord, serveurs Minecraft et sites. Cinq bots officiels, listing Bump, profils Me, serveur Cantale et Krônes.',
    '/accueil': 'Hébergement de bots Discord, serveurs Minecraft et sites. Cinq bots officiels, listing Bump, profils Me, serveur Cantale et Krônes.',
    '/faq': 'Réponses courtes : compte, panel, Krônes, bots officiels, Bump, Cantale et support.',
    '/stats': 'Uptime mesuré sur 7 jours, machines du panel, catalogue, Bump et comptes — sans chiffre inventé.',
    '/contact': 'Ticket Discord pour un bug, un paiement ou la modération. Compte lié et présence sur le serveur Synkrone requis.',
    '/cgu': 'Conditions générales d’utilisation de Synkrone : compte, Krônes, rangs, données et modération.',
    '/cgv': 'Conditions générales de vente des packs de Krônes : prix TTC, délivrance, rétractation et médiation.',
    '/krones': 'Portefeuille Krônes : packs, rangs, hébergement et journal des mouvements.',
    '/login': 'Une seule connexion Synkrone : Discord, Google, GitHub ou e-mail pour le site et le panel.',
    '/discord/bots': 'Cinq bots officiels Synkrone : Vax, Arceus, Asuna, Kayaba et Yui. Fiches, préfixes et invitations.',
    '/discord/bots/vax': 'Vax — bot de modération Synkrone : warns, mutes, bans, tickets et journaux.',
    '/discord/bots/arceus': 'Arceus — bot Pokémon Synkrone : capture, combats et collection.',
    '/discord/bots/asuna': 'Asuna — bot de jeux Synkrone : mini-jeux, économie ludique et XP.',
    '/discord/bots/kayaba': 'Kayaba — bot de combat Synkrone : PvP cadré et progression.',
    '/discord/bots/yui': 'Yui — bot d’architecture Synkrone : salons, rôles et organisation.',
    '/discord/bots/bot': 'Créer et héberger votre propre bot Discord sur le panel Synkrone.',
    '/discord/publicbot': 'Catalogue public des bots communautaires Synkrone.',
    '/discord/dashbot': 'Dashbot : invitations et suivi des bots communautaires.',
    '/discord/commandes': 'Packs de commandes pour les bots Synkrone.',
    '/discord/bump': 'Listing public des serveurs Discord de la communauté Synkrone.',
    '/discord/me': 'Profils publics Me : se retrouver, visites, likes, mise en avant.',
    '/minecraft': 'Cantale, serveur Java 1.21 à trois vies, et trois modpacks à télécharger.',
    '/minecraft/serveur': 'Cantale — play.cantale.world, Java 1.21, factions, Cantox.',
    '/minecraft/modpack': 'Modpacks Synkrone : Xenus, The French Baguette et Vanipack.',
    '/minecraft/modpack/accueil': 'Modpacks Synkrone : Xenus, The French Baguette et Vanipack.',
    '/minecraft/modpack/xenus': 'Xenus — modpack skyblock 1.19.2, magie et techno.',
    '/minecraft/modpack/thefrenchbaguette': 'The French Baguette — modpack aventure FR, quêtes, 1.16.5.',
    '/minecraft/modpack/vanipack': 'Vanipack — vanilla+ 1.21.7 / 1.21.8.',
    '/compte': 'Votre espace Synkrone : liaisons, Krônes, services hébergés et serveurs.',
    '/serveur': 'Configurer un serveur où un bot officiel Synkrone est présent.'
};

const LEAF_BY_PATH = {
    '/': '/accueil/index.html',
    '/accueil': '/accueil/index.html',
    '/faq': '/faq/index.html',
    '/stats': '/stats/index.html',
    '/contact': '/contact.html',
    '/cgu': '/cgu.html',
    '/cgv': '/cgv.html',
    '/krones': '/krones/index.html',
    '/login': '/login.html',
    '/discord': '/discord/bots/index.html',
    '/discord/bots': '/discord/bots/index.html',
    '/minecraft': '/minecraft/serveur/index.html',
    '/minecraft/serveur': '/minecraft/serveur/index.html',
    '/compte': '/compte/index.html',
    '/serveur': '/serveur/index.html'
};

const FRAME_BY_PATH = {
    '/discord/publicbot': '/discord/publicbot/index.html',
    '/discord/dashbot': '/discord/dashbot/index.html',
    '/discord/commandes': '/discord/commandes/index.html',
    '/discord/bump': '/discord/bump/index.html',
    '/discord/me': '/discord/me/index.html',
    '/minecraft/modpack': '/minecraft/modpack/index.html',
    '/minecraft/modpack/accueil': '/minecraft/modpack/index.html?tab=accueil',
    '/minecraft/modpack/xenus': '/minecraft/modpack/index.html?tab=xenus',
    '/minecraft/modpack/thefrenchbaguette': '/minecraft/modpack/index.html?tab=thefrenchbaguette',
    '/minecraft/modpack/vanipack': '/minecraft/modpack/index.html?tab=vanipack',
    '/discord/bots/vax': '/discord/bots/vax.html',
    '/discord/bots/arceus': '/discord/bots/arceus.html',
    '/discord/bots/asuna': '/discord/bots/asuna.html',
    '/discord/bots/kayaba': '/discord/bots/kayaba.html',
    '/discord/bots/yui': '/discord/bots/yui.html',
    '/discord/bots/bot': '/discord/bots/bot.html',
    '/admin': '/admin/utilisateur/index.html',
    '/admin/utilisateur': '/admin/utilisateur/index.html',
    '/admin/annonce': '/admin/annonce/index.html',
    '/admin/pm2': '/admin/pm2/index.html',
    '/admin/plateforme': '/admin/plateforme/index.html',
    '/admin/services': '/admin/services/index.html',
    '/admin/tickets': '/admin/tickets/index.html',
    '/equipe': '/equipe/espace-travail/index.html',
    '/equipe/espace-travail': '/equipe/espace-travail/index.html',
    '/equipe/cloud': '/equipe/cloud/index.html'
};

const BOT_FRAME_SLUGS = new Set(['vax', 'arceus', 'asuna', 'kayaba', 'yui', 'bot']);

function normalizePath(pathname) {
    let value = String(pathname || '/');
    if (value.length > 1 && value.endsWith('/')) value = value.slice(0, -1);
    return value || '/';
}

function isFramePath(pathname) {
    return Boolean(frameSrcForPath(pathname));
}

function frameSrcForPath(pathname) {
    const current = normalizePath(pathname);
    if (FRAME_BY_PATH[current]) return FRAME_BY_PATH[current];
    if (current.startsWith('/discord/bots/')) {
        const slug = current.slice('/discord/bots/'.length);
        if (BOT_FRAME_SLUGS.has(slug)) return `/discord/bots/${slug}.html`;
    }
    if (current.startsWith('/minecraft/modpack/')) {
        const tab = current.slice('/minecraft/modpack/'.length);
        if (tab) return `/minecraft/modpack/index.html?tab=${encodeURIComponent(tab)}`;
    }
    if (current.startsWith('/equipe/cloud/') && current !== '/equipe/cloud') {
        const cloudPath = current.slice('/equipe/cloud/'.length);
        return `/equipe/cloud/index.html?cloudPath=${encodeURIComponent(cloudPath)}`;
    }
    if (current.startsWith('/admin/')) return FRAME_BY_PATH['/admin/utilisateur'];
    if (current.startsWith('/equipe/')) return FRAME_BY_PATH['/equipe/espace-travail'];
    return null;
}

function leafForPath(pathname) {
    const current = normalizePath(pathname);
    if (frameSrcForPath(current)) return null;
    if (LEAF_BY_PATH[current]) return LEAF_BY_PATH[current];
    return null;
}

function descriptionForPath(pathname) {
    const current = normalizePath(pathname);
    return PAGE_DESCRIPTIONS[current] || PAGE_DESCRIPTIONS['/'];
}

function extractTagInner(html, tag) {
    const match = String(html || '').match(new RegExp(`<${tag}[^>]*>([\\s\\S]*?)</${tag}>`, 'i'));
    return match ? match[1] : '';
}

function extractAttr(html, tag, attr) {
    const match = String(html || '').match(new RegExp(`<${tag}[^>]*\\s${attr}=["']([^"']+)["'][^>]*>`, 'i'));
    return match ? match[1] : '';
}

const CHROME_BREAKING_HREF = /fonts\.googleapis|fonts\.gstatic|font-awesome|cdnjs\.cloudflare|cdn\.tailwindcss|\/design\/synkrone\.css/i;
const CHROME_BREAKING_SCRIPT = /<script\b[^>]*\bsrc=["'][^"']*(?:tailwindcss|font-awesome|cdnjs\.cloudflare)[^"']*["'][^>]*>\s*<\/script>/gi;

function styleLeaksToChrome(css) {
    const text = String(css || '');
    if (/(?:html|body)[^{]*\{[^}]*(?:100vw|\bdisplay\s*:\s*flex\b)/i.test(text)) return true;
    if (/\*\s*\{[^}]*(?:margin\s*:\s*0)[^}]*padding\s*:\s*0/i.test(text)) return true;
    return false;
}

function extractLeafParts(html) {
    const head = extractTagInner(html, 'head');
    let body = extractTagInner(html, 'body') || String(html || '');
    body = body.replace(CHROME_BREAKING_SCRIPT, '');
    const links = [...head.matchAll(/<link\b[^>]*>/gi)]
        .map((row) => row[0])
        .filter((tag) => /rel=["']stylesheet["']/i.test(tag))
        .filter((tag) => !CHROME_BREAKING_HREF.test(tag));
    const styles = [...head.matchAll(/<style\b[\s\S]*?<\/style>/gi)]
        .map((row) => row[0])
        .filter((tag) => !styleLeaksToChrome(tag));
    const title = (extractTagInner(html, 'title') || '').trim();
    const description = extractAttr(head, 'meta', 'content') && /name=["']description["']/i.test(head)
        ? (head.match(/<meta[^>]*name=["']description["'][^>]*content=["']([^"']*)["'][^>]*>/i)
            || head.match(/<meta[^>]*content=["']([^"']*)["'][^>]*name=["']description["'][^>]*>/i)
            || [])[1]
        : '';
    return {
        title,
        description: description || '',
        headExtras: `${links.join('\n')}\n${styles.join('\n')}`.trim(),
        body
    };
}

function applyMeta(shell, { title, description, pathname }) {
    const url = SITE_ORIGIN + (normalizePath(pathname) === '/' ? '/' : normalizePath(pathname));
    let html = shell;
    if (title) {
        html = html.replace(/<title>[^<]*<\/title>/i, `<title>${title}</title>`);
        html = html.replace(/property="og:title" content="[^"]*"/, `property="og:title" content="${title}"`);
        html = html.replace(/name="twitter:title" content="[^"]*"/, `name="twitter:title" content="${title}"`);
    }
    if (description) {
        html = html.replace(/name="description" content="[^"]*"/, `name="description" content="${description}"`);
        html = html.replace(/property="og:description" content="[^"]*"/, `property="og:description" content="${description}"`);
        html = html.replace(/name="twitter:description" content="[^"]*"/, `name="twitter:description" content="${description}"`);
    }
    html = html.replace(/property="og:url" content="[^"]*"/, `property="og:url" content="${url}"`);
    html = html.replace(/rel="canonical" href="[^"]*"/, `rel="canonical" href="${url}"`);
    return html;
}

function applyFrameShell(html, frameSrc) {
    let next = html.replace(
        /<div id="content-root"[^>]*>[\s\S]*?<\/div>\s*<!--LEAF_BODY-->/,
        '<div id="content-root" class="content-frame hidden" data-leaf=""></div><!--LEAF_BODY-->'
    );
    next = next.replace(
        /<iframe id="content-frame"[^>]*>/,
        `<iframe id="content-frame" class="content-frame" title="Contenu de la section" src="${frameSrc}">`
    );
    return next;
}

async function renderShell({ shellPath, publicDir, pathname }) {
    const shell = await fs.readFile(shellPath, 'utf8');
    const leafRel = leafForPath(pathname);
    const frameSrc = frameSrcForPath(pathname);
    const description = descriptionForPath(pathname);
    if (frameSrc) {
        return applyFrameShell(applyMeta(shell, { title: '', description, pathname }), frameSrc);
    }
    if (!leafRel) {
        return applyMeta(shell, { title: '', description, pathname });
    }
    let leafHtml = '';
    try {
        leafHtml = await fs.readFile(path.join(publicDir, leafRel.replace(/^\//, '')), 'utf8');
    } catch {
        return applyMeta(shell, { title: '', description, pathname });
    }
    const parts = extractLeafParts(leafHtml);
    const title = parts.title || '';
    const desc = parts.description || description;
    let html = applyMeta(shell, { title, description: desc, pathname });
    const markedHead = parts.headExtras.replace(/<(link|style)\b[^>]*>/gi, (tag) => {
        const attr = /accueil\.css/i.test(tag) ? 'shared' : '1';
        return tag.replace(/<(link|style)\b/i, `<$1 data-leaf-asset="${attr}"`);
    });
    html = html.replace('<!--LEAF_HEAD-->', markedHead);
    html = html.replace(
        /<div id="content-root"[^>]*>[\s\S]*?<\/div>\s*<!--LEAF_BODY-->/,
        `<div id="content-root" class="content-frame" data-leaf="${leafRel}">${parts.body}</div><!--LEAF_BODY-->`
    );
    return html;
}

module.exports = {
    PAGE_DESCRIPTIONS,
    LEAF_BY_PATH,
    FRAME_BY_PATH,
    leafForPath,
    frameSrcForPath,
    isFramePath,
    descriptionForPath,
    extractLeafParts,
    styleLeaksToChrome,
    renderShell,
    SITE_ORIGIN
};
