import { pool } from "@/db";
import { ACCOUNT_SCHEMA_SQL } from "@/db/account-schema-sql";
import { PLATFORM_SCHEMA_SQL } from "@/db/platform-schema-sql";

let ready: Promise<void> | null = null;
let platformReady: Promise<void> | null = null;

export async function ensureAccountSchema() {
  if (!ready) {
    ready = pool
      .query(ACCOUNT_SCHEMA_SQL)
      .then(() => undefined)
      .catch((err) => {
        ready = null;
        throw err;
      });
  }
  return ready;
}

export async function ensurePlatformSchema() {
  if (!platformReady) {
    platformReady = pool
      .query(PLATFORM_SCHEMA_SQL)
      .then(() => undefined)
      .catch((err) => {
        platformReady = null;
        throw err;
      });
  }
  return platformReady;
}
