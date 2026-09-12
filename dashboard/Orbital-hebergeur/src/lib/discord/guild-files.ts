import { FilesystemManager } from "@/lib/filesystem/manager";

export const WELCOME_DEFAULT = {
  channel_id: null as string | number | null,
  embed_title: "Bienvenue sur {guild}",
  embed_description: "{user.mention} nous a rejoint !",
  content_message: "On acclame tous {user.mention} !\nNous sommes désormais {guild.count}.",
};

export const GOODBYE_DEFAULT = {
  channel_id: null as string | number | null,
  embed_title: "Départ de {user}",
  embed_description: "Triste de te voir partir...",
  content_message: "{user.mention} nous a quitté.\nNous sommes désormais {guild.count}.",
};

export const EMBED_DEFAULT = {
  color: 0x660099,
  footer: "",
  author: "",
  thumbnail: "",
  image: "",
};

export function welcomePath(guildId: string) {
  return `cogs/ADMIN/configuration/joinleave/bienvenue/data/${guildId}/config.json`;
}

export function welcomePathStaff(guildId: string) {
  return `cogs/staff/configuration/joinleave/bienvenue/data/${guildId}/config.json`;
}

export function goodbyePath(guildId: string) {
  return `cogs/ADMIN/configuration/joinleave/aurevoir/data_leave/${guildId}/config.json`;
}

export function goodbyePathStaff(guildId: string) {
  return `cogs/staff/configuration/joinleave/aurevoir/data_leave/${guildId}/config.json`;
}

export function embedPath(guildId: string) {
  return `data/addons/data_embed_type/${guildId}.json`;
}

export const RUNTIME_STATS_PATH = "data/runtime_stats.json";

export async function readJsonFile<T>(fsm: FilesystemManager, rel: string): Promise<T | null> {
  try {
    if (!(await fsm.exists(rel))) return null;
    const raw = await fsm.read(rel);
    const parsed = JSON.parse(raw) as T;
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

export async function writeJsonFile(fsm: FilesystemManager, rel: string, data: unknown) {
  await fsm.write(rel, `${JSON.stringify(data, null, 4)}\n`);
}

export function parseColor(value: unknown, fallback = EMBED_DEFAULT.color): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  const raw = String(value ?? "")
    .trim()
    .replace(/^#/, "");
  if (!raw) return fallback;
  const n = Number.parseInt(raw, 16);
  return Number.isFinite(n) ? n : fallback;
}

export function colorToHex(value: unknown): string {
  const n = parseColor(value);
  return `#${n.toString(16).padStart(6, "0")}`;
}
