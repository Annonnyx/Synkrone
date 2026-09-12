import fs from "node:fs/promises";
import path from "node:path";
import { eq } from "drizzle-orm";
import { db } from "@/db";
import { services, sftpCredentials, users } from "@/db/schema";
import { encryptSecret, verifyPassword } from "@/lib/crypto";
import { dataRoot, type ServiceType } from "@/lib/paths";
import { sha512Crypt } from "@/lib/sha512crypt";
import { sftpUserConfLine } from "@/lib/sftp/format";

/**
 * SFTPManager — issues per-service SFTP accounts.
 *
 * Authentication is the Orbital account password (scrypt on `users.password_hash`).
 * The account password is never stored in plaintext. On login / password change we
 * materialise a Unix SHA-512 crypt into `${DATA_ROOT}/sftp/owner-crypt.json`, then
 * render `${DATA_ROOT}/sftp/users.conf` for the `sftp` gateway (atmoz/sftp).
 * Each account is chrooted to a single service volume (§45).
 */
const ACCOUNT_MARKER = "account";

export function publicSftpEndpoint() {
  const host = String(process.env.SFTP_HOST || "").trim() || "sftp.localhost";
  const port = Number(process.env.SFTP_PORT || 2022);
  return {
    host,
    port: Number.isFinite(port) && port > 0 ? port : 2022,
  };
}

type OwnerCryptMap = Record<string, string>;

function ownerCryptFile(): string {
  return path.join(dataRoot(), "sftp", "owner-crypt.json");
}

async function readOwnerCrypts(): Promise<OwnerCryptMap> {
  try {
    const parsed: unknown = JSON.parse(await fs.readFile(ownerCryptFile(), "utf8"));
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    const out: OwnerCryptMap = {};
    for (const [userId, value] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof value === "string" && value.startsWith("$6$")) out[userId] = value;
    }
    return out;
  } catch {
    return {};
  }
}

async function writeOwnerCrypts(map: OwnerCryptMap): Promise<void> {
  const file = ownerCryptFile();
  await fs.mkdir(path.dirname(file), { recursive: true });
  await fs.writeFile(file, `${JSON.stringify(map)}\n`, { mode: 0o600 });
  await fs.chmod(file, 0o600);
}

export const SFTPManager = {
  accountFile(): string {
    return path.join(dataRoot(), "sftp", "users.conf");
  },

  async issue(serviceId: string, type: ServiceType, slug: string) {
    const username = `${type}_${slug}_${serviceId.slice(0, 6)}`
      .replace(/[^a-z0-9_]/gi, "")
      .toLowerCase();
    const chroot = `/data/${type}/${serviceId}`;
    await db.delete(sftpCredentials).where(eq(sftpCredentials.serviceId, serviceId));
    const endpoint = publicSftpEndpoint();
    await db.insert(sftpCredentials).values({
      serviceId,
      username,
      passwordEnc: encryptSecret(ACCOUNT_MARKER),
      host: endpoint.host,
      port: endpoint.port,
      chroot,
    });
    await this.sync();
    return { username, chroot, auth: "account" as const };
  },

  /** Called when the owner types their account password (login, register, change). */
  async applyOwnerPassword(userId: string, password: string): Promise<void> {
    const map = await readOwnerCrypts();
    map[userId] = sha512Crypt(password);
    await writeOwnerCrypts(map);
    await this.sync();
  },

  /** Rewrites the gateway account file from the database (source of truth). */
  async sync(): Promise<void> {
    const crypts = await readOwnerCrypts();
    const rows = await db
      .select({
        username: sftpCredentials.username,
        chroot: sftpCredentials.chroot,
        enabled: sftpCredentials.enabled,
        ownerId: services.ownerId,
      })
      .from(sftpCredentials)
      .innerJoin(services, eq(services.id, sftpCredentials.serviceId));
    const lines = rows
      .filter((r) => r.enabled)
      .map((r) => sftpUserConfLine(r.username, r.chroot, crypts[r.ownerId]));
    const file = this.accountFile();
    await fs.mkdir(path.dirname(file), { recursive: true });
    await fs.writeFile(file, `${lines.join("\n")}\n`, { mode: 0o600 });
    await fs.chmod(file, 0o600);
  },

  /** True if `password` is the Orbital login of the service owner. */
  async authenticate(username: string, password: string): Promise<boolean> {
    const [row] = await db
      .select({
        passwordHash: users.passwordHash,
        enabled: sftpCredentials.enabled,
      })
      .from(sftpCredentials)
      .innerJoin(services, eq(services.id, sftpCredentials.serviceId))
      .innerJoin(users, eq(users.id, services.ownerId))
      .where(eq(sftpCredentials.username, username))
      .limit(1);
    if (!row?.enabled) return false;
    return verifyPassword(password, row.passwordHash);
  },

  async rotate(serviceId: string) {
    const [row] = await db
      .select()
      .from(sftpCredentials)
      .where(eq(sftpCredentials.serviceId, serviceId))
      .limit(1);
    if (!row) throw new Error("No SFTP account for this service");
    await this.sync();
    return { username: row.username, auth: "account" as const };
  },
};
