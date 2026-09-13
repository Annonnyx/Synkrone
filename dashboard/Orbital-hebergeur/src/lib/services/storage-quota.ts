const MB = 1024 * 1024;

/** True when adding extraBytes would go past the service storage ceiling. */
export function extraBytesWouldExceed(usedBytes: number, extraBytes: number, limitMb: number): boolean {
  if (!Number.isFinite(limitMb) || limitMb <= 0) return false;
  const used = Math.max(0, Number(usedBytes) || 0);
  const extra = Math.max(0, Number(extraBytes) || 0);
  return used + extra > limitMb * MB;
}

export function isOverQuota(usedMb: number, limitMb: number): boolean {
  if (!Number.isFinite(limitMb) || limitMb <= 0) return false;
  return usedMb > limitMb;
}

export const STORAGE_QUOTA_ERROR = "STORAGE_QUOTA_EXCEEDED";
