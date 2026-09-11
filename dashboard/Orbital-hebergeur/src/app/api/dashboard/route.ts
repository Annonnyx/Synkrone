import { desc, eq } from "drizzle-orm";
import { db } from "@/db";
import { auditLogs, containers, serviceDatabases, services } from "@/db/schema";
import { route } from "@/lib/api";
import { requireUser } from "@/lib/auth";
import { docker } from "@/lib/docker/engine";
import { getProvider } from "@/lib/runtime";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return route(async () => {
    const user = await requireUser();
    const rows = await db
      .select()
      .from(services)
      .where(eq(services.ownerId, user.id))
      .orderBy(desc(services.createdAt));

    const ping = await docker.ping();

    const enriched = await Promise.all(
      rows.map(async (svc) => {
        const [container] = await db
          .select()
          .from(containers)
          .where(eq(containers.serviceId, svc.id))
          .orderBy(desc(containers.createdAt))
          .limit(1);
        let stats = null;
        let state = svc.state;
        if (ping.ok && container?.dockerContainerId) {
          const provider = getProvider(svc.type);
          const status = await provider.status(svc.id).catch(() => null);
          if (status) state = status.state;
          if (status?.state === "RUNNING") {
            stats = await provider.stats(svc.id).catch(() => null);
          }
        }
        return {
          id: svc.id,
          name: svc.name,
          type: svc.type,
          state,
          slug: svc.slug,
          memoryLimitMb: svc.memoryLimitMb,
          cpuLimit: svc.cpuLimit,
          storageLimitMb: svc.storageLimitMb,
          lastError: svc.lastError,
          container: container
            ? { id: container.dockerContainerId, image: container.image, name: container.containerName }
            : null,
          stats,
        };
      }),
    );

    const activity = await db
      .select()
      .from(auditLogs)
      .where(eq(auditLogs.userId, user.id))
      .orderBy(desc(auditLogs.createdAt))
      .limit(12);

    const databases = await db
      .select()
      .from(serviceDatabases)
      .where(eq(serviceDatabases.ownerId, user.id));

    const totals = enriched.reduce(
      (acc, s) => {
        acc.memoryLimitMb += s.memoryLimitMb;
        acc.cpuMillicores += s.cpuLimit;
        acc.storageLimitMb += s.storageLimitMb;
        acc.memoryUsedMb += s.stats?.memoryMb ?? 0;
        acc.cpuPercent += s.stats?.cpuPercent ?? 0;
        acc.diskMb += s.stats?.diskMb ?? 0;
        acc.rxKb += s.stats?.networkRxKb ?? 0;
        acc.txKb += s.stats?.networkTxKb ?? 0;
        if (s.state === "RUNNING") acc.running += 1;
        if (s.state === "CRASHED" || s.state === "ERROR") acc.failing += 1;
        return acc;
      },
      {
        memoryLimitMb: 0,
        memoryUsedMb: 0,
        cpuMillicores: 0,
        cpuPercent: 0,
        storageLimitMb: 0,
        diskMb: 0,
        rxKb: 0,
        txKb: 0,
        running: 0,
        failing: 0,
      },
    );

    return {
      services: enriched,
      totals,
      activity,
      databases: databases.length,
      engine: { reachable: ping.ok, version: ping.version ?? null, error: ping.error ?? null },
      alerts: enriched
        .filter((s) => s.state === "CRASHED" || s.state === "ERROR")
        .map((s) => ({
          serviceId: s.id,
          name: s.name,
          state: s.state,
          message: s.lastError ?? "Service stopped unexpectedly",
        })),
    };
  });
}
