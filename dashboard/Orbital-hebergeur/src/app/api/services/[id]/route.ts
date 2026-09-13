import { NextRequest } from "next/server";
import { desc, eq } from "drizzle-orm";
import { db } from "@/db";
import {
  backups,
  containers,
  deployments,
  discordBots,
  domains,
  envVars,
  minecraftAddons,
  minecraftServers,
  serviceDatabases,
  sftpCredentials,
  webProjects,
} from "@/db/schema";
import { body, route } from "@/lib/api";
import { audit } from "@/lib/audit";
import { HttpError, requireUser } from "@/lib/auth";
import { decryptSecret, isLockedSecret, rewrapSecret } from "@/lib/crypto";
import { publicSftpEndpoint } from "@/lib/sftp/manager";
import { applicationIdFromToken } from "@/lib/discord/token";
import { withRequiredConfigCommand } from "@/lib/discord/ensure-config";
import { authorizeService } from "@/lib/runtime";
import { dnsRecordsFor, domainHints } from "@/lib/domains/public";
import { createJob, dispatch } from "@/lib/jobs/queue";
import { deleteServiceJob } from "@/lib/jobs/handlers";
import { deletionDeadline } from "@/lib/services/inactivity";
import { isPerServiceSftpSecret } from "@/lib/sftp/password";
import { deleteValidationMessage, validateServiceDelete } from "@/lib/services/delete-confirm";
import { touchOwnerActivity } from "@/lib/services/lifecycle";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(_req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  return route(async () => {
    const user = await requireUser();
    const svc = await authorizeService(id, user.id, "viewer");
    const [container] = await db
      .select()
      .from(containers)
      .where(eq(containers.serviceId, id))
      .orderBy(desc(containers.createdAt))
      .limit(1);

    const detail: Record<string, unknown> = { service: svc, container: container ?? null };
    if (svc.type === "discord") {
      const [bot] = await db.select().from(discordBots).where(eq(discordBots.serviceId, id));
      if (bot?.tokenEnc) {
        const wrapped = rewrapSecret(bot.tokenEnc);
        if (wrapped && wrapped !== bot.tokenEnc) {
          await db.update(discordBots).set({ tokenEnc: wrapped }).where(eq(discordBots.id, bot.id));
          bot.tokenEnc = wrapped;
        }
      }
      if (bot && !bot.applicationId && bot.tokenEnc) {
        const fromToken = applicationIdFromToken(decryptSecret(bot.tokenEnc) ?? "");
        if (fromToken) {
          await db.update(discordBots).set({ applicationId: fromToken }).where(eq(discordBots.id, bot.id));
          bot.applicationId = fromToken;
        }
      }
      const plain = decryptSecret(bot?.tokenEnc);
      detail.discord = bot
        ? {
            ...bot,
            commands: withRequiredConfigCommand(bot.commands ?? []),
            tokenEnc: undefined,
            hasToken: Boolean(plain),
            tokenUnreadable: isLockedSecret(bot.tokenEnc),
          }
        : null;
    }
    if (svc.type === "minecraft") {
      const [mc] = await db
        .select()
        .from(minecraftServers)
        .where(eq(minecraftServers.serviceId, id));
      detail.minecraft = mc ?? null;
      detail.addons = await db
        .select()
        .from(minecraftAddons)
        .where(eq(minecraftAddons.serviceId, id));
    }
    if (svc.type === "web") {
      const [web] = await db.select().from(webProjects).where(eq(webProjects.serviceId, id));
      detail.web = web ? { ...web, webhookSecretEnc: undefined } : null;
      detail.deployments = await db
        .select()
        .from(deployments)
        .where(eq(deployments.serviceId, id))
        .orderBy(desc(deployments.number))
        .limit(20);
      const domainRows = await db.select().from(domains).where(eq(domains.serviceId, id));
      detail.domains = domainRows.map((d) => ({
        ...d,
        records: dnsRecordsFor(d.hostname),
      }));
      detail.domainHints = domainHints(svc.slug);
    }
    detail.env = (await db.select().from(envVars).where(eq(envVars.serviceId, id))).map((e) => ({
      id: e.id,
      key: e.key,
      secret: e.secret,
    }));
    detail.backups = await db
      .select()
      .from(backups)
      .where(eq(backups.serviceId, id))
      .orderBy(desc(backups.createdAt));
    const [sftp] = await db
      .select()
      .from(sftpCredentials)
      .where(eq(sftpCredentials.serviceId, id));
    const sftpPlain = sftp ? decryptSecret(sftp.passwordEnc) : null;
    detail.sftp = sftp
      ? {
          ...sftp,
          passwordEnc: undefined,
          hasPassword: isPerServiceSftpSecret(sftpPlain),
          ...publicSftpEndpoint(),
        }
      : null;
    detail.databases = (
      await db.select().from(serviceDatabases).where(eq(serviceDatabases.serviceId, id))
    ).map((d) => ({ ...d, passwordEnc: undefined }));
    const suspendedAt = svc.suspendedAt?.getTime() ?? null;
    detail.inactivity = {
      suspended: Boolean(suspendedAt) || svc.state === "SUSPENDED",
      warned: Boolean(svc.deletionWarnedAt),
      deleteAt: suspendedAt ? new Date(deletionDeadline(suspendedAt)).toISOString() : null,
      storageOverflow: Boolean(svc.storageOverflowAt),
    };
    return detail;
  });
}

