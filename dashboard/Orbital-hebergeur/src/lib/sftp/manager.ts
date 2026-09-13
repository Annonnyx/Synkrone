import fs from "node:fs/promises";
import path from "node:path";
import { eq } from "drizzle-orm";
import { db } from "@/db";
import { services, sftpCredentials } from "@/db/schema";
import { decryptSecret, encryptSecret } from "@/lib/crypto";
import { dataRoot, type ServiceType } from "@/lib/paths";
import { sftpUserConfLine } from "@/lib/sftp/format";
import {
  generateSftpSecret,
  isPerServiceSftpSecret,
  sftpPasswordMatches,
} from "@/lib/sftp/password";
import { sha512Crypt } from "@/lib/sha512crypt";

/**
 * SFTPManager — issues a dedicated password per service (OAuth users have none).
 *
 * The plaintext is stored encrypted on `sftp_credentials.password_enc` and shown
 * once at issue/rotate. `sync()` renders `${DATA_ROOT}/sftp/users.conf` for the
 * atmoz/sftp gateway from glibc SHA-512 crypt hashes (never the account password).
 */
type ServiceCryptMap = Record<string, string>;

export function publicSftpEndpoint() {
  const host = String(process.env.SFTP_HOST || "").trim() || "sftp.localhost";
  const port = Number(process.env.SFTP_PORT || 2022);
  return {
    host,
    port: Number.isFinite(port) && port > 0 ? port : 2022,
  };
}

function serviceCryptFile(): string {
  return path.join(dataRoot(), "sftp", "service-crypt.json");
}

async function readServiceCrypts(): Promise<ServiceCryptMap> {
  try {
    const parsed: unknown = JSON.parse(await fs.readFile(serviceCryptFile(), "utf8"));
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    const out: ServiceCryptMap = {};
    for (const [serviceId, value] of Object.entries(parsed as Record<string, unknown>)) {
      if (typeof value === "string" && value.startsWith("$6$")) out[serviceId] = value;
    }
    return out;
  } catch {
    return {};
  }
}

async function writeServiceCrypts(map: ServiceCryptMap): Promise<void> {
  const file = serviceCryptFile();
  await fs.mkdir(path.dirname(file), { recursive: true });
  await fs.writeFile(file, `${JSON.stringify(map)}\n`, { mode: 0o600 });
  await fs.chmod(file, 0o600);
}

async function rememberCrypt(serviceId: string, crypt: string): Promise<void> {
  const map = await readServiceCrypts();
  map[serviceId] = crypt;
  await writeServiceCrypts(map);
}

async function cryptForRow(
  serviceId: string,
  passwordEnc: string,
  cache: ServiceCryptMap,
): Promise<string | null> {
  if (cache[serviceId]) return cache[serviceId];
  const plain = decryptSecret(passwordEnc);
  if (!isPerServiceSftpSecret(plain)) return null;
  const crypt = sha512Crypt(plain as string);
  cache[serviceId] = crypt;
  return crypt;
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
    const { password, crypt } = generateSftpSecret();
    await db.delete(sftpCredentials).where(eq(sftpCredentials.serviceId, serviceId));
    const endpoint = publicSftpEndpoint();
    await db.insert(sftpCredentials).values({
      serviceId,
      username,
      passwordEnc: encryptSecret(password),
      host: endpoint.host,
      port: endpoint.port,
      chroot,
    });
    await rememberCrypt(serviceId, crypt);
    await this.sync();
    return { username, chroot, auth: "service" as const, password };
  },

  async setEnabled(serviceId: string, enabled: boolean): Promise<void> {
    await db.update(sftpCredentials).set({ enabled }).where(eq(sftpCredentials.serviceId, serviceId));
    await this.sync();
  },

  /** Rewrites the gateway account file from the database (source of truth). */
  async sync(): Promise<void> {
    const crypts = await readServiceCrypts();
    let dirty = false;
    const rows = await db
      .select({
        serviceId: sftpCredentials.serviceId,
        username: sftpCredentials.username,
        chroot: sftpCredentials.chroot,
        enabled: sftpCredentials.enabled,
        passwordEnc: sftpCredentials.passwordEnc,
      })
      .from(sftpCredentials)
      .innerJoin(services, eq(services.id, sftpCredentials.serviceId));
    const lines: string[] = [];
    for (const r of rows) {
      if (!r.enabled) continue;
      const had = Boolean(crypts[r.serviceId]);
      const crypt = await cryptForRow(r.serviceId, r.passwordEnc, crypts);
      if (!crypt) continue;
      if (!had) dirty = true;
      lines.push(sftpUserConfLine(r.username, r.chroot, crypt));
    }
    if (dirty) await writeServiceCrypts(crypts);
    const file = this.accountFile();
    await fs.mkdir(path.dirname(file), { recursive: true });
    await fs.writeFile(file, `${lines.join("\n")}${lines.length ? "\n" : ""}`, { mode: 0o600 });
    await fs.chmod(file, 0o600);
  },

  async hasUsablePassword(serviceId: string): Promise<boolean> {
    const [row] = await db
      .select({ passwordEnc: sftpCredentials.passwordEnc })
      .from(sftpCredentials)
      .where(eq(sftpCredentials.serviceId, serviceId))
      .limit(1);
    if (!row) return false;
    return isPerServiceSftpSecret(decryptSecret(row.passwordEnc));
  },

  /** True if `password` is this service's SFTP secret — never the account password. */
  async authenticate(username: string, password: string): Promise<boolean> {
    const [row] = await db
      .select({
        serviceId: sftpCredentials.serviceId,
        passwordEnc: sftpCredentials.passwordEnc,
        enabled: sftpCredentials.enabled,
      })
      .from(sftpCredentials)
      .where(eq(sftpCredentials.username, username))
      .limit(1);
    if (!row?.enabled) return false;
    const ok = sftpPasswordMatches(decryptSecret(row.passwordEnc), password);
    if (ok) {
      const { touchOwnerActivity } = await import("@/lib/services/lifecycle");
      await touchOwnerActivity(row.serviceId).catch(() => undefined);
    }
    return ok;
  },

  async rotate(serviceId: string) {
    const [row] = await db
      .select()
      .from(sftpCredentials)
      .where(eq(sftpCredentials.serviceId, serviceId))
      .limit(1);
    if (!row) throw new Error("No SFTP account for this service");
    const { password, crypt } = generateSftpSecret();
    await db
      .update(sftpCredentials)
      .set({ passwordEnc: encryptSecret(password), enabled: true })
      .where(eq(sftpCredentials.id, row.id));
    await rememberCrypt(serviceId, crypt);
    await this.sync();
    return { username: row.username, auth: "service" as const, password };
  },
};
