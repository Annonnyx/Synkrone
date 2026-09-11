import { eq } from "drizzle-orm";
import { NextRequest } from "next/server";
import { db } from "@/db";
import { services } from "@/db/schema";
import { body, fail, route } from "@/lib/api";
import { HttpError } from "@/lib/auth";
import { FilesystemManager } from "@/lib/filesystem/manager";
import { requireInternalAdmin } from "@/lib/internal-admin";
import { getProvider, toRecord } from "@/lib/runtime";
import type { ServiceType } from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Ctx = { params: Promise<{ id: string; action: string }> };

async function loadService(id: string) {
  const rows = await db.select().from(services).where(eq(services.id, id)).limit(1);
  if (!rows.length) throw new HttpError(404, "Service introuvable");
  return rows[0];
}

export async function GET(req: NextRequest, ctx: Ctx) {
  return route(async () => {
    requireInternalAdmin(req);
    const { id, action } = await ctx.params;
    const svc = await loadService(id);
    if (action === "files") {
      const dir = req.nextUrl.searchParams.get("path") || "/";
      const fsm = new FilesystemManager(svc.type as ServiceType, svc.id);
      return { path: dir, entries: await fsm.list(dir) };
    }
    if (action === "file") {
      const file = req.nextUrl.searchParams.get("path");
      if (!file) return fail("path requis");
      const fsm = new FilesystemManager(svc.type as ServiceType, svc.id);
      return { path: file, content: await fsm.read(file) };
    }
    if (action === "status") {
      return getProvider(svc.type).status(id);
    }
    return fail("Action inconnue", 404);
  });
}

export async function POST(req: NextRequest, ctx: Ctx) {
  return route(async () => {
    requireInternalAdmin(req);
    const { id, action } = await ctx.params;
    const svc = await loadService(id);
    const provider = getProvider(svc.type);

    if (action === "start" || action === "stop" || action === "restart" || action === "kill") {
      await provider[action](id);
      return { ok: true, status: await provider.status(id) };
    }
    if (action === "file") {
      const payload = await body<{ path?: string; content?: string }>(req);
      if (!payload.path) return fail("path requis");
      const fsm = new FilesystemManager(svc.type as ServiceType, svc.id);
      await fsm.write(payload.path, String(payload.content ?? ""));
      return { ok: true, path: payload.path };
    }
    if (action === "recreate") {
      await provider.remove(id);
      await provider.create(toRecord(svc));
      await provider.start(id);
      return { ok: true };
    }
    return fail("Action inconnue", 404);
  });
}
