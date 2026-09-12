'use strict';

const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.join(__dirname, '..', '..', '..');
const PUBLIC = path.join(ROOT, 'Synkrone', 'test', 'synkrone_authdiscord', 'public');
const OUT = path.join(PUBLIC, 'assets', 'tw-local.css');

const FILES = [
    'discord/publicbot/index.html',
    'equipe/espace-travail/index.html',
    'equipe/cloud/index.html'
];

const SPACE = {
    0: '0', '0.5': '0.125rem', 1: '0.25rem', '1.5': '0.375rem', 2: '0.5rem',
    '2.5': '0.625rem', 3: '0.75rem', 4: '1rem', 5: '1.25rem', 6: '1.5rem',
    7: '1.75rem', 8: '2rem', 10: '2.5rem', 12: '3rem', 14: '3.5rem',
    16: '4rem', 20: '5rem', 24: '6rem', 36: '9rem', 48: '12rem',
    64: '16rem', 72: '18rem', 80: '20rem', 96: '24rem'
};

const COLORS = {
    white: '#fff', black: '#000',
    base: '#eef0ea', surface: '#fff', surfaceHover: '#e3e6dd',
    sysBorder: '#5c6a661f', borderHover: '#5c6a6640',
    accentRed: '#a8462f', accentBlue: '#3f6b52', accentGold: '#b8823d',
    krones: '#b8823d', textDim: '#5c6a66',
    panel: '#fff', border: '#5c6a661f', accent: '#3f6b52',
    accentHover: '#2e5039', card: '#e3e6dd',
    'gray-100': '#f3f4f6', 'gray-200': '#e5e7eb', 'gray-300': '#d1d5db',
    'gray-400': '#9ca3af', 'gray-500': '#6b7280', 'gray-600': '#4b5563',
    'gray-700': '#374151', 'gray-900': '#111827',
    'red-300': '#fca5a5', 'red-400': '#f87171', 'red-500': '#ef4444',
    'red-600': '#dc2626', 'red-900': '#7f1d1d',
    'blue-400': '#60a5fa', 'blue-500': '#3b82f6', 'blue-600': '#2563eb',
    'amber-400': '#fbbf24', 'amber-600': '#d97706',
    'indigo-400': '#818cf8', 'indigo-600': '#4f46e5',
    'purple-300': '#d8b4fe', 'purple-400': '#c084fc', 'purple-500': '#a855f7',
    'orange-400': '#fb923c', 'teal-400': '#2dd4bf',
    'emerald-300': '#6ee7b7', 'yellow-300': '#fde047', 'yellow-500': '#eab308',
    'green-400': '#4ade80', 'green-500': '#22c55e'
};

const RADIUS = {
    '': '0.25rem', sm: '0.125rem', md: '0.375rem', lg: '0.5rem',
    xl: '0.75rem', full: '9999px'
};
const SHADOW = {
    sm: '0 1px 2px rgba(0,0,0,.08)',
    '': '0 1px 3px rgba(0,0,0,.12)',
    md: '0 4px 6px rgba(0,0,0,.12)',
    lg: '0 10px 15px rgba(0,0,0,.15)',
    xl: '0 20px 25px rgba(0,0,0,.18)',
    '2xl': '0 25px 50px rgba(0,0,0,.22)',
    inner: 'inset 0 2px 4px rgba(0,0,0,.08)'
};
const TEXT = {
    xs: '0.75rem', sm: '0.875rem', base: '1rem', lg: '1.125rem',
    xl: '1.25rem', '2xl': '1.5rem', '3xl': '1.875rem', '4xl': '2.25rem'
};
const Z = { 0: 0, 10: 10, 20: 20, 50: 50 };

