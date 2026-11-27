import * as echarts from "echarts/core";
import { install as BarChart } from "echarts/lib/chart/bar/install.js";
import { install as LineChart } from "echarts/lib/chart/line/install.js";
import { install as GridComponent } from "echarts/lib/component/grid/install.js";
import { install as TooltipComponent } from "echarts/lib/component/tooltip/install.js";
import { install as AriaComponent } from "echarts/lib/component/aria/install.js";
import { install as CanvasRenderer } from "echarts/lib/renderer/installCanvasRenderer.js";

echarts.use([BarChart, LineChart, GridComponent, TooltipComponent, AriaComponent, CanvasRenderer]);

let chart = null;
let ro = null;

function isDark() {
  return document.documentElement.dataset.theme === "dark";
}

function palette() {
  return isDark()
    ? { bar: "#6b9d7e", text: "#eef0ea", muted: "#8fa096", line: "#333e38", bg: "transparent" }
    : { bar: "#3f6b52", text: "#1b211e", muted: "#5c6a66", line: "#5c6a661f", bg: "transparent" };
}

function render(bars) {
  const el = document.getElementById("st-bars");
  if (!el) return;
  const data = Array.isArray(bars) ? bars : [];
  const rows = data.length ? data : Array.from({ length: 7 }, () => ({ pct: 0, date: "" }));
  const labels = rows.map((b) => (b.date ? String(b.date).slice(5) : ""));
  const values = rows.map((b) => Number(b.pct) || 0);
  const c = palette();
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  if (chart) {
    try { chart.dispose(); } catch {}
    chart = null;
  }
  if (ro) {
    try { ro.disconnect(); } catch {}
    ro = null;
  }

  el.style.height = "120px";
  el.style.minHeight = "120px";
  chart = echarts.init(el, null, { renderer: "canvas" });
  chart.setOption({
    backgroundColor: c.bg,
    animation: !reduce,
    animationDuration: 600,
    animationEasing: "cubicOut",
    grid: { left: 8, right: 8, top: 16, bottom: 8, containLabel: true },
    tooltip: {
      trigger: "axis",
      backgroundColor: isDark() ? "#232b27" : "#ffffff",
      borderColor: c.line,
      textStyle: { color: c.text, fontFamily: '"IBM Plex Sans", system-ui, sans-serif', fontSize: 12 },
      axisPointer: { type: "shadow" },
      formatter: (params) => {
        const p = Array.isArray(params) ? params[0] : params;
        return `${p.name} — ${String(p.value).replace(".", ",")} %`;
      },
    },
    xAxis: {
      type: "category",
      data: labels,
      axisLine: { lineStyle: { color: c.line } },
      axisTick: { show: false },
      axisLabel: { color: c.muted, fontFamily: '"IBM Plex Mono", monospace', fontSize: 10 },
    },
    yAxis: {
      type: "value",
      min: 0,
      max: 100,
      splitLine: { lineStyle: { color: c.line } },
      axisLabel: { color: c.muted, fontFamily: '"IBM Plex Mono", monospace', fontSize: 10, formatter: "{value} %" },
    },
    series: [
      {
        type: "bar",
        data: values,
        barMaxWidth: 28,
        itemStyle: { color: c.bar, borderRadius: [2, 2, 0, 0] },
        emphasis: { itemStyle: { color: isDark() ? "#9ecfb0" : "#2e5039" } },
      },
    ],
    aria: { enabled: true, label: { description: "Uptime quotidien sur 7 jours, en pourcent." } },
    textStyle: { fontFamily: '"IBM Plex Sans", system-ui, sans-serif', color: c.text },
  });
  ro = new ResizeObserver(() => chart && chart.resize());
  ro.observe(el);
}

function destroy() {
  if (ro) {
    try { ro.disconnect(); } catch {}
    ro = null;
  }
  if (chart) {
    try { chart.dispose(); } catch {}
    chart = null;
  }
}

window.synkroneStatusChart = { render, destroy };
