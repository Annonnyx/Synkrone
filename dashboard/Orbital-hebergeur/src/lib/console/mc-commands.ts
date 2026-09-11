/**
 * Vanilla / Bukkit command names for the in-panel console datalist and Tab.
 * Argument completion would need RCON + Brigadier; we do not fake that.
 */
export const MINECRAFT_CONSOLE_COMMANDS = [
  "advancement",
  "attribute",
  "ban",
  "ban-ip",
  "banlist",
  "bossbar",
  "clear",
  "clone",
  "data",
  "datapack",
  "debug",
  "defaultgamemode",
  "deop",
  "difficulty",
  "effect",
  "enchant",
  "execute",
  "experience",
  "fill",
  "forceload",
  "function",
  "gamemode",
  "gamerule",
  "give",
  "help",
  "item",
  "kick",
  "kill",
  "list",
  "locate",
  "loot",
  "me",
  "msg",
  "op",
  "pardon",
  "pardon-ip",
  "particle",
  "playsound",
  "recipe",
  "reload",
  "save-all",
  "save-off",
  "save-on",
  "say",
  "schedule",
  "scoreboard",
  "seed",
  "setblock",
  "setidletimeout",
  "setworldspawn",
  "spawnpoint",
  "spectate",
  "spreadplayers",
  "stop",
  "stopsound",
  "summon",
  "tag",
  "team",
  "teleport",
  "tell",
  "tellraw",
  "time",
  "title",
  "tp",
  "trigger",
  "weather",
  "whitelist",
  "worldborder",
  "xp",
] as const;

/** Completes the first token only. Returns null when there is nothing honest to offer. */
export function tabCompleteMinecraft(origin: string, cycle: number): string | null {
  const blank = /^(\s*)$/.exec(origin);
  if (blank) {
    const pick = MINECRAFT_CONSOLE_COMMANDS[mod(cycle, MINECRAFT_CONSOLE_COMMANDS.length)];
    return `${blank[1]}${pick}`;
  }
  const match = /^(\s*)(\S+)(\s+.*)?$/.exec(origin);
  if (!match) return null;
  const lead = match[1] ?? "";
  const token = match[2] ?? "";
  const rest = match[3] ?? "";
  if (rest.length > 0) return null;
  const q = token.toLowerCase();
  const matches = MINECRAFT_CONSOLE_COMMANDS.filter((name) => name.startsWith(q));
  if (matches.length === 0) return null;
  return `${lead}${matches[mod(cycle, matches.length)]}`;
}

function mod(n: number, m: number) {
  return ((n % m) + m) % m;
}
