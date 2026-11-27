/**
 * Entrée du bundle vitrine `public/assets/status-chart.js` : Apache ECharts
 * tree-shaké. `import { BarChart } from "echarts/charts"` ne tree-shake pas sous
 * esbuild (`sideEffects` inclut `lib/chart/*.js`) : imports profonds obligatoires.
 * Ces chemins n'ont pas de déclarations TS → un `declare module` local dans le
 * panel règle TS7016. Jamais `import from "echarts"`.
 */
import * as echarts from 'echarts/lib/export/core.js';
import { install as BarChart } from 'echarts/lib/chart/bar/install.js';
import { install as LineChart } from 'echarts/lib/chart/line/install.js';
import { install as GridComponent } from 'echarts/lib/component/grid/install.js';
import { install as TooltipComponent } from 'echarts/lib/component/tooltip/install.js';
import { install as LegendComponent } from 'echarts/lib/component/legend/install.js';
import { install as AriaComponent } from 'echarts/lib/component/aria/install.js';
import { install as CanvasRenderer } from 'echarts/lib/renderer/installCanvasRenderer.js';

echarts.use([BarChart, LineChart, GridComponent, TooltipComponent, LegendComponent, AriaComponent, CanvasRenderer]);

window.SynkroneChart = echarts;
