import { NextRequest } from "next/server";
import { eq } from "drizzle-orm";
import { db } from "@/db";
import { users } from "@/db/schema";
import { discordIdForUser } from "@/lib/oauth/accounts";
import { body, fail, ok, rateLimit, route } from "@/lib/api";
import { audit } from "@/lib/audit";
import {
  changePassword,
  destroySession,
  getCurrentUser,
  requireUser,
} from "@/lib/auth";

export const runtime = "nodejs";

export async function POST(
  req: NextRequest,
  ctx: { params: Promise<{ action: string }> },
) {
  const { action } = await ctx.params;
  return route(async () => {
    if (action === "register" || action === "login") {
      return fail("Use Discord, Google or GitHub to sign in", 404);
    }
    if (action === "logout") {
      const user = await getCurrentUser();
      await destroySession();
      await audit({ userId: user?.id, action: "auth.logout" });
      return ok({ ok: true });
    }
    if (action === "password") {
      const user = await requireUser();
      rateLimit(`password:${user.id}`, 8);
      const { currentPassword, newPassword } = await body<{
        currentPassword?: string;
        newPassword: string;
      }>(req);
      if (!newPassword) return fail("newPassword is required");
      await changePassword(user.id, currentPassword, newPassword);
      await audit({ userId: user.id, action: "auth.password_change" });
      return ok({ ok: true });
    }
    return fail("Unknown auth action", 404);
  });
}

export async function GET(_req: NextRequest, ctx: { params: Promise<{ action: string }> }) {
  const { action } = await ctx.params;
  return route(async () => {
    if (action === "me") {
      const user = await getCurrentUser();
      if (!user) return ok({ user: null });
      const [row] = await db
        .select({ passwordHash: users.passwordHash })
        .from(users)
        .where(eq(users.id, user.id))
        .limit(1);
      const discordId = await discordIdForUser(user.id);
      return ok({ user: { ...user, hasPassword: Boolean(row?.passwordHash), discordId } });
    }
    return fail("Unknown auth action", 404);
  });
}
