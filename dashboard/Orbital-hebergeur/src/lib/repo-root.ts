import { existsSync } from "node:fs";
import path from "node:path";

function looksLikeRepo(dir: string) {
  return (
    existsSync(path.join(dir, "bots/synkrone/py")) ||
    existsSync(path.join(dir, "templates/discord/main.py"))
  );
}

export function synkroneRepoRoot(): string {
  const fromEnv = process.env.SYNKRONE_REPO_ROOT?.trim();
  if (fromEnv) return path.resolve(fromEnv);
  let dir = process.cwd();
  for (let i = 0; i < 10; i++) {
    if (looksLikeRepo(dir)) return dir;
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  return path.resolve(process.cwd(), "../..");
}
