import fs from "node:fs/promises";
import path from "node:path";
import { TYPE_CPU_HARD_CAP } from "@/lib/services/resource-presets";

export type TypeLimits = {
  cpuMillicores: number;
  memoryMb: number;
  storageMb: number;
};

export type DiscountTarget = "all" | "discord" | "minecraft" | "web" | "ram" | "cpu" | "storage";

export type PromoDiscount = {
  id: string;
  label: string;
  targets: DiscountTarget[];
  percent: number;
  startsAt: number;
  endsAt: number;
  enabled?: boolean;
};

export type PlatformSettings = {
  discordEnabled: boolean;
  minecraftEnabled: boolean;
  webEnabled: boolean;
  maxCpuMillicores: number;
  maxMemoryMb: number;
  maxStorageMb: number;
  limits: {
    discord: TypeLimits;
    minecraft: TypeLimits;
    web: TypeLimits;
  };
  discounts: PromoDiscount[];
};

const DEFAULTS: PlatformSettings = {
  discordEnabled: true,
  minecraftEnabled: true,
  webEnabled: true,
  maxCpuMillicores: 4000,
  maxMemoryMb: 8192,
  maxStorageMb: 51200,
  limits: {
    discord: { cpuMillicores: 1000, memoryMb: 2048, storageMb: 10240 },
    minecraft: { cpuMillicores: 4000, memoryMb: 8192, storageMb: 51200 },
    web: { cpuMillicores: 1000, memoryMb: 4096, storageMb: 20480 },
  },
  discounts: [],
};

function repoRoot() {
  return process.env.SYNKRONE_REPO_ROOT?.trim()
    || path.resolve(process.cwd(), "..", "..");
}

function dataPath() {
  return path.join(repoRoot(), "apps", "www", "data", "platform.json");
}

function asInt(value: unknown, fallback: number, min: number, max: number) {
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(max, Math.max(min, Math.trunc(n)));
}

export function normalizePlatform(raw: unknown): PlatformSettings {
  const src = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  const limitsIn = src.limits && typeof src.limits === "object" ? (src.limits as Record<string, Record<string, unknown>>) : {};
  const out: PlatformSettings = {
    discordEnabled: src.discordEnabled !== false,
    minecraftEnabled: src.minecraftEnabled !== false,
    webEnabled: src.webEnabled !== false,
    maxCpuMillicores: asInt(src.maxCpuMillicores, DEFAULTS.maxCpuMillicores, 100, 16000),
    maxMemoryMb: asInt(src.maxMemoryMb, DEFAULTS.maxMemoryMb, 64, 65536),
    maxStorageMb: asInt(src.maxStorageMb, DEFAULTS.maxStorageMb, 512, 204800),
    limits: { ...DEFAULTS.limits },
    discounts: [],
  };
  for (const type of ["discord", "minecraft", "web"] as const) {
    const row = limitsIn[type] || {};
    const fallback = DEFAULTS.limits[type];
    out.limits[type] = {
      cpuMillicores: asInt(
        row.cpuMillicores,
        fallback.cpuMillicores,
        100,
        Math.min(out.maxCpuMillicores, TYPE_CPU_HARD_CAP[type]),
      ),
      memoryMb: asInt(row.memoryMb, fallback.memoryMb, 64, out.maxMemoryMb),
      storageMb: asInt(row.storageMb, fallback.storageMb, 512, out.maxStorageMb),
    };
  }
  if (process.env.SYNKRONE_DISABLE_DISCORD === "1") out.discordEnabled = false;
  if (process.env.SYNKRONE_DISABLE_MINECRAFT === "1") out.minecraftEnabled = false;
  if (process.env.SYNKRONE_DISABLE_WEB === "1") out.webEnabled = false;
  const allowed = new Set(["all", "discord", "minecraft", "web", "ram", "cpu", "storage"]);
  const discountsIn = Array.isArray(src.discounts) ? src.discounts : [];
  const discounts: PromoDiscount[] = [];
  discountsIn.forEach((row, index) => {
    if (!row || typeof row !== "object") return;
    const item = row as Record<string, unknown>;
    const targets = (Array.isArray(item.targets) ? item.targets : [])
      .map((target) => String(target || "").toLowerCase())
      .filter((target): target is DiscountTarget => allowed.has(target));
    const endsAt = Number(item.endsAt);
    const startsAt = Number.isFinite(Number(item.startsAt)) ? Math.trunc(Number(item.startsAt)) : Date.now();
    if (!targets.length || !Number.isFinite(endsAt) || endsAt <= startsAt) return;
    discounts.push({
      id: String(item.id || `promo-${index}`),
      label: String(item.label || "Promo").slice(0, 80),
      targets,
      percent: asInt(item.percent, 0, 0, 100),
      startsAt,
      endsAt: Math.trunc(endsAt),
      enabled: item.enabled !== false,
    });
  });
  out.discounts = discounts;
  return out;
}

export async function readPlatformSettings(): Promise<PlatformSettings> {
  try {
    const raw = JSON.parse(await fs.readFile(dataPath(), "utf8"));
    return normalizePlatform(raw);
  } catch {
    return normalizePlatform(DEFAULTS);
  }
}
