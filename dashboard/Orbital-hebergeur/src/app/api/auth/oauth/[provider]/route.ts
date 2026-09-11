import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { fail, rateLimit, route } from "@/lib/api";
import { audit } from "@/lib/audit";
import { getCurrentUser, requireUser } from "@/lib/auth";
import { unlinkOAuthAccount } from "@/lib/oauth/accounts";
import { authorizationUrl, getProviderConfig, panelUrl } from "@/lib/oauth/providers";
import { createOAuthState, OAUTH_STATE_COOKIE, sanitizeReturnTo } from "@/lib/oauth/state";
import { isOAuthProvider, type OAuthIntent } from "@/lib/oauth/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ provider: string }> };

function cookieSecure() {
  return process.env.NODE_ENV === "production";
}

function errorRedirect(req: NextRequest, intent: OAuthIntent, code: string) {
  const dest =
    intent === "link" ? "/dashboard/account/profile" : "/login";
  const url = panelUrl(req.nextUrl.origin, dest);
  url.searchParams.set("oauth_error", code);
  return NextResponse.redirect(url);
}

export async function GET(req: NextRequest, ctx: Ctx) {
  const { provider } = await ctx.params;
  const ip = req.headers.get("x-forwarded-for") ?? "local";
  try {
    rateLimit(`oauth-start:${ip}`, 20);
  } catch {
    return fail("Too many requests, slow down", 429);
  }
  if (!isOAuthProvider(provider)) return fail("Unknown OAuth provider", 404);

  const intentRaw = req.nextUrl.searchParams.get("intent");
  const user = await getCurrentUser();
  const intent: OAuthIntent =
    intentRaw === "link" || (intentRaw !== "login" && user) ? "link" : "login";
  if (intent === "link" && !user) {
    return errorRedirect(req, "login", "oauth_link_required");
  }

  const config = getProviderConfig(provider);
  if (!config) return errorRedirect(req, intent, "not_configured");

  const started = createOAuthState({
    provider,
    intent,
    returnTo: sanitizeReturnTo(req.nextUrl.searchParams.get("returnTo")),
  });
  const store = await cookies();
  store.set(OAUTH_STATE_COOKIE, started.cookie, {
    httpOnly: true,
    sameSite: "lax",
    secure: cookieSecure(),
    path: "/",
    maxAge: 600,
  });

  const url = authorizationUrl({
    provider,
    config,
    origin: req.nextUrl.origin,
    nonce: started.nonce,
    verifier: started.verifier,
    intent,
  });
  return NextResponse.redirect(url);
}

export async function DELETE(_req: NextRequest, ctx: Ctx) {
  const { provider } = await ctx.params;
  return route(async () => {
    if (!isOAuthProvider(provider)) return fail("Unknown OAuth provider", 404);
    const user = await requireUser();
    await unlinkOAuthAccount(user.id, provider);
    await audit({ userId: user.id, action: `oauth.unlink.${provider}` });
    return { ok: true };
  });
}
