import { count, eq } from "drizzle-orm";
import { db } from "@/db";
import { containers, services } from "@/db/schema";
import { route } from "@/lib/api";
import { requireUser } from "@/lib/auth";
import { docker, DOCKER_SOCKET } from "@/lib/docker/engine";
import { NETWORKS } from "@/lib/docker/adapter";
import { dataRoot } from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return route(async () => {
    const user = await requireUser();
    const ping = await docker.ping();
    const [{ value: serviceCount }] = await db
      .select({ value: count() })
      .from(services)
      .where(eq(services.ownerId, user.id));
    const [{ value: containerCount }] = await db.select({ value: count() }).from(containers);
    return {
      docker: {
        reachable: ping.ok,
        version: ping.version ?? null,
        error: ping.error ?? null,
        socket: DOCKER_SOCKET,
      },
      networks: NETWORKS,
      dataRoot: dataRoot(),
      imageMode: process.env.RUNTIME_IMAGE_MODE ?? "public",
      counts: { services: serviceCount, containers: containerCount },
    };
  });
}
