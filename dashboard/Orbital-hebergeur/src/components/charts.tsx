"use client";

/**
 * Graphes du panel : ECharts tree-shaké (voir src/lib/echarts.ts).
 * Un seul composant de cycle de vie (init / ResizeObserver / dispose), puis un
 * effet séparé par données. `animation: false` si prefers-reduced-motion.
 * Conteneur toujours à hauteur explicite, `aria.enabled` + résumé texte à côté.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { echarts, prefersReducedMotion, type EChartsOption } from "@/lib/echarts";

export function EChart({
    option,
    height = 220,
    ariaLabel,
    className,
}: {
    option: EChartsOption;
    height?: number;
    ariaLabel: string;
    className?: string;
}) {
    const host = useRef<HTMLDivElement | null>(null);
    const chart = useRef<echarts.EChartsInstance | null>(null);

    useEffect(() => {
        const el = host.current;
        if (!el) return;
        const instance = echarts.init(el, undefined, { renderer: "canvas" });
        chart.current = instance;
        const observer = new ResizeObserver(() => instance.resize());
        observer.observe(el);
        return () => {
            observer.disconnect();
            instance.dispose();
            chart.current = null;
        };
    }, []);

    useEffect(() => {
        chart.current?.setOption(option);
    }, [option]);

    return (
        <div
            ref={host}
            className={className}
            style={{ height, width: "100%" }}
            role="img"
            aria-label={ariaLabel}
        />
    );
}

const darkAxes = {
    axisLine: { lineStyle: { color: "rgba(143,160,150,.34)" } },
    axisLabel: { color: "#8fa096" },
    splitLine: { lineStyle: { color: "rgba(143,160,150,.16)" } }
};

const lightAxes = {
    axisLine: { lineStyle: { color: "rgba(92,106,102,.34)" } },
    axisLabel: { color: "#5c6a66" },
    splitLine: { lineStyle: { color: "rgba(92,106,102,.16)" } }
};

/** data-theme et class="dark" viennent du même cookie : on suit l'attribut. */
function useIsDark(): boolean {
    const [dark, setDark] = useState(
        () => typeof document !== "undefined" && document.documentElement.getAttribute("data-theme") === "dark"
    );
    useEffect(() => {
        const root = document.documentElement;
        const observer = new MutationObserver(() => {
            setDark(root.getAttribute("data-theme") === "dark");
        });
        observer.observe(root, { attributes: true, attributeFilter: ["data-theme", "class"] });
        return () => observer.disconnect();
    }, []);
    return dark;
}

/** Trois quotas réels du panel (CPU, RAM, disque) en barres horizontales, 0–100 %. */
export function QuotaBarsChart({
    quotas,
    labels,
}: {
    quotas: Array<{ name: string; percent: number; detail: string }>;
    labels: { title: string; description: string };
}) {
    const isDark = useIsDark();
    const axes = isDark ? darkAxes : lightAxes;
    const accent = isDark ? "#6b9d7e" : "#3f6b52";
    const muted = isDark ? "#8fa096" : "#5c6a66";

    const option = useMemo<EChartsOption>(() => {
        const rows = [...quotas].sort((a, b) => a.percent - b.percent);
        return {
            backgroundColor: "transparent",
            animation: !prefersReducedMotion(),
            animationDuration: 600,
            aria: { enabled: true, label: { description: labels.description } },
            grid: { left: 8, right: 24, top: 8, bottom: 8, containLabel: true },
            tooltip: {
                trigger: "item",
                backgroundColor: isDark ? "rgba(27,33,30,.94)" : "rgba(255,255,255,.96)",
                borderColor: isDark ? "rgba(255,255,255,.12)" : "rgba(92,106,102,.24)",
                textStyle: { color: isDark ? "#eef0ea" : "#1b211e" }
            },
            xAxis: { type: "value", min: 0, max: 100, ...axes, axisLabel: { ...axes.axisLabel, formatter: "{value}%" } },
            yAxis: {
                type: "category",
                data: rows.map((row) => row.name),
                axisLabel: { color: muted, fontSize: 12, fontFamily: "IBM Plex Mono, monospace" },
                axisLine: { lineStyle: { color: isDark ? "rgba(143,160,150,.34)" : "rgba(92,106,102,.34)" } },
                axisTick: { show: false }
            },
            series: [
                {
                    name: labels.title,
                    type: "bar",
                    data: rows.map((row) => ({
                        value: Math.max(0, Math.min(100, Math.round(row.percent * 100) / 100)),
                        detail: row.detail
                    })),
                    barMaxWidth: 18,
                    itemStyle: { color: accent, borderRadius: [0, 3, 3, 0] },
                    tooltip: {
                        valueFormatter: () => ""
                    }
                }
            ]
        };
    }, [quotas, labels, axes, accent, muted, isDark]);

    return <EChart option={option} height={200} ariaLabel={labels.description} />;
}

/** Journal Krônes : ligne de `ledger[].balanceAfter` contre `ledger[].at`. */
export function LedgerLineChart({
    rows,
    labels,
}: {
    rows: Array<{ at: number; balanceAfter: number }>;
    labels: { description: string; seriesName: string };
}) {
    const isDark = useIsDark();
    const axes = isDark ? darkAxes : lightAxes;
    const accent = isDark ? "#6b9d7e" : "#3f6b52";
    const amber = "#b8823d";

    const option = useMemo<EChartsOption>(() => {
        const data = rows.map((row) => [row.at, row.balanceAfter]);
        return {
            backgroundColor: "transparent",
            animation: !prefersReducedMotion(),
            animationDuration: 600,
            aria: { enabled: true, label: { description: labels.description } },
            grid: { left: 8, right: 16, top: 24, bottom: 8, containLabel: true },
            tooltip: {
                trigger: "axis",
                backgroundColor: isDark ? "rgba(27,33,30,.94)" : "rgba(255,255,255,.96)",
                borderColor: isDark ? "rgba(255,255,255,.12)" : "rgba(92,106,102,.24)",
                textStyle: { color: isDark ? "#eef0ea" : "#1b211e" }
            },
            xAxis: {
                type: "time",
                ...axes,
                axisLabel: { ...axes.axisLabel, hideOverlap: true, formatter: (value: number) =>
                    new Date(value).toLocaleDateString(undefined, { day: "2-digit", month: "2-digit" }) }
            },
            yAxis: { type: "value", ...axes, axisLabel: { ...axes.axisLabel, formatter: (value: number) => String(value) } },
            series: [
                {
                    name: labels.seriesName,
                    type: "line",
                    data,
                    showSymbol: data.length < 40,
                    smooth: false,
                    lineStyle: { color: accent, width: 2 },
                    itemStyle: { color: amber },
                    areaStyle: {
                        color: {
                            type: "linear",
                            x: 0,
                            y: 0,
                            x2: 0,
                            y2: 1,
                            colorStops: [
                                { offset: 0, color: isDark ? "rgba(107,157,126,.28)" : "rgba(63,107,82,.22)" },
                                { offset: 1, color: "rgba(63,107,82,0)" }
                            ]
                        }
                    }
                }
            ]
        };
    }, [rows, labels, axes, accent, amber, isDark]);

    return <EChart option={option} height={220} ariaLabel={labels.description} />;
}
