import { NextRequest } from "next/server";
import { and, desc, eq } from "drizzle-orm";
import { db } from "@/db";
import { apiKeys, auditLogs, projects, sftpCredentials, services, webhooks } from "@/db/schema";
import { body, fail, route } from "@/lib/api";
import { audit } from "@/lib/audit";
import { requireUser } from "@/lib/auth";
import { encryptSecret, randomToken, sha256 } from "@/lib/crypto";
import { publicSftpEndpoint } from "@/lib/sftp/manager";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ section: string }> };

export async function GET(_req: NextRequest, ctx: Ctx) {
  const { section } = await ctx.params;
  return route(async () => {
    const user = await requireUser();
    switch (section) {
      case "api-keys":
        return {
          keys: (
            await db
              .select()
              .from(apiKeys)
              .where(eq(apiKeys.userId, user.id))
              .orderBy(desc(apiKeys.createdAt))
          ).map((k) => ({ ...k, keyHash: undefined })),
        };
      case "audit":
        return {
          logs: await db
            .select()
            .from(auditLogs)
            .where(eq(auditLogs.userId, user.id))
            .orderBy(desc(auditLogs.createdAt))
            .limit(100),
        };
      case "projects":
        return {
          projects: await db
            .select()
            .from(projects)
            .where(eq(projects.ownerId, user.id))
            .orderBy(desc(projects.createdAt)),
        };
      case "sftp": {
        const rows = await db
          .select({
            id: sftpCredentials.id,
            serviceId: sftpCredentials.serviceId,
            username: sftpCredentials.username,
            host: sftpCredentials.host,
            port: sftpCredentials.port,
            chroot: sftpCredentials.chroot,
            enabled: sftpCredentials.enabled,
            serviceName: services.name,
            serviceType: services.type,
          })
          .from(sftpCredentials)
          .innerJoin(services, eq(services.id, sftpCredentials.serviceId))
          .where(eq(services.ownerId, user.id));
        const endpoint = publicSftpEndpoint();
        return { accounts: rows.map((row) => ({ ...row, host: endpoint.host, port: endpoint.port })) };
      }
      case "webhooks":
        return {
          webhooks: (
            await db.select().from(webhooks).where(eq(webhooks.userId, user.id))
          ).map((w) => ({ ...w, secretEnc: undefined })),
        };
      default:
        return fail("Unknown section", 404);
    }
  });
}

export async function POST(req: NextRequest, ctx: Ctx) {
  const { section } = await ctx.params;
  return route(async () => {
    const user = await requireUser();
    if (section === "api-keys") {
      const { name } = await body<{ name: string }>(req);
      const raw = `orb_${randomToken(24)}`;
      const [row] = await db
        .insert(apiKeys)
        .values({
          userId: user.id,
          name: name || "Untitled key",
          prefix: raw.slice(0, 12),
          keyHash: sha256(raw),
        })
        .returning();
      await audit({ userId: user.id, action: "apikey.create", detail: row.name });
      return { key: { ...row, keyHash: undefined }, secret: raw };
    }
    if (section === "projects") {
      const { name, description } = await body<{ name: string; description?: string }>(req);
      if (!name?.trim()) return fail("name is required");
      const [row] = await db
        .insert(projects)
        .values({ ownerId: user.id, name: name.trim(), description })
        .returning();
      return { project: row };
    }
    if (section === "webhooks") {
      const { url, events, serviceId } = await body<{
        url: string;
        events: string[];
        serviceId?: string;
      }>(req);
      if (!/^https?:\/\//.test(url ?? "")) return fail("A valid URL is required");
      const secret = randomToken(16);
      const [row] = await db
        .insert(webhooks)
        .values({
          userId: user.id,
          serviceId: serviceId ?? null,
          url,
          events: events ?? [],
          secretEnc: encryptSecret(secret),
        })
        .returning();
      return { webhook: { ...row, secretEnc: undefined }, secret };
    }
    return fail("Unknown section", 404);
  });
}

export async function DELETE(req: NextRequest, ctx: Ctx) {
  const { section } = await ctx.params;
  return route(async () => {
    const user = await requireUser();
    const id = new URL(req.url).searchParams.get("id");
    if (!id) return fail("id is required");
    if (section === "api-keys") {
      await db
        .update(apiKeys)
        .set({ revokedAt: new Date() })
        .where(and(eq(apiKeys.id, id), eq(apiKeys.userId, user.id)));
      await audit({ userId: user.id, action: "apikey.revoke" });
      return { ok: true };
    }
    if (section === "webhooks") {
      await db.delete(webhooks).where(and(eq(webhooks.id, id), eq(webhooks.userId, user.id)));
      return { ok: true };
    }
    return fail("Unknown section", 404);
  });
}
