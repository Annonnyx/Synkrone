import { readFile } from "node:fs/promises";
import path from "node:path";
import { and, count, eq } from "drizzle-orm";
import { db } from "@/db";
import { ensureAccountSchema } from "@/db/ensure-schema";
import { oauthAccounts, services, siteProfiles, users, wallets } from "@/db/schema";
import { HttpError } from "@/lib/auth";
import { decryptSecret, encryptSecret } from "@/lib/crypto";
import { isUniqueViolation } from "@/lib/db-errors";
import { synkroneRepoRoot } from "@/lib/repo-root";
import {
  discordIdFromIdentityRow,
  discordIdFromPublicId,
  discordIdFromSiteUser,
  isDiscordSnowflake,
  isPanelUserId,
  isPlaceholderEmail,
  pickCanonicalUserId,
  planPanelIdentityLink,
} from "./identity-link";
import { mergePanelUsers } from "./merge-users";
import { getProviderConfig, refreshProviderToken } from "./providers";
import type { OAuthIntent, OAuthProfile, OAuthProvider, OAuthTokens, ProviderStatus } from "./types";
import { OAUTH_PROVIDERS } from "./types";

function placeholderEmail(provider: OAuthProvider, providerUserId: string): string {
  return `${provider}-${providerUserId}@oauth.synkrone.local`;
}

export function oauthPlaceholderEmail(provider: OAuthProvider, providerUserId: string): string {
  return placeholderEmail(provider, providerUserId);
}

export async function discordIdForUser(userId: string): Promise<string | null> {
  try {
    const row = await getOAuthAccount(userId, "discord");
    if (row?.providerAccountId) return row.providerAccountId;
  } catch {
    /* oauth_accounts should already exist */
  }
  try {
    await ensureAccountSchema();
    const [profile] = await db
      .select({ publicId: siteProfiles.publicId })
      .from(siteProfiles)
      .where(eq(siteProfiles.userId, userId))
      .limit(1);
    const snowflake = discordIdFromPublicId(profile?.publicId);
    if (snowflake) {
      await backfillDiscordOAuth(userId, snowflake).catch(() => undefined);
      return snowflake;
    }
  } catch {
    /* site_profiles missing or empty */
  }
  const legacy = await discordIdFromLegacyFiles(userId);
  if (!legacy) return null;
  await rememberDiscordLink(userId, {
    id: legacy,
    name: legacy,
    login: legacy,
    email: null,
    emailVerified: false,
    avatarUrl: null,
  }).catch(() => undefined);
  return legacy;
}

async function discordIdFromLegacyFiles(userId: string): Promise<string | null> {
  const root = synkroneRepoRoot();
  try {
    const map = JSON.parse(
      await readFile(path.join(root, "Synkrone/test/synkrone_authdiscord/data/identity-map.json"), "utf8"),
    ) as {
      byPanelId?: Record<string, { discordId?: string; siteUserId?: string }>;
    };
    const fromMap = discordIdFromIdentityRow(map.byPanelId?.[userId]);
    if (fromMap) return fromMap;
  } catch {
    /* optional file */
  }
  try {
    const raw = JSON.parse(
      await readFile(path.join(root, "Synkrone/test/synkrone_authdiscord/data/users.json"), "utf8"),
    ) as {
      users?: Record<string, { id?: string; dbId?: string; providers?: { discord?: string } }>;
    };
    for (const user of Object.values(raw.users || {})) {
      const found = discordIdFromSiteUser(userId, user);
      if (found) return found;
    }
  } catch {
    /* optional file */
  }
  return null;
}

async function discordIdFromDb(userId: string): Promise<string | null> {
  try {
    const row = await getOAuthAccount(userId, "discord");
    if (row?.providerAccountId && isDiscordSnowflake(row.providerAccountId)) {
      return row.providerAccountId;
    }
  } catch {
    /* oauth_accounts missing */
  }
  try {
    await ensureAccountSchema();
    const [profile] = await db
      .select({ publicId: siteProfiles.publicId })
      .from(siteProfiles)
      .where(eq(siteProfiles.userId, userId))
      .limit(1);
    return discordIdFromPublicId(profile?.publicId);
  } catch {
    return null;
  }
}

