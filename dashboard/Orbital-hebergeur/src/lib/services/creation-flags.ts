export const CREATE_KINDS = ["discord", "minecraft", "web"] as const;
export type CreateKind = (typeof CREATE_KINDS)[number];

export type CreationFlags = {
  discordEnabled: boolean;
  minecraftEnabled: boolean;
  webEnabled: boolean;
};

export function isCreationEnabled(flags: CreationFlags | null | undefined, type: string) {
  if (!flags) return true;
  if (type === "discord") return flags.discordEnabled !== false;
  if (type === "minecraft") return flags.minecraftEnabled !== false;
  if (type === "web") return flags.webEnabled !== false;
  return true;
}

export function firstCreateHref(flags: CreationFlags | null | undefined) {
  for (const type of CREATE_KINDS) {
    if (isCreationEnabled(flags, type)) return `/dashboard/new/${type}`;
  }
  return null;
}

export function creationDisabledMessage(type: string) {
  if (type === "discord") return "La création de bots Discord est désactivée.";
  if (type === "minecraft") return "La création de serveurs Minecraft est désactivée.";
  if (type === "web") return "La création de sites est désactivée.";
  return "La création de ce type de service est désactivée.";
}
