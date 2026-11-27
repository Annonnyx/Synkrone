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
    '/cookies': 'Politique cookies de Synkrone : cookies strictement nécessaires, pas de publicité ni de traçage.',
    '/krones': 'Portefeuille Krônes : packs, rangs, hébergement et journal des mouvements.',
    '/login': 'Une seule connexion Synkrone : Discord, Google ou GitHub pour le site et l’hébergement.',
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

const PAGE_TITLES = {
    '/': 'Synkrone — Accueil',
    '/accueil': 'Synkrone — Accueil',
    '/faq': 'Synkrone — FAQ',
    '/stats': 'Synkrone — Statut',
    '/contact': 'Synkrone — Contact',
    '/cgu': 'Synkrone — CGU',
    '/cgv': 'Synkrone — CGV',
    '/cookies': 'Synkrone — Cookies',
    '/krones': 'Synkrone — Krônes',
    '/login': 'Connexion — Synkrone',
    '/discord': 'Synkrone — Bots',
    '/discord/bots': 'Synkrone — Bots',
    '/discord/bots/vax': 'Synkrone — Vax',
    '/discord/bots/arceus': 'Synkrone — Arceus',
    '/discord/bots/asuna': 'Synkrone — Asuna',
    '/discord/bots/kayaba': 'Synkrone — Kayaba',
    '/discord/bots/yui': 'Synkrone — Yui',
    '/discord/bots/bot': 'Synkrone — Créer un bot',
    '/discord/publicbot': 'Synkrone — Catalogue',
    '/discord/dashbot': 'Synkrone — Dashbot',
    '/discord/commandes': 'Synkrone — Commandes',
    '/discord/bump': 'Synkrone — Bump',
    '/discord/me': 'Synkrone — Me',
    '/minecraft': 'Synkrone — Minecraft',
    '/minecraft/serveur': 'Synkrone — Cantale',
    '/minecraft/modpack': 'Synkrone — Modpacks',
    '/minecraft/modpack/accueil': 'Synkrone — Modpacks',
    '/minecraft/modpack/xenus': 'Synkrone — Xenus',
    '/minecraft/modpack/thefrenchbaguette': 'Synkrone — The French Baguette',
    '/minecraft/modpack/vanipack': 'Synkrone — Vanipack',
    '/compte': 'Synkrone — Compte',
    '/serveur': 'Synkrone — Serveur'
};

const DEFAULT_IMAGE = `${SITE_ORIGIN}/logo/Synk_2B9348.png`;

