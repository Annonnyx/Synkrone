# anime.js v4 — guide d'usage correct

Doc : https://animejs.com/documentation/ · Taille : ~3 Ko (WAAPI) → ~25 Ko tout inclus, **tree-shakable**.
Install : `npm i animejs` (v4+). **Tout ce qui suit est la v4.**

## Quand l'utiliser / ne pas l'utiliser

| ✅ Utiliser | ❌ Ne pas utiliser |
|---|---|
| Timeline multi-éléments, séquences, `stagger` (grille, from center) | Apparition/disparition d'un composant React conditionnel → `motion` `AnimatePresence` |
| SVG : tracer un chemin (`createDrawable`), morph (`morphTo`), suivre un chemin (`createMotionPath`) | Hover/focus simples → CSS `transition` |
| Animation synchronisée au scroll (`onScroll`) | Dessiner des graphiques → ECharts |
| Compteurs/valeurs d'objets JS (`animate(obj, { value })`) | Layout animations de listes React → `motion` `layout` |
| Drag/spring/flick (`createDraggable`, `spring`) | Effets texte déjà fournis par React Bits (si le projet les utilise) |
| Split de texte lettres/mots (`splitText`) + scramble (`scrambleText`) | |

## Différences v3 → v4 (erreurs classiques des agents)

| v3 (FAUX en v4) | v4 (correct) |
|---|---|
| `anime({ targets: '.a', translateX: 100, easing: 'easeOutExpo' })` | `animate('.a', { x: 100, ease: 'outExpo' })` |
| `anime.timeline({...}).add({ targets })` | `createTimeline({ defaults }).add('.a', {...}, position)` |
| `anime.stagger(50)` | `import { stagger }` → `delay: stagger(50)` |
| `direction: 'alternate'` | `alternate: true` (+ `loop: true`) |
| `translateX/translateY` | `x` / `y` (aussi `rotate`, `scale`, `skew`…) |
| `value: [from, to]` | idem **ou** `{ from, to }` ; keyframes : tableau `[{ to: 1.2, duration: 200 }, { to: 1 }]` |
| `anime.set` / `anime.remove` | `utils.set` / `utils.remove` (`import { utils }`) |
| `update`/`complete` callbacks | `onUpdate`, `onComplete`, `onBegin`, `onLoop` ; `.then()` / `await anim` fonctionne |
| `autoplay: false` + `anim.play()` | idem ; `anim.pause() / .restart() / .reverse() / .seek(ms) / .revert()` |

Easings v4 : `'out(3)'`, `'inOut(4)'`, `'outExpo'`, `'inOutQuad'`, `'outElastic(1, .5)'`, `spring({ bounce: .5 })`,
`cubicBezier(.7,.1,.5,.9)`, `steps(5)`. Défaut : `'out(2)'` ; durée par défaut : 1000 ms.

## Imports

```ts
import { animate, createTimeline, createScope, stagger, utils, onScroll, splitText,
         createDrawable, morphTo, createMotionPath, spring, createDraggable, scrambleText } from "animejs";
```
Sous-modules pour bundle minimal : `animejs/animation`, `animejs/timeline`, `animejs/scope`, `animejs/stagger`, `animejs/svg`, `animejs/events`, `animejs/draggable`, `animejs/easings`, `animejs/utils`, `animejs/text`, `animejs/waapi`…

## Pattern React OBLIGATOIRE (StrictMode-safe)

```tsx
import { useEffect, useRef } from "react";
import { animate, createScope, createTimeline, stagger, utils } from "animejs";

export function Reveal() {
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!root.current) return;
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

    const scope = createScope({ root }).add(() => {
      // tout ce qui est créé ici est limité à root ET nettoyé par revert()
      if (reduce) { utils.set(".item", { opacity: 1, y: 0 }); return; }
      createTimeline({ defaults: { ease: "outExpo", duration: 900 } })
        .add(".title", { opacity: [0, 1], y: [24, 0] })
        .add(".item", { opacity: [0, 1], y: [24, 0], delay: stagger(80) }, "-=600");
    });

    return () => scope.revert();          // ← indispensable (StrictMode double-monte)
  }, []);

  return (
    <div ref={root}>
      <h2 className="title opacity-0">Titre</h2>
      <p className="item opacity-0">…</p>
    </div>
  );
}
```
Notes :
- Éléments à révéler : état initial `opacity-0` en classe (évite le flash), et `utils.set` si reduced-motion.
- Méthode appelable depuis un handler : `scope.add('nom', (arg) => animate(...))` puis `scopeRef.current.methods.nom(arg)`.
- Les sélecteurs CSS sont **résolus dans `root`** ; pour un élément précis passe plutôt un `ref.current`.
- Ne déclenche pas `animate()` dans le corps du render.
- Animer une valeur de state sans re-render : `const o = { v: 0 }; animate(o, { v: 100, onUpdate: () => (el.textContent = String(Math.round(o.v))) })`.

