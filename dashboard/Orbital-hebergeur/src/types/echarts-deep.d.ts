/**
 * Les imports profonds d'ECharts (chart/<x>/install.js, component/<x>/install.js,
 * renderer/installCanvasRenderer.js) n'ont pas de déclarations TS : TS7016 sans ça.
 * `import type { EChartsOption } from "echarts"` reste un import de types uniquement
 * (effacé à la compilation) : jamais `import ... from "echarts"` à l'exécution.
 */
declare module "echarts/lib/export/core.js" {
    export const use: (modules: unknown[]) => void;
    export const init: (
        el: HTMLElement | null,
        theme?: string | object | null,
        opts?: { renderer?: "canvas" | "svg"; width?: number; height?: number; devicePixelRatio?: number }
    ) => EChartsInstance;
    export const graphic: {
        LinearGradient: new (
            x: number,
            y: number,
            x2: number,
            y2: number,
            colorStops: Array<{ offset: number; color: string }>
        ) => object;
    };
    export interface EChartsInstance {
        setOption: (option: unknown, opts?: { notMerge?: boolean; replaceMerge?: string[] }) => void;
        resize: () => void;
        dispose: () => void;
        on: (event: string, handler: (params: unknown) => void) => void;
        off: (event: string) => void;
    }
}
declare module "echarts/lib/chart/bar/install.js" {
    export const install: (module: unknown) => void;
}
declare module "echarts/lib/chart/line/install.js" {
    export const install: (module: unknown) => void;
}
declare module "echarts/lib/component/grid/install.js" {
    export const install: (module: unknown) => void;
}
declare module "echarts/lib/component/tooltip/install.js" {
    export const install: (module: unknown) => void;
}
declare module "echarts/lib/component/legend/install.js" {
    export const install: (module: unknown) => void;
}
declare module "echarts/lib/component/aria/install.js" {
    export const install: (module: unknown) => void;
}
declare module "echarts/lib/renderer/installCanvasRenderer.js" {
    export const install: (module: unknown) => void;
}
