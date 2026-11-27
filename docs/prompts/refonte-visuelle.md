# Prompt de planification — refonte visuelle Synkrone

À coller tel quel dans une nouvelle session en mode Plan.

Tu planifies la refonte visuelle de synkrone.app. Tu ne codes pas. Tu livres un plan de réalisation : direction, pages, outils, ordre. Chaque choix d’outil cite le skill et une raison.

Lis d’abord, dans cet ordre, et suis-les :

- `SKILLS/SKILL.md` (le fichier `SKILL.MD` vide n’est pas le skill)
- `SKILLS/references/gsap.md`, `lenis.md`, `anime-js.md`, `echarts.md`, `kokonut-ui.md`, `watermelon-ui.md`, `react-bits.md`, `recipes.md`
- `apps/www/lib/leaf-pages.js` (routes et textes publics réels)
- `apps/www/design/synkrone.css` (tokens actuels)
- `Synkrone/test/synkrone_authdiscord/public/index.html` et `public/accueil/index.html` (coquille et accueil)
- `dashboard/Orbital-hebergeur/src/app` (panel Next)

## Ce que voit un visiteur

Deux surfaces, une seule marque.

1. Vitrine. Express sert du HTML. La coquille (`index.html`) enferme les pages dans un cadre en position absolute, avec `html`/`body` en `overflow: hidden`. Le scroll document n’existe pas : Lenis et ScrollTrigger ne peuvent pas s’y poser. Les pages vivent dans `Synkrone/test/synkrone_authdiscord/public/`. Routes réelles dans `leaf-pages.js` : accueil, FAQ, statut, contact, CGU, CGV, cookies, Krônes, login, bots (Vax, Arceus, Asuna, Kayaba, Yui, créer un bot), catalogue, dashbot, commandes, Bump, Me, Minecraft / Cantale, modpacks (Xenus, The French Baguette, Vanipack), compte, serveur.

2. Panel d’hébergement, servi sur `/hebergement`. Next 16, React 19, Tailwind 4, lucide. Pas de shadcn, pas de motion, pas de GSAP. Pages : entrée (redirection login ou dashboard), dashboard (services, quotas CPU/RAM/disque, états), liste et fiche service, création `new/[type]`, Krônes, compte, infrastructure. C’est un outil : console, fichiers, création. La refonte change le chrome, la hiérarchie et les états vides, pas les flux métier.

Identité actuelle, à prendre position dessus (l’amplifier ou la remplacer, avec une raison écrite) : palette pierre `#eef0ea`, basalte `#1b211e`, mousse `#3f6b52`, ambre `#b8823d`, brique `#a8462f`, ardoise `#5c6a66`. Zilla Slab pour les titres, IBM Plex Sans et Mono. Rayons 4–6 px. Le CSS appelle ça une salle machines. Le thème clair/sombre existe déjà (cookie `synkrone_theme`).

Promesse déjà écrite, à garder : créer un bot Discord, un serveur Minecraft ou un site, payé en Krônes, piloté depuis un panel. Cinq bots officiels, Cantale Java 1.21, Bump, Me. Aucun chiffre qui n’est pas déjà mesuré (le bandeau statut le dit).

## Hors de ce plan

Hub interne, `/ui`, `/sharing`, pages `/admin`, bots Python, certificats, DNS, secrets, historique git. Les routes publiques, le SEO (titres, descriptions, canonical, JSON-LD), l’auth Discord/Google/GitHub, Postgres, les Krônes et les APIs du panel restent. La refonte est visuelle.

## Direction à trancher dans le plan

Le plan ouvre par une direction en une phrase, puis les conséquences concrètes : une police de titres, une police de texte, cinq tokens (fond, texte, accent, accent chaud, danger), un rayon, une règle de mouvement. Évite le SaaS violet générique et le glassmorphism partout. La salle machines peut rester le matériau, à condition que le mouvement et la typo la rendent mémorable au premier écran.

Un seul moment signature pour la vitrine (celui qu’on retient), nommé et justifié. Le reste de la page est plus calme que ce moment.

## Routage des outils (obligatoire)

