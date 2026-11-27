"use client";

import { useEffect, useMemo, useRef } from "react";
import { echarts, type EChartsOption } from "@/lib/echarts";
import { useTheme } from "@/lib/theme";

function token(name: string, fallback: string) {
  if (typeof document === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function reduced() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

export function EChart({
  option,
  height = 220,
  label,
}: {
  option: EChartsOption;
  height?: number;
  label: string;
}) {
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<ReturnType<typeof echarts.init> | null>(null);

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
    const calm = reduced();
    chart.current?.setOption(
      {
        ...option,
        animation: !calm,
        animationDuration: 0,
        animationDurationUpdate: calm ? 0 : 280,
      },
      true,
    );
  }, [option]);

  return <div ref={host} role="img" aria-label={label} style={{ height, width: "100%" }} />;
}

function palette() {
  return {
    accent: token("--sk-accent", "#3f6b52"),
    danger: token("--sk-danger", "#a8462f"),
    gold: token("--sk-gold", "#b8823d"),
    ink: token("--sk-text", "#1b211e"),
    mute: token("--sk-text-muted", "#5c6a66"),
    line: token("--sk-border", "#5c6a661f"),
  };
}

function axis(colors: ReturnType<typeof palette>) {
  return {
    axisLabel: { color: colors.mute, fontFamily: "IBM Plex Sans, sans-serif", fontSize: 11 },
    axisLine: { lineStyle: { color: colors.line } },
    axisTick: { show: false },
    splitLine: { lineStyle: { color: colors.line } },
  };
}

export function QuotaChart({
  cpu,
  memory,
  disk,
  labels,
}: {
  cpu: number;
  memory: number;
  disk: number;
  labels: { cpu: string; memory: string; disk: string };
}) {
  const { theme } = useTheme();
  const cpuLabel = labels.cpu;
  const memoryLabel = labels.memory;
  const diskLabel = labels.disk;
  const label = `${cpuLabel} ${cpu.toFixed(1)} %. ${memoryLabel} ${memory.toFixed(1)} %. ${diskLabel} ${disk.toFixed(1)} %.`;
  const option = useMemo<EChartsOption>(() => {
    const colors = palette();
    const shared = axis(colors);
    const values = [cpu, memory, disk];
    return {
      backgroundColor: "transparent",
      aria: { enabled: true, label: { description: label } },
      grid: { left: 12, right: 12, top: 16, bottom: 8, containLabel: true },
      tooltip: { trigger: "axis", valueFormatter: (value) => `${value} %` },
      xAxis: { type: "value", max: 100, ...shared },
      yAxis: {
        type: "category",
        data: [cpuLabel, memoryLabel, diskLabel],
        ...shared,
      },
      series: [
        {
          type: "bar",
          data: values.map((value) => ({
            value: Math.round(value * 10) / 10,
            itemStyle: { color: value > 85 ? colors.danger : colors.accent },
          })),
          barMaxWidth: 18,
        },
      ],
      textStyle: { color: colors.ink },
    };
  }, [cpu, memory, disk, cpuLabel, memoryLabel, diskLabel, label, theme]);

  return (
    <div className="panel mt-4 p-3">
      <EChart option={option} height={180} label={label} />
    </div>
  );
}

export function LedgerChart({
  rows,
  label,
  locale,
}: {
  rows: Array<{ at: number; balanceAfter: number }>;
  label: string;
  locale: string;
}) {
  const { theme } = useTheme();
  const points = useMemo(
    () => [...rows].sort((a, b) => a.at - b.at),
    [rows],
  );
  const option = useMemo<EChartsOption>(() => {
    const colors = palette();
    const shared = axis(colors);
    const loc = locale === "en" ? "en-GB" : "fr-FR";
    return {
      backgroundColor: "transparent",
      aria: { enabled: true, label: { description: label } },
      grid: { left: 12, right: 12, top: 16, bottom: 8, containLabel: true },
      tooltip: {
        trigger: "axis",
        valueFormatter: (value) => `${Number(value).toLocaleString(loc)} ₭`,
      },
      xAxis: {
        type: "category",
        data: points.map((row) => new Date(row.at).toLocaleString(loc)),
        ...shared,
      },
      yAxis: { type: "value", ...shared },
      series: [
        {
          type: "line",
          data: points.map((row) => row.balanceAfter),
          showSymbol: points.length < 24,
          lineStyle: { color: colors.gold, width: 2 },
          itemStyle: { color: colors.gold },
        },
      ],
      textStyle: { color: colors.ink },
    };
  }, [points, label, locale, theme]);

  return (
    <div className="panel mb-6 p-3">
      <EChart option={option} height={220} label={label} />
    </div>
  );
}
