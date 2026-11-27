# Plan de réalisation — refonte visuelle Synkrone

Spec à appliquer telle quelle. Ne replanifie pas. Ne réécris pas les textes métier. N’invente ni feature, ni chiffre.

Baseline : `main` du dépôt `https://github.com/Annonnyx/Synkrone.git` au commit qui ajoute ce fichier. La vitrine est du HTML servi par Express. Le panel est déjà Next. Aucune librairie de motion n’est installée sur cette baseline.

## 1. Direction

La salle machines s’allume : pierre et basalte, un rack ambre au premier écran, puis des pages calmes qui mènent au panel. On amplifie l’identité actuelle.

- Titres : Zilla Slab. Texte : IBM Plex Sans. Indices, IP, préfixes, soldes : IBM Plex Mono. Déjà chargées. Ne change pas le reste de l’échelle typo.
- Titre du hero, lui seul : `clamp(3.25rem, 8vw, 6.5rem)`.
- Tokens : fond `#eef0ea` (sombre `#1b211e`), texte `#1b211e` (sombre `#eef0ea`), accent mousse `#3f6b52` (sombre `#6b9d7e`, hover `#9ecfb0`), accent chaud ambre `#b8823d`, danger brique `#a8462f`.
- Rayon 4 px. 6 px seulement pour le bandeau cookies et les cartes qui ont déjà `--sk-radius-lg`.
- Mouvement : un nœud, un moteur. Lissage du document seulement sur les pages récit. Si `prefers-reduced-motion` : pas de Lenis, pas de tweens, contenu déjà en place.

Moment signature, nommé **Allumage**, uniquement sur le hero de l’accueil. Les quatre armoires existent déjà (`.cabinets`, `.c1`–`.c4`, `.grid-plane`). Un bus SVG ambre `aria-hidden` est tracé avec anime.js v4 `createDrawable` dans `createTimeline`, puis les armoires montent en opacity et transform. En même temps, GSAP SplitText révèle le h1 « Synkrone » avec un masque de lignes. Le texte reste dans le DOM pour les lecteurs d’écran. Le chapô, les deux liens et la ligne « 5 bots officiels · Cantale Java 1.21 · Bump et Me » sont lisibles au premier paint. En dessous, la page se lit, elle n’est pas épinglée. `ScrollTrigger.batch` seulement sur `.bot-card`, `.plate`, puis `.project`. Pas de pin, pas de scrub, pas de WebGL, pas de React Bits. Pas de compteur qui part de zéro : une frame intermédiaire serait un faux total, et reduced-motion exige la valeur mesurée tout de suite.

## 2. Véhicule technique

La vitrine reste le HTML servi par Express (`apps/www`, fichiers dans `Synkrone/test/synkrone_authdiscord/public/`). GSAP, Lenis et anime.js seulement là. Les registries restent sur le panel.

Raison : `renderShell` dans `apps/www/lib/leaf-pages.js` émet déjà title, description, canonical, image OG et JSON-LD (`WebPage`, `FAQPage`, `SoftwareApplication`). Une SPA Vite repousserait le SEO côté client. Une deuxième app Next dupliquerait les routes à côté du panel. Le panel est déjà Next 16, React 19, Tailwind 4.

`renderShell` pose `data-scroll` et `data-motion` sur `<html>`. Aujourd’hui `html, body` sont `overflow: hidden` et `.content-frame` est `position: absolute` : Lenis et ScrollTrigger ne peuvent pas s’y accrocher. Lenis une fois, `autoRaf: false`, piloté par `gsap.ticker` (`lenis.raf(time * 1000)`), CSS `lenis/dist/lenis.css`. Pas de second rAF, pas de `ScrollTrigger.scrollerProxy`, pas de ScrollSmoother.

La vitrine n’a pas de bundler hors `apps/www/scripts/build-tw-local.js`. Un script voisin émet deux fichiers navigateur dans `public/assets/` :

- `motion.js` : gsap, ScrollTrigger, SplitText, lenis, imports nommés anime.js v4. Chargé seulement si `data-motion="story"`.
- `status-chart.js` : ECharts tree-shaké. Jamais le paquet complet.

Dépendances installées dans `apps/www`. Le panel ne reçoit ni GSAP, ni Lenis, ni anime.js.

Modes de scroll :

- `data-scroll="doc"` : flux document, header sticky, footer dans le flux.
- `data-scroll="stage"` : on garde la scène viewport / iframe.
- `data-motion="story"` : Lenis, seulement sur un sous-ensemble des pages `doc`.

