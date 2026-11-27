---
name: ai-ui-stack
description: >
  Stack UI/animation/data-viz pour projets React + Vite/Next + Tailwind. À utiliser DÈS QUE la tâche
  touche : landing page, dashboard, graphiques/KPI/data-viz, animations (texte, scroll, SVG, timeline,
  micro-interactions), backgrounds visuels, smooth scroll, scroll storytelling (pin, scrub),
  composants d'interface d'agent IA / chat / tool-calls, blocs de page ou templates. Choisit le BON
  outil parmi GSAP 3 (plugins gratuits), Lenis, anime.js v4, Apache ECharts, Kokonut UI,
  Watermelon UI et React Bits, les installe via CLI/registry/npm (jamais en recopiant de mémoire)
  et les intègre correctement (thème, nettoyage, accessibilité, perf, bundle).
---

# ai-ui-stack — choisir et utiliser les bons outils UI

Sept outils, **rôles distincts**. Un bon résultat = le bon outil à la bonne place, installé
proprement, intégré au design system du projet. Ne mélange pas les rôles. GSAP et Lenis sont
gratuits (licence standard no-charge, et MIT) : les utiliser à fond, pas les éviter.

| Outil | Rôle (une phrase) | Nature | Réf. |
|---|---|---|---|
| **GSAP 3** | Scroll storytelling (pin, scrub, batch), SplitText accessible, FLIP, DrawSVG/MorphSVG, drag + inertie. Tous les plugins sont dans le paquet public | lib npm (`gsap`, `@gsap/react`) | `references/gsap.md` |
| **Lenis** | Smooth scroll **natif** (sticky, ancres, barre conservés), synchronisé avec ScrollTrigger. Uniquement pages vitrine | lib npm (`lenis`), MIT | `references/lenis.md` |
| **Apache ECharts** | Toute visualisation de **données** (courbes, barres, radar, gauge, heatmap, sankey, carte…) | lib npm (`echarts`) | `references/echarts.md` |
| **anime.js v4** | Séquences **locales** : timeline d'un composant, stagger, SVG draw/morph/path, `onScroll` d'apparition, compteurs, spring | lib npm (`animejs`) | `references/anime-js.md` |
| **React Bits** | **Effets créatifs prêts à l'emploi** : texte animé, backgrounds (WebGL/canvas), curseurs, cartes à effet. Catalogue gratuit seulement | registry shadcn, code copié | `references/react-bits.md` |
| **Kokonut UI** | Composants **produit/IA** soignés : chat, prompt input, tool calls, approvals, boutons, cartes, nav, inputs. Catalogue gratuit seulement | registry shadcn + MCP, code copié | `references/kokonut-ui.md` |
| **Watermelon UI** | **Catalogue énorme** (800+) de blocs de page, dashboards, templates, composants animés — découverte via MCP/API | registry `@watermelon`, code copié | `references/watermelon-ui.md` |

Complément implicite : **shadcn/ui** pour les primitives (button, dialog, input…) et **`motion`**
(`motion/react`) pour les animations *de composant React* (enter/exit, layout, hover, gestes) — c'est
la dépendance commune de Kokonut/React Bits/Watermelon.

---

## 0. Procédure obligatoire (dans cet ordre)

1. **Preflight** — `bash SKILLS/scripts/preflight.sh` (ou lire à la main : framework, Tailwind v3/v4,
   `components.json`, alias `@/`, `src/lib/utils.ts`, deps déjà présentes : `motion`, `framer-motion`, `animejs`, `echarts`, `gsap`, `three`, `ogl`).
2. **Router** — pour *chaque* besoin de l'UI, applique l'arbre de décision §1. Écris la décision
   (besoin → outil → raison) dans ta réponse/plan **avant** de coder.
3. **Chercher avant d'écrire** — interroge le catalogue (llms.txt, `.md` de la doc, MCP, API — §2).
   Ne réécris jamais from scratch un composant qui existe dans un registry.
4. **Installer** via CLI (`scripts/setup.sh` une seule fois, puis `npx shadcn@latest add …`) — §3.
5. **Intégrer** selon les règles dures §4 (thème, cleanup, a11y, perf).
6. **Vérifier** : `npm run build`, ouvrir la page, contrôle checklist §6.

---

## 1. Arbre de décision (le cœur du skill)

Parcours **de haut en bas, premier match gagnant**.

