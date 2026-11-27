# React Bits — effets créatifs animés (code que tu possèdes)

Site : https://reactbits.dev · llms.txt : https://reactbits.dev/llms.txt · licence **MIT + Commons Clause** : libre dans une app ou un site, y compris commercial ; interdit de revendre ou redistribuer les composants eux-mêmes. 4 variantes : **JS-CSS, JS-TW, TS-CSS, TS-TW**.
Pro (payant, registry `@reactbits-pro` / `@reactbits-starter`) : blocs, templates, app UI → **ne pas installer sans licence**. Ports : Vue Bits, Svelte Bits, Solid Bits.

## Quand le choisir

- **Backgrounds** plein écran (WebGL/canvas) : `Aurora`, `Particles`, `Galaxy`, `Silk`, `Plasma`, `Waves`, `LightRays`, `DotGrid`, `Beams`, `Orb`, `Iridescence`, `Threads`, `LiquidChrome`, `Prism`, `PixelBlast`, `Hyperspeed`, `Lightning`…
- **Text Animations** : `SplitText`, `BlurText`, `ShinyText`, `GradientText`, `DecryptedText`, `ScrambledText`, `TextType`, `RotatingText`, `CountUp`, `ScrollReveal`, `ScrollFloat`, `ScrollVelocity`, `Shuffle`, `TrueFocus`, `GlitchText`, `FuzzyText`…
- **Animations** (interactions/effets) : `Magnet`, `ClickSpark`, `GlareHover`, `ElectricBorder`, `StarBorder`, `AnimatedContent`, `FadeContent`, `BlobCursor`, `SplashCursor`, `TargetCursor`, `ImageTrail`, `LogoLoop`, `Noise`, `GradualBlur`, `MetaBalls`…
- **Components** : `SpotlightCard`, `MagicBento`, `TiltedCard`, `Dock`, `CardNav`, `PillNav`, `StaggeredMenu`, `Carousel`, `Stepper`, `ChromaGrid`, `ScrollStack`, `Masonry`, `ProfileCard`, `GlassSurface`, `Folder`, `Lanyard`…
- **Micro** : `HoldButton`, `SlideCommit`, `SquishSwitch`, `SpringCheck`, `PromptBar`, `SwipeToast`, `WarmTooltip`, `LatticeLoader`…

**Vérifie les noms** dans `llms.txt` (catalogue vivant, noms PascalCase = identifiants CLI).

**Ne pas choisir** pour : composants « produit » finis (→ Kokonut), sections de page (→ Watermelon), données (→ ECharts), séquences scénarisées sur-mesure (→ anime.js).

## Installation (testée)

```bash
# components.json → "registries": { "@react-bits": "https://reactbits.dev/r/{name}.json" }
npx shadcn@latest add @react-bits/<Nom>-<LANG>-<STYLE> -y
#   LANG = JS | TS     STYLE = CSS | TW      → par défaut en projet Tailwind + TS : <Nom>-TS-TW
# équivalent sans registry : npx shadcn@latest add https://reactbits.dev/r/<Nom>-TS-TW
# alt. : npx jsrepo@latest add https://reactbits.dev/r/<Nom>-TS-TW
```
Écrit **à plat** dans `src/components/<Nom>.tsx` (et installe ses deps : `motion`, `gsap`, `ogl`, `three`…).
Exemple validé : `ShinyText-TS-TW`, `CountUp-TS-TW`, `SpotlightCard-TS-TW`, `Aurora-TS-TW` (dep `ogl`).

**Choix de variante** : projet Tailwind ⇒ `-TW` ; sinon `-CSS` (ajoute un `.css`). TypeScript ⇒ `TS`.

## Choisir selon les dépendances

