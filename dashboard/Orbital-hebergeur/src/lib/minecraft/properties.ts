/**
 * Full `server.properties` catalogue. The panel exposes every documented key so
 * the file can be managed entirely from the UI instead of the raw editor.
 * Defaults mirror the vanilla dedicated server; Synkrone only overrides the few
 * keys it owns (port, MOTD, level name).
 */

export type PropertyKind = "boolean" | "integer" | "string" | "enum";

export type PropertyDef = {
  key: string;
  kind: PropertyKind;
  default: string;
  category: string;
  description: string;
  options?: string[];
  min?: number;
  max?: number;
  /** Written by the platform (port allocation, volume layout): read-only in the UI. */
  managed?: boolean;
};

export const PROPERTY_CATEGORIES = [
  "Server",
  "Gameplay",
  "World",
  "Players",
  "Performance",
  "Network",
  "Resource pack",
  "RCON & query",
  "Advanced",
] as const;

export const SERVER_PROPERTIES: PropertyDef[] = [
  /* ------------------------------- Server -------------------------------- */
  {
    key: "motd",
    kind: "string",
    default: "A Minecraft Server",
    category: "Server",
    description: "Message shown in the multiplayer server list.",
  },
  {
    key: "server-port",
    kind: "integer",
    default: "25565",
    category: "Server",
    description: "Java edition listening port. Allocated by Orbital.",
    min: 1,
    max: 65535,
    managed: true,
  },
  {
    key: "server-ip",
    kind: "string",
    default: "",
    category: "Server",
    description: "Bind address. Leave empty to listen on every interface.",
  },
  {
    key: "max-players",
    kind: "integer",
    default: "20",
    category: "Server",
    description: "Maximum number of simultaneous players.",
    min: 0,
    max: 2147483647,
  },
  {
    key: "online-mode",
    kind: "boolean",
    default: "true",
    category: "Server",
    description: "Authenticate players against Mojang. Disable only behind a proxy.",
  },
  {
    key: "enable-status",
    kind: "boolean",
    default: "true",
    category: "Server",
    description: "Answer server list pings.",
  },
  {
    key: "hide-online-players",
    kind: "boolean",
    default: "false",
    category: "Server",
    description: "Hide the player sample from the server list response.",
  },
  {
    key: "white-list",
    kind: "boolean",
    default: "false",
    category: "Server",
    description: "Only allow players listed in whitelist.json.",
  },
  {
    key: "enforce-whitelist",
    kind: "boolean",
    default: "false",
    category: "Server",
    description: "Kick players removed from the whitelist while connected.",
  },
  {
    key: "enforce-secure-profile",
    kind: "boolean",
    default: "true",
    category: "Server",
    description: "Require a Mojang-signed chat profile to join.",
  },
  {
    key: "accepts-transfers",
    kind: "boolean",
    default: "false",
    category: "Server",
    description: "Accept players transferred from another server.",
  },
  {
    key: "bug-report-link",
    kind: "string",
    default: "",
    category: "Server",
    description: "URL offered to players when the client crashes.",
  },

  /* ------------------------------ Gameplay -------------------------------- */
  {
    key: "gamemode",
    kind: "enum",
    default: "survival",
    category: "Gameplay",
    description: "Default game mode for new players.",
    options: ["survival", "creative", "adventure", "spectator"],
  },
  {
    key: "force-gamemode",
    kind: "boolean",
    default: "false",
    category: "Gameplay",
    description: "Reset players to the default game mode when they join.",
  },
  {
    key: "difficulty",
    kind: "enum",
    default: "easy",
    category: "Gameplay",
    description: "World difficulty.",
    options: ["peaceful", "easy", "normal", "hard"],
  },
  {
    key: "hardcore",
    kind: "boolean",
    default: "false",
    category: "Gameplay",
    description: "Death bans the player to spectator mode.",
  },
  {
    key: "pvp",
    kind: "boolean",
    default: "true",
    category: "Gameplay",
    description: "Allow players to damage each other.",
  },
  {
    key: "allow-flight",
    kind: "boolean",
    default: "false",
    category: "Gameplay",
    description: "Tolerate flight in survival (required by some mods).",
  },
  {
    key: "allow-nether",
    kind: "boolean",
    default: "true",
    category: "Gameplay",
    description: "Allow travelling to the Nether.",
  },
  {
    key: "spawn-monsters",
    kind: "boolean",
    default: "true",
    category: "Gameplay",
    description: "Spawn hostile mobs.",
  },
  {
    key: "spawn-protection",
    kind: "integer",
    default: "16",
    category: "Gameplay",
    description: "Radius around spawn that only operators can edit.",
    min: 0,
  },
  {
    key: "enable-command-block",
    kind: "boolean",
    default: "false",
    category: "Gameplay",
    description: "Enable command blocks.",
  },
  {
    key: "op-permission-level",
    kind: "integer",
    default: "4",
    category: "Gameplay",
    description: "Permission level granted by /op.",
    min: 0,
    max: 4,
  },
  {
    key: "function-permission-level",
    kind: "integer",
    default: "2",
    category: "Gameplay",
    description: "Permission level used when running functions.",
    min: 0,
    max: 4,
  },
  {
    key: "broadcast-console-to-ops",
    kind: "boolean",
    default: "true",
    category: "Gameplay",
    description: "Relay console command output to online operators.",
  },
  {
    key: "broadcast-rcon-to-ops",
    kind: "boolean",
    default: "true",
    category: "Gameplay",
    description: "Relay RCON command output to online operators.",
  },

  /* -------------------------------- World --------------------------------- */
  {
    key: "level-name",
    kind: "string",
    default: "world",
    category: "World",
    description: "World folder name inside the volume.",
  },
  {
    key: "level-seed",
    kind: "string",
    default: "",
    category: "World",
    description: "Seed used when generating the world. Empty means random.",
  },
  {
    key: "level-type",
    kind: "enum",
    default: "minecraft:normal",
    category: "World",
    description: "World generation preset.",
    options: [
      "minecraft:normal",
      "minecraft:flat",
      "minecraft:large_biomes",
      "minecraft:amplified",
      "minecraft:single_biome_surface",
    ],
  },
  {
    key: "generate-structures",
    kind: "boolean",
    default: "true",
    category: "World",
    description: "Generate villages, temples and other structures.",
  },
  {
    key: "generator-settings",
    kind: "string",
    default: "{}",
    category: "World",
    description: "JSON generator settings, mostly used by superflat worlds.",
  },
  {
    key: "max-world-size",
    kind: "integer",
    default: "29999984",
    category: "World",
    description: "World border radius in blocks.",
    min: 1,
    max: 29999984,
  },
  {
    key: "initial-enabled-packs",
    kind: "string",
    default: "vanilla",
    category: "World",
    description: "Comma separated datapacks enabled on world creation.",
  },
  {
    key: "initial-disabled-packs",
    kind: "string",
    default: "",
    category: "World",
    description: "Comma separated datapacks disabled on world creation.",
  },

  /* ------------------------------- Players -------------------------------- */
  {
    key: "player-idle-timeout",
    kind: "integer",
    default: "0",
    category: "Players",
    description: "Kick idle players after N minutes. 0 disables it.",
    min: 0,
  },
  {
    key: "pause-when-empty-seconds",
    kind: "integer",
    default: "60",
    category: "Players",
    description: "Pause the tick loop after N seconds without players. 0 disables it.",
    min: 0,
  },
  {
    key: "text-filtering-config",
    kind: "string",
    default: "",
    category: "Players",
    description: "Endpoint used for chat text filtering.",
  },
  {
    key: "text-filtering-version",
    kind: "integer",
    default: "0",
    category: "Players",
    description: "Version of the text filtering protocol.",
    min: 0,
  },
  {
    key: "log-ips",
    kind: "boolean",
    default: "true",
    category: "Players",
    description: "Write player IP addresses to the server log.",
  },

  /* ----------------------------- Performance ------------------------------ */
  {
    key: "view-distance",
    kind: "integer",
    default: "10",
    category: "Performance",
    description: "Chunk radius sent to clients. Biggest lever on CPU and RAM.",
    min: 2,
    max: 32,
  },
  {
    key: "simulation-distance",
    kind: "integer",
    default: "10",
    category: "Performance",
    description: "Chunk radius where entities and blocks tick.",
    min: 3,
    max: 32,
  },
  {
    key: "entity-broadcast-range-percentage",
    kind: "integer",
    default: "100",
    category: "Performance",
    description: "Percentage of the default range at which entities are sent to clients.",
    min: 10,
    max: 1000,
  },
  {
    key: "max-tick-time",
    kind: "integer",
    default: "60000",
    category: "Performance",
    description: "Watchdog timeout in ms. -1 disables the watchdog.",
    min: -1,
  },
  {
    key: "max-chained-neighbor-updates",
    kind: "integer",
    default: "1000000",
    category: "Performance",
    description: "Cap on consecutive neighbour block updates.",
  },
  {
    key: "sync-chunk-writes",
    kind: "boolean",
    default: "true",
    category: "Performance",
    description: "Write chunks synchronously. Disabling trades safety for speed.",
  },
  {
    key: "region-file-compression",
    kind: "enum",
    default: "deflate",
    category: "Performance",
    description: "Compression algorithm used for region files.",
    options: ["deflate", "lz4", "none"],
  },
  {
    key: "use-native-transport",
    kind: "boolean",
    default: "true",
    category: "Performance",
    description: "Use the optimised Linux network stack.",
  },
  {
    key: "enable-jmx-monitoring",
    kind: "boolean",
    default: "false",
    category: "Performance",
    description: "Expose tick timing over JMX.",
  },

  /* ------------------------------- Network -------------------------------- */
  {
    key: "network-compression-threshold",
    kind: "integer",
    default: "256",
    category: "Network",
    description: "Compress packets above this size. -1 disables compression.",
    min: -1,
  },
  {
    key: "prevent-proxy-connections",
    kind: "boolean",
    default: "false",
    category: "Network",
    description: "Reject players connecting through a VPN or proxy.",
  },
  {
    key: "rate-limit",
    kind: "integer",
    default: "0",
    category: "Network",
    description: "Packets per second before a player is kicked. 0 disables it.",
    min: 0,
  },

  /* ---------------------------- Resource pack ----------------------------- */
  {
    key: "resource-pack",
    kind: "string",
    default: "",
    category: "Resource pack",
    description: "URL of the server resource pack.",
  },
  {
    key: "resource-pack-sha1",
    kind: "string",
    default: "",
    category: "Resource pack",
    description: "SHA-1 of the resource pack archive.",
  },
  {
    key: "resource-pack-id",
    kind: "string",
    default: "",
    category: "Resource pack",
    description: "UUID identifying the resource pack.",
  },
  {
    key: "resource-pack-prompt",
    kind: "string",
    default: "",
    category: "Resource pack",
    description: "Rich text prompt shown when offering the pack.",
  },
  {
    key: "require-resource-pack",
    kind: "boolean",
    default: "false",
    category: "Resource pack",
    description: "Disconnect players who decline the resource pack.",
  },

  /* ---------------------------- RCON and query ---------------------------- */
  {
    key: "enable-rcon",
    kind: "boolean",
    default: "false",
    category: "RCON & query",
    description: "Expose the RCON console. Orbital drives the console over stdin instead.",
  },
  {
    key: "rcon.port",
    kind: "integer",
    default: "25575",
    category: "RCON & query",
    description: "RCON listening port.",
    min: 1,
    max: 65535,
  },
  {
    key: "rcon.password",
    kind: "string",
    default: "",
    category: "RCON & query",
    description: "RCON password. Stored in clear text in server.properties.",
  },
  {
    key: "enable-query",
    kind: "boolean",
    default: "false",
    category: "RCON & query",
    description: "Enable the GameSpy4 query protocol.",
  },
  {
    key: "query.port",
    kind: "integer",
    default: "25565",
    category: "RCON & query",
    description: "Query listening port.",
    min: 1,
    max: 65535,
  },

  /* ------------------------------- Advanced -------------------------------- */
  {
    key: "debug",
    kind: "boolean",
    default: "false",
    category: "Advanced",
    description: "Verbose debug output.",
  },
];

