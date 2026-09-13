import { PANEL_BASE_PATH } from "@/lib/panel-base";

export const PRODUCTION_ORIGIN = "https://synkrone.app";
export const LOCAL_ORIGIN = "http://127.0.0.1:3668";

function trimSlash(value: string | undefined | null): string {
  return String(value || "").trim().replace(/\/$/, "");
}

export function stripPanelSuffix(origin: string): string {
  return trimSlash(origin).replace(/\/hebergement$/i, "");
}

export function isLoopbackOrigin(value: string | undefined | null): boolean {
  const raw = String(value || "").trim();
  if (!raw) return false;
  try {
    const url = new URL(raw.includes("://") ? raw : `http://${raw}`);
    const host = String(url.hostname || "").toLowerCase();
    return host === "localhost" || host === "127.0.0.1" || host === "::1" || host === "0.0.0.0";
  } catch {
    return /^(https?:\/\/)?(127\.0\.0\.1|localhost|\[::1\]|::1|0\.0\.0\.0)(:|\/|$)/i.test(raw);
  }
}

function isProductionEnv(env: NodeJS.Dict<string> = process.env): boolean {
  return String(env.NODE_ENV || "").trim() === "production";
}

export function envOriginCandidates(env: NodeJS.Dict<string> = process.env): Array<string | undefined> {
  return [env.PUBLIC_SITE_ORIGIN, env.PUBLIC_ORIGIN, env.SYNKRONE_PANEL_ORIGIN, env.ORBITAL_PUBLIC_ORIGIN];
}

export function pickPublicOrigin(
  candidates: Array<string | undefined | null>,
  env: NodeJS.Dict<string> = process.env,
): string {
  const list = candidates.map(trimSlash).filter(Boolean);
  const publicOne = list.find((item) => !isLoopbackOrigin(item));
  if (publicOne) return stripPanelSuffix(publicOne);
  if (isProductionEnv(env)) return PRODUCTION_ORIGIN;
  const first = list[0];
  return first ? stripPanelSuffix(first) : "";
}

export function withPanelOrigin(origin: string): string {
  const clean = stripPanelSuffix(origin) || LOCAL_ORIGIN;
  if (clean.endsWith(PANEL_BASE_PATH)) return clean;
  try {
    const url = new URL(clean);
    if (url.pathname && url.pathname !== "/") return clean;
  } catch {
    /* keep appending */
  }
  return `${clean}${PANEL_BASE_PATH}`;
}

export function originFromRequest(req: Request): string {
  const proto = (req.headers.get("x-forwarded-proto") || "http").split(",")[0].trim() || "http";
  const host = (req.headers.get("x-forwarded-host") || req.headers.get("host") || "").split(",")[0].trim();
  if (!host) {
    try {
      return new URL(req.url).origin;
    } catch {
      return "";
    }
  }
  return `${proto}://${host}`;
}

export function publicPanelOrigin(
  reqOrigin?: string | null,
  env: NodeJS.Dict<string> = process.env,
): string {
  const picked =
    pickPublicOrigin([...envOriginCandidates(env), reqOrigin], env) || `${LOCAL_ORIGIN}`;
  return withPanelOrigin(picked);
}

export function oauthRedirectUri(
  provider: string,
  reqOrigin?: string | null,
  env: NodeJS.Dict<string> = process.env,
): string {
  return `${publicPanelOrigin(reqOrigin, env)}/api/auth/oauth/${provider}/callback`;
}
