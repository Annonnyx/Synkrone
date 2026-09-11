import { and, eq } from "drizzle-orm";
import { db } from "@/db";
import { oauthAccounts, users } from "@/db/schema";
import { HttpError } from "@/lib/auth";
import { decryptSecret, encryptSecret } from "@/lib/crypto";
import { getProviderConfig, refreshProviderToken } from "./providers";
import type { OAuthIntent, OAuthProfile, OAuthProvider, OAuthTokens, ProviderStatus } from "./types";
import { OAUTH_PROVIDERS } from "./types";

function placeholderEmail(provider: OAuthProvider, providerUserId: string): string {
  return `${provider}-${providerUserId}@oauth.synkrone.local`;
}

function expiresAtFrom(tokens: OAuthTokens): Date | null {
  if (!tokens.expiresIn || tokens.expiresIn <= 0) return null;
  return new Date(Date.now() + tokens.expiresIn * 1000);
}

export async function listProviderStatus(userId?: string | null): Promise<ProviderStatus[]> {
  const linked = userId
    ? await db.select().from(oauthAccounts).where(eq(oauthAccounts.userId, userId))
    : [];
  return OAUTH_PROVIDERS.map((id) => {
    const row = linked.find((r) => r.provider === id);
    return {
      id,
      configured: Boolean(getProviderConfig(id)),
      linked: Boolean(row),
      login: row?.providerLogin ?? null,
      email: row?.email ?? null,
    };
  });
}

export async function getOAuthAccount(userId: string, provider: OAuthProvider) {
  const [row] = await db
    .select()
    .from(oauthAccounts)
    .where(and(eq(oauthAccounts.userId, userId), eq(oauthAccounts.provider, provider)))
    .limit(1);
  return row ?? null;
}

export async function completeOAuthLogin(input: {
  provider: OAuthProvider;
  profile: OAuthProfile;
  tokens: OAuthTokens;
  intent: OAuthIntent;
  currentUserId?: string | null;
}): Promise<{ userId: string; created: boolean }> {
  const { provider, profile, tokens, intent, currentUserId } = input;
  const [byProvider] = await db
    .select()
    .from(oauthAccounts)
    .where(
      and(eq(oauthAccounts.provider, provider), eq(oauthAccounts.providerAccountId, profile.id)),
    )
    .limit(1);

  if (intent === "link" || currentUserId) {
    if (!currentUserId) throw new HttpError(401, "Sign in before linking an account", "OAUTH_LINK_REQUIRED");
    if (byProvider && byProvider.userId !== currentUserId) {
      throw new HttpError(
        409,
        "This provider account is already linked to another user",
        "OAUTH_LINKED_OTHER",
      );
    }
    await upsertOAuthAccount(currentUserId, provider, profile, tokens);
    await maybeFillProfile(currentUserId, profile);
    return { userId: currentUserId, created: false };
  }

  if (byProvider) {
    await upsertOAuthAccount(byProvider.userId, provider, profile, tokens);
    await maybeFillProfile(byProvider.userId, profile);
    return { userId: byProvider.userId, created: false };
  }

  const email = profile.email?.toLowerCase() ?? null;
  if (email && profile.emailVerified) {
    const [existing] = await db.select().from(users).where(eq(users.email, email)).limit(1);
    if (existing) {
      await upsertOAuthAccount(existing.id, provider, profile, tokens);
      await maybeFillProfile(existing.id, profile);
      return { userId: existing.id, created: false };
    }
  }

  const [created] = await db
    .insert(users)
    .values({
      email: email ?? placeholderEmail(provider, profile.id),
      name: profile.name || profile.login || provider,
      avatarUrl: profile.avatarUrl,
      passwordHash: null,
    })
    .returning({ id: users.id });
  await upsertOAuthAccount(created.id, provider, profile, tokens);
  return { userId: created.id, created: true };
}