```
Le besoin affiche des DONNÉES (chiffres → formes) ?
 ├─ oui, graphique/axes/tooltip/légende/zoom/>1 série ............ ECharts  (JAMAIS un faux chart en div/CSS/anime.js)
 ├─ oui, simple KPI chiffré qui "monte" ........................... React Bits CountUp, sinon anime.js (utils/animate sur un objet)
 └─ oui, mini sparkline/jauge décorative sans interaction ......... SVG + anime.js (ou ECharts si données réelles)

Le besoin est une INTERFACE D'AGENT IA / CHAT ?
 └─ prompt input, model selector, tool calls, approvals, citations,
    streaming/loading, diff review, memory, voice, checkout in-chat  Kokonut UI (catégorie AI) — d'abord

Le besoin est une SECTION/PAGE entière (hero, pricing, features, footer, dashboard, template) ?
 └─ Watermelon UI (blocks / dashboards / templates) via MCP `compose_page` / `search`
    Si Watermelon n'a rien de pertinent → Kokonut Pro/Cards, sinon composer à la main avec shadcn

Le besoin est un EFFET VISUEL "wow" décoratif ?
 ├─ background plein écran (aurora, particules, grille, ondes) ..... React Bits Backgrounds (ou Kokonut Backgrounds)
 ├─ texte animé (split, blur-in, shiny, scramble, typewriter) ...... React Bits Text Animations
 │    (cas simple de reveal sur UN titre dans un projet qui a déjà anime.js → anime.js splitText)
 └─ curseur, glow/spotlight card, tilt, magnet ..................... React Bits (Animations / Components)

Le besoin est un COMPOSANT interactif de produit (bouton, nav, input, card, toast, empty state) ?
 └─ Kokonut UI d'abord → Watermelon animated-components ensuite → shadcn/ui en dernier recours

La page est une VITRINE dont le scroll doit être fluide (pas un dashboard, pas un formulaire) ?
 └─ Lenis (MIT) + GSAP ticker. Jamais avec ScrollSmoother. Jamais un 2ᵉ requestAnimationFrame. Détail : references/lenis.md

Le besoin est une ANIMATION CUSTOM ORCHESTRÉE (séquence, SVG, scroll, stagger de grille, motion path, drag/spring) ?
 ├─ pin, scrub, section horizontale, batch de reveals, parallaxe au scroll document
 │     ................................................................ GSAP ScrollTrigger
 ├─ titre découpé en lignes/mots avec texte accessible pour le lecteur d'écran
 │     ................................................................ GSAP SplitText (mask, autoSplit)
 ├─ réordonnancement DOM / shared element entre deux layouts .......... GSAP Flip
 ├─ drag qui continue après le relâchement ............................ GSAP Draggable + InertiaPlugin
 ├─ sur du SVG local (tracé, morph, suivre un chemin) ................. anime.js (createDrawable / morphTo / createMotionPath)
 │     ou GSAP DrawSVG / MorphSVG / MotionPath si GSAP est déjà chargé pour le scroll
 ├─ séquence locale / stagger / apparition onScroll ................... anime.js (createTimeline / stagger / onScroll)
 ├─ enter/exit/layout/hover/geste d'UN composant React ................ motion (motion/react)  ← pas anime.js ni GSAP
 └─ simple hover/transition d'état .................................... CSS (transition / @starting-style) — pas de lib
```

### Règles de départage (conflits fréquents)

| Situation | Décision | Pourquoi |
|---|---|---|
| anime.js **vs** motion pour animer un composant React | **motion** si c'est piloté par l'état React (mount/unmount, layout, `whileHover`) ; **anime.js** si c'est une séquence impérative locale, du SVG, une grille de stagger | motion s'intègre au cycle React ; anime.js excelle en chorégraphie locale |
| anime.js **vs** GSAP | **GSAP** dès qu'il y a pin/scrub/batch/FLIP/inertie ou un composant React Bits qui importe déjà `gsap`. **anime.js** pour une séquence enfermée dans un composant, sans scroll document | un seul propriétaire de `transform` par élément ; si GSAP est chargé, le scroll reste dans GSAP |
| Lenis **vs** ScrollSmoother | **Lenis** (scroll natif, `position: sticky` intact). ScrollSmoother seulement si on veut explicitement ses `data-speed`. **Jamais les deux** | deux smooth-scrolls se battent le même `scroll` |
| Même élément animé par 2 moteurs | **Interdit** (GSAP + anime.js + motion + CSS sur le même `transform`) | un seul propriétaire de `transform`/`opacity` par élément ; sinon imbrique (wrapper ≠ enfant) |
| React Bits propose gsap/three/ogl, le projet n'a que motion | Préférer la variante dont les deps sont **déjà installées**. Si le composant choisi importe `gsap`, le garder et **ne pas** réanimer ces nœuds avec anime.js. `three` : une scène max par page | poids du bundle |
| Kokonut **vs** Watermelon pour un composant | **Kokonut** = qualité/finition + IA ; **Watermelon** = largeur du catalogue + blocs de page/dashboards | ne prends pas Watermelon pour un chat IA si Kokonut l'a |
| Chart décoratif vs chart réel | Données réelles/éditables ⇒ **ECharts** ; illustration figée ⇒ SVG | accessibilité, tooltips, resize |
| Besoin non couvert | shadcn/ui + Tailwind, ou `motion` ; **ne pas inventer** un outil hors de cette liste sans le justifier | cohérence |

