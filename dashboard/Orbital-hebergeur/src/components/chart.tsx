"use client";

import { useEffect, useRef } from "react";
import { echarts, type EChartsOption } from "@/lib/echarts";

export function Chart({
  option,
  className,
  height = 220,
  ariaLabel,
}: {
  option: EChartsOption;
  className?: string;
  height?: number;
  ariaLabel?: string;
}) {
  const el = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  const optRef = useRef(option);
  optRef.current = option;

  useEffect(() => {
    if (!el.current) return;
    const c = echarts.init(el.current, undefined, { renderer: "canvas" });
    chart.current = c;
    c.setOption(optRef.current);
    const ro = new ResizeObserver(() => c.resize());
    ro.observe(el.current);
    return () => {
      ro.disconnect();
      c.dispose();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    chart.current?.setOption(option);
  }, [option]);

  return <div ref={el} className={className} style={{ height }} role="img" aria-label={ariaLabel} />;
}