async function upsertOAuthAccount(
  userId: string,
  provider: OAuthProvider,
  profile: OAuthProfile,
  tokens: OAuthTokens,
) {
  const [existing] = await db
    .select()
    .from(oauthAccounts)
    .where(and(eq(oauthAccounts.userId, userId), eq(oauthAccounts.provider, provider)))
    .limit(1);
  const values = {
    providerAccountId: profile.id,
    providerLogin: profile.login,
    email: profile.email,
    avatarUrl: profile.avatarUrl,
    accessTokenEnc: encryptSecret(tokens.accessToken),
    refreshTokenEnc: tokens.refreshToken ? encryptSecret(tokens.refreshToken) : existing?.refreshTokenEnc ?? null,
    expiresAt: expiresAtFrom(tokens),
    scope: tokens.scope ?? existing?.scope ?? null,
    updatedAt: new Date(),
  };
  if (existing) {
    await db.update(oauthAccounts).set(values).where(eq(oauthAccounts.id, existing.id));
    return;
  }
  await db.insert(oauthAccounts).values({
    userId,
    provider,
    ...values,
  });
}

async function maybeFillProfile(userId: string, profile: OAuthProfile) {
  const [row] = await db.select().from(users).where(eq(users.id, userId)).limit(1);
  if (!row) return;
  const patch: Partial<typeof users.$inferInsert> = {};
  if (!row.avatarUrl && profile.avatarUrl) patch.avatarUrl = profile.avatarUrl;
  if (row.name.startsWith("user") && profile.name) patch.name = profile.name;
  if (Object.keys(patch).length) {
    await db.update(users).set(patch).where(eq(users.id, userId));
  }
}

export async function unlinkOAuthAccount(userId: string, provider: OAuthProvider) {
  const [user] = await db.select().from(users).where(eq(users.id, userId)).limit(1);
  const linked = await db.select().from(oauthAccounts).where(eq(oauthAccounts.userId, userId));
  if (!user?.passwordHash && linked.length <= 1 && linked[0]?.provider === provider) {
    throw new HttpError(
      400,
      "Set a password before unlinking your last sign-in method",
      "OAUTH_LAST_METHOD",
    );
  }
  await db
    .delete(oauthAccounts)
    .where(and(eq(oauthAccounts.userId, userId), eq(oauthAccounts.provider, provider)));
}

export async function getValidAccessToken(userId: string, provider: OAuthProvider): Promise<string> {
  const row = await getOAuthAccount(userId, provider);
  if (!row?.accessTokenEnc) {
    throw new HttpError(403, "This account is not linked", "OAUTH_NOT_LINKED");
  }
  const current = decryptSecret(row.accessTokenEnc);
  if (!current) throw new HttpError(403, "Stored token could not be decrypted", "OAUTH_TOKEN_INVALID");

  const expiring = row.expiresAt && row.expiresAt.getTime() < Date.now() + 60_000;
  if (!expiring) return current;

  const refresh = row.refreshTokenEnc ? decryptSecret(row.refreshTokenEnc) : null;
  const config = getProviderConfig(provider);
  if (!refresh || !config) {
    if (row.expiresAt && row.expiresAt.getTime() < Date.now()) {
      throw new HttpError(401, "Provider token expired — link the account again", "OAUTH_TOKEN_EXPIRED");
    }
    return current;
  }
  try {
    const tokens = await refreshProviderToken({ provider, config, refreshToken: refresh });
    await db
      .update(oauthAccounts)
      .set({
        accessTokenEnc: encryptSecret(tokens.accessToken),
        refreshTokenEnc: tokens.refreshToken ? encryptSecret(tokens.refreshToken) : row.refreshTokenEnc,
        expiresAt: expiresAtFrom(tokens),
        scope: tokens.scope ?? row.scope,
        updatedAt: new Date(),
      })
      .where(eq(oauthAccounts.id, row.id));
    return tokens.accessToken;
  } catch {
    if (row.expiresAt && row.expiresAt.getTime() < Date.now()) {
      throw new HttpError(401, "Provider token expired — link the account again", "OAUTH_TOKEN_EXPIRED");
    }
    return current;
  }
}
