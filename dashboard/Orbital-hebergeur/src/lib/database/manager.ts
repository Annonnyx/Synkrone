import { sql } from "drizzle-orm";
import { db } from "@/db";
import { encryptSecret, randomPassword, shortId } from "@/lib/crypto";

/**
 * DatabaseManager — provisions REAL databases with per-database users.
 *
 * The platform ships with PostgreSQL (the same engine the panel uses, on a
 * dedicated `orbital-database` network). Each provisioned database gets its own
 * role, its own password and privileges limited to that database only (§46/§47).
 * A MySQL driver can be registered later behind the same interface.
 */

export type ProvisionedDatabase = {
  dbName: string;
  dbUser: string;
  password: string;
  host: string;
  port: number;
};

function parseAdminUrl() {
  const url = new URL(process.env.DATABASE_URL as string);
  return {
    host: process.env.DB_PUBLIC_HOST ?? url.hostname,
    port: Number(url.port || 5432),
  };
}

function safeIdent(value: string): string {
  if (!/^[a-z_][a-z0-9_]{2,50}$/.test(value)) throw new Error("Invalid database identifier");
  return `"${value}"`;
}

export const DatabaseManager = {
  async create(baseName: string): Promise<ProvisionedDatabase> {
    const suffix = shortId(6);
    const dbName = `orb_${baseName.replace(/[^a-z0-9]/gi, "").toLowerCase().slice(0, 12) || "db"}_${suffix}`;
    const dbUser = `${dbName}_u`.slice(0, 60);
    const password = randomPassword(28);
    const { host, port } = parseAdminUrl();

    await db.execute(
      sql.raw(`CREATE ROLE ${safeIdent(dbUser)} LOGIN PASSWORD '${password.replace(/'/g, "''")}'`),
    );
    await db.execute(sql.raw(`CREATE DATABASE ${safeIdent(dbName)} OWNER ${safeIdent(dbUser)}`));
    await db.execute(
      sql.raw(`REVOKE ALL ON DATABASE ${safeIdent(dbName)} FROM PUBLIC`),
    );
    await db.execute(
      sql.raw(`GRANT ALL PRIVILEGES ON DATABASE ${safeIdent(dbName)} TO ${safeIdent(dbUser)}`),
    );
    return { dbName, dbUser, password, host, port };
  },

  async resetPassword(dbUser: string): Promise<string> {
    const password = randomPassword(28);
    await db.execute(
      sql.raw(`ALTER ROLE ${safeIdent(dbUser)} WITH PASSWORD '${password.replace(/'/g, "''")}'`),
    );
    return password;
  },

  async drop(dbName: string, dbUser: string): Promise<void> {
    await db.execute(sql.raw(`DROP DATABASE IF EXISTS ${safeIdent(dbName)} WITH (FORCE)`));
    await db.execute(sql.raw(`DROP ROLE IF EXISTS ${safeIdent(dbUser)}`));
  },

  connectionString(d: ProvisionedDatabase): string {
    return `postgresql://${d.dbUser}:${encodeURIComponent(d.password)}@${d.host}:${d.port}/${d.dbName}`;
  },

  encrypt: encryptSecret,
};
