import catalogJson from "./command-catalog.json" with { type: "json" };
import cogsJson from "./command-cogs.json" with { type: "json" };

export type CatalogCommand = {
  id: string;
  name: string;
  description: string;
  source: string;
};

export type CatalogCategory = {
  id: string;
  name: string;
  description: string;
  commands: CatalogCommand[];
};

export type CogMapEntry = {
  category: string;
  source: string;
  file: string | null;
  custom: boolean;
};

export const COMMAND_CATALOG = catalogJson as {
  version: number;
  defaultPrefix: string;
  count: number;
  categories: CatalogCategory[];
};

export const COMMAND_COGS = (cogsJson as { cogs: Record<string, CogMapEntry> }).cogs;

export const OFFICIAL_BOTS = [
  { id: "vax", name: "Vax", role: "Modération", dir: "bots/synkrone/py/Vax", prefix: "!" },
  { id: "arceus", name: "Arceus", role: "Pokémon", dir: "bots/synkrone/py/Arceus", prefix: "'" },
  { id: "asuna", name: "Asuna", role: "Jeux", dir: "bots/synkrone/py/Asuna", prefix: "$" },
  { id: "kayaba", name: "Kayaba", role: "Combat", dir: "bots/synkrone/py/Kayaba", prefix: "." },
  { id: "yui", name: "Yui", role: "Architecture", dir: "bots/synkrone/py/Yui", prefix: "?" },
] as const;

export type OfficialBotId = (typeof OFFICIAL_BOTS)[number]["id"];

export const CUSTOM_CATEGORY_IDS = [
  "moderation",
  "configuration",
  "admin",
  "public",
] as const;

const CATEGORY_INTENTS: Record<string, string[]> = {
  moderation: ["Guilds", "GuildMembers", "GuildMessages", "MessageContent"],
  configuration: ["Guilds", "GuildMembers", "GuildMessages", "MessageContent"],
  admin: ["Guilds", "GuildMembers", "GuildMessages"],
  public: ["Guilds", "GuildMessages"],
  fun: ["Guilds", "GuildMessages", "MessageContent"],
  utilitaires: ["Guilds"],
  casino: ["Guilds", "GuildMessages", "MessageContent"],
  pokemon: ["Guilds", "GuildMessages", "MessageContent"],
  economie: ["Guilds", "GuildMessages"],
  collection: ["Guilds", "GuildMessages"],
  stats: ["Guilds"],
  yui: ["Guilds", "GuildMembers", "GuildMessages"],
  owner: ["Guilds"],
};

export const DISCORD_MODULES = COMMAND_CATALOG.categories.map((cat) => ({
  id: cat.id,
  label: cat.name,
  intents: CATEGORY_INTENTS[cat.id] ?? ["Guilds"],
}));

export const DISCORD_COMMANDS: Record<
  string,
  Array<{ name: string; description: string; permission: string }>
> = Object.fromEntries(
  COMMAND_CATALOG.categories.map((cat) => [
    cat.id,
    cat.commands.map((cmd) => ({
      name: cmd.name,
      description: cmd.description,
      permission: "",
    })),
  ]),
);

export function customCategories() {
  return COMMAND_CATALOG.categories.filter((cat) =>
    (CUSTOM_CATEGORY_IDS as readonly string[]).includes(cat.id),
  );
}

export function customCommandsFor(modules: string[]): CatalogCommand[] {
  return customCategories()
    .filter((cat) => modules.includes(cat.id))
    .flatMap((cat) => cat.commands.filter((cmd) => COMMAND_COGS[cmd.id]?.custom && COMMAND_COGS[cmd.id]?.file));
}

export function isOfficialFlavor(value: string | undefined | null): value is OfficialBotId {
  return OFFICIAL_BOTS.some((b) => b.id === value);
}

export function officialBot(id: string) {
  return OFFICIAL_BOTS.find((b) => b.id === id) ?? null;
}

export function cogForCommand(cmd: { name: string; module?: string; id?: string }) {
  const byId = cmd.id ? COMMAND_COGS[cmd.id] : undefined;
  if (byId?.file) return byId;
  const byName = COMMAND_COGS[cmd.name];
  if (byName?.file) return byName;
  if (cmd.name === "stats" && COMMAND_COGS.botstats?.file) return COMMAND_COGS.botstats;
  if (cmd.module && COMMAND_COGS[cmd.module]?.file) return COMMAND_COGS[cmd.module];
  return byName ?? byId ?? null;
}

export function flavorFromModules(modules: string[]): OfficialBotId | "custom" {
  const official = modules.find((m) => m.startsWith("official:"));
  if (official) {
    const id = official.slice("official:".length);
    if (isOfficialFlavor(id)) return id;
  }
  return "custom";
}
