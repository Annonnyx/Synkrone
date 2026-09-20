import { eq } from "drizzle-orm";
import { NextRequest, NextResponse } from "next/server";
import { db } from "@/db";
import { ensureAccountSchema } from "@/db/ensure-schema";
import { siteProfiles, users } from "@/db/schema";
import { HttpError, issueSessionToken } from "@/lib/auth";
import { requireInternalAdmin } from "@/lib/internal-admin";
import { privilegeFromRecord } from "@/lib/krones/roles";
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
      link?: {
        provider?: string;
        profile?: { id?: string; name?: string; login?: string; email?: string; avatarUrl?: string };
      };
      siteRole?: string;
      siteIsTeamOwner?: boolean;
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
    // The site forwards its staff role: apply it so a site Admin keeps
    // unlimited Krônes in the panel even without access to users.json.
    const sitePriv = privilegeFromRecord({
      role: typeof body.siteRole === "string" ? body.siteRole : undefined,
      isTeamOwner: body.siteIsTeamOwner === true,
    });
    if (sitePriv) {
      try {
        await ensureAccountSchema();
        if (sitePriv === "admin") {
          const [row] = await db.select().from(users).where(eq(users.id, identity.userId)).limit(1);
          if (row && String(row.role || "").toLowerCase() !== "admin") {
            await db.update(users).set({ role: "admin" }).where(eq(users.id, identity.userId));
          }
        }
        const [profile] = await db
          .select()
          .from(siteProfiles)
          .where(eq(siteProfiles.userId, identity.userId))
          .limit(1);
        if (profile) {
          const current = privilegeFromRecord({ role: profile.role, isTeamOwner: profile.isTeamOwner });
          const rank = (p: string | null) => (p === "admin" ? 2 : p === "dev" ? 1 : 0);
          if (rank(sitePriv) > rank(current)) {
            await db
              .update(siteProfiles)
              .set({
                role: typeof body.siteRole === "string" && body.siteRole ? body.siteRole : profile.role,
                isTeamOwner: body.siteIsTeamOwner === true ? true : profile.isTeamOwner,
                updatedAt: new Date(),
              })
              .where(eq(siteProfiles.userId, identity.userId));
          }
        }
      } catch {
        /* role sync is best-effort */
      }
    }
    const link = body.link;
    const linkProvider = String(link?.provider || "");
    if (link?.profile?.id && isOAuthProvider(linkProvider)) {
      const linked = await ensurePanelIdentity({
        provider: linkProvider,
        currentUserId: identity.userId,
        profile: {
          id: String(link.profile.id),
          name: String(link.profile.name || link.profile.login || link.provider),
          login: String(link.profile.login || link.profile.name || ""),
          email: link.profile.email ? String(link.profile.email) : undefined,
          avatarUrl: link.profile.avatarUrl ? String(link.profile.avatarUrl) : undefined,
        },
      });
      identity.userId = linked.userId;
      identity.discordId = linked.discordId || identity.discordId;
    }
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
