import { readFile } from "node:fs/promises";
import path from "node:path";
import { eq } from "drizzle-orm";
import { db } from "@/db";
import { siteProfiles, users } from "@/db/schema";
import { getOAuthAccount } from "@/lib/oauth/accounts";
import { synkroneRepoRoot } from "@/lib/repo-root";

export type KronesPrivilege = "admin" | "dev" | null;

export const DEV_PLAN = "Synkral";
export const LOW_BALANCE = 300;

function normalizeRole(role: string) {
  return role
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
}

export function privilegeFromRecord(user: { role?: string; isTeamOwner?: boolean } | null | undefined): KronesPrivilege {
  if (!user) return null;
  if (user.isTeamOwner) return "admin";
  const role = normalizeRole(String(user.role || ""));
  if (role === "admin") return "admin";
  if (role === "dev" || role === "equipe" || role === "equipes" || role === "staff") return "dev";
  return null;
}

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

export async function resolveKronesPrivilege(userId: string): Promise<KronesPrivilege> {
  const [row] = await db.select().from(users).where(eq(users.id, userId)).limit(1);
  if (row?.role === "admin") return "admin";
  const [profile] = await db.select().from(siteProfiles).where(eq(siteProfiles.userId, userId)).limit(1);
  if (profile) {
    return privilegeFromRecord({ role: profile.role, isTeamOwner: profile.isTeamOwner });
  }
  const discord = await getOAuthAccount(userId, "discord");
  return privilegeFromRecord(await siteUser(discord?.providerAccountId ?? null));
}

export function applyPrivilegePlan(wallet: { plan: string }, privilege: KronesPrivilege, gradeOrder: string[]) {
  if (privilege !== "dev") return false;
  const current = gradeOrder.indexOf(wallet.plan);
  const mid = gradeOrder.indexOf(DEV_PLAN);
  if (current < mid) {
    wallet.plan = DEV_PLAN;
    return true;
  }
  return false;
}