export async function PATCH(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  return route(async () => {
    const user = await requireUser();
    const svc = await authorizeService(id, user.id, "admin");
    const patch = await body<{
      name?: string;
      description?: string;
      cpuMillicores?: number;
      memoryMb?: number;
      storageMb?: number;
      restartPolicy?: string;
      maxRestarts?: number;
    }>(req);
    const { services: servicesTable } = await import("@/db/schema");
    const { clampResources } = await import("@/lib/services/limits");
    const { readPlatformSettings } = await import("@/lib/platform-settings");
    const settings = await readPlatformSettings();
    const resources = clampResources(settings, svc.type as "discord" | "minecraft" | "web", {
      cpuMillicores: patch.cpuMillicores ?? svc.cpuLimit,
      memoryMb: patch.memoryMb ?? svc.memoryLimitMb,
      storageMb: patch.storageMb ?? svc.storageLimitMb,
    });
    await db
      .update(servicesTable)
      .set({
        name: patch.name ?? svc.name,
        description: patch.description ?? svc.description,
        cpuLimit: resources.cpuMillicores,
        memoryLimitMb: resources.memoryMb,
        storageLimitMb: resources.storageMb,
        restartPolicy: patch.restartPolicy ?? svc.restartPolicy,
        maxRestarts: patch.maxRestarts ?? svc.maxRestarts,
        updatedAt: new Date(),
      })
      .where(eq(servicesTable.id, id));
    await touchOwnerActivity(id);
    await audit({ userId: user.id, serviceId: id, action: "service.update" });
    return {
      ok: true,
      note: "Resource limits apply to the container on the next create/redeploy.",
    };
  });
}

export async function DELETE(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  return route(async () => {
    const user = await requireUser();
    const svc = await authorizeService(id, user.id, "owner");
    const payload = await body<{ name?: string; confirmDiskGone?: boolean }>(req);
    const check = validateServiceDelete(svc.name, String(payload.name ?? ""), payload.confirmDiskGone === true);
    if (!check.ok) throw new HttpError(400, deleteValidationMessage(check.code), check.code);
    const jobId = await createJob({
      type: "DELETE_CONTAINER",
      serviceId: id,
      userId: user.id,
      steps: ["Removing container", "Deleting volume", "Removing records"],
    });
    dispatch(deleteServiceJob(jobId, id));
    await audit({ userId: user.id, serviceId: id, action: "service.delete", detail: svc.name });
    return { jobId };
  });
}
