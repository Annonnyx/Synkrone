import type { ServiceKind } from "@/lib/services/limits-types";

export type { ServiceKind } from "@/lib/services/limits-types";

/** Product ceiling per family — Discord/Web never go above 1 vCPU. */
export const TYPE_CPU_HARD_CAP: Record<ServiceKind, number> = {
  discord: 1000,
  web: 1000,
  minecraft: 4000,
};

export const CPU_PRESETS: Record<ServiceKind, number[]> = {
  discord: [250, 500, 1000],
  web: [250, 500, 1000],
  minecraft: [500, 1000, 2000, 4000],
};

export function defaultCpuMillicores(type: ServiceKind): number {
  if (type === "discord") return 500;
  if (type === "web") return 1000;
  return 2000;
}

export function cpuPresetsFor(type: ServiceKind, capMillicores?: number): number[] {
  const cap = capMillicores ?? TYPE_CPU_HARD_CAP[type];
  return CPU_PRESETS[type].filter((c) => c <= cap);
}

/** Short label for millicores (250 → "0.25", 1000 → "1"). */
export function formatCpuCores(millicores: number): string {
  const cores = millicores / 1000;
  if (!Number.isFinite(cores)) return "0";
  if (Number.isInteger(cores)) return String(cores);
  return String(Math.round(cores * 100) / 100);
}

export function cpuPluralSuffix(millicores: number): string {
  return millicores / 1000 > 1 ? "s" : "";
}
