export const HISTORY_LIMIT = 200;

export function historyKey(serviceId: string) {
  return `orbital:console:history:${serviceId}`;
}

export function parseHistory(raw: string | null): string[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item): item is string => typeof item === "string" && item.trim().length > 0)
      .slice(-HISTORY_LIMIT);
  } catch {
    return [];
  }
}

export function readHistory(serviceId: string): string[] {
  try {
    return parseHistory(localStorage.getItem(historyKey(serviceId)));
  } catch {
    return [];
  }
}

export function writeHistory(serviceId: string, entries: string[]) {
  try {
    localStorage.setItem(historyKey(serviceId), JSON.stringify(entries.slice(-HISTORY_LIMIT)));
  } catch {
    /* private mode / quota */
  }
}

export function clearHistory(serviceId: string) {
  try {
    localStorage.removeItem(historyKey(serviceId));
  } catch {
    /* private mode */
  }
}

export function commitHistoryEntry(entries: string[], cmd: string): string[] {
  const trimmed = cmd.trim();
  if (!trimmed) return entries;
  if (entries[entries.length - 1] === trimmed) return entries;
  return [...entries, trimmed].slice(-HISTORY_LIMIT);
}

/** Newest first. Empty query returns the full history. */
export function searchHistory(entries: string[], query: string): string[] {
  const newest = [...entries].reverse();
  const q = query.trim().toLowerCase();
  if (!q) return newest;
  return newest.filter((entry) => entry.toLowerCase().includes(q));
}
