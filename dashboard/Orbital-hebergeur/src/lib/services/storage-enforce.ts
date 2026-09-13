import { eq } from "drizzle-orm";
import { db } from "@/db";
import { services } from "@/db/schema";
import { FilesystemError, FilesystemManager } from "@/lib/filesystem/manager";
import { SFTPManager } from "@/lib/sftp/manager";
import { extraBytesWouldExceed, isOverQuota, STORAGE_QUOTA_ERROR } from "@/lib/services/storage-quota";
import type { ServiceType } from "@/lib/paths";

type QuotaService = {
  id: string;
  type: string;
  storageLimitMb: number;
  storageOverflowAt?: Date | null;
  lastError?: string | null;
};

export async function assertServiceWriteFits(svc: QuotaService, extraBytes: number): Promise<void> {
  if (svc.storageOverflowAt) {
    throw new FilesystemError(STORAGE_QUOTA_ERROR, 403);
  }
  const fsm = new FilesystemManager(svc.type as ServiceType, svc.id);
  const used = await fsm.diskUsageBytes();
  if (extraBytesWouldExceed(used, extraBytes, svc.storageLimitMb)) {
    throw new FilesystemError(STORAGE_QUOTA_ERROR, 403);
  }
}

export async function refreshStorageOverflow(svc: QuotaService, usedMb?: number): Promise<boolean> {
  const used =
    usedMb ?? (await new FilesystemManager(svc.type as ServiceType, svc.id).diskUsageMb());
  const over = isOverQuota(used, svc.storageLimitMb);
  if (over && !svc.storageOverflowAt) {
    await db
      .update(services)
      .set({
        storageOverflowAt: new Date(),
        lastError: STORAGE_QUOTA_ERROR,
        updatedAt: new Date(),
      })
      .where(eq(services.id, svc.id));
    await SFTPManager.setEnabled(svc.id, false).catch(() => undefined);
    return true;
  }
  if (!over && svc.storageOverflowAt) {
    await db
      .update(services)
      .set({
        storageOverflowAt: null,
        lastError: svc.lastError === STORAGE_QUOTA_ERROR ? null : svc.lastError,
        updatedAt: new Date(),
      })
      .where(eq(services.id, svc.id));
    await SFTPManager.setEnabled(svc.id, true).catch(() => undefined);
    return false;
  }
  return over;
}
