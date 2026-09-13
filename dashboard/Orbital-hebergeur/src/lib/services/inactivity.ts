export const IDLE_BEFORE_SUSPEND_MS = 30 * 24 * 60 * 60 * 1000;
export const PAUSE_BEFORE_DELETE_MS = 14 * 24 * 60 * 60 * 1000;
export const DELETE_WARNING_LEAD_MS = 3 * 24 * 60 * 60 * 1000;
export const ACTIVITY_DEBOUNCE_MS = 5 * 60 * 1000;

export type InactivityAction = "none" | "suspend" | "warn-delete" | "delete";

export type InactivityInput = {
  now: number;
  lastOwnerActivityAt: number;
  suspendedAt: number | null;
  deletionWarnedAt: number | null;
  state?: string | null;
};

/** Container running is not activity. Only owner panel actions reset the clock. */
export function inactivityAction(row: InactivityInput): InactivityAction {
  if (row.state === "CREATING" || row.state === "DELETING") return "none";
  if (row.suspendedAt != null) {
    const pausedFor = row.now - row.suspendedAt;
    if (pausedFor >= PAUSE_BEFORE_DELETE_MS) return "delete";
    if (
      pausedFor >= PAUSE_BEFORE_DELETE_MS - DELETE_WARNING_LEAD_MS &&
      row.deletionWarnedAt == null
    ) {
      return "warn-delete";
    }
    return "none";
  }
  if (row.now - row.lastOwnerActivityAt >= IDLE_BEFORE_SUSPEND_MS) return "suspend";
  return "none";
}

export function deletionDeadline(suspendedAt: number): number {
  return suspendedAt + PAUSE_BEFORE_DELETE_MS;
}

export function shouldRecordActivity(
  lastAt: number | null,
  now: number,
  minIntervalMs = ACTIVITY_DEBOUNCE_MS,
): boolean {
  if (lastAt == null) return true;
  return now - lastAt >= minIntervalMs;
}
