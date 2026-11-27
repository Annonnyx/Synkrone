import * as echarts from "echarts/core";
import { install as BarChart } from "echarts/lib/chart/bar/install.js";
import { install as LineChart } from "echarts/lib/chart/line/install.js";
import { install as AriaComponent } from "echarts/lib/component/aria/install.js";
import { install as GridComponent } from "echarts/lib/component/grid/install.js";
import { install as TooltipComponent } from "echarts/lib/component/tooltip/install.js";
import { install as CanvasRenderer } from "echarts/lib/renderer/installCanvasRenderer.js";

echarts.use([
  BarChart,
  LineChart,
  GridComponent,
  TooltipComponent,
  AriaComponent,
  CanvasRenderer,
]);

export { echarts };
export type { EChartsOption } from "echarts";
