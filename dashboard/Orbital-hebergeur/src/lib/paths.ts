import { existsSync, mkdirSync, accessSync, constants } from "node:fs";
import path from "node:path";

/**
 * Volume root. Production uses /data (bind-mounted into the control API).
 * When /data is not writable (local dev / CI sandbox) we fall back to
 * <cwd>/.data so the filesystem manager keeps working on real files.
 */
function resolveRoot(): string {
  // Always absolute: the filesystem manager compares resolved paths against the
  // root to reject escapes, which a relative root would make impossible.
  const configured = path.resolve(process.env.PLATFORM_DATA_DIR ?? "/data");
  try {
    if (!existsSync(configured)) mkdirSync(configured, { recursive: true });
    accessSync(configured, constants.W_OK);
    return configured;
  } catch {
    const fallback = path.join(process.cwd(), ".data");
    mkdirSync(fallback, { recursive: true });
    return fallback;
  }
}

let cached: string | null = null;
export function dataRoot(): string {
  if (!cached) cached = resolveRoot();
  return cached;
}

export type ServiceType = "discord" | "minecraft" | "web";

/** Volume path for a service. Derived ONLY from the authenticated serviceId. */
export function serviceVolume(type: ServiceType, serviceId: string): string {
  if (!/^[a-zA-Z0-9-]+$/.test(serviceId)) throw new Error("Invalid service id");
  const dir = path.join(dataRoot(), type, serviceId);
  mkdirSync(dir, { recursive: true });
  return dir;
}

export function backupsDir(serviceId: string): string {
  if (!/^[a-zA-Z0-9-]+$/.test(serviceId)) throw new Error("Invalid service id");
  const dir = path.join(dataRoot(), "backups", serviceId);
  mkdirSync(dir, { recursive: true });
  return dir;
}

/** In-container mount point per runtime family. */
export const MOUNT_POINT: Record<ServiceType, string> = {
  discord: "/app",
  minecraft: "/data",
  web: "/srv/app",
};
