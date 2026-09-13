import { NextRequest, NextResponse } from "next/server";
import { HttpError, issueSessionToken } from "@/lib/auth";
import { requireInternalAdmin } from "@/lib/internal-admin";
import { ensurePanelIdentity } from "@/lib/oauth/accounts";
import { isOAuthProvider } from "@/lib/oauth/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  try {
    requireInternalAdmin(req);
    const body = (await req.json()) as {
      provider?: string;
      userId?: string;
      profile?: { id?: string; name?: string; login?: string; email?: string; avatarUrl?: string };
    };
    const provider = String(body.provider || "");
    if (!isOAuthProvider(provider)) {
      return NextResponse.json({ error: "unknown_provider" }, { status: 400 });
    }
    const profile = body.profile || {};
    if (!profile.id) {
      return NextResponse.json({ error: "missing_profile" }, { status: 400 });
    }
    const identity = await ensurePanelIdentity({
      provider,
      currentUserId: body.userId,
      profile: {
        id: String(profile.id),
        name: String(profile.name || profile.login || provider),
        login: String(profile.login || profile.name || ""),
        email: profile.email ? String(profile.email) : undefined,
        avatarUrl: profile.avatarUrl ? String(profile.avatarUrl) : undefined,
      },
    });
    const token = await issueSessionToken(identity.userId);
    return NextResponse.json({
      ok: true,
      token,
      userId: identity.userId,
      created: identity.created,
      discordId: identity.discordId,
    });
  } catch (err) {
    const status = err instanceof HttpError ? err.status : 500;
    return NextResponse.json({ error: err instanceof Error ? err.message : "bridge_failed" }, { status });
  }
}
