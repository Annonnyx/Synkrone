import { createHash, createHmac, timingSafeEqual } from "node:crypto";
import { randomToken } from "@/lib/crypto";
import type { OAuthIntent, OAuthProvider } from "./types";

export const OAUTH_STATE_COOKIE = "orbital_oauth";
export const OAUTH_STATE_TTL_MS = 10 * 60 * 1000;

export type OAuthStatePayload = {
  v: 1;
  n: string;
  p: OAuthProvider;
  i: OAuthIntent;
  r?: string;
  exp: number;
  cv: string;
};

function stateKey(): Buffer {
  const raw = process.env.PLATFORM_SECRET_KEY ?? "insecure-development-key";
  return createHash("sha256").update(`orbital-oauth::${raw}`).digest();
}

export function createCodeVerifier(): string {
  return randomToken(32);
}

export function codeChallenge(verifier: string): string {
  return createHash("sha256").update(verifier).digest("base64url");
}

export function signOAuthState(payload: OAuthStatePayload): string {
  const body = Buffer.from(JSON.stringify(payload)).toString("base64url");
  const sig = createHmac("sha256", stateKey()).update(body).digest("base64url");
  return `${body}.${sig}`;
}

export function verifyOAuthState(token: string | undefined | null): OAuthStatePayload | null {
  if (!token) return null;
  const dot = token.lastIndexOf(".");
  if (dot <= 0) return null;
  const body = token.slice(0, dot);
  const sig = token.slice(dot + 1);
  const expected = createHmac("sha256", stateKey()).update(body).digest("base64url");
  const a = Buffer.from(sig);
  const b = Buffer.from(expected);
  if (a.length !== b.length || !timingSafeEqual(a, b)) return null;
  try {
    const parsed = JSON.parse(Buffer.from(body, "base64url").toString("utf8")) as OAuthStatePayload;
    if (parsed.v !== 1 || !parsed.n || !parsed.p || !parsed.i || !parsed.cv) return null;
    if (typeof parsed.exp !== "number" || parsed.exp < Date.now()) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function createOAuthState(input: {
  provider: OAuthProvider;
  intent: OAuthIntent;
  returnTo?: string;
}): { nonce: string; cookie: string; verifier: string; payload: OAuthStatePayload } {
  const payload: OAuthStatePayload = {
    v: 1,
    n: randomToken(24),
    p: input.provider,
    i: input.intent,
    r: input.returnTo,
    exp: Date.now() + OAUTH_STATE_TTL_MS,
    cv: createCodeVerifier(),
  };
  return { nonce: payload.n, cookie: signOAuthState(payload), verifier: payload.cv, payload };
}

/** Only same-origin panel paths. Rejects protocol-relative and external URLs. */
export function sanitizeReturnTo(value: string | null | undefined): string | undefined {
  if (!value) return undefined;
  if (!value.startsWith("/")) return undefined;
  if (value.startsWith("//") || value.includes("\\")) return undefined;
  if (value.includes("://")) return undefined;
  if (value.length > 256) return undefined;
  return value;
}
