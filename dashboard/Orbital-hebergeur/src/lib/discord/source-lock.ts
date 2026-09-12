const GRADE_ORDER = ["Aucun", "Kronium", "Synkral", "Kronalloy", "Synkronite", "Kronix"];
const SOURCE_GRADE = "Kronalloy";

export function isProtectedBotSource(relPath: string): boolean {
  const n = String(relPath || "")
    .replaceAll("\\", "/")
    .replace(/^\/+/, "")
    .toLowerCase();
  if (!n || n === ".") return false;
  if (n === "cogs" || n.startsWith("cogs/")) return true;
  if (n === "synkrone_slash.py") return true;
  if (n === "synkrone_custom.py") return true;
  return false;
}

export function isVolumeRoot(relPath: string): boolean {
  const n = String(relPath || "")
    .replaceAll("\\", "/")
    .replace(/^\/+/, "");
  return n === "" || n === ".";
}

export function canEditCommandSources(input: {
  plan?: string | null;
  privilege?: "admin" | "dev" | null;
  unlimited?: boolean;
}): boolean {
  if (input.unlimited) return true;
  if (input.privilege === "admin" || input.privilege === "dev") return true;
  const plan = String(input.plan || "Aucun");
  return GRADE_ORDER.indexOf(plan) >= GRADE_ORDER.indexOf(SOURCE_GRADE);
}
