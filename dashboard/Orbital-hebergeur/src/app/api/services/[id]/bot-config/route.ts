import { NextRequest } from "next/server";
import { eq } from "drizzle-orm";
import { db } from "@/db";
import { discordBots } from "@/db/schema";
import { body, fail, route } from "@/lib/api";
import { HttpError, requireUser } from "@/lib/auth";
import { decryptSecret } from "@/lib/crypto";
import { authorizeService } from "@/lib/runtime";
import { FilesystemManager } from "@/lib/filesystem/manager";
import {
  EMBED_DEFAULT,
  GOODBYE_DEFAULT,
  RUNTIME_STATS_PATH,
  WELCOME_DEFAULT,
  colorToHex,
  embedPath,
  goodbyePath,
  goodbyePathStaff,
  parseColor,
  readJsonFile,
  welcomePath,
  welcomePathStaff,
  writeJsonFile,
} from "@/lib/discord/guild-files";
import { CUSTOM_PATH, DEFAULTS_PATH, normalizeDefault } from "@/lib/discord/custom-config";
import type { ServiceType } from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ id: string }> };

const DISCORD_API = "https://discord.com/api/v10";

async function botToken(serviceId: string): Promise<string | null> {
  const [bot] = await db.select().from(discordBots).where(eq(discordBots.serviceId, serviceId)).limit(1);
  return decryptSecret(bot?.tokenEnc);
}

