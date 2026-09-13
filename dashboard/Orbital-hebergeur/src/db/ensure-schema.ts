import { pool } from "@/db";
import { ACCOUNT_SCHEMA_SQL } from "@/db/account-schema-sql";

let ready: Promise<void> | null = null;

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