function extractClasses(html) {
    const found = new Set();
    const add = (raw) => {
        String(raw || '').split(/\s+/).forEach((name) => {
            const clean = name.replace(/[^a-zA-Z0-9_:\-[\]/%.#]+/g, '');
            if (!clean || clean.startsWith('${') || clean === '?' || clean === ':') return;
            found.add(clean);
        });
    };
    for (const match of html.matchAll(/class(?:Name)?=["']([^"']+)["']/g)) add(match[1]);
    for (const match of html.matchAll(/class(?:Name)?=\{?`([^`]+)`/g)) add(match[1]);
    return found;
}

function escapeClass(name) {
    return `.${name.replace(/[:[\]/%#.]/g, (ch) => `\\${ch}`)}`;
}

function parseColor(token) {
    const [name, alpha] = String(token).split('/');
    if (COLORS[name]) {
        if (!alpha) return COLORS[name];
        const hex = COLORS[name].replace('#', '');
        if (hex.length === 3 || hex.length === 6) {
            const full = hex.length === 3 ? hex.split('').map((c) => c + c).join('') : hex;
            const r = parseInt(full.slice(0, 2), 16);
            const g = parseInt(full.slice(2, 4), 16);
            const b = parseInt(full.slice(4, 6), 16);
            return `rgba(${r},${g},${b},${Number(alpha) / 100})`;
        }
    }
    if (name.startsWith('[') && name.endsWith(']')) return name.slice(1, -1);
    if (name.startsWith('#') || name.startsWith('rgb')) return name;
    return null;
}

function space(token) {
    if (SPACE[token] != null) return SPACE[token];
    if (token.startsWith('[') && token.endsWith(']')) return token.slice(1, -1);
    if (token === 'px') return '1px';
    if (token === 'auto') return 'auto';
    if (token === 'full') return '100%';
    if (token === 'screen') return '100vh';
    if (token === 'fit') return 'fit-content';
    if (/^\d+\/\d+$/.test(token)) {
        const [a, b] = token.split('/').map(Number);
        return `${(a / b) * 100}%`;
    }
    return null;
}

function rule(cls) {
    const sel = escapeClass(cls);
    if (cls === 'flex') return `${sel}{display:flex}`;
    if (cls === 'inline-flex') return `${sel}{display:inline-flex}`;
    if (cls === 'block') return `${sel}{display:block}`;
    if (cls === 'inline-block') return `${sel}{display:inline-block}`;
    if (cls === 'hidden') return `${sel}{display:none}`;
    if (cls === 'grid') return `${sel}{display:grid}`;
    if (cls === 'sr-only') return `${sel}{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);border:0}`;
    if (cls === 'flex-col') return `${sel}{flex-direction:column}`;
    if (cls === 'flex-row') return `${sel}{flex-direction:row}`;
    if (cls === 'flex-row-reverse') return `${sel}{flex-direction:row-reverse}`;
    if (cls === 'flex-wrap') return `${sel}{flex-wrap:wrap}`;
    if (cls === 'flex-1') return `${sel}{flex:1 1 0%}`;
    if (cls === 'flex-none') return `${sel}{flex:none}`;
    if (cls === 'shrink-0') return `${sel}{flex-shrink:0}`;
    if (cls === 'items-center') return `${sel}{align-items:center}`;
    if (cls === 'items-start') return `${sel}{align-items:flex-start}`;
    if (cls === 'items-end') return `${sel}{align-items:flex-end}`;
    if (cls === 'items-stretch') return `${sel}{align-items:stretch}`;
    if (cls === 'items-baseline') return `${sel}{align-items:baseline}`;
    if (cls === 'justify-center') return `${sel}{justify-content:center}`;
    if (cls === 'justify-between') return `${sel}{justify-content:space-between}`;
    if (cls === 'justify-end') return `${sel}{justify-content:flex-end}`;
    if (cls === 'self-start') return `${sel}{align-self:flex-start}`;
    if (cls === 'relative') return `${sel}{position:relative}`;
    if (cls === 'absolute') return `${sel}{position:absolute}`;
    if (cls === 'fixed') return `${sel}{position:fixed}`;
    if (cls === 'sticky') return `${sel}{position:sticky}`;
    if (cls === 'inset-0') return `${sel}{inset:0}`;
    if (cls === 'truncate') return `${sel}{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}`;
    if (cls === 'text-center') return `${sel}{text-align:center}`;
    if (cls === 'text-left') return `${sel}{text-align:left}`;
    if (cls === 'text-right') return `${sel}{text-align:right}`;
    if (cls === 'uppercase') return `${sel}{text-transform:uppercase}`;
    if (cls === 'italic') return `${sel}{font-style:italic}`;
    if (cls === 'font-bold') return `${sel}{font-weight:700}`;
    if (cls === 'font-semibold') return `${sel}{font-weight:600}`;
    if (cls === 'font-medium') return `${sel}{font-weight:500}`;
    if (cls === 'font-mono') return `${sel}{font-family:ui-monospace,monospace}`;
    if (cls === 'underline') return `${sel}{text-decoration:underline}`;
    if (cls === 'line-through') return `${sel}{text-decoration:line-through}`;
    if (cls === 'break-words') return `${sel}{overflow-wrap:anywhere}`;
    if (cls === 'whitespace-nowrap') return `${sel}{white-space:nowrap}`;
    if (cls === 'whitespace-pre-wrap') return `${sel}{white-space:pre-wrap}`;
    if (cls === 'leading-tight') return `${sel}{line-height:1.25}`;
    if (cls === 'leading-relaxed') return `${sel}{line-height:1.625}`;
    if (cls === 'tracking-widest') return `${sel}{letter-spacing:.1em}`;
    if (cls === 'cursor-pointer') return `${sel}{cursor:pointer}`;
    if (cls === 'cursor-grab') return `${sel}{cursor:grab}`;
    if (cls === 'cursor-not-allowed') return `${sel}{cursor:not-allowed}`;
    if (cls === 'pointer-events-none') return `${sel}{pointer-events:none}`;
    if (cls === 'pointer-events-auto') return `${sel}{pointer-events:auto}`;
    if (cls === 'overflow-hidden') return `${sel}{overflow:hidden}`;
    if (cls === 'overflow-auto') return `${sel}{overflow:auto}`;
    if (cls === 'overflow-x-auto') return `${sel}{overflow-x:auto}`;
    if (cls === 'overflow-y-auto') return `${sel}{overflow-y:auto}`;
    if (cls === 'overflow-y-hidden') return `${sel}{overflow-y:hidden}`;
    if (cls === 'object-cover') return `${sel}{object-fit:cover}`;
    if (cls === 'object-contain') return `${sel}{object-fit:contain}`;
    if (cls === 'outline-none') return `${sel}{outline:0}`;
    if (cls === 'border-none') return `${sel}{border:0}`;
    if (cls === 'border-collapse') return `${sel}{border-collapse:collapse}`;
    if (cls === 'border-dashed') return `${sel}{border-style:dashed}`;
    if (cls === 'border') return `${sel}{border-width:1px}`;
    if (cls === 'border-2') return `${sel}{border-width:2px}`;
    if (cls === 'border-4') return `${sel}{border-width:4px}`;
    if (cls === 'border-t') return `${sel}{border-top-width:1px}`;
    if (cls === 'border-b') return `${sel}{border-bottom-width:1px}`;
    if (cls === 'border-l') return `${sel}{border-left-width:1px}`;
    if (cls === 'border-r') return `${sel}{border-right-width:1px}`;
    if (cls === 'border-l-4') return `${sel}{border-left-width:4px}`;
    if (cls === 'border-t-4') return `${sel}{border-top-width:4px}`;
    if (cls === 'border-transparent') return `${sel}{border-color:transparent}`;
    if (cls === 'mx-auto') return `${sel}{margin-left:auto;margin-right:auto}`;
    if (cls === 'ml-auto') return `${sel}{margin-left:auto}`;
    if (cls === 'mt-auto') return `${sel}{margin-top:auto}`;
    if (cls === 'animate-spin') return `${sel}{animation:tw-spin 1s linear infinite}`;
    if (cls === 'transition') return `${sel}{transition:color .15s,background .15s,border-color .15s,transform .15s}`;
    if (cls === 'transition-all') return `${sel}{transition:all .15s}`;
    if (cls === 'transition-transform') return `${sel}{transition:transform .15s}`;
    if (cls === 'duration-75') return `${sel}{transition-duration:75ms}`;
    if (cls === 'duration-200') return `${sel}{transition-duration:200ms}`;
    if (cls === 'duration-500') return `${sel}{transition-duration:500ms}`;
    if (cls === 'ease-out') return `${sel}{transition-timing-function:cubic-bezier(0,0,.2,1)}`;
    if (cls === 'transform') return `${sel}{transform:translateZ(0)}`;
    if (cls === 'rotate-90') return `${sel}{transform:rotate(90deg)}`;
    if (cls === '-translate-y-1/2') return `${sel}{transform:translateY(-50%)}`;
    if (cls === 'translate-x-full') return `${sel}{transform:translateX(100%)}`;
    if (cls === 'line-clamp-2') return `${sel}{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}`;
    if (cls === 'col-span-full') return `${sel}{grid-column:1/-1}`;
    if (cls === 'col-span-3') return `${sel}{grid-column:span 3/span 3}`;
    if (cls === 'grid-cols-1') return `${sel}{grid-template-columns:repeat(1,minmax(0,1fr))}`;
    if (cls === 'w-fit') return `${sel}{width:fit-content}`;
    if (cls === 'h-px') return `${sel}{height:1px}`;
    if (cls === 'top-1\\/2' || cls === 'top-1/2') return `${escapeClass('top-1/2')}{top:50%}`;
    if (cls === 'backdrop-blur' || cls === 'backdrop-blur-sm') return `${sel}{backdrop-filter:blur(8px)}`;
    if (cls === 'shadow-inner') return `${sel}{box-shadow:${SHADOW.inner}}`;
    if (cls === 'empty\\:hidden' || cls === 'empty:hidden') return `${sel}:empty{display:none}`;
    if (cls === 'first\\:ml-0' || cls === 'first:ml-0') return `${sel}:first-child{margin-left:0}`;
    if (cls === '-space-x-2') return `${sel}>:not([hidden])~:not([hidden]){margin-left:-0.5rem}`;
    if (cls === 'space-x-\\[-8px\\]' || cls === 'space-x-[-8px]') return `${escapeClass('space-x-[-8px]')}>:not([hidden])~:not([hidden]){margin-left:-8px}`;

    let m;
    if ((m = cls.match(/^grid-cols-(\d+)$/))) return `${sel}{grid-template-columns:repeat(${m[1]},minmax(0,1fr))}`;
    if ((m = cls.match(/^gap-(\S+)$/))) {
        const v = space(m[1]);
        return v ? `${sel}{gap:${v}}` : '';
    }
    if ((m = cls.match(/^space-x-(\S+)$/))) {
        const v = space(m[1]);
        return v ? `${sel}>:not([hidden])~:not([hidden]){margin-left:${v}}` : '';
    }
    if ((m = cls.match(/^space-y-(\S+)$/))) {
        const v = space(m[1]);
        return v ? `${sel}>:not([hidden])~:not([hidden]){margin-top:${v}}` : '';
    }
    if ((m = cls.match(/^(p|px|py|pt|pr|pb|pl|m|mx|my|mt|mr|mb|ml)-(\S+)$/))) {
        const v = space(m[2]);
        if (!v) return '';
        const map = {
            p: `padding:${v}`, px: `padding-left:${v};padding-right:${v}`,
            py: `padding-top:${v};padding-bottom:${v}`, pt: `padding-top:${v}`,
            pr: `padding-right:${v}`, pb: `padding-bottom:${v}`, pl: `padding-left:${v}`,
            m: `margin:${v}`, mx: `margin-left:${v};margin-right:${v}`,
            my: `margin-top:${v};margin-bottom:${v}`, mt: `margin-top:${v}`,
            mr: `margin-right:${v}`, mb: `margin-bottom:${v}`, ml: `margin-left:${v}`
        };
        return `${sel}{${map[m[1]]}}`;
    }
    if ((m = cls.match(/^-ml-(\S+)$/))) {
        const v = space(m[1]);
        return v ? `${sel}{margin-left:-${v}}` : '';
    }
    if ((m = cls.match(/^(w|h|min-w|min-h|max-w|max-h)-(\S+)$/))) {
        const v = space(m[2]) || ({
            xs: '20rem', sm: '24rem', md: '28rem', lg: '32rem',
            xl: '36rem', '2xl': '42rem', '3xl': '48rem', '4xl': '56rem',
            '5xl': '64rem', '6xl': '72rem', none: 'none'
        })[m[2]];
        if (!v) return '';
        const prop = { w: 'width', h: 'height', 'min-w': 'min-width', 'min-h': 'min-height', 'max-w': 'max-width', 'max-h': 'max-height' }[m[1]];
        return `${sel}{${prop}:${v}}`;
    }
    if ((m = cls.match(/^(top|right|bottom|left)-(\S+)$/))) {
        const v = space(m[2]);
        return v ? `${sel}{${m[1]}:${v}}` : '';
    }
    if ((m = cls.match(/^z-(.+)$/))) {
        const raw = m[1];
        const v = raw.startsWith('[') ? raw.slice(1, -1) : (Z[raw] ?? raw);
        return `${sel}{z-index:${v}}`;
    }
    if ((m = cls.match(/^opacity-(\d+)$/))) return `${sel}{opacity:${Number(m[1]) / 100}}`;
    if ((m = cls.match(/^rounded(?:-(.+))?$/))) {
        const key = m[1] || '';
        if (key.startsWith('t-') || key.startsWith('b-') || key.startsWith('l-') || key.startsWith('r-') || key.startsWith('tl') || key.startsWith('tr') || key.startsWith('bl') || key.startsWith('br')) {
            const parts = key.split('-');
            const side = parts[0];
            const size = parts.slice(1).join('-') || '';
            const val = RADIUS[size] || RADIUS[''];
            const map = {
                t: `border-top-left-radius:${val};border-top-right-radius:${val}`,
                b: `border-bottom-left-radius:${val};border-bottom-right-radius:${val}`,
                l: `border-top-left-radius:${val};border-bottom-left-radius:${val}`,
                r: `border-top-right-radius:${val};border-bottom-right-radius:${val}`,
                tl: `border-top-left-radius:${val}`,
                tr: `border-top-right-radius:${val}`,
                bl: `border-bottom-left-radius:${val}`,
                br: `border-bottom-right-radius:${val}`
            };
            return map[side] ? `${sel}{${map[side]}}` : '';
        }
        const val = RADIUS[key] || (key.startsWith('[') ? key.slice(1, -1) : null);
        return val ? `${sel}{border-radius:${val}}` : '';
    }
    if ((m = cls.match(/^shadow(?:-(.+))?$/))) {
        const val = SHADOW[m[1] || ''];
        return val ? `${sel}{box-shadow:${val}}` : '';
    }
    if ((m = cls.match(/^text-(.+)$/))) {
        if (TEXT[m[1]]) return `${sel}{font-size:${TEXT[m[1]]}}`;
        if (m[1].startsWith('[') && m[1].endsWith(']')) return `${sel}{font-size:${m[1].slice(1, -1)}}`;
        const color = parseColor(m[1]);
        return color ? `${sel}{color:${color}}` : '';
    }
    if ((m = cls.match(/^bg-(.+)$/))) {
        const color = parseColor(m[1]);
        return color ? `${sel}{background-color:${color}}` : '';
    }
    if ((m = cls.match(/^border-(.+)$/))) {
        if (m[1] === 't-transparent') return `${sel}{border-top-color:transparent}`;
        if (m[1] === 'l-transparent') return `${sel}{border-left-color:transparent}`;
        if (m[1] === 'b-black/20') return `${sel}{border-bottom-color:rgba(0,0,0,.2)}`;
        if (m[1] === 'l-[12px]') return `${sel}{border-left-width:12px}`;
        if (m[1] === 'b-[12px]') return `${sel}{border-bottom-width:12px}`;
        const color = parseColor(m[1]);
        return color ? `${sel}{border-color:${color}}` : '';
    }
    return '';
}

function wrapVariant(cls) {
    if (cls.startsWith('sm:')) {
        const inner = rule(cls.slice(3));
        return inner ? `@media(min-width:640px){${inner}}` : '';
    }
    if (cls.startsWith('md:')) {
        const inner = rule(cls.slice(3));
        return inner ? `@media(min-width:768px){${inner}}` : '';
    }
    if (cls.startsWith('lg:')) {
        const inner = rule(cls.slice(3));
        return inner ? `@media(min-width:1024px){${inner}}` : '';
    }
    if (cls.startsWith('hover:')) {
        const inner = rule(cls.slice(6));
        return inner.replace(/^(\.\S+)\{/, '$1:hover{');
    }
    if (cls.startsWith('focus:')) {
        const inner = rule(cls.slice(6));
        return inner.replace(/^(\.\S+)\{/, '$1:focus{');
    }
    if (cls.startsWith('group-hover:')) {
        const inner = rule(cls.slice(12));
        return inner.replace(/^(\.\S+)\{/, '.group:hover $1{');
    }
    if (cls.startsWith('peer-checked:after:')) {
        const inner = rule(cls.slice(19));
        return inner.replace(/^(\.\S+)\{/, '.peer:checked~.peer-after, .peer:checked::after{');
    }
    if (cls.startsWith('peer-checked:')) {
        const inner = rule(cls.slice(13));
        return inner.replace(/^(\.\S+)\{/, '.peer:checked{');
    }
    if (cls.startsWith('peer-focus:')) {
        const inner = rule(cls.slice(11));
        return inner.replace(/^(\.\S+)\{/, '.peer:focus{');
    }
    if (cls.startsWith('after:')) {
        if (cls === "after:content-['']") return `${escapeClass(cls)},.after\\:content-\\[\\'\\'\\]::after{content:''}`;
        const inner = rule(cls.slice(6));
        return inner.replace(/^(\.\S+)\{/, '$1::after{');
    }
    return css;
}

function build() {
    const classes = new Set();
    for (const rel of FILES) {
        const html = fs.readFileSync(path.join(PUBLIC, rel), 'utf8');
        extractClasses(html).forEach((c) => classes.add(c));
    }
    const blocks = [
        ':root{--tw-colors-base:#eef0ea;--tw-colors-surface:#fff;--tw-colors-surfaceHover:#e3e6dd;--tw-colors-sysBorder:#5c6a661f;--tw-colors-borderHover:#5c6a6640;--tw-colors-accentRed:#a8462f;--tw-colors-accentBlue:#3f6b52;--tw-colors-accentGold:#b8823d;--tw-colors-krones:#b8823d;--tw-colors-textDim:#5c6a66;}',
        '@keyframes tw-spin{to{transform:rotate(360deg)}}',
        '.peer::after{content:"";position:absolute}'
    ];
    for (const cls of [...classes].sort()) {
        if (cls.startsWith('fa-')) continue;
        const css = /^(sm|md|lg|hover|focus|group-hover|peer-checked|peer-focus|after):/.test(cls)
            ? wrapVariant(cls)
            : rule(cls);
        if (css) blocks.push(css);
    }
    fs.writeFileSync(OUT, `/* generated — do not edit by hand. node apps/www/scripts/build-tw-local.js */\n${blocks.join('\n')}\n`);
    console.log(`tw-local.css: ${classes.size} classes, ${fs.statSync(OUT).size} bytes`);
}

build();
