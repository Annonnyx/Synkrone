import {
  createCipheriv,
  createDecipheriv,
  createHash,
  randomBytes,
  scryptSync,
  timingSafeEqual,
} from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

/**
 * Secrets (Discord tokens, DB passwords, env values) are encrypted at rest with
 * AES-256-GCM. The master key is only PLATFORM_SECRET_KEY — never DATABASE_URL
 * (rotating the DB password used to lock every stored token).
 *
 * Env is read via `process.env[name]` so Next.js cannot inline the value at
 * build time. An empty PLATFORM_SECRET_KEY is treated as unset. We also read
 * the panel `.env` on disk, because Next will not overlay the file when the
 * parent process already exported an empty PLATFORM_SECRET_KEY.
 */
function envMaterial(name: string): string {
  const env = process.env;
  return String(env[name] ?? "").trim();
}

export function parseDotenvKeys(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of String(text ?? "").split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq <= 0) continue;
    const key = trimmed.slice(0, eq).trim();
    let value = trimmed.slice(eq + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    if (key && value) out[key] = value;
  }
  return out;
}

function dotenvFiles(): string[] {
  const names = [".env", path.join("dashboard", "Orbital-hebergeur", ".env")];
  const files: string[] = [];
  let dir = process.cwd();
  for (let i = 0; i < 8; i++) {
    for (const name of names) files.push(path.join(dir, name));
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return files;
}

function ignoreDotenvFiles(): boolean {
  return envMaterial("SYNKRONE_CRYPTO_IGNORE_DOTENV") === "1";
}

function fileSecretMaterials(): string[] {
  if (ignoreDotenvFiles()) return [];
  const values: string[] = [];
  const seen = new Set<string>();
  for (const file of dotenvFiles()) {
    try {
      if (!existsSync(file)) continue;
      const parsed = parseDotenvKeys(readFileSync(file, "utf8"));
      for (const key of ["PLATFORM_SECRET_KEY", "DATABASE_URL"] as const) {
        const value = String(parsed[key] ?? "").trim();
        if (!value || seen.has(value)) continue;
        seen.add(value);
        values.push(value);
      }
    } catch {
      /* unreadable .env */
    }
  }
  return values;
}

function filePlatformKey(): string {
  if (ignoreDotenvFiles()) return "";
  for (const file of dotenvFiles()) {
    try {
      if (!existsSync(file)) continue;
      const value = String(parseDotenvKeys(readFileSync(file, "utf8")).PLATFORM_SECRET_KEY ?? "").trim();
      if (value) return value;
    } catch {
      /* unreadable .env */
    }
  }
  return "";
}

/** Key used to encrypt new secrets. DATABASE_URL is never a write key. */
export function preferredSecretMaterial(): string {
  return envMaterial("PLATFORM_SECRET_KEY") || filePlatformKey() || "insecure-development-key";
}

function hasConfiguredPlatformKey(): boolean {
  return Boolean(envMaterial("PLATFORM_SECRET_KEY") || filePlatformKey());
}

function secretMaterials(): string[] {
  const ordered = [
    preferredSecretMaterial(),
    envMaterial("PLATFORM_SECRET_KEY"),
    filePlatformKey(),
    ...fileSecretMaterials(),
    envMaterial("DATABASE_URL"),
    String(process.env["DATABASE_URL"] ?? ""),
    "insecure-development-key",
    "",
  ];
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of ordered) {
    if (seen.has(raw)) continue;
    seen.add(raw);
    out.push(raw);
  }
  return out;
}

function keyFromMaterial(raw: string): Buffer {
  return createHash("sha256").update(`orbital::${raw}`).digest();
}

function decryptWithMaterial(payload: string, raw: string): string | null {
  const parts = payload.split(".");
  if (parts.length !== 4 || parts[0] !== "v1") return null;
  try {
    const iv = Buffer.from(parts[1], "base64url");
    const tag = Buffer.from(parts[2], "base64url");
    const data = Buffer.from(parts[3], "base64url");
    const decipher = createDecipheriv("aes-256-gcm", keyFromMaterial(raw), iv);
    decipher.setAuthTag(tag);
    return Buffer.concat([decipher.update(data), decipher.final()]).toString("utf8");
  } catch {
    return null;
  }
}

export function encryptSecret(plain: string): string {
  if (process.env.NODE_ENV === "production" && !hasConfiguredPlatformKey()) {
    throw new Error(
      "PLATFORM_SECRET_KEY is missing. Refusing to encrypt secrets with a fallback key.",
    );
  }
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", keyFromMaterial(preferredSecretMaterial()), iv);
  const enc = Buffer.concat([cipher.update(plain, "utf8"), cipher.final()]);
  const tag = cipher.getAuthTag();
  return `v1.${iv.toString("base64url")}.${tag.toString("base64url")}.${enc.toString("base64url")}`;
}

export function decryptSecret(payload: string | null | undefined): string | null {
  if (payload == null) return null;
  const text = String(payload).trim();
  if (!text) return null;
  for (const raw of secretMaterials()) {
    const plain = decryptWithMaterial(text, raw);
    if (plain !== null) return plain;
  }
  return null;
}

/** Ciphertext is present but none of the current keys can open it. */
export function isLockedSecret(payload: string | null | undefined): boolean {
  if (payload == null || !String(payload).trim()) return false;
  return decryptSecret(payload) === null;
}

/** True when the payload opens with the key we would use to encrypt today. */
export function opensWithPreferredKey(payload: string | null | undefined): boolean {
  if (payload == null) return false;
  const text = String(payload).trim();
  if (!text) return false;
  return decryptWithMaterial(text, preferredSecretMaterial()) !== null;
}

/** Re-encrypt with today's key when an older fallback still opens the blob. */
export function rewrapSecret(payload: string | null | undefined): string | null {
  const text = payload == null ? "" : String(payload).trim();
  if (!text) return null;
  const plain = decryptSecret(text);
  if (plain == null) return null;
  if (opensWithPreferredKey(text)) return text;
  return encryptSecret(plain);
}

export function hashPassword(password: string): string {
  const salt = randomBytes(16);
  const derived = scryptSync(password, salt, 64);
  return `scrypt.${salt.toString("base64url")}.${derived.toString("base64url")}`;
}

export function verifyPassword(password: string, stored: string | null): boolean {
  if (!stored) return false;
  const [scheme, saltB64, hashB64] = stored.split(".");
  if (scheme !== "scrypt" || !saltB64 || !hashB64) return false;
  const salt = Buffer.from(saltB64, "base64url");
  const expected = Buffer.from(hashB64, "base64url");
  const actual = scryptSync(password, salt, expected.length);
  return expected.length === actual.length && timingSafeEqual(expected, actual);
}

export function sha256(value: string): string {
  return createHash("sha256").update(value).digest("hex");
}

export function randomToken(bytes = 32): string {
  return randomBytes(bytes).toString("base64url");
}

export function randomPassword(length = 24): string {
  const alphabet =
    "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789!@%^*_-";
  const buf = randomBytes(length);
  let out = "";
  for (let i = 0; i < length; i += 1) out += alphabet[buf[i] % alphabet.length];
  return out;
}

/** Non reversible fingerprint used to display "which" token is stored. */
export function fingerprint(value: string): string {
  return sha256(value).slice(0, 12);
}

export function slugify(input: string): string {
  return (
    input
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 32) || "service"
  );
}

export function shortId(len = 6): string {
  return randomBytes(16).toString("hex").slice(0, len);
}
