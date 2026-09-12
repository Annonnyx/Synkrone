import { NextRequest } from "next/server";
import { eq } from "drizzle-orm";
import { db } from "@/db";
import { discordBots, services, users } from "@/db/schema";
import { route } from "@/lib/api";
import { decryptSecret } from "@/lib/crypto";
import { requireInternalAdmin } from "@/lib/internal-admin";
import { FilesystemManager } from "@/lib/filesystem/manager";
import { RUNTIME_STATS_PATH, readJsonFile } from "@/lib/discord/guild-files";
import { userIdForDiscordAccount } from "@/lib/oauth/accounts";
import type { ServiceType } from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const DISCORD_API = "https://discord.com/api/v10";
const MANAGE_GUILD = BigInt(0x20);

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

async function tokenForService(serviceId: string): Promise<string | null> {
  const [bot] = await db.select().from(discordBots).where(eq(discordBots.serviceId, serviceId)).limit(1);
  return decryptSecret(bot?.tokenEnc);
}

async function memberCanManage(token: string, guildId: string, userId: string): Promise<boolean> {
  const guild = await discordGet<{ owner_id?: string }>(token, `/guilds/${guildId}`);
  if (guild?.owner_id === userId) return true;
  const member = await discordGet<{ roles?: string[] }>(token, `/guilds/${guildId}/members/${userId}`);
  const roles = await discordGet<Array<{ id: string; permissions: string }>>(token, `/guilds/${guildId}/roles`);
  if (!member || !roles) return false;
  const mine = new Set(member.roles || []);
  return roles.some((role) => mine.has(role.id) && (BigInt(role.permissions || "0") & MANAGE_GUILD) === MANAGE_GUILD);
}

export async function GET(req: NextRequest) {
  return route(async () => {
    requireInternalAdmin(req);
    const applicationId = String(req.nextUrl.searchParams.get("applicationId") || "").trim();
    const discordUserId = String(req.nextUrl.searchParams.get("discordUserId") || "").trim();
    const serviceId = String(req.nextUrl.searchParams.get("serviceId") || "").trim();
    const guildId = String(req.nextUrl.searchParams.get("guildId") || "").trim();
    const memberId = String(req.nextUrl.searchParams.get("memberId") || "").trim();
    const email = String(req.nextUrl.searchParams.get("email") || "").trim().toLowerCase();

    async function serviceByApp(appId: string) {
      const [bot] = await db.select().from(discordBots).where(eq(discordBots.applicationId, appId)).limit(1);
      if (!bot) return null;
      const [svc] = await db.select().from(services).where(eq(services.id, bot.serviceId)).limit(1);
      if (!svc) return null;
      return {
        found: true as const,
        serviceId: svc.id,
        name: svc.name,
        state: svc.state,
        flavor: bot.flavor,
        applicationId: bot.applicationId,
        ownerId: svc.ownerId,
      };
    }

    if (guildId && (serviceId || applicationId)) {
      const svc = serviceId ? { serviceId } : await serviceByApp(applicationId);
      if (!svc) return { found: false, channels: [] };
      const token = await tokenForService(svc.serviceId);
      const channels = token
        ? ((await discordGet<Array<{ id: string; name: string; type: number }>>(
            token,
            `/guilds/${guildId}/channels`,
          )) || [])
            .filter((ch) => ch.type === 0 || ch.type === 5)
            .map((ch) => ({ id: ch.id, name: ch.name }))
        : [];
      const manageGuild = token && memberId ? await memberCanManage(token, guildId, memberId) : false;
      return { found: true, serviceId: svc.serviceId, channels, manageGuild };
    }

    if (applicationId) {
      const found = await serviceByApp(applicationId);
      return found || { found: false };
    }

    if (discordUserId || email) {
      let ownerId = discordUserId ? await userIdForDiscordAccount(discordUserId) : null;
      if (!ownerId && email) {
        const [byEmail] = await db.select({ id: users.id }).from(users).where(eq(users.email, email)).limit(1);
        ownerId = byEmail?.id ?? null;
      }
      if (!ownerId) return { linked: false, services: [] };
      const rows = await db.select().from(services).where(eq(services.ownerId, ownerId));
      const out = [];
      for (const svc of rows) {
        if (svc.type !== "discord") {
          out.push({
            id: svc.id,
            name: svc.name,
            type: svc.type,
            state: svc.state,
            flavor: null,
            applicationId: null,
            guilds: [] as Array<{ id: string; name: string }>,
          });
          continue;
        }
        const [bot] = await db.select().from(discordBots).where(eq(discordBots.serviceId, svc.id)).limit(1);
        const fsm = new FilesystemManager(svc.type as ServiceType, svc.id);
        const stats = await readJsonFile<{ guilds?: Array<{ id: string; name: string }> }>(fsm, RUNTIME_STATS_PATH);
        out.push({
          id: svc.id,
          name: svc.name,
          type: svc.type,
          state: svc.state,
          flavor: bot?.flavor ?? "custom",
          applicationId: bot?.applicationId ?? null,
          guilds: Array.isArray(stats?.guilds) ? stats.guilds : [],
        });
      }
      return { linked: true, services: out };
    }

    return { error: "applicationId or discordUserId required" };
  });
}