Applique `SKILLS/SKILL.md`. Résumé à respecter :

- Vitrine marketing (accueil, bots, Minecraft, Krônes en tant que récit) : Lenis une fois, piloté par `gsap.ticker`, `autoRaf: false`, CSS Lenis importé. ScrollTrigger pour un pin ou un scrub si la direction l’exige, `ScrollTrigger.batch` pour les cartes. SplitText sur le titre d’accueil, avec masque et texte accessible. `prefers-reduced-motion` : pas de Lenis, pas de tweens, contenu déjà en place.
- Séquence locale, trait SVG, stagger enfermé dans un composant : anime.js v4 (`animate`, `createTimeline`, `createScope` + `revert`). Jamais `anime({targets})`.
- Hover, apparition conditionnelle, layout React : motion. Un nœud, un seul moteur.
- Chiffres réels (statut, quotas du panel, historique Krônes) : ECharts en `echarts/core` + `use([...])`. Jamais l’import complet. Pas d’oklch dans les options. Conteneur avec une hauteur. `animation: false` si reduced-motion.
- Effet prêt à l’emploi (fond, texte, carte) : React Bits catalogue gratuit, variante TS-TW. Une scène WebGL max par page. Si le composant importe `gsap`, ces nœuds restent à GSAP.
- Chrome produit du panel (états vides, boutons d’action, nav, toasts) : Kokonut gratuit d’abord, puis Watermelon (`@watermelon/<slug>`), puis le panel actuel. Pas de Kokonut Pro, pas de React Bits Pro.
- Pages légales, login, formulaires, fiche service (console, fichiers) : pas de Lenis, pas de pin. Mouvement limité aux changements d’état.
- Dashboards Watermelon : seulement si un bloc remplace vraiment un écran du panel. Les graphes SVG de ces blocs sont remplacés par ECharts dès que la donnée est réelle.

Le plan dit, page par page, l’outil retenu. Il dit aussi ce qui reste du HTML actuel.

## Décision technique à trancher

La vitrine n’est pas en React. Les registries (Kokonut, Watermelon, React Bits) et `useGSAP` supposent React + Tailwind. Le panel l’est déjà (Tailwind 4, sans shadcn).

Le plan choisit un véhicule et le justifie :

- Soit une app React (Vite ou Next) pour la vitrine, qui reprend les routes de `leaf-pages.js` et consomme les APIs Express existantes. La coquille iframe disparaît. Le panel reste l’app Next actuelle, habillée avec les mêmes tokens.
- Soit la vitrine reste en HTML, et seuls GSAP, Lenis et anime.js s’y posent (les registries sont alors réservés au panel).

Dans les deux cas, la coquille `overflow: hidden` est levée sur les pages qui défilent. Le panel, les formulaires et les pages légales ne reçoivent pas Lenis. shadcn n’est ajouté que là où un registry l’exige, via `SKILLS/scripts/setup.sh`, sans écraser un `utils.ts` déjà correct.

## Forme du plan que tu rends

1. Direction (phrase, tokens, typo, mouvement, moment signature).
2. Véhicule technique retenu.
3. Parcours visiteur : accueil, puis les sections, puis la porte du panel. Ce qui est un récit, ce qui est un outil.
4. Pour chaque route de `leaf-pages.js` et chaque page du panel : intention visuelle en une ligne, outil, ce qui ne bouge pas.
5. Système commun (header, footer, thème clair/sombre, focus, reduced-motion) partagé entre vitrine et panel.
6. Ordre de chantier en quatre étapes maximum : tokens et coquille, accueil, gabarits de section (bot, Minecraft, Krônes, Bump, Me), chrome du panel et ses graphes.
7. Vérification : desktop et 390 px, clavier, contraste, reduced-motion, console propre, aucun chiffre inventé, build des deux apps.
8. Risques : routes et SEO à préserver, iframe actuelle, double thème, panel sans shadcn, bundle ECharts et WebGL.

Tu ne proposes pas de nouvelle fonctionnalité. Tu ne réécris pas les textes métier. Tu rends la même promesse impossible à confondre avec un template.
