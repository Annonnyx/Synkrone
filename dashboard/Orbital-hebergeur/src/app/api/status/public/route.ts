import { count } from "drizzle-orm";
import { db } from "@/db";
import { services } from "@/db/schema";
import { docker } from "@/lib/docker/engine";
import { isDatabaseUnavailable } from "@/lib/db-errors";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

function emptyHosting() {
  return { discord: 0, minecraft: 0, web: 0, total: 0, running: 0 };
}

export async function GET() {
  const hosting = emptyHosting();
  let dockerOk = false;
  try {
    const ping = await docker.ping();
    dockerOk = Boolean(ping.ok);
  } catch {
    dockerOk = false;
  }
  try {
    const rows = await db
      .select({
        type: services.type,
        state: services.state,
        n: count(),
      })
      .from(services)
      .groupBy(services.type, services.state);
    for (const row of rows) {
      const n = Number(row.n) || 0;
      hosting.total += n;
      if (row.type === "discord" || row.type === "minecraft" || row.type === "web") {
        hosting[row.type] += n;
      }
      if (row.state === "RUNNING") hosting.running += n;
    }
    return Response.json({ ok: true, docker: dockerOk, hosting });
  } catch (err) {
    if (isDatabaseUnavailable(err)) {
      return Response.json({ ok: false, docker: dockerOk, hosting: emptyHosting() });
    }
    return Response.json({ ok: false, docker: dockerOk, hosting: emptyHosting() });
  }
}
