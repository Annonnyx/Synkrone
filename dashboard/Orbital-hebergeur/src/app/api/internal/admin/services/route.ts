import { desc, eq } from "drizzle-orm";
import { NextRequest } from "next/server";
import { db } from "@/db";
import { containers, services, users } from "@/db/schema";
import { route } from "@/lib/api";
import { requireInternalAdmin } from "@/lib/internal-admin";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  return route(async () => {
    requireInternalAdmin(req);
    const rows = await db
      .select({
        id: services.id,
        name: services.name,
        type: services.type,
        state: services.state,
        slug: services.slug,
        cpuLimit: services.cpuLimit,
        memoryLimitMb: services.memoryLimitMb,
        storageLimitMb: services.storageLimitMb,
        lastError: services.lastError,
        createdAt: services.createdAt,
        updatedAt: services.updatedAt,
        ownerId: services.ownerId,
        ownerName: users.name,
        ownerEmail: users.email,
      })
      .from(services)
      .leftJoin(users, eq(users.id, services.ownerId))
      .orderBy(desc(services.updatedAt));

    const withContainers = await Promise.all(
      rows.map(async (svc) => {
        const [c] = await db
          .select()
          .from(containers)
          .where(eq(containers.serviceId, svc.id))
          .orderBy(desc(containers.createdAt))
          .limit(1);
        return { ...svc, container: c ?? null };
      }),
    );
    return { services: withContainers };
  });
}
