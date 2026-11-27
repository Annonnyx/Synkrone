# Lenis — smooth scroll natif (MIT, gratuit)

Paquet `lenis`. Doc : https://github.com/darkroomengineering/lenis · React : `lenis/react` · CSS : `import "lenis/dist/lenis.css"`.

Lenis lisse le scroll **du navigateur**. `position: sticky`, les ancres et la barre native continuent de marcher. Ce n'est pas un hijack qui translate un conteneur.

À réserver aux pages vitrine / récit. Pas sur un dashboard, un formulaire long, ou un chat.

Limites : pas de CSS `scroll-snap` (utiliser `lenis/snap`), le smooth s'arrête au-dessus d'une iframe, Safari plafonne à 60 ips (moins en économie d'énergie).

## Une seule boucle, avec GSAP

`gsap.ticker` donne des **secondes**. `lenis.raf` attend des **millisecondes**.

```ts
import Lenis from "lenis";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(ScrollTrigger);

const lenis = new Lenis({ autoRaf: false });
lenis.on("scroll", ScrollTrigger.update);
const onTick = (time: number) => lenis.raf(time * 1000);
gsap.ticker.add(onTick);
gsap.ticker.lagSmoothing(0);
```

Cleanup : `gsap.ticker.remove(onTick)` puis `lenis.destroy()`.

Ne pas ajouter un `requestAnimationFrame` à côté. Ne pas appeler `ScrollTrigger.scrollerProxy` pour un Lenis de document : ce proxy sert aux scrollers qui déplacent un élément interne (ancien Locomotive). Lenis met à jour le vrai `window` scroll, ScrollTrigger le lit directement.

Ne pas monter ScrollSmoother en même temps.

## React

```tsx
import { ReactLenis, useLenis } from "lenis/react";
import "lenis/dist/lenis.css";

const ref = useRef<{ lenis?: { raf: (t: number) => void } }>(null);

useEffect(() => {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const onTick = (time: number) => ref.current?.lenis?.raf(time * 1000);
  gsap.ticker.add(onTick);
  gsap.ticker.lagSmoothing(0);
  return () => gsap.ticker.remove(onTick);
}, []);

return (
  <ReactLenis root options={{ autoRaf: false }} ref={ref}>
    {children}
  </ReactLenis>
);
```

`root` rend l'instance globale : `useLenis()` la renvoie (`scrollTo`, `stop`, `start`, `resize`). Une seule instance racine par document.

`autoRaf: false` est obligatoire quand GSAP conduit la boucle. Sans GSAP, laisser le raf interne de Lenis et ne pas en ajouter un autre.

## Réglage

- `lerp: 0.1` est le défaut fluide. Monter vers `0.15`–`0.2` si la page a l'air en retard. Ne pas régler `lerp` et `duration` en espérant que les deux s'additionnent : `lerp` pour la molette continue, `duration` pour `scrollTo`.
- `lenis.scrollTo("#id", { offset: -80, duration: 1.1 })` pour les ancres sous un header fixe.
- `lenis.stop()` tant qu'une modale est ouverte, `lenis.start()` à la fermeture.
- `syncTouch` reste **off** : sur iOS il se bat avec le scroll natif.
- Après un changement de hauteur : `ScrollTrigger.refresh()` et `lenis.resize()`.

Un conteneur imbriqué (`overflow: auto`) a besoin de son propre `ReactLenis` avec `root={false}` et les options `wrapper` / `content`. L'instance racine ne lisse pas un div toute seule.