export const PROPERTY_BY_KEY: Record<string, PropertyDef> = Object.fromEntries(
  SERVER_PROPERTIES.map((p) => [p.key, p]),
);

/** Keys Synkrone sets differently from vanilla. */
const ORBITAL_OVERRIDES: Record<string, string> = {
  motd: "A Synkrone Minecraft server",
  difficulty: "normal",
};

export function defaultProperties(): Record<string, string> {
  const out: Record<string, string> = {};
  for (const def of SERVER_PROPERTIES) out[def.key] = def.default;
  return { ...out, ...ORBITAL_OVERRIDES };
}

/** Coerces a submitted value to something the server will accept. */
export function normalizeProperty(key: string, value: string): string {
  const def = PROPERTY_BY_KEY[key];
  const raw = String(value ?? "").trim();
  if (!def) return raw;
  if (def.kind === "boolean") return raw === "true" ? "true" : "false";
  if (def.kind === "integer") {
    const n = Number.parseInt(raw, 10);
    if (Number.isNaN(n)) return def.default;
    const clamped = Math.min(def.max ?? n, Math.max(def.min ?? n, n));
    return String(clamped);
  }
  if (def.kind === "enum" && def.options && !def.options.includes(raw)) return def.default;
  return raw;
}

/** server.properties keys are lowercase words separated by dots or dashes. */
export function isValidPropertyKey(key: string): boolean {
  return /^[a-z0-9][a-z0-9._-]{0,63}$/.test(key);
}

export function normalizeProperties(input: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(input ?? {})) {
    const clean = key.trim();
    if (!isValidPropertyKey(clean)) continue;
    out[clean] = normalizeProperty(clean, value).replace(/[\r\n]/g, " ");
  }
  return out;
}
