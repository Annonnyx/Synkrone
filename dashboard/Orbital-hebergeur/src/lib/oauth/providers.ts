import { PANEL_BASE_PATH } from "@/lib/panel-base";
import type { OAuthIntent, OAuthProvider, OAuthProfile, OAuthTokens } from "./types";
import { codeChallenge } from "./state";

export type ProviderConfig = {
  id: OAuthProvider;
  clientId: string;
  clientSecret: string;
};

function withPanelOrigin(origin: string): string {
  const clean = origin.replace(/\/$/, "");
  if (clean.endsWith(PANEL_BASE_PATH)) return clean;
  try {
    const url = new URL(clean);
    if (url.pathname && url.pathname !== "/") return clean;
  } catch {
    /* keep appending */
  }
  return `${clean}${PANEL_BASE_PATH}`;
}

export function publicOrigin(reqOrigin?: string | null): string {
  const fromEnv = (process.env.SYNKRONE_PANEL_ORIGIN || process.env.ORBITAL_PUBLIC_ORIGIN)
    ?.trim()
    .replace(/\/$/, "");
  if (fromEnv) return withPanelOrigin(fromEnv);
  if (reqOrigin) return withPanelOrigin(reqOrigin);
  return `http://127.0.0.1:3668${PANEL_BASE_PATH}`;
}

export function panelUrl(origin: string, path: string): URL {
  const base = publicOrigin(origin);
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return new URL(`${base}${normalized}`);
}

export function oauthRedirectUri(provider: OAuthProvider, origin?: string | null): string {
  return `${publicOrigin(origin)}/api/auth/oauth/${provider}/callback`;
}

function envPair(primaryId: string, primarySecret: string, fallbackId: string, fallbackSecret: string) {
  const id = process.env[primaryId]?.trim() || process.env[fallbackId]?.trim();
  const secret = process.env[primarySecret]?.trim() || process.env[fallbackSecret]?.trim();
  return { id, secret };
}

export function getProviderConfig(provider: OAuthProvider): ProviderConfig | null {
  const map: Record<OAuthProvider, { id?: string; secret?: string }> = {
    github: envPair("GITHUB_PANEL_CLIENT_ID", "GITHUB_PANEL_CLIENT_SECRET", "GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET"),
    google: envPair("GOOGLE_PANEL_CLIENT_ID", "GOOGLE_PANEL_CLIENT_SECRET", "GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"),
    discord: { id: process.env.DISCORD_CLIENT_ID, secret: process.env.DISCORD_CLIENT_SECRET },
  };
  const row = map[provider];
  const clientId = row.id?.trim();
  const clientSecret = row.secret?.trim();
  if (!clientId || !clientSecret) return null;
  return { id: provider, clientId, clientSecret };
}

export function isProviderConfigured(provider: OAuthProvider): boolean {
  return getProviderConfig(provider) !== null;
}

export function configuredProviders(): OAuthProvider[] {
  return (["github", "google", "discord"] as const).filter(isProviderConfigured);
}

export function authorizationUrl(input: {
  provider: OAuthProvider;
  config: ProviderConfig;
  origin?: string | null;
  nonce: string;
  verifier: string;
  intent: OAuthIntent;
}): string {
  const redirectUri = oauthRedirectUri(input.provider, input.origin);
  const challenge = codeChallenge(input.verifier);
  if (input.provider === "github") {
    const url = new URL("https://github.com/login/oauth/authorize");
    url.searchParams.set("client_id", input.config.clientId);
    url.searchParams.set("redirect_uri", redirectUri);
    url.searchParams.set("scope", "read:user user:email repo");
    url.searchParams.set("state", input.nonce);
    url.searchParams.set("code_challenge", challenge);
    url.searchParams.set("code_challenge_method", "S256");
    url.searchParams.set("allow_signup", "true");
    return url.toString();
  }
  if (input.provider === "google") {
    const url = new URL("https://accounts.google.com/o/oauth2/v2/auth");
    url.searchParams.set("client_id", input.config.clientId);
    url.searchParams.set("redirect_uri", redirectUri);
    url.searchParams.set("response_type", "code");
    url.searchParams.set("scope", "openid email profile");
    url.searchParams.set("state", input.nonce);
    url.searchParams.set("code_challenge", challenge);
    url.searchParams.set("code_challenge_method", "S256");
    url.searchParams.set("access_type", "offline");
    url.searchParams.set("include_granted_scopes", "true");
    url.searchParams.set("prompt", input.intent === "link" ? "consent" : "select_account");
    return url.toString();
  }
  const url = new URL("https://discord.com/api/oauth2/authorize");
  url.searchParams.set("client_id", input.config.clientId);
  url.searchParams.set("redirect_uri", redirectUri);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("scope", "identify email");
  url.searchParams.set("state", input.nonce);
  url.searchParams.set("code_challenge", challenge);
  url.searchParams.set("code_challenge_method", "S256");
  url.searchParams.set("prompt", "consent");
  return url.toString();
}

type TokenJson = {
  access_token?: string;
  refresh_token?: string;
  expires_in?: number;
  scope?: string;
  error?: string;
  error_description?: string;
};