async function relatedPanelIdsFromLegacy(snowflake: string): Promise<string[]> {
  const ids: string[] = [];
  const root = synkroneRepoRoot();
  try {
    const map = JSON.parse(
      await readFile(path.join(root, "Synkrone/test/synkrone_authdiscord/data/identity-map.json"), "utf8"),
    ) as {
      byDiscordId?: Record<string, { panelUserId?: string }>;
      bySiteId?: Record<string, { panelUserId?: string }>;
      byPanelId?: Record<string, { discordId?: string; siteUserId?: string }>;
    };
    const row = map.byDiscordId?.[snowflake] || map.bySiteId?.[snowflake];
    if (row?.panelUserId) ids.push(String(row.panelUserId));
    for (const [panelId, entry] of Object.entries(map.byPanelId || {})) {
      if (discordIdFromIdentityRow(entry) === snowflake) ids.push(panelId);
    }
  } catch {
    /* optional file */
  }
  try {
    const raw = JSON.parse(
      await readFile(path.join(root, "Synkrone/test/synkrone_authdiscord/data/users.json"), "utf8"),
    ) as {
      users?: Record<string, { id?: string; dbId?: string; providers?: { discord?: string } }>;
    };
    for (const user of Object.values(raw.users || {})) {
      const snow =
        discordIdFromPublicId(user.id) || discordIdFromPublicId(user.providers?.discord);
      if (snow === snowflake && isPanelUserId(user.dbId)) ids.push(String(user.dbId));
    }
  } catch {
    /* optional file */
  }
  return [...new Set(ids.filter((id) => isPanelUserId(id)))];
}

async function relatedPanelIdsForUser(userId: string, snowflake: string | null): Promise<string[]> {
  const ids: string[] = [];
  const root = synkroneRepoRoot();
  try {
    const map = JSON.parse(
      await readFile(path.join(root, "Synkrone/test/synkrone_authdiscord/data/identity-map.json"), "utf8"),
    ) as {
      byDiscordId?: Record<string, { panelUserId?: string; discordId?: string }>;
      bySiteId?: Record<string, { panelUserId?: string; discordId?: string }>;
      byPanelId?: Record<string, { panelUserId?: string; discordId?: string; siteUserId?: string }>;
    };
    const row = map.byPanelId?.[userId];
    if (row?.panelUserId) ids.push(String(row.panelUserId));
    const snow = snowflake || discordIdFromIdentityRow(row) || discordIdFromPublicId(row?.discordId);
    if (snow) {
      const byDiscord = map.byDiscordId?.[snow] || map.bySiteId?.[snow];
      if (byDiscord?.panelUserId) ids.push(String(byDiscord.panelUserId));
      for (const [panelId, entry] of Object.entries(map.byPanelId || {})) {
        if (discordIdFromIdentityRow(entry) === snow) ids.push(panelId);
      }
    }
  } catch {
    /* optional file */
  }
  return [...new Set(ids.filter((id) => isPanelUserId(id)))];
}