async function discordGet<T>(token: string, path: string): Promise<T | null> {
  try {
    const res = await fetch(`${DISCORD_API}${path}`, {
      headers: { Authorization: `Bot ${token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(4000),
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export async function GET(req: NextRequest, ctx: Ctx) {
  return route(async () => {
    const user = await requireUser();
    const { id } = await ctx.params;
    const svc = await authorizeService(id, user.id, "viewer");
    if (svc.type !== "discord") return fail("Not a Discord service", 400);
    const fsm = new FilesystemManager(svc.type as ServiceType, svc.id);
    const token = await botToken(id);
    const stats = (await readJsonFile<Record<string, unknown>>(fsm, RUNTIME_STATS_PATH)) || {};
    const guildId = req.nextUrl.searchParams.get("guildId") || "";

    type Guild = { id: string; name: string };
    let guilds: Guild[] = [];
    if (Array.isArray(stats.guilds)) {
      guilds = (stats.guilds as Guild[]).filter((g) => g?.id && g?.name);
    }
    if (token && guilds.length === 0) {
      const remote = await discordGet<Array<{ id: string; name: string }>>(token, "/users/@me/guilds");
      if (remote) guilds = remote.map((g) => ({ id: g.id, name: g.name }));
    }

    const selected = guildId || guilds[0]?.id || "";
    let channels: Array<{ id: string; name: string; type: number }> = [];
    if (selected && token) {
      const remote = await discordGet<Array<{ id: string; name: string; type: number }>>(
        token,
        `/guilds/${selected}/channels`,
      );
      channels = (remote || []).filter((ch) => ch.type === 0 || ch.type === 5);
    }

    const welcome = selected
      ? { ...WELCOME_DEFAULT, ...((await readJsonFile<Record<string, unknown>>(fsm, welcomePath(selected))) || {}) }
      : { ...WELCOME_DEFAULT };
    const goodbye = selected
      ? { ...GOODBYE_DEFAULT, ...((await readJsonFile<Record<string, unknown>>(fsm, goodbyePath(selected))) || {}) }
      : { ...GOODBYE_DEFAULT };
    const embedRaw = selected
      ? { ...EMBED_DEFAULT, ...((await readJsonFile<Record<string, unknown>>(fsm, embedPath(selected))) || {}) }
      : { ...EMBED_DEFAULT };
    const defaults = normalizeDefault((await readJsonFile(fsm, DEFAULTS_PATH)) || {});
    const customRaw = selected ? ((await readJsonFile<Record<string, unknown>>(fsm, CUSTOM_PATH(selected))) || {}) : {};
    const customIdentity =
      customRaw.identity && typeof customRaw.identity === "object"
        ? (customRaw.identity as Record<string, unknown>)
        : {};

    return {
      guilds,
      selectedGuildId: selected,
      channels,
      stats: {
        uptimeSeconds: Number(stats.uptimeSeconds || 0),
        guildCount: Number(stats.guildCount || guilds.length || 0),
        uniqueUsers: Number(stats.uniqueUsers || 0),
        commandsTotal: Number(stats.commandsTotal || 0),
        commandsMonth: Number(stats.commandsMonth || 0),
        commandsToday: Number(stats.commandsToday || 0),
        updatedAt: stats.updatedAt || null,
      },
      welcome: {
        channel_id: welcome.channel_id ? String(welcome.channel_id) : "",
        embed_title: String(welcome.embed_title || WELCOME_DEFAULT.embed_title),
        embed_description: String(welcome.embed_description || WELCOME_DEFAULT.embed_description),
        content_message: String(welcome.content_message || WELCOME_DEFAULT.content_message),
      },
      goodbye: {
        channel_id: goodbye.channel_id ? String(goodbye.channel_id) : "",
        embed_title: String(goodbye.embed_title || GOODBYE_DEFAULT.embed_title),
        embed_description: String(goodbye.embed_description || GOODBYE_DEFAULT.embed_description),
        content_message: String(goodbye.content_message || GOODBYE_DEFAULT.content_message),
      },
      embed: {
        color: colorToHex(embedRaw.color),
        footer: String(embedRaw.footer || ""),
        author: String(embedRaw.author || ""),
        thumbnail: String(embedRaw.thumbnail || ""),
        image: String(embedRaw.image || ""),
      },
      defaults,
      allow: defaults.allow,
      displayName: String(customIdentity.displayName || ""),
      hasToken: Boolean(token),
    };
  });
}

export async function PATCH(req: NextRequest, ctx: Ctx) {
  return route(async () => {
    const user = await requireUser();
    const { id } = await ctx.params;
    const svc = await authorizeService(id, user.id, "member");
    if (svc.type !== "discord") return fail("Not a Discord service", 400);
    const payload = await body<{
      guildId?: string;
      welcome?: Record<string, string>;
      goodbye?: Record<string, string>;
      embed?: Record<string, string>;
      avatarDataUrl?: string;
      defaults?: Record<string, unknown>;
      displayName?: string;
    }>(req);
    const fsm = new FilesystemManager(svc.type as ServiceType, svc.id);

    if (payload.defaults) {
      const defaults = normalizeDefault(payload.defaults);
      await writeJsonFile(fsm, DEFAULTS_PATH, defaults);
      await writeJsonFile(fsm, "data/addons/data_embed_type/global_config.json", {
        color: parseColor(defaults.identity.embedColor),
        footer: defaults.identity.embedFooter,
        thumbnail: defaults.identity.embedThumbnail,
      });
    }

    if (payload.avatarDataUrl) {
      const token = await botToken(id);
      if (!token) throw new HttpError(400, "Discord token missing");
      const match = String(payload.avatarDataUrl).match(/^data:(image\/(?:png|jpeg));base64,([A-Za-z0-9+/=]+)$/);
      if (!match) return fail("Avatar must be a PNG or JPEG data URL", 400);
      const bytes = Buffer.from(match[2], "base64");
      if (bytes.length > 8 * 1024 * 1024) return fail("Avatar exceeds 8 MB", 413);
      const res = await fetch(`${DISCORD_API}/users/@me`, {
        method: "PATCH",
        headers: {
          Authorization: `Bot ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ avatar: payload.avatarDataUrl }),
      });
      if (!res.ok) {
        const text = await res.text();
        return fail(text.slice(0, 200) || "Avatar update failed", res.status);
      }
    }

    const guildId = String(payload.guildId || "").trim();
    if (!guildId && (payload.welcome || payload.goodbye || payload.embed || payload.displayName !== undefined)) {
      return fail("guildId is required");
    }
    if (guildId && payload.welcome) {
      const current = (await readJsonFile<Record<string, unknown>>(fsm, welcomePath(guildId))) || {
        ...WELCOME_DEFAULT,
      };
      const next = {
        ...current,
        channel_id: payload.welcome.channel_id ? String(payload.welcome.channel_id) : null,
        embed_title: payload.welcome.embed_title ?? current.embed_title,
        embed_description: payload.welcome.embed_description ?? current.embed_description,
        content_message: payload.welcome.content_message ?? current.content_message,
      };
      await writeJsonFile(fsm, welcomePath(guildId), next);
      await writeJsonFile(fsm, welcomePathStaff(guildId), next);
    }
    if (guildId && payload.goodbye) {
      const current = (await readJsonFile<Record<string, unknown>>(fsm, goodbyePath(guildId))) || {
        ...GOODBYE_DEFAULT,
      };
      const next = {
        ...current,
        channel_id: payload.goodbye.channel_id ? String(payload.goodbye.channel_id) : null,
        embed_title: payload.goodbye.embed_title ?? current.embed_title,
        embed_description: payload.goodbye.embed_description ?? current.embed_description,
        content_message: payload.goodbye.content_message ?? current.content_message,
      };
      await writeJsonFile(fsm, goodbyePath(guildId), next);
      await writeJsonFile(fsm, goodbyePathStaff(guildId), next);
    }
    if (guildId && payload.embed) {
      const current = (await readJsonFile<Record<string, unknown>>(fsm, embedPath(guildId))) || {
        ...EMBED_DEFAULT,
      };
      const next = {
        ...current,
        color: parseColor(payload.embed.color, Number(current.color) || EMBED_DEFAULT.color),
        footer: payload.embed.footer ?? current.footer,
        author: payload.embed.author ?? current.author,
        thumbnail: payload.embed.thumbnail ?? current.thumbnail,
        image: payload.embed.image ?? current.image,
      };
      await writeJsonFile(fsm, embedPath(guildId), next);
    }
    if (guildId && (payload.embed || payload.welcome || payload.goodbye || payload.displayName !== undefined)) {
      const existingCustom =
        (await readJsonFile<Record<string, unknown>>(fsm, CUSTOM_PATH(guildId))) || {};
      const identity =
        existingCustom.identity && typeof existingCustom.identity === "object"
          ? { ...(existingCustom.identity as Record<string, unknown>) }
          : {};
      const texts =
        existingCustom.texts && typeof existingCustom.texts === "object"
          ? { ...(existingCustom.texts as Record<string, unknown>) }
          : {};
      const channels =
        existingCustom.channels && typeof existingCustom.channels === "object"
          ? { ...(existingCustom.channels as Record<string, unknown>) }
          : {};
      if (payload.embed) {
        identity.embedColor = colorToHex(
          parseColor(payload.embed.color, parseColor(identity.embedColor, EMBED_DEFAULT.color)),
        );
        if (payload.embed.footer !== undefined) identity.footerText = payload.embed.footer;
        if (payload.embed.thumbnail !== undefined) identity.logo = payload.embed.thumbnail;
      }
      if (payload.displayName !== undefined) identity.displayName = String(payload.displayName).slice(0, 32);
      if (payload.welcome?.content_message !== undefined) texts.welcome = payload.welcome.content_message;
      if (payload.goodbye?.content_message !== undefined) texts.goodbye = payload.goodbye.content_message;
      if (payload.welcome?.channel_id !== undefined) channels.welcome = payload.welcome.channel_id || "";
      if (payload.goodbye?.channel_id !== undefined) channels.goodbye = payload.goodbye.channel_id || "";
      await writeJsonFile(fsm, CUSTOM_PATH(guildId), {
        ...existingCustom,
        identity,
        texts,
        channels,
      });
    }
    return { ok: true };
  });
}
