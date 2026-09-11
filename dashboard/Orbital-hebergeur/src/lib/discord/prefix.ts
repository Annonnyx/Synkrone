export const BOT_PREFIX_MAX = 10;

/** Trimmed prefix, 1–10 characters, no control characters. */
export function normalizeBotPrefix(raw: unknown): string | null {
  if (typeof raw !== "string") return null;
  const value = raw.trim();
  if (value.length < 1 || value.length > BOT_PREFIX_MAX) return null;
  if (/[\u0000-\u001F\u007F]/.test(value)) return null;
  return value;
}