async function healOverlappingUsers(userId: string): Promise<string> {
  const seed = String(userId || "").trim();
  if (!isPanelUserId(seed)) return seed;
  try {
    await ensureAccountSchema();
  } catch {
    return seed;
  }
  const [seedUser] = await db.select().from(users).where(eq(users.id, seed)).limit(1);
  if (!seedUser) return seed;

  const related = new Set<string>([seed]);
  const snowflake = await discordIdFromDb(seed);
  const mapped = await relatedPanelIdsForUser(seed, snowflake);
  const emails = new Set<string>();
  const seedEmail = String(seedUser.email || "").trim().toLowerCase();
  if (seedEmail && !isPlaceholderEmail(seedEmail)) emails.add(seedEmail);
  try {
    const oauthRows = await db.select().from(oauthAccounts).where(eq(oauthAccounts.userId, seed));
    for (const row of oauthRows) {
      const email = String(row.email || "").trim().toLowerCase();
      if (email && !isPlaceholderEmail(email)) emails.add(email);
    }
  } catch {
    /* oauth_accounts missing */
  }

  if (snowflake) {
    try {
      const byOauth = await db
        .select({ userId: oauthAccounts.userId })
        .from(oauthAccounts)
        .where(and(eq(oauthAccounts.provider, "discord"), eq(oauthAccounts.providerAccountId, snowflake)));
      for (const row of byOauth) related.add(row.userId);
    } catch {
      /* */
    }
    try {
      const byPublic = await db
        .select({ userId: siteProfiles.userId })
        .from(siteProfiles)
        .where(eq(siteProfiles.publicId, snowflake));
      for (const row of byPublic) related.add(row.userId);
    } catch {
      /* */
    }
    try {
      const [byPlaceholder] = await db
        .select({ id: users.id })
        .from(users)
        .where(eq(users.email, placeholderEmail("discord", snowflake)))
        .limit(1);
      if (byPlaceholder) related.add(byPlaceholder.id);
    } catch {
      /* */
    }
    for (const id of await relatedPanelIdsFromLegacy(snowflake)) related.add(id);
  }
  for (const id of mapped) related.add(id);

  for (const email of emails) {
    try {
      const matches = await db.select({ id: users.id }).from(users).where(eq(users.email, email));
      for (const row of matches) related.add(row.id);
    } catch {
      /* */
    }
  }

  const candidates: Array<{
    userId: string;
    hasDiscord?: boolean;
    publicIdIsSnowflake?: boolean;
    services?: number;
    wallet?: number;
  }> = [];
  for (const id of related) {
    if (!isPanelUserId(id)) continue;
    const [exists] = await db.select({ id: users.id }).from(users).where(eq(users.id, id)).limit(1);
    if (!exists) continue;
    let publicIdIsSnowflake = false;
    try {
      const [profile] = await db
        .select({ publicId: siteProfiles.publicId })
        .from(siteProfiles)
        .where(eq(siteProfiles.userId, id))
        .limit(1);
      publicIdIsSnowflake = Boolean(discordIdFromPublicId(profile?.publicId));
    } catch {
      /* */
    }
    let serviceCount = 0;
    let wallet = 0;
    try {
      const [svc] = await db.select({ n: count() }).from(services).where(eq(services.ownerId, id));
      serviceCount = Number(svc?.n) || 0;
    } catch {
      /* */
    }
    try {
      const [row] = await db
        .select({ balance: wallets.balance })
        .from(wallets)
        .where(eq(wallets.userId, id))
        .limit(1);
      wallet = Number(row?.balance) || 0;
    } catch {
      /* */
    }
    candidates.push({
      userId: id,
      hasDiscord: Boolean(await discordIdFromDb(id)),
      publicIdIsSnowflake,
      services: serviceCount,
      wallet,
    });
  }

  const canonical = pickCanonicalUserId(candidates, seed);
  if (!canonical) return seed;
  for (const id of related) {
    if (id !== canonical && isPanelUserId(id)) {
      await mergePanelUsers(id, canonical).catch(() => undefined);
    }
  }
  return canonical;
}

