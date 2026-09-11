import { HttpError } from "@/lib/auth";
import { readPlatformSettings, type PlatformSettings, type TypeLimits } from "@/lib/platform-settings";

export type ServiceKind = "discord" | "minecraft" | "web";

export function limitsFor(settings: PlatformSettings, type: ServiceKind): TypeLimits {
  return settings.limits[type] || settings.limits.web;
}

export async function assertCreationAllowed(type: string) {
  const settings = await readPlatformSettings();
  if (type === "minecraft" && !settings.minecraftEnabled) {
    throw new HttpError(403, "La création de serveurs Minecraft est désactivée.");
  }
  return settings;
}

export function clampResources(
  settings: PlatformSettings,
  type: ServiceKind,
  input: { cpuMillicores?: number; memoryMb?: number; storageMb?: number },
) {
  const cap = limitsFor(settings, type);
  return {
    cpuMillicores: Math.min(Math.max(input.cpuMillicores || 1000, 100), cap.cpuMillicores),
    memoryMb: Math.min(Math.max(input.memoryMb || 512, 64), cap.memoryMb),
    storageMb: Math.min(Math.max(input.storageMb || 5120, 512), cap.storageMb),
  };
}
