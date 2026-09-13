import type { PlatformSettings, TypeLimits } from "@/lib/platform-settings";
import type { ServiceKind } from "@/lib/services/limits-types";
import { defaultCpuMillicores, TYPE_CPU_HARD_CAP } from "@/lib/services/resource-presets";

export function limitsFor(settings: PlatformSettings, type: ServiceKind): TypeLimits {
  return settings.limits[type] || settings.limits.web;
}

function finiteOr(value: number | undefined, fallback: number) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

export function clampResources(
  settings: PlatformSettings,
  type: ServiceKind,
  input: { cpuMillicores?: number; memoryMb?: number; storageMb?: number },
) {
  const cap = limitsFor(settings, type);
  const cpuCap = Math.min(cap.cpuMillicores, TYPE_CPU_HARD_CAP[type]);
  return {
    cpuMillicores: Math.min(Math.max(finiteOr(input.cpuMillicores, defaultCpuMillicores(type)), 100), cpuCap),
    memoryMb: Math.min(Math.max(finiteOr(input.memoryMb, 512), 64), cap.memoryMb),
    storageMb: Math.min(Math.max(finiteOr(input.storageMb, 5120), 512), cap.storageMb),
  };
}