export async function ensurePanelIdentity(input: {
  provider: OAuthProvider;
  profile: {
    id: string;
    name?: string;
    login?: string | null;
    email?: string | null;
    avatarUrl?: string | null;
    emailVerified?: boolean;
  };
  currentUserId?: string | null;
}): Promise<{ userId: string; created: boolean; discordId: string | null }> {
  const profile: OAuthProfile = {
    id: String(input.profile.id),
    name: String(input.profile.name || input.profile.login || input.provider),
    login: input.profile.login || input.profile.name || null,
    email: input.profile.email || null,
    emailVerified: Boolean(input.profile.emailVerified),
    avatarUrl: input.profile.avatarUrl || null,
  };
  const [byProvider] = await db
    .select({ userId: oauthAccounts.userId })
    .from(oauthAccounts)
    .where(
      and(eq(oauthAccounts.provider, input.provider), eq(oauthAccounts.providerAccountId, profile.id)),
    )
    .limit(1);
  const currentUserId = isPanelUserId(input.currentUserId) ? String(input.currentUserId).trim() : null;
  const currentDiscord = currentUserId ? await discordIdFromDb(currentUserId) : null;
  const existingDiscord = byProvider?.userId ? await discordIdFromDb(byProvider.userId) : null;
  let plan = planPanelIdentityLink({
    existingOauthUserId: byProvider?.userId,
    currentUserId,
    currentHasDiscord: Boolean(currentDiscord),
    existingHasDiscord: Boolean(existingDiscord),
    differentDiscord: Boolean(currentDiscord && existingDiscord && currentDiscord !== existingDiscord),
  });
  if (plan.action === "link") {
    const [existing] = await db.select({ id: users.id }).from(users).where(eq(users.id, plan.userId)).limit(1);
    if (!existing) plan = { action: "create" };
  }
  if (plan.action === "conflict") {
    throw new HttpError(
      409,
      "This provider account is already linked to another user",
      "OAUTH_LINKED_OTHER",
    );
  }
  if (plan.action === "merge") {
    await mergePanelUsers(plan.fromUserId, plan.userId, { preferFromProviders: [input.provider] });
  }
  const result =
    plan.action === "link" || plan.action === "merge"
      ? await completeOAuthLogin({
          provider: input.provider,
          profile,
          tokens: { accessToken: "" },
          intent: "link",
          currentUserId: plan.userId,
        })
      : await completeOAuthLogin({
          provider: input.provider,
          profile,
          tokens: { accessToken: "" },
          intent: "login",
        });
  const healedId = await healOverlappingUsers(result.userId);
  const discordId =
    input.provider === "discord" && isDiscordSnowflake(profile.id)
      ? profile.id
      : await discordIdForUser(healedId);
  return { ...result, userId: healedId, discordId };
}

export async function userIdForDiscordAccount(discordUserId: string): Promise<string | null> {
  const id = String(discordUserId || "").trim();
  if (!isDiscordSnowflake(id)) return null;
  const [account] = await db
    .select({ userId: oauthAccounts.userId })
    .from(oauthAccounts)
    .where(and(eq(oauthAccounts.provider, "discord"), eq(oauthAccounts.providerAccountId, id)))
    .limit(1);
  if (account) return account.userId;
  const [user] = await db
    .select({ id: users.id })
    .from(users)
    .where(eq(users.email, placeholderEmail("discord", id)))
    .limit(1);
  return user?.id ?? null;
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
  const { provider, profile, tokens, intent } = input;
  const currentUserId = isPanelUserId(input.currentUserId) ? String(input.currentUserId).trim() : null;
  const [byProvider] = await db
    .select()
    .from(oauthAccounts)
    .where(
      and(eq(oauthAccounts.provider, provider), eq(oauthAccounts.providerAccountId, profile.id)),
    )
    .limit(1);

  const currentDiscord = currentUserId ? await discordIdFromDb(currentUserId) : null;
  const existingDiscord = byProvider?.userId ? await discordIdFromDb(byProvider.userId) : null;
  const plan = planPanelIdentityLink({
    existingOauthUserId: byProvider?.userId,
    currentUserId: intent === "link" || currentUserId ? currentUserId : null,
    currentHasDiscord: Boolean(currentDiscord),
    existingHasDiscord: Boolean(existingDiscord),
    differentDiscord: Boolean(currentDiscord && existingDiscord && currentDiscord !== existingDiscord),
  });

  if (plan.action === "conflict") {
    throw new HttpError(
      409,
      "This provider account is already linked to another user",
      "OAUTH_LINKED_OTHER",
    );
  }
  if (plan.action === "link" && !currentUserId && !plan.userId) {
    throw new HttpError(401, "Sign in before linking an account", "OAUTH_LINK_REQUIRED");
  }
  if ((intent === "link" || currentUserId) && !currentUserId && plan.action !== "reuse") {
    throw new HttpError(401, "Sign in before linking an account", "OAUTH_LINK_REQUIRED");
  }

  let userId: string | null = null;
  let created = false;

  if (plan.action === "merge") {
    userId = await mergePanelUsers(plan.fromUserId, plan.userId, { preferFromProviders: [provider] });
  } else if (plan.action === "link") {
    userId = plan.userId;
  } else if (plan.action === "reuse") {
    userId = plan.userId;
  }

  const email = profile.email?.toLowerCase() ?? null;
  if (!userId && email && profile.emailVerified) {
    const [existing] = await db.select().from(users).where(eq(users.email, email)).limit(1);
    if (existing) userId = existing.id;
  }

  if (!userId) {
    try {
      const [row] = await db
        .insert(users)
        .values({
          email: email ?? placeholderEmail(provider, profile.id),
          name: profile.name || profile.login || provider,
          avatarUrl: profile.avatarUrl,
          passwordHash: null,
        })
        .returning({ id: users.id });
      userId = row.id;
      created = true;
    } catch (err) {
      if (!isUniqueViolation(err) || !email) throw err;
      const [existing] = await db.select().from(users).where(eq(users.email, email)).limit(1);
      if (!existing) throw err;
      userId = existing.id;
    }
  }

  await upsertOAuthAccount(userId, provider, profile, tokens);
  await maybeFillProfile(userId, profile);
  const healedId = await healOverlappingUsers(userId);
  return finishOAuthLogin(healedId, created && healedId === userId, provider, profile);
}

