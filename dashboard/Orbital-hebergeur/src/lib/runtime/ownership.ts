import { execFile } from "node:child_process";
import { promisify } from "node:util";

const exec = promisify(execFile);

/**
 * Volume ownership — service volumes are created by the panel (usually root),
 * but most runtimes run as an unprivileged container user (minecraft and node
 * as 1000:1000, static web as 101:101). Without a chown, every container
 * write is denied (e.g. Paper failing to download its jar with
 * AccessDeniedException on /data).
 *
 * The SFTP gateway accounts use the same uid:gid (1000:1000), so aligning the
 * volume on the runtime user keeps file access working on both sides.
 */

/** Parse a "uid:gid" container user. Null = root or invalid → no chown needed. */
export function parseVolumeOwner(user: string | undefined): { uid: number; gid: number } | null {
  const match = /^\s*(\d+)\s*:\s*(\d+)\s*$/.exec(String(user ?? ""));
  if (!match) return null;
  const uid = Number(match[1]);
  const gid = Number(match[2]);
  if (!Number.isSafeInteger(uid) || !Number.isSafeInteger(gid)) return null;
  if (uid === 0) return null;
  return { uid, gid };
}

/** Recursively hand the volume root to the runtime user. Throws on failure. */
export async function chownVolumeRoot(root: string, owner: { uid: number; gid: number }): Promise<void> {
  await exec("chown", ["-R", `${owner.uid}:${owner.gid}`, root]);
}
