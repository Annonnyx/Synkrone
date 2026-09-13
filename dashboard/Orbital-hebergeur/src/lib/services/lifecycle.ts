import { eq } from "drizzle-orm";
import { db } from "@/db";
import { services } from "@/db/schema";
import { shouldRecordActivity } from "@/lib/services/inactivity";

export async function touchOwnerActivity(serviceId: string, now = Date.now()): Promise<void> {
  const [svc] = await db
    .select({
      suspendedAt: services.suspendedAt,
      lastOwnerActivityAt: services.lastOwnerActivityAt,
    })
    .from(services)
    .where(eq(services.id, serviceId))
    .limit(1);
  if (!svc) return;
  // Opening a paused service is not Resume — only the Resume/Start action clears pause.
  if (svc.suspendedAt) return;
  const last = svc.lastOwnerActivityAt?.getTime() ?? null;
  if (!shouldRecordActivity(last, now)) return;
  await db
    .update(services)
    .set({ lastOwnerActivityAt: new Date(now), updatedAt: new Date(now) })
    .where(eq(services.id, serviceId));
}

export async function clearSuspension(serviceId: string, now = Date.now()): Promise<void> {
  await db
    .update(services)
    .set({
      suspendedAt: null,
      inactivityNotifiedAt: null,
      deletionWarnedAt: null,
      lastOwnerActivityAt: new Date(now),
      updatedAt: new Date(now),
    })
    .where(eq(services.id, serviceId));
}
