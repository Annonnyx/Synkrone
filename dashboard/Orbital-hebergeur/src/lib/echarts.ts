/**
 * Point d'entrée ECharts unique du panel.
 *
 * `import { BarChart } from "echarts/charts"` ne tree-shake pas sous esbuild/webpack
 * (le paquet déclare `sideEffects: ["lib/chart/*.js", ...]`) : imports profonds
 * obligatoires. Jamais `import ... from "echarts"` à l'exécution.
 *
 * ECharts ne parse ni `oklch()` ni les alias : la palette est dupliquée en hex,
 * alignée sur les tokens pierre/basalte/mousse/ambre/brique de globals.css.
 */
import * as echarts from "echarts/lib/export/core.js";
import { install as BarChart } from "echarts/lib/chart/bar/install.js";
import { install as LineChart } from "echarts/lib/chart/line/install.js";
import { install as GridComponent } from "echarts/lib/component/grid/install.js";
import { install as TooltipComponent } from "echarts/lib/component/tooltip/install.js";
import { install as LegendComponent } from "echarts/lib/component/legend/install.js";
import { install as AriaComponent } from "echarts/lib/component/aria/install.js";
import { install as CanvasRenderer } from "echarts/lib/renderer/installCanvasRenderer.js";
import type { EChartsOption } from "echarts";

echarts.use([BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent, AriaComponent, CanvasRenderer]);

export type { EChartsOption };

/** Tokens hex — un seul chemin d'écriture : globals.css reste la source. */
export const palette = {
    accent: "#3f6b52",
    accentDark: "#6b9d7e",
    amber: "#b8823d",
    brick: "#a8462f",
    slate: "#5c6a66",
    ink: "#1b211e",
    stone: "#eef0ea"
} as const;

export function prefersReducedMotion(): boolean {
    if (typeof window === "undefined" || !window.matchMedia) return false;
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export { echarts };
