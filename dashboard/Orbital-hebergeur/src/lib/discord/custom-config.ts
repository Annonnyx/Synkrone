export const ALLOW_KEYS = [
  "displayName",
  "avatar",
  "embedColor",
  "embedPalette",
  "embedLogo",
  "embedFooter",
  "font",
  "whiteLabel",
  "texts",
  "channels",
  "roles",
  "modules",
  "cooldowns",
  "commandPerms",
] as const;

export type AllowKey = (typeof ALLOW_KEYS)[number];

export const MODULES = [
  { id: "welcome", label: "Welcome", autoName: "bienvenue" },
  { id: "goodbye", label: "Goodbye", autoName: "au-revoir" },
  { id: "logs", label: "Logs", autoName: "logs" },
  { id: "tickets", label: "Tickets", autoName: "tickets" },
  { id: "mute", label: "Mute", autoName: "Muted" },
] as const;

export type AllowMap = Record<AllowKey, boolean>;

export type DefaultConfig = {
  version: 1;
  identity: {
    displayName: string;
    activityType: string;
    activityText: string;
    embedColor: string;
    embedFooter: string;
    embedThumbnail: string;
  };
  install: Record<string, { provision: "auto" | "manual"; autoName: string }>;
  allow: AllowMap;
  modules: Record<string, { enabled: boolean }>;
  limits: { autoCreatedMax: number; premiumFonts: boolean };
};

export function emptyAllow(): AllowMap {
  return {
    displayName: false,
    avatar: false,
    embedColor: true,
    embedPalette: true,
    embedLogo: true,
    embedFooter: true,
    font: true,
    whiteLabel: false,
    texts: true,
    channels: true,
    roles: true,
    modules: false,
    cooldowns: false,
    commandPerms: false,
  };
}

export function defaultConfig(): DefaultConfig {
  const install: DefaultConfig["install"] = {};
  const modules: DefaultConfig["modules"] = {};
  for (const mod of MODULES) {
    install[mod.id] = { provision: "manual", autoName: mod.autoName };
    modules[mod.id] = { enabled: true };
  }
  return {
    version: 1,
    identity: {
      displayName: "",
      activityType: "playing",
      activityText: "",
      embedColor: "#660099",
      embedFooter: "",
      embedThumbnail: "",
    },
    install,
    allow: emptyAllow(),
    modules,
    limits: { autoCreatedMax: 20, premiumFonts: false },
  };
}

export function normalizeDefault(raw: unknown): DefaultConfig {
  const base = defaultConfig();
  const src = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  const identity = src.identity && typeof src.identity === "object" ? (src.identity as Record<string, unknown>) : {};
  const allowIn = src.allow && typeof src.allow === "object" ? (src.allow as Record<string, unknown>) : {};
  const installIn = src.install && typeof src.install === "object" ? (src.install as Record<string, unknown>) : {};
  const modulesIn = src.modules && typeof src.modules === "object" ? (src.modules as Record<string, unknown>) : {};
  const limits = src.limits && typeof src.limits === "object" ? (src.limits as Record<string, unknown>) : {};
  const allow = emptyAllow();
  for (const key of ALLOW_KEYS) {
    if (typeof allowIn[key] === "boolean") allow[key] = allowIn[key];
  }
  for (const mod of MODULES) {
    const item = installIn[mod.id] && typeof installIn[mod.id] === "object" ? (installIn[mod.id] as Record<string, unknown>) : {};
    base.install[mod.id] = {
      provision: item.provision === "auto" ? "auto" : "manual",
      autoName: String(item.autoName || mod.autoName).slice(0, 80),
    };
    const modItem = modulesIn[mod.id];
    if (typeof modItem === "boolean") base.modules[mod.id] = { enabled: modItem };
    else if (modItem && typeof modItem === "object" && typeof (modItem as { enabled?: unknown }).enabled === "boolean") {
      base.modules[mod.id] = { enabled: Boolean((modItem as { enabled: boolean }).enabled) };
    }
  }
  return {
    version: 1,
    identity: {
      displayName: String(identity.displayName || "").slice(0, 32),
      activityType: String(identity.activityType || "playing"),
      activityText: String(identity.activityText || "").slice(0, 120),
      embedColor: String(identity.embedColor || "#660099"),
      embedFooter: String(identity.embedFooter || "").slice(0, 200),
      embedThumbnail: String(identity.embedThumbnail || "").slice(0, 400),
    },
    install: base.install,
    allow,
    modules: base.modules,
    limits: {
      autoCreatedMax: Math.max(0, Math.min(100, Number(limits.autoCreatedMax) || 20)),
      premiumFonts: Boolean(limits.premiumFonts),
    },
  };
}

export function isAllowed(allow: AllowMap, key: AllowKey) {
  if (allow[key]) return true;
  if (allow.whiteLabel && ["displayName", "avatar", "embedLogo", "embedFooter"].includes(key)) return true;
  return false;
}

export const DEFAULTS_PATH = "config/defaults.json";
export const CUSTOM_PATH = (guildId: string) => `data/synkrone_custom/${guildId}.json`;
