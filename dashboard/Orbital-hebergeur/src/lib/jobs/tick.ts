import { eq } from "drizzle-orm";
import { db } from "@/db";
import { services } from "@/db/schema";
import { discordIdForUser } from "@/lib/oauth/accounts";
import { dmDiscordUser } from "@/lib/discord/owner-dm";
import { publicOrigin, panelUrl } from "@/lib/oauth/providers";
import { getProvider } from "@/lib/runtime";
import { appendConsole, setServiceState } from "@/lib/runtime/base";
import { deleteServiceJob } from "@/lib/jobs/handlers";
import { createJob, dispatch } from "@/lib/jobs/queue";
import { inactivityAction } from "@/lib/services/inactivity";
import { refreshStorageOverflow } from "@/lib/services/storage-enforce";
import { STORAGE_QUOTA_ERROR } from "@/lib/services/storage-quota";
import type { ServiceType } from "@/lib/paths";

const DEFAULT_TICK_MS = 15 * 60 * 1000;

function servicePanelUrl(serviceId: string): string {
  try {
    return panelUrl(publicOrigin(), `/dashboard/services/${serviceId}`).toString();
  } catch {
    return "";
  }
}

function suspendMessage(name: string, url: string): string {
  const link = url ? `\n${url}` : "";
  return (
    `[Synkrone] « ${name} » a été mis en pause après 30 jours sans activité dans le panneau. ` +
    `Le disque est conservé. Cliquez sur Reprendre sous 14 jours, sinon le service et ses fichiers seront supprimés.\n` +
    `Paused after 30 days idle. Resume within 14 days or it will be deleted.${link}`
  );
}

function warnMessage(name: string, url: string): string {
  const link = url ? `\n${url}` : "";
  return (
    `[Synkrone] « ${name} » sera définitivement supprimé dans 3 jours (pause sans reprise).\n` +
    `This service will be deleted in 3 days unless you Resume.${link}`
  );
}

async function notifyOwner(ownerId: string, content: string): Promise<void> {
  try {
    const discordId = await discordIdForUser(ownerId);
    if (!discordId) return;
    await dmDiscordUser(discordId, content);
  } catch {
    /* closed DMs / missing token */
  }
}

export async function enforceStorageQuotas(): Promise<void> {
  const rows = await db
    .select({
      id: services.id,
      type: services.type,
      state: services.state,
      storageLimitMb: services.storageLimitMb,
      storageOverflowAt: services.storageOverflowAt,
      lastError: services.lastError,
    })
    .from(services);
  for (const svc of rows) {
    if (svc.state === "CREATING" || svc.state === "DELETING") continue;
    try {
      const over = await refreshStorageOverflow(svc);
      if (over && svc.state === "RUNNING") {
        const provider = getProvider(svc.type as ServiceType);
        await provider.stop(svc.id).catch(() => undefined);
        await appendConsole(svc.id, "Stopped: storage quota exceeded", "stderr");
        await db
          .update(services)
          .set({ lastError: STORAGE_QUOTA_ERROR, updatedAt: new Date() })
          .where(eq(services.id, svc.id));
      }
    } catch (err) {
      console.error("[tick] storage", svc.id, err instanceof Error ? err.message : err);
    }
  }
}

export async function processInactivity(now = Date.now()): Promise<void> {
  const rows = await db.select().from(services);
  for (const svc of rows) {
    const action = inactivityAction({
      now,
      lastOwnerActivityAt: (svc.lastOwnerActivityAt ?? svc.createdAt).getTime(),
      suspendedAt: svc.suspendedAt?.getTime() ?? null,
      deletionWarnedAt: svc.deletionWarnedAt?.getTime() ?? null,
      state: svc.state,
    });
    try {
      if (action === "suspend") await suspendService(svc.id, svc.ownerId, svc.name, svc.type);
      else if (action === "warn-delete") await warnDeletion(svc.id, svc.ownerId, svc.name);
      else if (action === "delete") await deleteIdleService(svc.id, svc.ownerId);
    } catch (err) {
      console.error("[tick] inactivity", svc.id, action, err instanceof Error ? err.message : err);
    }
  }
}

async function suspendService(serviceId: string, ownerId: string, name: string, type: string) {
  const provider = getProvider(type as ServiceType);
  await provider.stop(serviceId).catch(() => undefined);
  await setServiceState(serviceId, "SUSPENDED");
  await db
    .update(services)
    .set({
      suspendedAt: new Date(),
      inactivityNotifiedAt: new Date(),
      updatedAt: new Date(),
    })
    .where(eq(services.id, serviceId));
  await appendConsole(serviceId, "Paused after 30 days without owner activity");
  await notifyOwner(ownerId, suspendMessage(name, servicePanelUrl(serviceId)));
}

async function warnDeletion(serviceId: string, ownerId: string, name: string) {
  await db
    .update(services)
    .set({ deletionWarnedAt: new Date(), updatedAt: new Date() })
    .where(eq(services.id, serviceId));
  await notifyOwner(ownerId, warnMessage(name, servicePanelUrl(serviceId)));
}

async function deleteIdleService(serviceId: string, ownerId: string) {
  await db.update(services).set({ state: "DELETING", updatedAt: new Date() }).where(eq(services.id, serviceId));
  const jobId = await createJob({
    type: "DELETE_CONTAINER",
    serviceId,
    userId: ownerId,
    steps: ["Removing container", "Deleting volume", "Removing records"],
    payload: { reason: "inactivity" },
  });
  dispatch(deleteServiceJob(jobId, serviceId));
}

export async function runPlatformTick(now = Date.now()): Promise<void> {
  await enforceStorageQuotas();
  await processInactivity(now);
}

let timer: ReturnType<typeof setInterval> | null = null;

export function startPlatformTick(): void {
  if (timer) return;
  const ms = Number(process.env.SYNKRONE_PLATFORM_TICK_MS || DEFAULT_TICK_MS);
  const interval = Number.isFinite(ms) && ms >= 30_000 ? ms : DEFAULT_TICK_MS;
  void runPlatformTick().catch((err) => console.error("[tick]", err));
  timer = setInterval(() => {
    void runPlatformTick().catch((err) => console.error("[tick]", err));
  }, interval);
}