| Dép. | Poids | Conseil |
|---|---|---|
| `motion` | déjà là (Kokonut/Watermelon) | idéal |
| `ogl` | léger (~30 Ko) WebGL | OK pour **un** background |
| `gsap` | paquet public, plugins inclus | le garder tel que le composant l'importe ; enregistrer le plugin s'il manque. Ne pas doubler avec anime.js sur les mêmes nœuds. Voir `references/gsap.md` |
| `three` (+ `@react-three/fiber`) | ~600 Ko+ | uniquement si la 3D est le cœur du design (Lanyard, ModelViewer) |

## Usage correct (APIs vérifiées sur les sources)

```tsx
import Aurora from "@/components/Aurora";
<div className="relative isolate overflow-hidden">
  {/* WRAPPER obligatoire : le root d'Aurora porte déjà `relative h-full w-full` → `absolute` en className serait annulé
      et le fond deviendrait un item de flex/grid qui pousse le contenu (bug réel rencontré) */}
  <div className="absolute inset-0 -z-10 pointer-events-none" aria-hidden>
    <Aurora colorStops={["#7c3aed", "#22d3ee", "#34d399"]} amplitude={1.1} blend={0.6} speed={0.6} />
  </div>
  …contenu…
</div>
// Props : colorStops[], amplitude, blend, speed, glow, brightness, layers, direction, mouseInteraction, opacity, paused, dpr…

import ShinyText from "@/components/ShinyText";
<ShinyText text="Le skill qui choisit pour vous" color="#a1a1aa" shineColor="#ffffff" speed={3} />

import CountUp from "@/components/CountUp";
<CountUp to={12840} separator=" " duration={2} trigger="view" suffix=" req/s" />   // trigger: 'view' | 'load' ; mode: 'count' | 'roll'

import SpotlightCard from "@/components/SpotlightCard";
<SpotlightCard spotlightColor="rgba(139,92,246,.25)" className="p-6 rounded-2xl">…</SpotlightCard>
```

## Règles

1. **Lire la source** installée : props et valeurs par défaut changent entre versions (le catalogue est vivant).
2. **Un seul « moment wow » dominant par écran** (fond OU titre animé OU curseur), les autres en discret.
3. Décoratif ⇒ `pointer-events-none`, `aria-hidden`, `-z-10`, hors du flux de lecture ; le texte doit rester lisible sans l'effet (contraste testé sur le fond le plus clair).
4. Backgrounds WebGL : un seul par page, `dpr` ≤ 2, pause hors écran (`paused`/IntersectionObserver), fallback CSS gradient si WebGL indisponible, jamais dans une liste/carte répétée.
5. Texte animé : garder le texte réel dans le DOM (SEO/lecteurs d'écran) ; `prefers-reduced-motion` → désactiver (`disabled`, `speed=0`, ou rendre `<span>` statique).
6. Les composants gèrent leur propre animation : **n'ajoute pas anime.js/motion sur le même élément**. Pour ajouter un effet, entoure d'un wrapper.
7. Adapte les couleurs au thème (props de couleur, ou classes TW) — ne laisse pas la palette violet/vert par défaut si elle jure.
8. Tailwind v4 : si une variante `-TW` utilise des utilitaires/plugins v3 (`tailwind.config`), corrige-les à la main ou prends `-CSS`.

## Pièges

- **Positionnement** : beaucoup de composants fixent eux-mêmes `relative`/`h-full w-full` sur leur racine. Ne positionne pas via `className` : place-les dans un wrapper `absolute inset-0` (sinon conflit de classes Tailwind et mise en page cassée). Vérifie toujours visuellement.

- Composants basés sur `gsap` : enregistrer les plugins (`gsap.registerPlugin(ScrollTrigger)`) est déjà dans le fichier ; ne pas dupliquer.
- Canvas sans dimension : le parent doit avoir `relative` + taille ; `Aurora/Particles` se calent sur le conteneur.
- SSR/Next : composants WebGL ⇒ `"use client"` + éventuellement `dynamic(() => import(...), { ssr: false })`.
- Import par défaut vs nommé : vérifier la fin du fichier (`export default` vs `export const`).
- Ne pas importer de CSS global fourni avec la variante `-CSS` dans un composant serveur.