async function finishOAuthLogin(
  userId: string,
  created: boolean,
  provider: OAuthProvider,
  profile: OAuthProfile,
) {
  if (provider === "discord" && isDiscordSnowflake(profile.id)) {
    await rememberDiscordLink(userId, profile);
  }
  return { userId, created };
}

async function siteRoleForDiscord(snowflake: string): Promise<{ role: string; isTeamOwner: boolean } | null> {
  try {
    const raw = JSON.parse(
      await readFile(
        path.join(synkroneRepoRoot(), "Synkrone/test/synkrone_authdiscord/data/users.json"),
        "utf8",
      ),
    ) as { users?: Record<string, { role?: string; isTeamOwner?: boolean }> };
    const row = raw.users?.[snowflake];
    if (!row || typeof row !== "object") return null;
    return {
      role: String(row.role || "Krobi"),
      isTeamOwner: Boolean(row.isTeamOwner),
    };
  } catch {
    return null;
  }
}

async function rememberDiscordLink(userId: string, profile: OAuthProfile) {
  const snowflake = discordIdFromPublicId(profile.id);
  if (!snowflake) return;
  try {
    await upsertOAuthAccount(userId, "discord", profile, { accessToken: "" });
  } catch {
    /* unique conflict — still record the site profile when possible */
  }
  try {
    await ensureAccountSchema();
    const [existing] = await db
      .select({ publicId: siteProfiles.publicId })
      .from(siteProfiles)
      .where(eq(siteProfiles.userId, userId))
      .limit(1);
    if (existing) {
      if (existing.publicId === snowflake) return;
      if (isDiscordSnowflake(existing.publicId) && existing.publicId !== snowflake) return;
      await db
        .update(siteProfiles)
        .set({ publicId: snowflake, updatedAt: new Date() })
        .where(eq(siteProfiles.userId, userId));
      return;
    }
    // Seed from the site users.json so a site Admin is not shadowed by a
    // default "Krobi" row (which used to hide unlimited Krônes in the panel).
    const site = await siteRoleForDiscord(snowflake);
    await db
      .insert(siteProfiles)
      .values({
        userId,
        publicId: snowflake,
        role: site?.role ?? "Krobi",
        isTeamOwner: site?.isTeamOwner ?? false,
        profile: {},
      })
      .onConflictDoNothing({ target: siteProfiles.userId });
  } catch {
    /* table missing or public_id taken — Discord oauth is the source of truth */
  }
}

