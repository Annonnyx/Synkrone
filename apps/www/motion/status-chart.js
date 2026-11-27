import * as echarts from "echarts/core";
import { install as BarChart } from "echarts/lib/chart/bar/install.js";
import { install as AriaComponent } from "echarts/lib/component/aria/install.js";
import { install as GridComponent } from "echarts/lib/component/grid/install.js";
import { install as TooltipComponent } from "echarts/lib/component/tooltip/install.js";
import { install as CanvasRenderer } from "echarts/lib/renderer/installCanvasRenderer.js";

echarts.use([BarChart, GridComponent, TooltipComponent, AriaComponent, CanvasRenderer]);

let chart = null;
let lastBars = [];

function reduced() {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function token(name, fallback) {
    const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return value || fallback;
}

function host() {
    return document.getElementById("st-bars");
}

function draw(bars) {
    const el = host();
    if (!el) return;
    lastBars = Array.isArray(bars) ? bars : [];
    if (!chart) {
        chart = echarts.init(el, undefined, { renderer: "canvas" });
        const observer = new ResizeObserver(() => chart && chart.resize());
        observer.observe(el);
    }
    const accent = token("--mousse", "#3f6b52");
    const ink = token("--hall-ink", token("--sk-text", "#1b211e"));
    const mute = token("--hall-mute", token("--sk-text-muted", "#5c6a66"));
    const line = token("--hall-line", token("--sk-border", "#5c6a661f"));
    const labels = lastBars.map((bar) => (bar && bar.date ? String(bar.date).slice(5) : ""));
    const values = lastBars.map((bar) => {
        const pct = Number(bar && bar.pct);
        return Number.isFinite(pct) ? pct : 0;
    });
    const summary = values.length
        ? values.map((pct, index) => `${labels[index] || "jour"} ${pct} %`).join(", ")
        : "Aucune mesure d’uptime sur 7 jours.";
    el.setAttribute("role", "img");
    el.setAttribute("aria-label", `Uptime quotidien. ${summary}`);
    chart.setOption({
        animation: !reduced(),
        animationDuration: 0,
        animationDurationUpdate: reduced() ? 0 : 280,
        backgroundColor: "transparent",
        aria: { enabled: true, label: { description: summary } },
        grid: { left: 40, right: 8, top: 16, bottom: 28 },
        tooltip: { trigger: "axis", valueFormatter: (value) => `${value} %` },
        xAxis: {
            type: "category",
            data: labels,
            axisLabel: { color: mute, fontFamily: "IBM Plex Mono, ui-monospace, monospace", fontSize: 11 },
            axisLine: { lineStyle: { color: line } },
            axisTick: { show: false }
        },
        yAxis: {
            type: "value",
            min: 0,
            max: 100,
            axisLabel: { color: mute, formatter: "{value} %" },
            splitLine: { lineStyle: { color: line } }
        },
        series: [{
            type: "bar",
            data: values,
            barMaxWidth: 28,
            itemStyle: { color: accent }
        }],
        textStyle: { color: ink, fontFamily: "IBM Plex Sans, sans-serif" }
    }, true);
}

window.synkroneStatusChart = draw;
window.addEventListener("synkrone-theme", () => draw(lastBars));
if (Array.isArray(window.__pendingStatusBars)) draw(window.__pendingStatusBars);
