import { NextRequest } from "next/server";
import { eq } from "drizzle-orm";
import { db } from "@/db";
import { users } from "@/db/schema";
import { discordIdForUser } from "@/lib/oauth/accounts";
import { body, fail, ok, rateLimit, route } from "@/lib/api";
import { audit } from "@/lib/audit";
import {
  changePassword,
  createSession,
  destroySession,
  getCurrentUser,
  loginUser,
  registerUser,
  requireUser,
} from "@/lib/auth";

export const runtime = "nodejs";

export async function POST(
  req: NextRequest,
  ctx: { params: Promise<{ action: string }> },
) {
  const { action } = await ctx.params;
  return route(async () => {
    const ip = req.headers.get("x-forwarded-for") ?? "local";
    if (action === "register") {
      rateLimit(`register:${ip}`, 10);
      const { email, name, password } = await body<{
        email: string;
        name: string;
        password: string;
      }>(req);
      if (!email || !name || !password) return fail("email, name and password are required");
      const userId = await registerUser(email, name, password);
      await createSession(userId);
      await audit({ userId, action: "auth.register" });
      return ok({ ok: true });
    }
    if (action === "login") {
      rateLimit(`login:${ip}`, 15);
      const { email, password } = await body<{ email: string; password: string }>(req);
      const userId = await loginUser(email ?? "", password ?? "");
      await createSession(userId);
      await audit({ userId, action: "auth.login" });
      return ok({ ok: true });
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
