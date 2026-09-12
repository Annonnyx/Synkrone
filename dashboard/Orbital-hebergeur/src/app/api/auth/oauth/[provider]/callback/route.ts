import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { audit } from "@/lib/audit";
import { createSession, getCurrentUser } from "@/lib/auth";
import { publicSiteOriginFromEnv } from "@/lib/discord/site-link-env";
import { completeOAuthLogin } from "@/lib/oauth/accounts";
import {
  exchangeAuthorizationCode,
  fetchProviderProfile,
  getProviderConfig,
  panelUrl,
  publicOrigin,
} from "@/lib/oauth/providers";
import { OAUTH_STATE_COOKIE, sanitizeReturnTo, verifyOAuthState } from "@/lib/oauth/state";
import { isOAuthProvider } from "@/lib/oauth/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ provider: string }> };

async function bridgeSiteSession(
  provider: string,
  profile: { id: string; name?: string; login?: string | null; email?: string | null; avatarUrl?: string | null },
) {
  const origin = publicSiteOriginFromEnv() || "http://127.0.0.1:3668";
  const key = String(process.env.PLATFORM_SECRET_KEY || "").trim();
  if (key.length < 16) return;
  try {
    const res = await fetch(`${origin}/api/internal/session-bridge`, {
      method: "POST",
      headers: {
        authorization: `Bearer ${key}`,
        "content-type": "application/json",
      },
      body: JSON.stringify({ provider, profile }),
    });
    if (!res.ok) return;
    const data = (await res.json()) as { sid?: string };
    if (!data.sid) return;
    const store = await cookies();
    store.set("synkrone.sid", data.sid, {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: 21 * 24 * 60 * 60,
    });
  } catch {
    /* site unreachable — panel session still stands */
  }
}

function redirectWith(origin: string, path: string, params: Record<string, string>) {
  const url = panelUrl(origin, path);
  for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);
  return NextResponse.redirect(url);
}

export async function GET(req: NextRequest, ctx: Ctx) {
  const { provider } = await ctx.params;
  const origin = publicOrigin(req.nextUrl.origin);
  const store = await cookies();
  const signed = store.get(OAUTH_STATE_COOKIE)?.value;
  store.delete(OAUTH_STATE_COOKIE);

  if (!isOAuthProvider(provider)) {
    return redirectWith(origin, "/login", { oauth_error: "unknown_provider" });
  }

  const denied = req.nextUrl.searchParams.get("error");
  if (denied) {
    return redirectWith(origin, "/login", { oauth_error: "denied" });
  }

  const payload = verifyOAuthState(signed);
  const nonce = req.nextUrl.searchParams.get("state");
  if (!payload || payload.p !== provider || payload.n !== nonce) {
    return redirectWith(origin, "/login", { oauth_error: "state" });
  }

  const code = req.nextUrl.searchParams.get("code");
  const config = getProviderConfig(provider);
  if (!code || !config) {
    return redirectWith(origin, "/login", { oauth_error: code ? "not_configured" : "missing_code" });
  }

  const current = await getCurrentUser();
  const intent = payload.i === "link" || current ? "link" : "login";
  const fallback = intent === "link" ? "/dashboard/account/profile" : "/login";

  try {
    const tokens = await exchangeAuthorizationCode({
      provider,
      config,
      code,
      verifier: payload.cv,
      origin: req.nextUrl.origin,
    });
    const profile = await fetchProviderProfile(provider, tokens.accessToken);
    const result = await completeOAuthLogin({
      provider,
      profile,
      tokens,
      intent,
      currentUserId: current?.id,
    });
    if (!current) await createSession(result.userId);
    await bridgeSiteSession(provider, profile);
    await audit({
      userId: result.userId,
      action: intent === "link" ? `oauth.link.${provider}` : `oauth.login.${provider}`,
      detail: profile.login ?? profile.email ?? profile.id,
    });
    const dest = sanitizeReturnTo(payload.r) ?? (intent === "link" ? "/dashboard/account/profile" : "/dashboard");
    const url = panelUrl(origin, dest);
    if (intent === "link") url.searchParams.set("linked", provider);
    return NextResponse.redirect(url);
  } catch (err) {
    const codeName =
      err && typeof err === "object" && "code" in err && typeof err.code === "string"
        ? err.code
        : "oauth_failed";
    const mapped =
      codeName === "OAUTH_LINKED_OTHER"
        ? "linked_other"
        : codeName === "OAUTH_LINK_REQUIRED"
          ? "oauth_link_required"
          : "oauth_failed";
    console.error("[oauth] callback failed", provider, mapped);
    return redirectWith(origin, fallback, { oauth_error: mapped });
  }
}
