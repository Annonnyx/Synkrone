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

function rankPrivilege(privilege: KronesPrivilege): number {
  if (privilege === "admin") return 2;
  if (privilege === "dev") return 1;
  return 0;
}

function bestPrivilege(privileges: Array<KronesPrivilege>): KronesPrivilege {
  let best: KronesPrivilege = null;
  for (const privilege of privileges) {
    if (rankPrivilege(privilege) > rankPrivilege(best)) best = privilege;
  }
  return best;
}

async function healPrivilege(
  userId: string,
  site: { role?: string; isTeamOwner?: boolean } | null,
  combined: KronesPrivilege,
  panelPriv: KronesPrivilege,
  profilePriv: KronesPrivilege,
) {
  if (!site || !combined) return;
  // The site users.json is the source of truth for staff roles: if it grants
  // more than the panel DB, push it back so every later lookup agrees.
  if (rankPrivilege(combined) <= Math.max(rankPrivilege(panelPriv), rankPrivilege(profilePriv))) return;
  try {
    if (combined === "admin") {
      const [row] = await db.select().from(users).where(eq(users.id, userId)).limit(1);
      if (row && String(row.role || "").toLowerCase() !== "admin") {
        await db.update(users).set({ role: "admin" }).where(eq(users.id, userId));
      }
    }
  } catch {
    /* users promotion is best-effort */
  }
  try {
    const [profile] = await db
      .select()
      .from(siteProfiles)
      .where(eq(siteProfiles.userId, userId))
      .limit(1);
    if (profile && rankPrivilege(privilegeFromRecord({ role: profile.role, isTeamOwner: profile.isTeamOwner })) < rankPrivilege(combined)) {
      await db
        .update(siteProfiles)
        .set({
          role: String(site.role || profile.role || "Admin"),
          isTeamOwner: Boolean(site.isTeamOwner ?? profile.isTeamOwner ?? combined === "admin"),
          updatedAt: new Date(),
        })
        .where(eq(siteProfiles.userId, userId));
    }
  } catch {
    /* site_profiles healing is best-effort */
  }
}

export async function resolveKronesPrivilege(userId: string): Promise<KronesPrivilege> {
  let panelPriv: KronesPrivilege = null;
  try {
    const [row] = await db.select().from(users).where(eq(users.id, userId)).limit(1);
    // Case-insensitive on purpose: the site stores "Admin", the panel "admin".
    panelPriv = privilegeFromRecord({ role: row?.role });
    if (panelPriv === "admin") return "admin";
  } catch {
    /* users lookup is best-effort */
  }
  const profile = await siteProfileForUser(userId);
  const profilePriv = privilegeFromRecord(
    profile ? { role: profile.role, isTeamOwner: profile.isTeamOwner } : null,
  );
  if (profilePriv === "admin" && panelPriv === "admin") return "admin";

  let discord: string | null = null;
  try {
    discord = await discordIdForUser(userId);
  } catch {
    discord = null;
  }
  // The site users.json is keyed by Discord snowflake: check every known id
  // for this panel user instead of stopping at the (possibly stale) local profile.
  const candidates = [discord, profile?.publicId ?? null].filter(
    (id): id is string => Boolean(id),
  );
  let site: { role?: string; isTeamOwner?: boolean } | null = null;
  let sitePriv: KronesPrivilege = null;
  for (const candidate of [...new Set(candidates)]) {
    const row = await siteUser(candidate);
    if (!row) continue;
    const priv = privilegeFromRecord(row);
    if (rankPrivilege(priv) > rankPrivilege(sitePriv)) {
      sitePriv = priv;
      site = row;
    }
    if (sitePriv === "admin") break;
  }

  const combined = bestPrivilege([panelPriv, profilePriv, sitePriv]);
  if (site && combined && rankPrivilege(combined) > rankPrivilege(profilePriv)) {
    await healPrivilege(userId, site, combined, panelPriv, profilePriv);
  }
  return combined;
}
