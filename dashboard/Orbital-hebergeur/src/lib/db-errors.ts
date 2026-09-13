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

function walkError(err: unknown, match: (code: string, message: string) => boolean): boolean {
  let current: unknown = err;
  for (let i = 0; i < 6 && current; i++) {
    const code =
      typeof current === "object" && current && "code" in current
        ? String((current as { code?: string }).code)
        : "";
    const message = current instanceof Error ? current.message : "";
    if (match(code, message)) return true;
    current = current instanceof Error ? current.cause : undefined;
  }
  return false;
}

/** True when Postgres is down, restarting, or the pool's TCP client is dead. */
export function isDatabaseUnavailable(err: unknown): boolean {
  return walkError(err, (code, message) => {
    if (CONNECT_CODES.has(code)) return true;
    return /database system is (starting up|shutting down)|connection terminated|too many clients|connect ECONNREFUSED/i.test(
      message,
    );
  });
}

/** True when a queried relation has not been created yet (e.g. site_profiles). */
export function isUndefinedTable(err: unknown): boolean {
  return walkError(err, (code, message) => {
    if (code === "42P01") return true;
    return /relation ["'].+["'] does not exist/i.test(message);
  });
}

/** True when a unique index / primary key rejected the write. */
export function isUniqueViolation(err: unknown): boolean {
  return walkError(err, (code, message) => {
    if (code === "23505") return true;
    return /duplicate key value violates unique constraint/i.test(message);
  });
}