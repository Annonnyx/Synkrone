import { and, eq, or } from "drizzle-orm";
import { db } from "@/db";
import { projectMembers, services } from "@/db/schema";
import { HttpError } from "@/lib/auth";
import type { ServiceType } from "@/lib/paths";
import { DiscordRuntimeProvider } from "./discord";
import { MinecraftRuntimeProvider } from "./minecraft";
import { WebRuntimeProvider } from "./web";
import type { RuntimeProvider, ServiceRecord } from "./types";

const providers: Record<ServiceType, RuntimeProvider> = {
  discord: new DiscordRuntimeProvider(),
  minecraft: new MinecraftRuntimeProvider(),
  web: new WebRuntimeProvider(),
};

export function getProvider(type: ServiceType | string): RuntimeProvider {
  const provider = providers[type as ServiceType];
  if (!provider) throw new HttpError(400, `Unknown service type: ${type}`);
  return provider;
}

export type AuthorizedService = typeof services.$inferSelect & { role: string };

/**
 * The ONLY way route handlers obtain a service. Ownership / membership is
 * verified here, and every filesystem or Docker path is derived from the row
 * returned by this function (§44, §73, §74).
 */
export async function authorizeService(
  serviceId: string,
  userId: string,
  minRole: "viewer" | "member" | "admin" | "owner" = "member",
): Promise<AuthorizedService> {
  const rows = await db
    .select({ svc: services, memberRole: projectMembers.role })
    .from(services)
    .leftJoin(
      projectMembers,
      and(eq(projectMembers.projectId, services.projectId), eq(projectMembers.userId, userId)),
    )
    .where(and(eq(services.id, serviceId), or(eq(services.ownerId, userId), eq(projectMembers.userId, userId))))
    .limit(1);
  if (!rows.length) throw new HttpError(404, "Service not found");
  const role = rows[0].svc.ownerId === userId ? "owner" : (rows[0].memberRole ?? "viewer");
  const rank = { viewer: 0, member: 1, admin: 2, owner: 3 } as const;
  if (rank[role as keyof typeof rank] < rank[minRole]) {
    throw new HttpError(403, `Requires ${minRole} permission on this project`);
  }
  return { ...rows[0].svc, role };
}

export function toRecord(svc: typeof services.$inferSelect): ServiceRecord {
  return {
    id: svc.id,
    type: svc.type as ServiceType,
    name: svc.name,
    slug: svc.slug,
    ownerId: svc.ownerId,
    projectId: svc.projectId,
    cpuLimit: svc.cpuLimit,
    memoryLimitMb: svc.memoryLimitMb,
    storageLimitMb: svc.storageLimitMb,
    restartPolicy: svc.restartPolicy,
    maxRestarts: svc.maxRestarts,
  };
}

export * from "./types";