const PAGE_IMAGES = {
    '/discord/bots/vax': `${SITE_ORIGIN}/assets/images/vax.png`,
    '/discord/bots/arceus': `${SITE_ORIGIN}/assets/images/arceus.png`,
    '/discord/bots/asuna': `${SITE_ORIGIN}/assets/images/asuna.png`,
    '/discord/bots/kayaba': `${SITE_ORIGIN}/assets/images/kayaba.png`,
    '/discord/bots/yui': `${SITE_ORIGIN}/assets/images/yui.png`,
    '/minecraft/serveur': `${SITE_ORIGIN}/assets/images/minecraft.png`,
    '/minecraft': `${SITE_ORIGIN}/assets/images/minecraft.png`,
    '/minecraft/modpack': `${SITE_ORIGIN}/assets/images/minecraft.png`,
    '/minecraft/modpack/accueil': `${SITE_ORIGIN}/assets/images/minecraft.png`,
    '/minecraft/modpack/xenus': `${SITE_ORIGIN}/assets/images/minecraft.png`,
    '/minecraft/modpack/thefrenchbaguette': `${SITE_ORIGIN}/assets/images/minecraft.png`,
    '/minecraft/modpack/vanipack': `${SITE_ORIGIN}/assets/images/minecraft.png`,
    '/discord/bump': `${SITE_ORIGIN}/assets/images/discord.png`,
    '/discord/me': `${SITE_ORIGIN}/assets/images/discord.png`,
    '/discord/publicbot': `${SITE_ORIGIN}/assets/images/discord.png`,
    '/discord/dashbot': `${SITE_ORIGIN}/assets/images/discord.png`,
    '/discord/commandes': `${SITE_ORIGIN}/assets/images/discord.png`,
    '/discord/bots': `${SITE_ORIGIN}/assets/images/discord.png`,
    '/discord': `${SITE_ORIGIN}/assets/images/discord.png`
};
const LEAF_BY_PATH = {
    '/': '/accueil/index.html',
    '/accueil': '/accueil/index.html',
    '/faq': '/faq/index.html',
    '/stats': '/stats/index.html',
    '/contact': '/contact.html',
    '/cgu': '/cgu.html',
    '/cgv': '/cgv.html',
    '/cookies': '/cookies.html',
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

// Pages récit : lissage du document (Lenis) + reveals batch. Tout le reste est un outil en scroll natif.
const STORY_PATHS = new Set(['/', '/accueil', '/discord', '/discord/bots', '/minecraft', '/minecraft/serveur']);

function shellAttrsForPath(pathname) {
    const current = normalizePath(pathname);
    if (frameSrcForPath(current)) return { scroll: 'stage', motion: 'off' };
    if (!leafForPath(current)) return { scroll: 'stage', motion: 'off' };
    return { scroll: 'doc', motion: STORY_PATHS.has(current) ? 'story' : 'off' };
}

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

function titleForPath(pathname) {
    const current = normalizePath(pathname);
    return PAGE_TITLES[current] || PAGE_TITLES['/'];
}

function imageForPath(pathname) {
    const current = normalizePath(pathname);
    return PAGE_IMAGES[current] || DEFAULT_IMAGE;
}

function escapeJsonLd(value) {
    return String(value || '').replace(/</g, '\\u003c');
}

function jsonLdForPath(pathname) {
    const current = normalizePath(pathname);
    const title = escapeJsonLd(titleForPath(current));
    const description = escapeJsonLd(descriptionForPath(current));
    const url = SITE_ORIGIN + (current === '/' ? '/' : current);
    const image = imageForPath(current);
    const base = {
        '@context': 'https://schema.org',
        '@type': 'WebPage',
        name: title,
        description,
        url,
        image,
        isPartOf: { '@type': 'WebSite', name: 'Synkrone', url: `${SITE_ORIGIN}/` }
    };
    if (current.startsWith('/discord/bots/')) {
        const slug = current.slice('/discord/bots/'.length);
        const names = { vax: 'Vax', arceus: 'Arceus', asuna: 'Asuna', kayaba: 'Kayaba', yui: 'Yui', bot: 'Créer un bot' };
        base['@type'] = 'SoftwareApplication';
        base.applicationCategory = 'CommunicationApplication';
        base.operatingSystem = 'Discord';
        base.offers = { '@type': 'Offer', price: '0', priceCurrency: 'EUR' };
        if (names[slug]) base.name = `Synkrone — ${names[slug]}`;
    }
    if (current === '/faq') {
        return {
            '@context': 'https://schema.org',
            '@type': 'FAQPage',
            name: title,
            description,
            url,
            image
        };
    }
    return base;
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

function applyMeta(shell, { title, description, pathname, image }) {
    const current = normalizePath(pathname);
    const url = SITE_ORIGIN + (current === '/' ? '/' : current);
    const resolvedTitle = title || titleForPath(current);
    const resolvedImage = image || imageForPath(current);
    let html = shell;
    if (resolvedTitle) {
        html = html.replace(/<title>[^<]*<\/title>/i, `<title>${resolvedTitle}</title>`);
        html = html.replace(/property="og:title" content="[^"]*"/, `property="og:title" content="${resolvedTitle}"`);
        html = html.replace(/name="twitter:title" content="[^"]*"/, `name="twitter:title" content="${resolvedTitle}"`);
    }
    if (description) {
        html = html.replace(/name="description" content="[^"]*"/, `name="description" content="${description}"`);
        html = html.replace(/property="og:description" content="[^"]*"/, `property="og:description" content="${description}"`);
        html = html.replace(/name="twitter:description" content="[^"]*"/, `name="twitter:description" content="${description}"`);
    }
    html = html.replace(/property="og:url" content="[^"]*"/, `property="og:url" content="${url}"`);
    html = html.replace(/rel="canonical" href="[^"]*"/, `rel="canonical" href="${url}"`);
    if (resolvedImage) {
        html = html.replace(/property="og:image" content="[^"]*"/, `property="og:image" content="${resolvedImage}"`);
        html = html.replace(/property="og:image:secure_url" content="[^"]*"/, `property="og:image:secure_url" content="${resolvedImage}"`);
        html = html.replace(/name="twitter:image" content="[^"]*"/, `name="twitter:image" content="${resolvedImage}"`);
        html = html.replace(/property="og:image:alt" content="[^"]*"/, `property="og:image:alt" content="${resolvedTitle}"`);
        html = html.replace(/name="twitter:image:alt" content="[^"]*"/, `name="twitter:image:alt" content="${resolvedTitle}"`);
    }
    const extra = `<script type="application/ld+json" data-leaf-jsonld="1">${JSON.stringify(jsonLdForPath(current))}</script>`;
    if (html.includes('data-leaf-jsonld="1"')) {
        html = html.replace(/<script type="application\/ld\+json" data-leaf-jsonld="1">[\s\S]*?<\/script>/, extra);
    } else if (html.includes('</head>')) {
        html = html.replace('</head>', `${extra}\n</head>`);
    }
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

function applyShellAttrs(html, attrs) {
    const { scroll, motion } = attrs || shellAttrsForPath('/');
    let next = String(html || '');
    if (/<html\b[^>]*\bdata-scroll=["']/.test(next)) {
        next = next
            .replace(/\sdata-scroll=["'][^"']*["']/, ` data-scroll="${scroll}"`)
            .replace(/\sdata-motion=["'][^"']*["']/, ` data-motion="${motion}"`);
        return next;
    }
    return next.replace(/<html\b([^>]*)>/i, `<html$1 data-scroll="${scroll}" data-motion="${motion}">`);
}

async function renderShell({ shellPath, publicDir, pathname }) {
    const shell = await fs.readFile(shellPath, 'utf8');
    const leafRel = leafForPath(pathname);
    const frameSrc = frameSrcForPath(pathname);
    const description = descriptionForPath(pathname);
    const title = titleForPath(pathname);
    const image = imageForPath(pathname);
    const attrs = shellAttrsForPath(pathname);
    if (frameSrc) {
        return applyShellAttrs(applyFrameShell(applyMeta(shell, { title, description, pathname, image }), frameSrc), attrs);
    }
    if (!leafRel) {
        return applyShellAttrs(applyMeta(shell, { title, description, pathname, image }), attrs);
    }
    let leafHtml = '';
    try {
        leafHtml = await fs.readFile(path.join(publicDir, leafRel.replace(/^\//, '')), 'utf8');
    } catch {
        return applyMeta(shell, { title, description, pathname, image });
    }
    const parts = extractLeafParts(leafHtml);
    const leafTitle = parts.title || title;
    const desc = parts.description || description;
    let html = applyMeta(shell, { title: leafTitle, description: desc, pathname, image });
    const markedHead = parts.headExtras.replace(/<(link|style)\b[^>]*>/gi, (tag) => {
        const attr = /accueil\.css/i.test(tag) ? 'shared' : '1';
        return tag.replace(/<(link|style)\b/i, `<$1 data-leaf-asset="${attr}"`);
    });
    html = html.replace('<!--LEAF_HEAD-->', markedHead);
    html = html.replace(
        /<div id="content-root"[^>]*>[\s\S]*?<\/div>\s*<!--LEAF_BODY-->/,
        `<div id="content-root" class="content-frame" data-leaf="${leafRel}">${parts.body}</div><!--LEAF_BODY-->`
    );
    return applyShellAttrs(html, attrs);
}

module.exports = {
    PAGE_DESCRIPTIONS,
    PAGE_TITLES,
    PAGE_IMAGES,
    DEFAULT_IMAGE,
    LEAF_BY_PATH,
    FRAME_BY_PATH,
    leafForPath,
    frameSrcForPath,
    isFramePath,
    descriptionForPath,
    titleForPath,
    imageForPath,
    jsonLdForPath,
    extractLeafParts,
    styleLeaksToChrome,
    renderShell,
    shellAttrsForPath,
    STORY_PATHS,
    SITE_ORIGIN
};