### Budgets (garde-fous)

- **≤ 1 background WebGL/canvas plein écran** par page ; il doit être `pointer-events-none`, en fond, mis en pause hors viewport/onglet.
- **≤ 1 dépendance WebGL nouvelle** (`three` ou `ogl`) par page. GSAP et Lenis ne comptent pas comme WebGL : les charger dès qu'un pin, un scrub ou un smooth scroll de vitrine est décidé.
- ECharts : **toujours tree-shaké** (`echarts/core`) ; jamais `import * as echarts from "echarts"` dans une app livrée (~1 Mo).
- anime.js : imports nommés (`import { animate, stagger } from "animejs"`) — v4 est tree-shakable.
- GSAP : `import { ScrollTrigger } from "gsap/ScrollTrigger"` puis `gsap.registerPlugin(...)`. Jamais le dépôt npm privé GreenSock, plus aucun token Club. En React : `useGSAP` de `@gsap/react` (revert automatique).
- Pas plus de ~3 « moments d'animation » simultanés à l'écran ; hiérarchise (1 héros, le reste discret).

---

## 2. Chercher avant d'écrire (machine-readable)

| Outil | Point d'entrée agent |
|---|---|
| Kokonut UI | `https://kokonutui.com/llms.txt` (liste + description), `https://kokonutui.com/setup.md`, **toute page de doc en Markdown avec la source complète : ajouter `.md`** (ex. `https://kokonutui.com/docs/buttons/particle-button.md`), MCP shadcn |
| Watermelon UI | MCP `https://mcp.watermelon.sh/mcp` (outils : `search`, `get_inspiration`, `get_component`, `compose_page`, `list_categories`), API `https://ui.watermelon.sh/api/v1/catalog/{summary,entries}`, `https://ui.watermelon.sh/llms.txt`, `openapi.json` |
| React Bits | `https://reactbits.dev/llms.txt`, registry `https://reactbits.dev/r/<Nom>-<LANG>-<STYLE>.json`, MCP via shadcn |
| GSAP 3 | `https://gsap.com/llms.txt` (index agent), docs `https://gsap.com/docs/v3/`. Plugins = imports `gsap/<Plugin>` |
| Lenis | `https://github.com/darkroomengineering/lenis` (README + `packages/react/README.md`), CSS `lenis/dist/lenis.css` |
| anime.js | `https://animejs.com/documentation/` (v4) — chaque section a un exemple ; migration v3→v4 : wiki GitHub |
| ECharts | `https://echarts.apache.org/en/option.html` (référence option), `https://echarts.apache.org/examples/en/index.html` (galerie, onglet *Full Code* = code tree-shaké généré), handbook `…/handbook/en/basics/import/` |

Commandes utiles :

```bash
# Kokonut : lister tout le catalogue / lire la source d'un composant avant de l'installer
curl -s https://kokonutui.com/llms.txt | grep -i "<mot-clé>"
curl -s https://kokonutui.com/docs/ai/ai-tool-calls.md

# Watermelon : filtrer par kind (components|animated-components|blocks|dashboards|templates) + category + limit
curl -s "https://ui.watermelon.sh/api/v1/catalog/entries?kind=animated-components&category=cards&limit=40"
curl -s "https://ui.watermelon.sh/api/v1/catalog/entries/animated-components/deployment-card"   # détail + registryUrl
# ⚠ l'API liste par ordre alphabétique avec limit=20 par défaut : TOUJOURS passer category + limit, ou utiliser le MCP `search`.

# MCP (une fois par machine)
claude mcp add --transport http watermelon https://mcp.watermelon.sh/mcp
npx shadcn@latest mcp init --client claude   # (ou cursor | vscode | codex) → parcourir @kokonutui / @react-bits
```

---

## 3. Installer (toujours par CLI)