## Recettes testées

**Stagger sur grille depuis le centre**
```ts
animate(".dot", {
  scale: [0, 1], opacity: [0, 1],
  delay: stagger(40, { grid: [12, 8], from: "center" }),
  ease: "outBack",
});
```

**Tracé SVG (line drawing)**
```ts
animate(createDrawable("path.line"), { draw: ["0 0", "0 1"], duration: 1600, ease: "inOutQuad" });
// draw = "début fin" en fractions de la longueur ; ['0 0','0 1','1 1'] = tracer puis effacer
```

**Morph de formes** (même nombre de points idéalement) : `animate("#a", { d: morphTo("#b"), ease: "inOutCirc", loop: true, alternate: true })`

**Suivre un chemin** : `animate(".car", { ...createMotionPath("#track"), duration: 4000, ease: "linear", loop: true })`

**Scroll** (déclenchement) :
```ts
animate(".card", { opacity: [0, 1], y: [40, 0], delay: stagger(100),
  autoplay: onScroll({ target: ".cards", enter: "bottom-=80 top", repeat: false }) });   // enter = "<position du CONTAINER/viewport> <position de la CIBLE>" : "bottom-=80 top" = quand le bas du viewport (−80px) atteint le haut de la cible ; repeat:false = ne joue qu'une fois (il n'y a PAS de param `once` en v4)
```
Scroll **synchronisé** (progression liée au scroll) : `autoplay: onScroll({ sync: true })` (ou `sync: 0.25` pour un lissage).
Scroll dans un conteneur : `onScroll({ container: ref.current })`.

**Compteur**
```ts
const state = { n: 0 };
animate(state, { n: 12840, duration: 1800, ease: "outExpo", modifier: utils.round(0),
  onUpdate: () => { el.textContent = state.n.toLocaleString("fr-FR"); } });
```
(Pour un KPI isolé, préférer React Bits `CountUp` — ne réécris pas si le composant existe.)

**Texte** : `const s = splitText(".headline", { chars: { wrap: "clip" } }); animate(s.chars, { y: ["100%", "0%"], delay: stagger(25), ease: "outExpo", duration: 900 });` — appelle `s.revert()` au cleanup (le scope le fait si créé dans `.add`). Splitter **après** `document.fonts.ready` si la mise en page dépend de la police.

**Drag + ressort** : `createDraggable(".knob", { container: ".track", releaseEase: spring({ stiffness: 120, damping: 12 }) })`

**Valeurs dérivées par fonction** : `x: (el, i, total) => i * 20`, `rotate: () => utils.random(-15, 15)`.

**Keyframes** : `animate(".b", { y: [{ to: -40, ease: "outQuad", duration: 300 }, { to: 0, ease: "outBounce", duration: 600 }] })`

**Positions de timeline** : `"+=200"` après la fin + 200 ms, `"-=300"` chevauchement, `"<"` même début que le précédent, `"<<+=100"`, nombre absolu `1200`, label `tl.label('x', 800)`.

## Choix WAAPI vs JS

`import { waapi } from "animejs"` → `waapi.animate(el, { transform: "translateX(100px)" })` : tourne sur le compositor (très léger, 3 Ko) pour de simples transitions de `transform/opacity` sur peu d'éléments. Utilise `animate` (JS) pour stagger complexes, timelines, objets JS, SVG, valeurs de fonction.

## Pièges

- Ne pas mélanger anime.js et CSS `transition` sur la même propriété (le `transition` CSS « mange » les frames).
- `transform` écrit par anime.js remplace `style.transform` : ne pas poser `transform` Tailwind (`-translate-x-1/2`) sur le même élément → utilise un wrapper, ou anime `x/y` en relatif.
- `loop: true` sans arrêt hors-viewport = CPU ; couple avec `onScroll` ou pause via `IntersectionObserver`.
- `animate()` retourne l'instance : stocke-la si tu dois `pause()`/`revert()` hors scope.
- Cibles inexistantes ⇒ pas d'erreur mais rien ne bouge : vérifie que les éléments sont montés dans `useEffect`.
- SSR (Next) : importer dans un composant `"use client"`, créer dans `useEffect`.

## Seuils `onScroll` (syntaxe vérifiée dans la doc)

`enter` / `leave` s'écrivent **`'<container> <target>'`** (viewport d'abord, cible ensuite), valeurs `start | end | top | bottom | center | <n>px | <n>%`, avec `+=`/`-=`.
- Défaut `enter: 'end start'`, `leave: 'start end'`.
- `'bottom top'` : entre quand le **bas du viewport** rencontre le **haut de la cible**.
- Paramètres existants : `container`, `target`, `axis`, `enter`, `leave`, `sync`, `repeat`, `debug`, callbacks `onEnter/onLeave/onUpdate…`. **Pas de `once`** → `repeat: false`.
- Astuce : `debug: true` affiche les repères de seuils à l'écran pendant la mise au point.