async function backfillDiscordOAuth(userId: string, snowflake: string) {
  const [taken] = await db
    .select({ userId: oauthAccounts.userId })
    .from(oauthAccounts)
    .where(and(eq(oauthAccounts.provider, "discord"), eq(oauthAccounts.providerAccountId, snowflake)))
    .limit(1);
  if (taken && taken.userId !== userId) return;
  const [user] = await db.select().from(users).where(eq(users.id, userId)).limit(1);
  if (!user) return;
  await upsertOAuthAccount(
    userId,
    "discord",
    {
      id: snowflake,
      name: user.name,
      login: user.name,
      email: user.email?.endsWith("@oauth.synkrone.local") ? null : user.email,
      emailVerified: false,
      avatarUrl: user.avatarUrl,
    },
    { accessToken: "" },
  );
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
    accessTokenEnc: tokens.accessToken ? encryptSecret(tokens.accessToken) : existing?.accessTokenEnc ?? null,
    refreshTokenEnc: tokens.refreshToken ? encryptSecret(tokens.refreshToken) : existing?.refreshTokenEnc ?? null,
    expiresAt: expiresAtFrom(tokens),
    scope: tokens.scope ?? existing?.scope ?? null,
    updatedAt: new Date(),
  };
  if (existing) {
    await db.update(oauthAccounts).set(values).where(eq(oauthAccounts.id, existing.id));
    return;
  }
  try {
    await db.insert(oauthAccounts).values({
      userId,
      provider,
      ...values,
    });
  } catch (err) {
    if (!isUniqueViolation(err)) throw err;
    const [taken] = await db
      .select({ id: oauthAccounts.id, userId: oauthAccounts.userId })
      .from(oauthAccounts)
      .where(and(eq(oauthAccounts.provider, provider), eq(oauthAccounts.providerAccountId, profile.id)))
      .limit(1);
    if (taken?.userId && taken.userId !== userId) {
      const kept = await mergePanelUsers(taken.userId, userId, { preferFromProviders: [provider] });
      if (kept !== userId) return;
      const [again] = await db
        .select()
        .from(oauthAccounts)
        .where(and(eq(oauthAccounts.userId, kept), eq(oauthAccounts.provider, provider)))
        .limit(1);
      if (again) {
        await db.update(oauthAccounts).set(values).where(eq(oauthAccounts.id, again.id));
        return;
      }
    }
    const [sameUser] = await db
      .select()
      .from(oauthAccounts)
      .where(and(eq(oauthAccounts.userId, userId), eq(oauthAccounts.provider, provider)))
      .limit(1);
    if (sameUser) {
      await db.update(oauthAccounts).set(values).where(eq(oauthAccounts.id, sameUser.id));
    }
  }
}

async function maybeFillProfile(userId: string, profile: OAuthProfile) {
  const [row] = await db.select().from(users).where(eq(users.id, userId)).limit(1);
  if (!row) return;
  const patch: Partial<typeof users.$inferInsert> = {};
  if (!row.avatarUrl && profile.avatarUrl) patch.avatarUrl = profile.avatarUrl;
  if (row.name.startsWith("user") && profile.name) patch.name = profile.name;
  const incomingEmail = String(profile.email || "").trim().toLowerCase();
  if (isPlaceholderEmail(row.email) && incomingEmail && !isPlaceholderEmail(incomingEmail)) {
    patch.email = incomingEmail;
  }
  if (!Object.keys(patch).length) return;
  try {
    await db.update(users).set(patch).where(eq(users.id, userId));
  } catch (err) {
    if (!isUniqueViolation(err)) throw err;
    delete patch.email;
    if (Object.keys(patch).length) {
      await db.update(users).set(patch).where(eq(users.id, userId));
    }
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
