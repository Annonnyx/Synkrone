# Recettes de composition & thème (ai-ui-stack)

## Thème : tokens partagés (Tailwind v4) — à définir UNE fois dans `src/index.css`

```css
@import "tailwindcss";
@custom-variant dark (&:is(.dark *));

:root {
  --radius: .75rem;
  --background: oklch(.145 .01 280);  --foreground: oklch(.97 0 0);
  --card: oklch(.19 .012 280);        --card-foreground: oklch(.97 0 0);
  --popover: oklch(.19 .012 280);     --popover-foreground: oklch(.97 0 0);
  --primary: oklch(.97 0 0);          --primary-foreground: oklch(.2 .01 280);
  --secondary: oklch(.25 .015 280);   --secondary-foreground: oklch(.97 0 0);
  --muted: oklch(.25 .015 280);       --muted-foreground: oklch(.7 .015 280);
  --accent: oklch(.28 .02 280);       --accent-foreground: oklch(.97 0 0);
  --destructive: oklch(.65 .22 25);
  --border: oklch(1 0 0 / 10%);       --input: oklch(1 0 0 / 14%);  --ring: oklch(.65 .2 290);
}
@theme inline {
  --color-background: var(--background); --color-foreground: var(--foreground);
  --color-card: var(--card); --color-card-foreground: var(--card-foreground);
  --color-popover: var(--popover); --color-popover-foreground: var(--popover-foreground);
  --color-primary: var(--primary); --color-primary-foreground: var(--primary-foreground);
  --color-secondary: var(--secondary); --color-secondary-foreground: var(--secondary-foreground);
  --color-muted: var(--muted); --color-muted-foreground: var(--muted-foreground);
  --color-accent: var(--accent); --color-accent-foreground: var(--accent-foreground);
  --color-destructive: var(--destructive); --color-border: var(--border);
  --color-input: var(--input); --color-ring: var(--ring);
  --radius-sm: calc(var(--radius) - 4px); --radius-md: calc(var(--radius) - 2px);
  --radius-lg: var(--radius); --radius-xl: calc(var(--radius) + 4px);
}
@layer base { * { border-color: var(--border); } body { background: var(--background); color: var(--foreground); } }
```
Dark par défaut ⇒ mets les valeurs dark dans `:root` (comme ci-dessus) **et** `<html class="dark">` pour les composants `dark:`.
ECharts n'accepte pas `oklch()` : duplique la palette en hex dans un module `theme.ts`.

## Recette A — Landing « produit IA »

1. **Fond** : `Aurora` (React Bits) dans un wrapper `absolute inset-0 -z-10 pointer-events-none` (jamais `absolute` directement sur le composant).
2. **Titre** : `ShinyText` pour le sous-titre ; titre H1 en texte simple + reveal anime.js (`splitText` + `stagger`) **ou** `BlurText` (un seul des deux).
3. **CTA** : `ParticleButton` (Kokonut) avec `onClick` async.
4. **Chiffres** : `CountUp` (React Bits) dans des `SpotlightCard`.
5. **Scroll** : Lenis + GSAP si la page se parcourt (pin / scrub / reveals en batch). Révéler une section sans la pinner peut rester en anime.js `onScroll({ repeat: false })`. Un seul des deux possède chaque nœud. `createDrawable` ou DrawSVG pour une ligne de connexion SVG.
6. **Sections** : blocs Watermelon (pricing/features/footer) harmonisés aux tokens.

## Recette B — Dashboard analytics

```
Layout/sidebar/cartes  → Watermelon dashboards (ou grid Tailwind + shadcn Card)
KPI                    → CountUp (React Bits) ; delta ↑↓ en couleur sémantique
Courbes/barres/radar…  → ECharts (<Chart option={…}/> du hook de référence)
Entrée en cascade      → anime.js stagger OU `ScrollTrigger.batch` si GSAP est déjà là (une fois, au montage). Pas les deux sur `.card`
États/agents           → Kokonut ai-tool-calls / uptime-card / Watermelon deployment-card
```
Données : une seule source (`useMemo` → options ECharts + KPI). Pas de chiffres inventés différents entre carte et chart.

## Recette C — Interface d'agent IA

`ai-prompt` (entrée) → `ai-loading` (progression) → `ai-tool-calls` (appels, relier à `part.state` du Vercel AI SDK) →
`ai-tool-approval` (actions sensibles : press-and-hold) → réponse + `ai-citations`. Sorties numériques de l'agent ⇒ **ECharts** dans la bulle.
Un seul accent de couleur ; pas de fond WebGL derrière un chat long (lisibilité + perf).

## Recette D — Router un besoin ambigu (exemples)

| Demande utilisateur | Décision |
|---|---|
| « Un graphique des ventes avec zoom » | ECharts `line` + `dataZoom` |
| « Un compteur qui monte à 10 000 » | React Bits `CountUp` |
| « Le logo se dessine puis le texte apparaît » | anime.js `createTimeline` + `createDrawable` + `splitText` |
| « Une modale qui s'ouvre en douceur » | motion `AnimatePresence` (ou shadcn Dialog) — pas anime.js |
| « Un fond animé sympa » | React Bits `Aurora`/`Particles` (1 seul) |
| « Page de pricing » | Watermelon block `pricing` |
| « Chat avec appels d'outils visibles » | Kokonut `ai-tool-calls` |
| « Effet de curseur magnétique sur un bouton » | React Bits `Magnet` |
| « Carte de statut de déploiement » | Watermelon `deployment-card` |
| « Heatmap d'activité sur 12 mois » | ECharts `heatmap` + `calendar` |
| « Révéler des cartes au scroll » | anime.js `onScroll` + `stagger`, ou `ScrollTrigger.batch` si GSAP est déjà chargé |
| « Section épinglée qui défile à l'horizontale » | GSAP ScrollTrigger `pin` + `scrub` |
| « Scroll fluide sur la landing » | Lenis piloté par `gsap.ticker` (pas sur un dashboard) |
| « Le titre se découpe en lignes accessibles » | GSAP SplitText (`mask: "lines"`) |
| « Bouton qui confirme une action serveur » | Kokonut `particle-button` |

## Pipeline de vérification

```bash
bash SKILLS/scripts/preflight.sh      # état
npm run build                                       # TypeScript + bundle
# regarder la taille du bundle : ECharts tree-shaké ≈ 400–600 Ko minifié selon les charts ; sinon ≈ 1 Mo ⇒ imports à corriger
```
Contrôle visuel : 375 px / 1280 px, mode reduced-motion (DevTools → Rendering), navigation clavier, console sans warnings.
