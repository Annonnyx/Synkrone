import {
  DISCORD_COMMANDS,
  DISCORD_MODULES,
} from "@/lib/discord/catalog";

export { DISCORD_COMMANDS, DISCORD_MODULES };

/**
 * Discord gateway intent catalogue. Safe to import from client components.
 *
 * Privileged intents (GuildMembers, MessageContent, GuildPresences) must be
 * enabled in the Discord developer portal for the application. The panel only
 * requests them when the user explicitly checks them — never as a side effect
 * of enabling a module.
 */

export const GATEWAY_INTENTS: ReadonlyArray<{
  id: string;
  bit: number;
  privileged?: boolean;
  portal?: string;
}> = [
  { id: "Guilds", bit: 1 << 0 },
  { id: "GuildMembers", bit: 1 << 1, privileged: true, portal: "Server Members Intent" },
  { id: "GuildMessages", bit: 1 << 9 },
  { id: "MessageContent", bit: 1 << 15, privileged: true, portal: "Message Content Intent" },
  { id: "GuildPresences", bit: 1 << 8, privileged: true, portal: "Presence Intent" },
  { id: "GuildMessageReactions", bit: 1 << 10 },
  { id: "GuildVoiceStates", bit: 1 << 7 },
];

export type GatewayIntentId = (typeof GATEWAY_INTENTS)[number]["id"];

export const PRIVILEGED_INTENT_IDS = GATEWAY_INTENTS.filter((i) => i.privileged).map((i) => i.id);

export const DISALLOWED_INTENTS_FATAL =
  "Used disallowed intents. Enable Server Members Intent and Message Content Intent in the Discord developer portal (Application → Bot), or uncheck GuildMembers, MessageContent and GuildPresences in the panel.";

export const DISCORD_DEV_PORTAL = "https://discord.com/developers/applications";

export function discordBotPortalUrl(applicationId?: string | null): string {
  if (applicationId) return `${DISCORD_DEV_PORTAL}/${applicationId}/bot`;
  return DISCORD_DEV_PORTAL;
}

const KNOWN_INTENTS = new Set<string>(GATEWAY_INTENTS.map((i) => i.id));
const PRIVILEGED = new Set<string>(PRIVILEGED_INTENT_IDS);

export function isPrivilegedIntent(id: string): boolean {
  return PRIVILEGED.has(id);
}

function uniqueKnown(ids: string[]): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const id of ids) {
    if (!KNOWN_INTENTS.has(id) || seen.has(id)) continue;
    seen.add(id);
    out.push(id);
  }
  return out;
}

/** Safe (non-privileged) intents implied by the selected modules. */
export function intentsForModules(modules: string[]): string[] {
  const set = new Set<string>(["Guilds"]);
  for (const m of DISCORD_MODULES) {
    if (!modules.includes(m.id)) continue;
    for (const intent of m.intents) {
      if (!isPrivilegedIntent(intent)) set.add(intent);
    }
  }
  return [...set];
}

/** Privileged intents a module would like — shown as a hint, never auto-enabled. */
export function suggestedPrivilegedIntents(modules: string[]): string[] {
  const set = new Set<string>();
  for (const m of DISCORD_MODULES) {
    if (!modules.includes(m.id)) continue;
    for (const intent of m.intents) {
      if (isPrivilegedIntent(intent)) set.add(intent);
    }
  }
  return [...set];
}

/**
 * Merge user-selected intents with module defaults.
 * Privileged intents are kept only when they appear in `requested`.
 */
export function resolveGatewayIntents(
  requested: string[] | undefined | null,
  modules: string[],
): string[] {
  const picked = uniqueKnown(requested ?? []);
  const safePicked = picked.filter((id) => !isPrivilegedIntent(id));
  const privileged = picked.filter(isPrivilegedIntent);
  const base = safePicked.length > 0 ? safePicked : intentsForModules(modules);
  return uniqueKnown([...base, ...privileged]);
}

/** Keep previously checked privileged intents when modules (and their safe intents) change. */
export function mergeIntentsForModules(current: string[], modules: string[]): string[] {
  return resolveGatewayIntents(
    current.filter(isPrivilegedIntent),
    modules,
  );
}

export function intentsBitfield(intents: string[]): number {
  return GATEWAY_INTENTS.filter((i) => intents.includes(i.id)).reduce((acc, i) => acc | i.bit, 0);
}