Routes récit : `/`, `/accueil`, `/discord`, `/discord/bots`, `/minecraft`, `/minecraft/serveur`.

`/krones` est une boutique (packs, tableau de rangs, calculateur RAM/CPU/stockage) : gabarit visuel seulement, scroll natif, pas de Lenis. Le récit Krônes est la bande de l’accueil.

Outils en scroll natif, mouvement limité à l’état : FAQ, statut, contact, CGU, CGV, cookies, login, compte, serveur, et tout le panel.

Les outils en iframe restent cadrés, scroll natif dedans, pas de Lenis (Lenis s’arrête au-dessus d’une iframe) : fiches bot, créer un bot, catalogue, Dashbot, commandes, Bump, Me, modpacks.

La navigation client est une SPA (`loadContent` dans `public/index.html`). Elle doit mettre à jour `data-scroll` et `data-motion` à chaque changement de page. Les attributs SSR ne suffisent pas. Le cookie de thème est déjà partagé : `synkrone_theme`.

ECharts : `import { BarChart } from "echarts/charts"` ne tree-shake pas sous esbuild (`sideEffects` inclut `lib/chart/*.js`). Imports profonds obligatoires : `echarts/lib/chart/bar/install.js`, `line/install.js`, `component/grid/install.js`, `component/tooltip/install.js`, `component/aria/install.js`, `renderer/installCanvasRenderer.js`. Ces chemins n’ont pas de déclarations TS : un `declare module` local règle TS7016. Jamais `import from "echarts"`. Pas de `three`, pas d’`ogl`.

Le reveal CSS actuel (`.reveal { opacity: 0 }` jusqu’à `.in`) se bat avec GSAP si les deux possèdent opacity/transform. En mode story, désactiver la transition CSS de `.reveal` et ne pas lancer l’IntersectionObserver. GSAP possède `.bot-card`, `.plate`, `.project`. Le cache de feuille (`snapshotLeaf` / `innerHTML`) doit voir le DOM après `SplitText.revert()`. `synkroneMotion.stop()` tourne avant chaque échange de feuille.

## 3. Parcours

Accueil : Allumage, puis des bandes lues (bots, Cantale, Krônes, Bump, Me). Récit.

Index bots et page Cantale : même gabarit de bandes, Lenis, batch sur les cartes. Pas de second Allumage. Récit.

Boutique Krônes, fiches, modpacks, catalogue, Dashbot, commandes, Bump, Me, FAQ, statut, contact, login, compte : outils. Scroll natif. La peau change, les flux non.

La porte du panel est le lien Hébergement, `target="_top"` vers `/hebergement`. Le panel est un outil : quotas, console, fichiers, création.

## 4. Pages

Vitrine, une ligne d’intention, l’outil, ce qui ne bouge pas.

| Route | Intention | Outil | Ne bouge pas |
|---|---|---|---|
| `/`, `/accueil` | Allumage, puis lecture | Lenis, SplitText sur le h1, batch, anime.js sur le bus SVG | Textes, liens, IP, invitations, chips de statut en texte |
| `/discord`, `/discord/bots` | Liste lue | Lenis + batch | Préfixes, URLs d’invitation |
| Fiches `/discord/bots/{vax,arceus,asuna,kayaba,yui,bot}` | Peau salle machines | Cadre, CSS seulement | Préfixes, invitations, iframe |
| `/discord/publicbot`, `/discord/dashbot`, `/discord/commandes` | Peau | Cadre, tokens | Iframe, logique |
| `/discord/bump`, `/discord/me` | Peau du gabarit | Cadre, tokens, rayon 4 px | Iframe, `overflow` interne, flux |
| `/minecraft`, `/minecraft/serveur` | Cantale lu | Lenis + batch | Copie de l’IP instantanée |
| Modpacks (`xenus`, `thefrenchbaguette`, `vanipack`, accueil) | Peau | Cadre | Query `tab`, liens CurseForge |
| `/krones` | Boutique calme, ambre sur solde et prix | Scroll natif, CSS | Calculateur, prix TTC, 150 ₭ = 1 €, « ne se reconvertissent pas » |
| `/stats` | Barres d’uptime réelles | ECharts sur `uptime.bars` (`pct`, `date`) déjà rendu dans `#st-bars` | `GET /api/status`, tuiles texte, liste d’incidents, « Pas de SLA annoncé » |
| `/faq` | Lecture | `details` CSS | JSON-LD `FAQPage` |
| `/contact`, `/login`, `/compte`, `/serveur` | État | CSS | Auth, champs, OAuth |
| `/cgu`, `/cgv`, `/cookies` | Lecture | Aucune lib | Textes légaux |

