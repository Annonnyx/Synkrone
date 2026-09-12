import {
  createCipheriv,
  createDecipheriv,
  createHash,
  randomBytes,
  scryptSync,
  timingSafeEqual,
} from "node:crypto";

/**
 * Secrets (Discord tokens, DB passwords, env values) are encrypted at rest with
 * AES-256-GCM. The master key comes from PLATFORM_SECRET_KEY. A derived key is
 * used so that the raw env value never becomes the cipher key directly.
 *
 * Env is read via `process.env[name]` so Next.js cannot inline the value at
 * build time (which would decrypt with a different key than the one used to
 * encrypt). An empty PLATFORM_SECRET_KEY is treated as unset so DATABASE_URL
 * or the development fallback can still open older rows.
 */
function envMaterial(name: string): string {
  return String(process.env[name] ?? "").trim();
}

function preferredSecretMaterial(): string {
  return envMaterial("PLATFORM_SECRET_KEY") || envMaterial("DATABASE_URL") || "insecure-development-key";
}

function secretMaterials(): string[] {
  const ordered = [
    preferredSecretMaterial(),
    envMaterial("PLATFORM_SECRET_KEY"),
    String(process.env["PLATFORM_SECRET_KEY"] ?? ""),
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