async function readTokenJson(res: Response): Promise<TokenJson> {
  const text = await res.text();
  try {
    return JSON.parse(text) as TokenJson;
  } catch {
    const params = new URLSearchParams(text);
    return {
      access_token: params.get("access_token") ?? undefined,
      refresh_token: params.get("refresh_token") ?? undefined,
      expires_in: params.get("expires_in") ? Number(params.get("expires_in")) : undefined,
      scope: params.get("scope") ?? undefined,
      error: params.get("error") ?? undefined,
      error_description: params.get("error_description") ?? undefined,
    };
  }
}

export async function exchangeAuthorizationCode(input: {
  provider: OAuthProvider;
  config: ProviderConfig;
  code: string;
  verifier: string;
  origin?: string | null;
}): Promise<OAuthTokens> {
  const redirectUri = oauthRedirectUri(input.provider, input.origin);
  return requestTokens(input.provider, input.config, {
    grant_type: "authorization_code",
    code: input.code,
    redirect_uri: redirectUri,
    code_verifier: input.verifier,
  });
}

export async function refreshProviderToken(input: {
  provider: OAuthProvider;
  config: ProviderConfig;
  refreshToken: string;
}): Promise<OAuthTokens> {
  return requestTokens(input.provider, input.config, {
    grant_type: "refresh_token",
    refresh_token: input.refreshToken,
  });
}

async function requestTokens(
  provider: OAuthProvider,
  config: ProviderConfig,
  fields: Record<string, string>,
): Promise<OAuthTokens> {
  const body = new URLSearchParams({
    client_id: config.clientId,
    client_secret: config.clientSecret,
    ...fields,
  });
  const endpoint =
    provider === "github"
      ? "https://github.com/login/oauth/access_token"
      : provider === "google"
        ? "https://oauth2.googleapis.com/token"
        : "https://discord.com/api/oauth2/token";
  const res = await fetch(endpoint, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body,
    cache: "no-store",
  });
  const json = await readTokenJson(res);
  if (!res.ok || !json.access_token) {
    const reason = json.error_description || json.error || `token exchange failed (${res.status})`;
    throw new Error(reason);
  }
  return {
    accessToken: json.access_token,
    refreshToken: json.refresh_token ?? null,
    expiresIn: json.expires_in ?? null,
    scope: json.scope ?? null,
  };
}

export async function fetchProviderProfile(
  provider: OAuthProvider,
  accessToken: string,
): Promise<OAuthProfile> {
  if (provider === "github") return fetchGithubProfile(accessToken);
  if (provider === "google") return fetchGoogleProfile(accessToken);
  return fetchDiscordProfile(accessToken);
}

async function fetchGithubProfile(accessToken: string): Promise<OAuthProfile> {
  const headers = {
    Accept: "application/vnd.github+json",
    Authorization: `Bearer ${accessToken}`,
    "User-Agent": "Synkrone-Panel",
    "X-GitHub-Api-Version": "2022-11-28",
  };
  const userRes = await fetch("https://api.github.com/user", { headers, cache: "no-store" });
  if (!userRes.ok) throw new Error(`GitHub profile failed (${userRes.status})`);
  const user = (await userRes.json()) as {
    id: number;
    login: string;
    name: string | null;
    email: string | null;
    avatar_url: string | null;
  };
  let email = user.email;
  let emailVerified = Boolean(email);
  if (!email) {
    const mailRes = await fetch("https://api.github.com/user/emails", { headers, cache: "no-store" });
    if (mailRes.ok) {
      const emails = (await mailRes.json()) as Array<{
        email: string;
        primary: boolean;
        verified: boolean;
      }>;
      const primary = emails.find((e) => e.primary && e.verified) ?? emails.find((e) => e.verified);
      if (primary) {
        email = primary.email;
        emailVerified = primary.verified;
      }
    }
  }
  return {
    id: String(user.id),
    email,
    emailVerified,
    name: user.name || user.login,
    avatarUrl: user.avatar_url,
    login: user.login,
  };
}

async function fetchGoogleProfile(accessToken: string): Promise<OAuthProfile> {
  const res = await fetch("https://openidconnect.googleapis.com/v1/userinfo", {
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Google profile failed (${res.status})`);
  const user = (await res.json()) as {
    sub: string;
    email?: string;
    email_verified?: boolean;
    name?: string;
    picture?: string;
  };
  return {
    id: user.sub,
    email: user.email ?? null,
    emailVerified: Boolean(user.email_verified),
    name: user.name || user.email || "Google user",
    avatarUrl: user.picture ?? null,
    login: user.email ?? null,
  };
}

async function fetchDiscordProfile(accessToken: string): Promise<OAuthProfile> {
  const res = await fetch("https://discord.com/api/users/@me", {
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Discord profile failed (${res.status})`);
  const user = (await res.json()) as {
    id: string;
    username: string;
    global_name?: string | null;
    email?: string | null;
    verified?: boolean;
    avatar?: string | null;
  };
  const avatarUrl = user.avatar
    ? `https://cdn.discordapp.com/avatars/${user.id}/${user.avatar}.png`
    : null;
  return {
    id: user.id,
    email: user.email ?? null,
    emailVerified: Boolean(user.verified && user.email),
    name: user.global_name || user.username,
    avatarUrl,
    login: user.username,
  };
}