`/stats` : barres 0–100, labels `date.slice(5)`, `aria.enabled`, tokens hex, hauteur fixe. `animation: false` si reduced-motion. Les chips de l’accueil (`#hs-up`, `#hs-run`, etc.) restent du texte, pas un second graphe.

Panel. Ne remplace aucun écran par un dashboard Watermelon. Kokonut gratuit, slugs à revérifier dans `https://kokonutui.com/llms.txt` au moment de l’install : `empty-state` (garder les props i18n), `inline-alert` pour moteur / service / solde bas (remplacer les rgba en dur par brique et ambre), `promise-toast` seulement s’il peut envelopper le `useToast()` existant, sinon restyler `components/toast.tsx`, `hold-button` seulement pour une confirmation destructive qui existe déjà. `motion` seulement dans les composants Kokonut. Réécrire tout import `framer-motion` vers `motion/react`.

| Page | Intention | Outil | Ne bouge pas |
|---|---|---|---|
| `src/app/page.tsx`, `login/page.tsx` | Rien à habiller | Redirections | Cibles actuelles |
| `dashboard/page.tsx` | Un graphe des trois quotas réels | ECharts barres horizontales de `totals` CPU, RAM, disque | Barre CSS fine sur chaque carte service, poll 10 s, `/api/dashboard`, liens de création, libellés d’audit |
| `dashboard/services/page.tsx` | Liste | Tokens + empty-state | Données |
| `dashboard/services/[id]/page.tsx` | Fiche outil | Tokens sur l’en-tête et la rangée d’onglets | Chaque onglet existant, Monaco, fichiers, console. Pas de Lenis, pas de pin, pas d’onglets animés |
| `dashboard/new/[type]/page.tsx` | Formulaire | Tokens, états disabled et erreur | Types, flags, champs, prix. Pas de Lenis |
| `dashboard/krones/page.tsx` | Journal lisible | ECharts ligne de `ledger[].balanceAfter` contre `ledger[].at`, seulement s’il y a au moins deux lignes | Le tableau reste la source lisible, plafond 30 lignes, lien vers `/krones` |
| `dashboard/account/[section]` | Compte | empty-state | Pas de graphe inventé |
| `dashboard/infrastructure/[section]` | Infra | empty-state | Le moteur reste des tuiles texte |

`EmptyState` réellement utilisé par les pages est exporté depuis `src/components/panel.tsx` (icon, title, hint, action, compact), pas depuis `src/components/ui/empty-state.tsx`.

React Bits n’est pas installé : le hero est une séquence custom et la vitrine n’est pas React. Un CountUp sur le panel animerait des mesures pollées.

shadcn entre seulement dans le panel, parce que Kokonut l’exige. Depuis `dashboard/Orbital-hebergeur` : `bash SKILLS/scripts/setup.sh` sans `--with-core`. Mapper les variables shadcn vers les alias hex existants. Pas d’oklch. `class="dark"` en même temps que `data-theme="dark"`, depuis le même cookie. `src/lib/utils.ts` n’existe pas encore : setup.sh peut écrire `cn` = clsx + twMerge. Après chaque `add`, si le CLI réécrit utils en `export { cn } from "cn"`, restaurer clsx + twMerge. Ne pas laisser le CLI écraser les primitives écrites à la main : `button.tsx`, `tabs.tsx`, `card.tsx`, `dialog.tsx`, `field.tsx`, `table.tsx`, `badge.tsx`. Les fichiers Kokonut vivent dans `src/components/kokonutui/`.

Ne pas remapper `--accent` du panel : c’est le vert de marque via `var(--sk-accent)`. Le token Tailwind `--color-accent` est autre chose et peut aliaser `--sk-accent-soft`.

## 5. Système commun

Garder le header, la nav, le footer, le bandeau cookies et les scripts de navigation de `public/index.html`. Changer la peau seulement. Le lien Hébergement reste `target="_top"` vers `/hebergement`. Le footer garde CGU, CGV, FAQ, Contact, Cookies, Discord.

Aligner l’accent sombre du panel `--sk-accent` / `--sk-accent-hover` sur la vitrine (`#6b9d7e` / `#9ecfb0`). Aujourd’hui le sombre du panel laisse la mousse `#3f6b52` sur le basalte.

