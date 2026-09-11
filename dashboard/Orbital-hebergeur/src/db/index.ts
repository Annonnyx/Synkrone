import { drizzle } from "drizzle-orm/node-postgres";
import { Pool } from "pg";

const databaseUrl = process.env.DATABASE_URL;

if (!databaseUrl) {
  throw new Error("DATABASE_URL is required");
}

const globalForDb = globalThis as typeof globalThis & {
  __arenaNextJsPostgresqlPool?: Pool;
};

function createPool() {
  const next = new Pool({
    connectionString: databaseUrl,
    max: 10,
    idleTimeoutMillis: 10_000,
    connectionTimeoutMillis: 5_000,
  });
  // A recycled idle client throws here after Postgres restarts; without a
  // listener that becomes an uncaughtException and takes the panel down.
  next.on("error", (err) => {
    console.error("[db] idle client error", err.message);
  });
  return next;
}

export const pool = globalForDb.__arenaNextJsPostgresqlPool ?? createPool();

if (process.env.NODE_ENV !== "production") {
  globalForDb.__arenaNextJsPostgresqlPool = pool;
}

export const db = drizzle(pool);
