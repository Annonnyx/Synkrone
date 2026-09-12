import { cookies, headers } from "next/headers";
import { and, eq, gt } from "drizzle-orm";
import { db } from "@/db";
import { isDatabaseUnavailable } from "@/lib/db-errors";
import { apiKeys, sessions, users } from "@/db/schema";
import { hashPassword, randomToken, sha256, verifyPassword } from "@/lib/crypto";
import { SFTPManager } from "@/lib/sftp/manager";

export const SESSION_COOKIE = "synkrone_session";
const LEGACY_SESSION_COOKIE = "orbital_session";
const SESSION_TTL_MS = 1000 * 60 * 60 * 24 * 21;

export type SessionUser = {
  id: string;
  email: string;
  name: string;
  role: string;
  avatarUrl: string | null;
};

export async function issueSessionToken(
  userId: string,
  meta?: { ip?: string | null; userAgent?: string | null },
): Promise<string> {
  const token = randomToken(32);
  await db.insert(sessions).values({
    userId,
    tokenHash: sha256(token),
    ip: meta?.ip ?? null,
    userAgent: meta?.userAgent ?? null,
    expiresAt: new Date(Date.now() + SESSION_TTL_MS),
  });
  return token;
}

export async function createSession(userId: string): Promise<string> {
  const hdrs = await headers();
  const token = await issueSessionToken(userId, {
    ip: hdrs.get("x-forwarded-for"),
    userAgent: hdrs.get("user-agent"),
  });
  const store = await cookies();
  store.set(SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: SESSION_TTL_MS / 1000,
  });
  return token;
}

export async function destroySession(): Promise<void> {
  const store = await cookies();
  const token = store.get(SESSION_COOKIE)?.value ?? store.get(LEGACY_SESSION_COOKIE)?.value;
  if (token) {
    await db.delete(sessions).where(eq(sessions.tokenHash, sha256(token)));
  }
  store.delete(SESSION_COOKIE);
  store.delete(LEGACY_SESSION_COOKIE);
}

export async function getCurrentUser(): Promise<SessionUser | null> {
  try {
    const store = await cookies();
    const token = store.get(SESSION_COOKIE)?.value ?? store.get(LEGACY_SESSION_COOKIE)?.value;
    if (token) {
      const rows = await db
        .select({
          id: users.id,
          email: users.email,
          name: users.name,
          role: users.role,
          avatarUrl: users.avatarUrl,
        })
        .from(sessions)
        .innerJoin(users, eq(users.id, sessions.userId))
        .where(
          and(eq(sessions.tokenHash, sha256(token)), gt(sessions.expiresAt, new Date())),
        )
        .limit(1);
      if (rows.length) return rows[0];
    }

    // API key authentication (Authorization: Bearer orb_xxx)
    const hdrs = await headers();
    const auth = hdrs.get("authorization");
    if (auth?.startsWith("Bearer ")) {
      const key = auth.slice(7).trim();
      const rows = await db
        .select({
          id: users.id,
          email: users.email,
          name: users.name,
          role: users.role,
          avatarUrl: users.avatarUrl,
          keyId: apiKeys.id,
          revokedAt: apiKeys.revokedAt,
        })
        .from(apiKeys)
        .innerJoin(users, eq(users.id, apiKeys.userId))
        .where(eq(apiKeys.keyHash, sha256(key)))
        .limit(1);
      if (rows.length && !rows[0].revokedAt) {
        await db
          .update(apiKeys)
          .set({ lastUsedAt: new Date() })
          .where(eq(apiKeys.id, rows[0].keyId));
        const { id, email, name, role, avatarUrl } = rows[0];
        return { id, email, name, role, avatarUrl };
      }
    }
    return null;
  } catch (err) {
    if (isDatabaseUnavailable(err)) {
      console.error("[auth] session lookup skipped: database unreachable");
      return null;
    }
    throw err;
  }
}

export class HttpError extends Error {
  status: number;
  code?: string;
  constructor(status: number, message: string, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export async function requireUser(): Promise<SessionUser> {
  const user = await getCurrentUser();
  if (!user) throw new HttpError(401, "Authentication required");
  return user;
}

export async function registerUser(email: string, name: string, password: string) {
  const existing = await db
    .select({ id: users.id })
    .from(users)
    .where(eq(users.email, email.toLowerCase()))
    .limit(1);
  if (existing.length) throw new HttpError(409, "An account already uses this email");
  if (password.length < 8)
    throw new HttpError(400, "Password must be at least 8 characters");
  const [row] = await db
    .insert(users)
    .values({
      email: email.toLowerCase(),
      name,
      passwordHash: hashPassword(password),
    })
    .returning({ id: users.id });
  await syncSftpPassword(row.id, password);
  return row.id;
}

export async function loginUser(email: string, password: string) {
  const rows = await db
    .select()
    .from(users)
    .where(eq(users.email, email.toLowerCase()))
    .limit(1);
  if (!rows.length || !verifyPassword(password, rows[0].passwordHash))
    throw new HttpError(401, "Invalid email or password");
  await syncSftpPassword(rows[0].id, password);
  return rows[0].id;
}

export async function changePassword(
  userId: string,
  currentPassword: string | undefined,
  newPassword: string,
) {
  if (newPassword.length < 8)
    throw new HttpError(400, "Password must be at least 8 characters");
  const [row] = await db.select().from(users).where(eq(users.id, userId)).limit(1);
  if (!row) throw new HttpError(404, "User not found");
  if (row.passwordHash) {
    if (!currentPassword || !verifyPassword(currentPassword, row.passwordHash)) {
      throw new HttpError(401, "Current password is incorrect");
    }
  }
  await db
    .update(users)
    .set({ passwordHash: hashPassword(newPassword) })
    .where(eq(users.id, userId));
  await syncSftpPassword(userId, newPassword);
}

async function syncSftpPassword(userId: string, password: string): Promise<void> {
  try {
    await SFTPManager.applyOwnerPassword(userId, password);
  } catch (err) {
    console.error("[sftp] failed to sync gateway password", err);
  }
}
