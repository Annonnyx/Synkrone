# Apache ECharts (v5/v6) — guide d'usage correct

Docs : https://echarts.apache.org/en/index.html · option : https://echarts.apache.org/en/option.html · exemples : https://echarts.apache.org/examples
Install : `npm i echarts` (pas de wrapper requis ; `echarts-for-react` seulement si le projet l'utilise déjà).

## Quand l'utiliser

**Toujours** pour de la donnée : tendances (`line`), comparaisons (`bar`), parts (`pie`/`sunburst`/`treemap`), corrélations (`scatter`),
profil multi-critères (`radar`), progression (`gauge`), calendrier/densité (`heatmap` + `calendar`), flux (`sankey`), hiérarchie (`tree`),
finance (`candlestick`), géo (`map`/`geo`), graphes (`graph`), séries temporelles volumineuses (`large`, `dataZoom`).
**Pas** pour : décoration pure, animation scénarisée (→ anime.js), simple barre de progression (→ composant).

## Règle bundle : TREE-SHAKING OBLIGATOIRE

```ts
// src/lib/echarts.ts — point d'entrée unique, importé partout
import * as echarts from "echarts/core";
import { LineChart, BarChart, PieChart, RadarChart, GaugeChart, HeatmapChart, ScatterChart, SankeyChart } from "echarts/charts";
import { GridComponent, TooltipComponent, LegendComponent, TitleComponent, DatasetComponent,
         DataZoomComponent, VisualMapComponent, RadarComponent, CalendarComponent, MarkLineComponent,
         MarkPointComponent, AriaComponent, GraphicComponent, ToolboxComponent } from "echarts/components";
import { LabelLayout, UniversalTransition } from "echarts/features";
import { CanvasRenderer } from "echarts/renderers";           // ou SVGRenderer (net, imprimable, peu de points)

echarts.use([LineChart, BarChart, PieChart, RadarChart, GaugeChart, HeatmapChart, ScatterChart, SankeyChart,
  GridComponent, TooltipComponent, LegendComponent, TitleComponent, DatasetComponent, DataZoomComponent,
  VisualMapComponent, RadarComponent, CalendarComponent, MarkLineComponent, MarkPointComponent,
  AriaComponent, GraphicComponent, ToolboxComponent, LabelLayout, UniversalTransition, CanvasRenderer]);

export { echarts };
export type { EChartsOption } from "echarts";
```
Ne **garde que** ce que la page utilise (chaque chart + composant = +Ko). Erreurs typiques :
- `Component series.xxx not exists. Load it first` → il manque le `XxxChart` dans `use()`.
- `Component grid/tooltip/legend … not exists` → composant manquant.
- `Renderer 'undefined' is not imported` → oublié `CanvasRenderer`/`SVGRenderer`.
- Dans l'onglet **Full Code** de l'éditeur d'exemples ECharts, le code tree-shaké exact est généré.

## Canvas vs SVG

- `CanvasRenderer` : défaut, performant (>1 000 points, heatmaps, animations).
- `SVGRenderer` : texte net en zoom, export/print, DOM inspectable, peu d'éléments, mobile à fort DPR.
- On peut enregistrer les deux et choisir à l'init : `echarts.init(el, null, { renderer: "svg" })`.

## Hook React (pattern de référence)

```tsx
import { useEffect, useRef } from "react";
import { echarts } from "@/lib/echarts";
import type { EChartsOption } from "echarts";

export function Chart({ option, className, height = 280, ariaLabel }:
  { option: EChartsOption; className?: string; height?: number; ariaLabel?: string }) {
  const el = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);

  // 1) cycle de vie : init + resize + dispose
  useEffect(() => {
    if (!el.current) return;
    const c = echarts.init(el.current, undefined, { renderer: "canvas" });
    chart.current = c;
    const ro = new ResizeObserver(() => c.resize());
    ro.observe(el.current);
    return () => { ro.disconnect(); c.dispose(); chart.current = null; };
  }, []);

  // 2) données : setOption à chaque changement (merge par défaut = transitions fluides)
  useEffect(() => { chart.current?.setOption(option); }, [option]);

  return <div ref={el} className={className} style={{ height }} role="img" aria-label={ariaLabel} />;
}
```
- Le conteneur **doit avoir une hauteur** (sinon chart invisible : `height` explicite ou parent flex avec `min-h`).
- Mémoïse `option` (`useMemo`) si elle dépend de props, sinon `setOption` à chaque render.
- `setOption(opt)` fusionne ; `setOption(opt, { notMerge: true })` remplace (changement de type de chart) ; `replaceMerge: ['series']` pour retirer des séries.
- Événements : `chart.on("click", params => …)` → pense à `chart.off` au cleanup si dépendances changeantes.
- Plusieurs charts liés (tooltip/zoom synchronisés) : `echarts.connect([c1, c2])` ou `group`.

## Thème dark cohérent avec le design system

```ts
export const palette = ["#8b5cf6", "#22d3ee", "#34d399", "#f472b6", "#fbbf24", "#60a5fa"];
export const base: EChartsOption = {
  backgroundColor: "transparent",
  color: palette,
  textStyle: { fontFamily: "Inter, system-ui, sans-serif", color: "#a1a1aa" },
  animationDuration: 900, animationEasing: "cubicOut", animationDurationUpdate: 500,
  tooltip: { trigger: "axis", backgroundColor: "rgba(24,24,27,.95)", borderColor: "rgba(255,255,255,.1)",
             textStyle: { color: "#fafafa" }, extraCssText: "backdrop-filter: blur(8px); border-radius: 10px;" },
  grid: { left: 8, right: 8, top: 32, bottom: 8, containLabel: true },   // ← containLabel évite les labels coupés
  aria: { enabled: true },
};
// axes sombres : axisLine/splitLine { lineStyle: { color: "rgba(255,255,255,.08)" } }, axisLabel { color: "#a1a1aa" }
```
Ou `echarts.registerTheme("app-dark", {...})` puis `echarts.init(el, "app-dark")`.
Dégradés : `new echarts.graphic.LinearGradient(0,0,0,1,[{offset:0,color:"rgba(139,92,246,.45)"},{offset:1,color:"rgba(139,92,246,0)"}])` (nécessite que `echarts/core` soit importé, pas seulement les charts).

## Choisir le bon type de chart

| Question | Chart | Notes |
|---|---|---|
| Évolution dans le temps | `line` (`smooth`, `areaStyle`, `showSymbol:false`) | `xAxis.type:'time'` si timestamps ; `dataZoom` si > 200 points |
| Comparer des catégories | `bar` (horizontal si labels longs) | trier ; `barMaxWidth` ; `stack` pour parts cumulées |
| Parts d'un tout (≤ 6) | `pie` en donut (`radius:['55%','75%']`) | > 6 parts ⇒ `bar` trié |
| Profil multi-critères | `radar` (`radar.indicator`) | ≤ 3 séries, valeurs normalisées |
| Une valeur vs objectif | `gauge` | `progress.show`, `pointer` off pour un look moderne |
| Densité 2D / jour×heure | `heatmap` + `visualMap` | `calendar` pour heatmap annuelle |
| Flux/parcours | `sankey` | `nodeAlign`, `emphasis.focus:'adjacency'` |
| Corrélation | `scatter` (`symbolSize` fn) | `large:true` > 5k points |
| Hiérarchie | `treemap`/`sunburst` | |
| Dataset partagé | `dataset` + `encode` | préférable pour tableaux → plusieurs séries |

Éviter : 3D (nécessite echarts-gl, hors périmètre), camembert multi-séries, double axe Y sans nécessité, > 8 couleurs.

## Fonctionnalités utiles

- **Animation de mise à jour** : `animationDurationUpdate`, `universalTransition: true` + `UniversalTransition` pour transformer bar ↔ pie.
- **Interactions** : `emphasis: { focus: 'series' }`, `legend.selectedMode`, `dataZoom: [{type:'inside'},{type:'slider'}]`, `toolbox.feature.saveAsImage`.
- **Séries temps réel** : conserver un tableau, `push`/`shift`, `setOption({ series: [{ data }] })` à intervalle ≥ 200 ms (jamais à chaque frame).
- **Formatters** : `valueFormatter: v => v.toLocaleString("fr-FR")`, `axisLabel.formatter: "{value} k€"`.
- **Responsive** : `media` dans l'option, ou recalcul via `ResizeObserver` (`legend.orient`, `grid.top`).
- **Accessibilité** : `aria: { enabled: true, label: { description: "…" } }` + résumé textuel visible à côté.
- **Reduced motion** : `animation: !matchMedia("(prefers-reduced-motion: reduce)").matches`.
- **Lazy-load** : charger le module chart via `React.lazy`/import dynamique si sous la ligne de flottaison.

## Pièges

1. Charts dans un onglet/accordéon masqué → taille 0 : appeler `chart.resize()` à l'affichage (le `ResizeObserver` le fait).
2. Clés d'`option` fausses en TS : utiliser `EChartsOption` ; en dev, ouvrir la console (ECharts logge les erreurs d'option).
3. Réutiliser le même `<div>` après `dispose()` sans `init` ⇒ « Can't get DOM width or height ».
4. `grid` sans `containLabel` ⇒ labels d'axe rognés ; `top` trop petit ⇒ légende qui chevauche.
5. Couleurs en `oklch()` ne sont pas parsées par ECharts → utiliser hex/rgb/hsl.
6. Ne mets pas ECharts dans un composant qui se re-monte à chaque rendu (clé instable).
