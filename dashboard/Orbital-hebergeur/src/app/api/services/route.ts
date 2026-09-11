import { NextRequest } from "next/server";
import { desc, eq } from "drizzle-orm";
import { db } from "@/db";
import { containers, services } from "@/db/schema";
import { body, route } from "@/lib/api";
import { requireUser } from "@/lib/auth";
import { createService, type CreateServiceInput } from "@/lib/services/create";

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

export async function POST(req: NextRequest) {
  return route(async () => {
    const user = await requireUser();
    const input = await body<CreateServiceInput>(req);
    return createService(user.id, input);
  });
}
