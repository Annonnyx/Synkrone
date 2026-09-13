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

export function privilegeFromRecord(
  user: { role?: string; isTeamOwner?: boolean } | null | undefined,
): KronesPrivilege {
  if (!user) return null;
  if (user.isTeamOwner) return "admin";
  const role = normalizeRole(String(user.role || ""));
  if (role === "admin") return "admin";
  if (role === "dev" || role === "equipe" || role === "equipes" || role === "staff") return "dev";
  return null;
}

export function applyPrivilegePlan(
  wallet: { plan: string },
  privilege: KronesPrivilege,
  gradeOrder: string[],
) {
  if (privilege !== "dev") return false;
  const current = gradeOrder.indexOf(wallet.plan);
  const mid = gradeOrder.indexOf(DEV_PLAN);
  if (current < mid) {
    wallet.plan = DEV_PLAN;
    return true;
  }
  return false;
}
