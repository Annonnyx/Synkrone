import { readFile } from "node:fs/promises";
import path from "node:path";
import { eq } from "drizzle-orm";
import { db } from "@/db";
import { ensureAccountSchema } from "@/db/ensure-schema";
import { siteProfiles, users } from "@/db/schema";
import { discordIdForUser } from "@/lib/oauth/accounts";
import { synkroneRepoRoot } from "@/lib/repo-root";
import {
  privilegeFromRecord,
  type KronesPrivilege,
} from "./roles";

export {
  applyPrivilegePlan,
  DEV_PLAN,
  LOW_BALANCE,
  privilegeFromRecord,
  type KronesPrivilege,
} from "./roles";

async function siteUser(discordId: string | null) {
  if (!discordId) return null;
  try {
    const file = path.join(
      synkroneRepoRoot(),
      "Synkrone/test/synkrone_authdiscord/data/users.json",
    );
    const raw = JSON.parse(await readFile(file, "utf8")) as {
      users?: Record<string, { role?: string; isTeamOwner?: boolean }>;
    };
    const row = raw.users?.[discordId];
    return row && typeof row === "object" ? row : null;
  } catch {
    return null;
  }
}

async function siteProfileForUser(userId: string) {
  try {
    await ensureAccountSchema();
    const [profile] = await db.select().from(siteProfiles).where(eq(siteProfiles.userId, userId)).limit(1);
    return profile ?? null;
  } catch {
    return null;
  }
}

export async function resolveKronesPrivilege(userId: string): Promise<KronesPrivilege> {
  try {
    const [row] = await db.select().from(users).where(eq(users.id, userId)).limit(1);
    if (row?.role === "admin") return "admin";
  } catch {
    /* users lookup is best-effort */
  }
  const profile = await siteProfileForUser(userId);
  if (profile) {
    return privilegeFromRecord({ role: profile.role, isTeamOwner: profile.isTeamOwner });
  }
  let discord: string | null = null;
  try {
    discord = await discordIdForUser(userId);
  } catch {
    discord = null;
  }
  return privilegeFromRecord(await siteUser(discord));
}
