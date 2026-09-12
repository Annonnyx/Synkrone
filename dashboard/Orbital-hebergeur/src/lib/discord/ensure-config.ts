import { COMMAND_COGS, DISCORD_COMMANDS } from "@/lib/discord/catalog";

export const CONFIG_COMMAND = "config";

export const CONFIG_COG_FILE =
  COMMAND_COGS.config?.file ?? "cogs/ADMIN/configuration/confighub/config.py";

export const CONFIG_COG_MODULE = CONFIG_COG_FILE.replace(/\.py$/i, "")
  .replaceAll("\\", "/")
  .replaceAll("/", ".");

const CONFIG_COMMAND_META = DISCORD_COMMANDS.configuration?.find((c) => c.name === CONFIG_COMMAND);

export function hasConfigHybridCommand(source: string): boolean {
  return /@commands\.hybrid_command\(\s*name=["']config["']/.test(String(source ?? ""));
}

export function withConfigCogEnabled(enabled: string[]): string[] {
  const next: string[] = [];
  const seen = new Set<string>();
  for (const item of enabled) {
    const name = String(item ?? "")
      .replaceAll("\\", "/")
      .replace(/\.py$/i, "")
      .replaceAll("/", ".")
      .trim();
    if (!name || seen.has(name)) continue;
    seen.add(name);
    next.push(name);
  }
  if (!seen.has(CONFIG_COG_MODULE)) next.push(CONFIG_COG_MODULE);
  return next;
}

export function withRequiredConfigCommand<T extends { name: string; enabled?: boolean }>(
  commands: T[],
): T[] {
  const next = commands.map((c) =>
    c.name === CONFIG_COMMAND ? ({ ...c, enabled: true } as T) : c,
  );
  if (next.some((c) => c.name === CONFIG_COMMAND)) return next;
  const added = {
    name: CONFIG_COMMAND,
    module: "configuration",
    enabled: true as const,
    description: CONFIG_COMMAND_META?.description ?? "Hub de configuration du serveur",
    permission: CONFIG_COMMAND_META?.permission ?? "",
    cooldown: 3,
    logging: false,
  };
  return [...next, added as unknown as T];
}