```bash
bash SKILLS/scripts/setup.sh      # idempotent : components.json + registries + cn() + alias + deps de base

# Kokonut UI  → src/components/kokonutui/<nom>.tsx
npx shadcn@latest add @kokonutui/<nom> -y

# React Bits  → nom PascalCase + suffixe variante : TS-TW = TypeScript + Tailwind (défaut recommandé)
npx shadcn@latest add @react-bits/<Nom>-TS-TW -y        # ex. ShinyText-TS-TW, Aurora-TS-TW, CountUp-TS-TW

# Watermelon  → namespace officiel, ou URL directe
npx shadcn@latest add @watermelon/<slug> -y
npx shadcn@latest add https://registry.watermelon.sh/r/<slug>.json -y

# motion, anime.js, ECharts, GSAP, Lenis (Lenis seulement si la page est une vitrine)
npm i motion animejs echarts gsap @gsap/react lenis
```

Règles d'installation :
- Lis la source générée **avant** de l'utiliser (props réelles, deps, imports).
- `-o` écrase les fichiers existants : à n'utiliser que si tu sais pourquoi.
- Le code installé **t'appartient** : modifie-le sur place (couleurs, tailles, props) plutôt que de l'envelopper.
- **Après chaque `add`**, relance le preflight/`git diff` : les registries peuvent écraser des fichiers partagés
  (cas réel : un composant Watermelon a réécrit `src/lib/utils.ts` en `export { cn } from "cn"` → build cassé ; il faut restaurer `clsx` + `tailwind-merge`).
- Watermelon importe souvent `framer-motion` ; remplace par `motion/react` (`sed -i "s#from 'framer-motion'#from 'motion/react'#"`) pour ne garder qu'**une** lib.
- Si `components.json`/alias `@/` manquent, ne copie pas à la main : lance `setup.sh`.
- Le projet cible peut interdire de modifier `vite.config.ts`/`package.json` à la main : utilise `npm i` et l'alias déjà présent.

---

## 4. Règles dures d'intégration

**Design system unique.** Les composants copiés utilisent les tokens shadcn (`bg-background`, `text-foreground`,
`border-border`, `bg-primary`, `text-muted-foreground`…). Définis-les **une fois** dans `src/index.css`
(`:root` + `@theme inline`, Tailwind v4). Aligne ensuite ECharts (palette, texte, `backgroundColor: "transparent"`)
et anime.js (couleurs) sur ces mêmes valeurs. Pas de 3 palettes différentes.

**Cycle de vie React (StrictMode = double mount).**
- anime.js : **toujours** `createScope({ root }).add(...)` dans `useEffect` + `return () => scope.revert()`.
- GSAP en React : **toujours** `useGSAP(() => { ... }, { scope })`. Pas de `gsap.to` dans le corps du render. `gsap.context` + `ctx.revert()` seulement s'il n'y a pas `@gsap/react`.
- Lenis : une instance racine, `autoRaf: false` quand GSAP drive le ticker (`lenis.raf(time * 1000)`), `lenis.destroy()` / retirer le callback au cleanup. `prefers-reduced-motion` → ne pas monter Lenis.
- ECharts : `init` dans `useEffect`, `ResizeObserver` → `chart.resize()`, `chart.dispose()` au cleanup ; `setOption` dans un effet séparé qui dépend des données.
- Aucun `document.querySelector` global : cible via `ref`/scope.

**Accessibilité & mouvement.**
- Respecte `prefers-reduced-motion` : anime.js → `utils.set(...état final...)` ; GSAP → `gsap.matchMedia()` sur `(prefers-reduced-motion: no-preference)` et ne pas créer les tweens sinon ; Lenis non monté ; motion → `useReducedMotion()` / `<MotionConfig reducedMotion="user">` ; ECharts → `animation: false`.
- Contenu essentiel jamais **uniquement** révélé par animation (état initial caché ⇒ prévoir fallback).
- Charts : `aria: { enabled: true }` dans l'option ECharts + titre/résumé texte à côté.
- Éléments décoratifs : `aria-hidden`, `pointer-events-none`.

**Performance.**
- Anime/motion : ne animer que `transform`, `opacity`, `filter` (éviter `width/height/top/left`).
- `will-change` seulement pendant l'animation. Pas d'animation infinie hors viewport (`onScroll`/IntersectionObserver).
- ECharts : > ~5 000 points ⇒ `large: true`, `sampling: "lttb"`, ou `dataZoom` ; jamais `setOption(…, true)` en boucle serrée.
- Un composant WebGL = un contexte : ne pas en monter 6 dans une liste.