Focus : anneau mousse 2 px, décalage 2 px. L’accent sert aux fonds de boutons (texte blanc) et aux grands titres. Le corps reste basalte ou ardoise, pas de petite mousse sur pierre.

Reduced-motion, les deux apps : pas de Lenis, pas de timeline, pas de SplitText, bus SVG déjà tracé, pas de ScrollTrigger, ECharts `animation: false`, motion sous `useReducedMotion` / `MotionConfig reducedMotion="user"`.

À 390 px la décoration du rack peut se replier. Le h1, le chapô et les deux liens restent entiers. Le masque SplitText ne doit pas couper le mot horizontalement. `overflow: hidden` sur le hero ne doit pas manger le titre.

## 6. Ordre de chantier

Chaque étape laisse un build utilisable.

1. Aligner les tokens hex dans les deux CSS. Attributs dans `renderShell`. Lever `overflow` seulement pour `data-scroll="doc"`. Header sticky. Focus. Sombre partagé et `class="dark"`. `apps/www/tests/leaf-pages.test.js` et `shell-query.test.js` restent verts. Pas encore de libs de motion.
2. `motion.js` et Allumage. Vérifier reduced-motion avant d’aller plus loin.
3. Formaliser `.band`, `.band-head`, `.sect-id`, `.plates`, `.bot-card` et les appliquer à la liste bots, Cantale, la boutique Krônes, et la peau Bump/Me. Lenis seulement sur `/discord/bots` et `/minecraft/serveur` en plus de l’accueil. Fiches, modpacks, catalogue, Dashbot, commandes : peau seulement, cadre conservé.
4. Panel : `setup.sh`, puis Kokonut, puis le graphe de quotas du dashboard et le graphe du journal Krônes. Fiche service, création, console et fichiers : tokens seulement.

`shellAttrsForPath` : une route frame, ou une route qui n’est pas une feuille, reçoit `{scroll:'stage', motion:'off'}`. Une feuille reçoit `{scroll:'doc', motion: story ? 'story' : 'off'}`. Ne pas traiter tout chemin à un seul segment comme une scène : `/accueil`, `/faq`, `/stats`, `/krones`, `/login` sont des feuilles.

Le build racine enchaîne le bundle vitrine puis le build du panel. La racine ne dépend pas d’echarts. ECharts est une dépendance de `apps/www` et de `dashboard/Orbital-hebergeur`, chacun installé dans son dossier.

## 7. Vérification

Desktop et 390 px : accueil (Allumage, bandes, menu), une fiche bot, Cantale, Krônes, statut, login, dashboard, fiche service (onglets console et fichiers). À 390 px le h1 entier, le chapô et les deux liens restent. Le rack peut disparaître.

Clavier : lien d’évitement, menu, onglets du panel, `details` de la FAQ, formulaire de contact, création de service. Focus visible.

Contraste clair et sombre. Reduced-motion : pas de Lenis dans le DOM, titre lisible sans attendre, graphes sans animation, console propre. Chiffres seulement depuis `/api/status`, `/api/dashboard`, `/api/krones`.

`node --test tests/*.test.js` dans `apps/www`. `npm run build` à la racine. Les deux apps démarrent. `node apps/www/server.js` sert la vitrine (port 3668 sauf `apps/www/.env`) et proxifie le panel sur `/hebergement`.

Mesurer `innerWidth` avant de conclure qu’un titre est coupé : un viewport d’outil étroit masque les armoires sous 720 px (règle déjà dans l’accueil).

## 8. Risques

Ne pas changer les pathnames ni lâcher l’injection des meta en ajoutant les attributs html. Les routes cadre gardent `#content-frame` et une scène de hauteur viewport. Un second Lenis dans une iframe est interdit.

Un cookie, deux fichiers de tokens, plus une classe `.dark` : un seul chemin d’écriture, des alias hex. Relire `globals.css` après setup.sh pour que l’init ne remplace pas pierre/basalte par une palette neutre. Relire chaque ajout shadcn pour qu’il n’écrase pas les primitives ni `utils.ts`.

ECharts est bundlé deux fois : un petit `status-chart.js` pour la vitrine, un module tree-shaké pour le panel. GSAP et Lenis ne se chargent que si `data-motion="story"`.

Hors de ce plan : hub interne, `/ui`, `/sharing`, pages `/admin`, bots Python, certificats, DNS, secrets, historique git. Les routes publiques, le SEO, l’auth Discord/Google/GitHub, Postgres, les Krônes et les APIs du panel restent.
