# GSAP 3 — scroll, texte, FLIP, drag

Docs : https://gsap.com/docs/v3/ · index agent : https://gsap.com/llms.txt
Install : `npm i gsap @gsap/react`

Depuis 2025 **tous** les plugins (ScrollTrigger, SplitText, Flip, DrawSVG, MorphSVG, MotionPath, Draggable, Inertia, Observer, CustomEase, ScrollSmoother, ScrollTo…) sont dans le paquet public `gsap`. Licence standard gratuite, y compris un usage commercial et du code généré par une IA. Interdit seulement : en faire un builder visuel d'animations qui concurrence Webflow.

Ne jamais ajouter de token Club, de `.npmrc` vers `npm.greensock.com`, ni `@gsap/business`.

## Quand l'utiliser / ne pas l'utiliser

| Utiliser | Ne pas utiliser |
|---|---|
| Pin, scrub, section horizontale, `ScrollTrigger.batch` | Hover d'un bouton → CSS ou motion |
| SplitText (lignes masquées, copie accessible) | Apparition/disparition conditionnelle React → motion `AnimatePresence` |
| Flip après un changement de DOM | Séquence locale sans scroll, et GSAP pas déjà chargé → anime.js |
| Draggable + InertiaPlugin | Graphique → ECharts |
| DrawSVG / MorphSVG / MotionPath **si** GSAP anime déjà la page | Réanimer un nœud déjà tweené par anime.js ou motion |

Si un composant React Bits importe `gsap`, enregistrer les plugins qu'il utilise et ne pas lancer anime.js sur les mêmes nœuds.

## Enregistrer, puis animer

```ts
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { SplitText } from "gsap/SplitText";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(ScrollTrigger, SplitText, useGSAP);
```

Importer depuis `gsap/NomDuPlugin`. Sans `registerPlugin`, le plugin est silencieux.

## React — `useGSAP`

`useGSAP` revert le contexte au démontage et quand `dependencies` change. Préférable à un `useEffect` nu. Les sélecteurs sont limités au `scope`.

```tsx
const root = useRef<HTMLElement>(null);

useGSAP(() => {
  const mm = gsap.matchMedia();
  mm.add("(prefers-reduced-motion: no-preference)", () => {
    gsap.from(".reveal", {
      y: 24,
      autoAlpha: 0,
      duration: 0.8,
      stagger: 0.06,
      ease: "power3.out",
    });
  });
}, { scope: root });
```

`autoAlpha` anime opacité **et** `visibility`. Ne pas poser en plus une `transition` CSS sur `transform` ou `opacity`.

## Timeline

```ts
const tl = gsap.timeline({ defaults: { duration: 0.6, ease: "power3.out" } });
tl.to(".a", { y: 0, autoAlpha: 1 })
  .to(".b", { y: 0, autoAlpha: 1 }, "<0.1")   // 0,1 s après le DÉBUT du précédent
  .to(".c", { scale: 1 }, "-=0.2");            // chevauche la fin
```

`"<"`, `"-=0.2"`, labels (`tl.addLabel("hero")`) plutôt que des délais absolus dès que la scène sera retouchée.

## ScrollTrigger

```ts
gsap.to(".panel", {
  xPercent: -100,
  ease: "none",
  scrollTrigger: {
    trigger: ".track",
    start: "top top",
    end: "+=100%",
    pin: true,
    scrub: 1,
    invalidateOnRefresh: true,
  },
});
```

- `scrub: true` est collé au scroll. `scrub: 0.6` à `1` rattrape en douceur.
- On pin le rail, on anime l'enfant. `anticipatePin: 1` si le pin saute sur un scroll rapide.
- Après polices, images, ou hauteur dynamique : `ScrollTrigger.refresh()`. Avec Lenis : `lenis.resize()` aussi.
- Liste : `ScrollTrigger.batch(".card", { onEnter: (els) => gsap.to(els, { autoAlpha: 1, y: 0, stagger: 0.05 }) })`. Pas un ScrollTrigger par carte.
- `once: true` pour une entrée qui ne doit pas rejouer.
- `markers: true` uniquement en debug.

Eases : déplacement `power3.out` / `power4.out`, arrivée de nulle part `expo.out`, scrub `none`, overshoot physique seulement `back.out(1.4)`. Pas d'`elastic` sur chaque entrée.

## Plugins à sortir sans hésiter

| Besoin | Appel |
|---|---|
| Texte | `new SplitText(el, { type: "lines,words", mask: "lines", autoSplit: true })` puis `split.revert()` au cleanup. Attendre `document.fonts.ready` avant le split |
| Layout | `const state = Flip.getState(items)` → changer le DOM → `Flip.from(state, { absolute: true, duration: 0.6, ease: "power2.inOut" })` |
| Trait SVG | `drawSVG: "0% 100%"` (plugin DrawSVG) |
| Morph | `morphSVG: { shape: "#b", type: "rotational" }` |
| Chemin | `motionPath: { path: "#track", align: "#track", autoRotate: true }` |
| Drag | `Draggable.create` + `inertia: true` (InertiaPlugin enregistré) |
| Curseur | `gsap.quickTo(el, "x", { duration: 0.4, ease: "power3" })` **une fois**, pas `gsap.to` à chaque `pointermove` |

## Pièges

- Animer `top` / `left` / `width` / `height` : reflow à chaque frame. Rester sur `x`, `y`, `xPercent`, `scale`, `rotation`, `autoAlpha`.
- `transform` Tailwind (`-translate-x-1/2`) et un tween `x` sur le même nœud s'écrasent. Wrapper, ou tout faire dans GSAP.
- Oublier `invalidateOnRefresh: true` sur un scrub qui lit des largeurs : au resize les valeurs sont périmées.
- SplitText avant le chargement des polices : les retours à la ligne sont faux.