**Hygiène de code.**
- TypeScript strict : `EChartsOption`/`ComposeOption`, refs typés, pas de `any`.
- Garde les composants copiés dans `src/components/{kokonutui,watermelon,<react-bits à plat>,ui}` ; **tes** wrappers dans `src/components/`.
- Crédite les sources dans le footer si le projet est public (MIT, mais bonne pratique).
- Ne pas committer de secrets ; les registries Pro (Kokonut Pro, React Bits Pro) sont **payants** : ne les utilise que si l'utilisateur a une licence.

---

## 5. Recettes de composition (qui fait quoi dans une même page)

| Page | Composition recommandée |
|---|---|
| **Landing SaaS / produit** | Watermelon (blocks : hero/pricing/features) + React Bits (Aurora/Particles en fond **un seul**, ShinyText/BlurText sur le titre) + anime.js (reveal au scroll `onScroll`, ligne SVG qui se dessine) + Kokonut (bouton CTA `particle-button`) |
| **Dashboard analytics** | Watermelon dashboards (layout/cartes) + **ECharts** (tous les charts) + React Bits CountUp (KPI) + anime.js (entrée en cascade `stagger` des cartes) |
| **App d'agent IA / chat** | Kokonut AI (`ai-prompt`, `ai-tool-calls`, `ai-loading`, `ai-tool-approval`, `ai-citations`) + shadcn primitives + ECharts pour les sorties chiffrées de l'agent |
| **Portfolio / vitrine créative** | React Bits (texte, curseur, backgrounds) + anime.js (timeline d'intro, morph SVG) + Kokonut (cards/nav) |
| **Page d'état / observabilité** | Kokonut `uptime-card`/`metric-card` + ECharts (heatmap/gauge/line) + Watermelon `deployment-card` |

Détails, snippets TS complets et pièges : `references/recipes.md`.

---

## 6. Checklist finale (à cocher avant de répondre)

- [ ] Chaque besoin a une décision écrite (outil + raison) conforme à l'arbre §1.
- [ ] Aucun composant du catalogue réécrit à la main ; installés par CLI ; source lue.
- [ ] `src/lib/utils.ts` intact (`cn` = clsx + twMerge) ; un seul alias `@/`.
- [ ] Une seule lib d'animation par élément ; pas de `framer-motion` + `motion` en double.
- [ ] ECharts tree-shaké, redimensionné, disposé ; palette = tokens du thème.
- [ ] anime.js dans `createScope` + `revert()` ; imports nommés. GSAP dans `useGSAP` + `registerPlugin`. Lenis sur un seul ticker, absent si reduced-motion ou dashboard.
- [ ] `prefers-reduced-motion` géré ; contraste ≥ 4.5:1 ; focus visibles ; clavier OK.
- [ ] ≤ 1 fond WebGL ; bundle raisonnable (`npm run build`, regarder la taille).
- [ ] `npm run build` réussi sans erreur TypeScript/Vite.
- [ ] Rendu **vérifié visuellement** (Playwright headless : `npx playwright install chromium`, captures desktop + 390 px, console sans erreur) — c'est ainsi qu'ont été trouvés : le conflit `relative`/`absolute` d'Aurora, un heatmap illisible, des labels de radar rognés.
- [ ] Résumé final : outils choisis, pourquoi, fichiers créés, dépendances ajoutées.

## 7. Anti-patterns (refuser)

1. Dessiner un « graphique » avec des `div` + anime.js alors que ECharts existe.
2. Importer tout ECharts / tout lodash-style ; oublier `echarts.use([...Renderer])` (erreur : *Renderer is not registered*).
3. anime.js v3 (`anime({targets})`, `anime.timeline`) — **c'est v4** : `animate(targets, params)`, `createTimeline()`, `ease` (pas `easing`), `delay: stagger()`.
3b. GSAP via `npm.greensock.com` ou sans `registerPlugin`. Lenis avec son propre `requestAnimationFrame` **en plus** du ticker GSAP, ou `ScrollTrigger.scrollerProxy` pour un Lenis de document. ScrollSmoother et Lenis ensemble.
4. `useEffect` sans cleanup ; animation relancée à chaque re-render.
5. Recopier de mémoire le code d'un composant Kokonut/React Bits/Watermelon (obsolète, props inventées).
6. Empiler 3 backgrounds animés + 5 textes qui brillent « parce que c'est joli ».
7. Animer `width/height/top/left` ; layout shift ; animations bloquant le contenu (> 600 ms avant lisibilité).
8. Installer un composant Pro payant sans licence.
9. Ignorer la sortie du CLI (fichier écrasé, dépendance manquante) et ne pas lancer le build.
10. Utiliser anime.js pour des animations d'apparition/disparition d'éléments React conditionnels (utilise motion `AnimatePresence`).
