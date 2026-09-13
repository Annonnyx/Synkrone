import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { ACCOUNT_SCHEMA_SQL } from "../src/db/account-schema-sql";
import { PLATFORM_SCHEMA_SQL } from "../src/db/platform-schema-sql";

test("panel account schema creates site_profiles and wallets without drizzle-kit", () => {
  assert.match(ACCOUNT_SCHEMA_SQL, /CREATE TABLE IF NOT EXISTS site_profiles/);
  assert.match(ACCOUNT_SCHEMA_SQL, /CREATE TABLE IF NOT EXISTS wallets/);
  assert.match(ACCOUNT_SCHEMA_SQL, /CREATE TABLE IF NOT EXISTS wallet_ledger/);
});

test("platform boot adds inactivity and storage columns without drizzle-kit", () => {
  assert.match(PLATFORM_SCHEMA_SQL, /last_owner_activity_at/);
  assert.match(PLATFORM_SCHEMA_SQL, /suspended_at/);
  assert.match(PLATFORM_SCHEMA_SQL, /storage_overflow_at/);
});

test("panel boot and first wallet use ensure the account tables", () => {
  const instrumentation = readFileSync(path.join(process.cwd(), "src/instrumentation.ts"), "utf8");
  assert.match(instrumentation, /ensureAccountSchema/);
  assert.match(instrumentation, /ensurePlatformSchema/);
  assert.match(instrumentation, /startPlatformTick/);
  const store = readFileSync(path.join(process.cwd(), "src/lib/krones/store.ts"), "utf8");
  assert.match(store, /ensureAccountSchema/);
  const privilege = readFileSync(path.join(process.cwd(), "src/lib/krones/privilege.ts"), "utf8");
  assert.match(privilege, /siteProfileForUser/);
  assert.match(privilege, /catch/);
});
