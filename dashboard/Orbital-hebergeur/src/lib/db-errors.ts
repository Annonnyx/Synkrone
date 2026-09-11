const CONNECT_CODES = new Set([
  "ECONNREFUSED",
  "ECONNRESET",
  "ETIMEDOUT",
  "ENOTFOUND",
  "EPIPE",
  "57P01",
  "57P02",
  "57P03",
]);

/** True when Postgres is down, restarting, or the pool's TCP client is dead. */
export function isDatabaseUnavailable(err: unknown): boolean {
  let current: unknown = err;
  for (let i = 0; i < 6 && current; i++) {
    const code =
      typeof current === "object" && current && "code" in current
        ? String((current as { code?: string }).code)
        : "";
    if (CONNECT_CODES.has(code)) return true;
    const message = current instanceof Error ? current.message : "";
    if (
      /database system is (starting up|shutting down)|connection terminated|too many clients|connect ECONNREFUSED/i.test(
        message,
      )
    ) {
      return true;
    }
    current = current instanceof Error ? current.cause : undefined;
  }
  return false;
}