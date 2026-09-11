import { NextRequest } from "next/server";
import path from "node:path";
import { and, eq } from "drizzle-orm";
import { db } from "@/db";
import { minecraftAddons, minecraftServers } from "@/db/schema";
import { body, fail, rateLimit, route } from "@/lib/api";
import { audit } from "@/lib/audit";
import { HttpError, requireUser } from "@/lib/auth";
import { FilesystemManager } from "@/lib/filesystem/manager";
import {
  ModrinthError,
  addonDirectory,
  addonKind,
  downloadStep,
  loaderCompat,
  resolveInstallPlan,
} from "@/lib/minecraft/modrinth";
import { authorizeService } from "@/lib/runtime";
import { appendConsole } from "@/lib/runtime/base";
import type { ServiceType } from "@/lib/paths";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 300;

const UPLOAD_EXTENSIONS = [".jar", ".zip"];
const MAX_UPLOAD_BYTES = 256 * 1024 * 1024;

type Ctx = { params: Promise<{ id: string }> };

async function minecraftContext(id: string, userId: string, minRole: "viewer" | "member") {
  const svc = await authorizeService(id, userId, minRole);
  if (svc.type !== "minecraft") throw new HttpError(400, "Not a Minecraft service");
  const [mc] = await db
    .select()
    .from(minecraftServers)
    .where(eq(minecraftServers.serviceId, id))
    .limit(1);
  if (!mc) throw new HttpError(400, "Minecraft configuration missing");
  return { svc, mc, fsm: new FilesystemManager(svc.type as ServiceType, svc.id) };
}

/** Keeps uploaded names inside the add-on directory and free of shell/path tricks. */
function safeFileName(name: string): string {
  const base = path.basename(name).replace(/[^A-Za-z0-9._+-]/g, "_");
  return base.replace(/^\.+/, "") || "addon.jar";
}

export async function GET(_req: NextRequest, ctx: Ctx) {
  const { id } = await ctx.params;
  return route(async () => {
    const user = await requireUser();
    const { svc, mc } = await minecraftContext(id, user.id, "viewer");
    const kind = addonKind(mc.software);
    return {
      software: mc.software,
      gameVersion: mc.version,
      kind,
      loaders: loaderCompat(mc.software),
      directory: kind === "none" ? null : addonDirectory(kind),
      addons: await db
        .select()
        .from(minecraftAddons)
        .where(eq(minecraftAddons.serviceId, svc.id)),
    };
  });
}

export async function POST(req: NextRequest, ctx: Ctx) {
  const { id } = await ctx.params;
  const contentType = req.headers.get("content-type") ?? "";

  return route(async () => {
    const user = await requireUser();
    rateLimit(`mods:write:${user.id}`, 60);
    const { svc, mc, fsm } = await minecraftContext(id, user.id, "member");

    /* ------------------------------ upload -------------------------------- */
    if (contentType.includes("multipart/form-data")) {
      const form = await req.formData();
      const file = form.get("file");
      if (!(file instanceof File)) return fail("file is required");
      const requested = String(form.get("kind") ?? "");
      const kind =
        requested === "plugin" || requested === "mod"
          ? requested
          : addonKind(mc.software) === "plugin"
            ? "plugin"
            : "mod";
      const fileName = safeFileName(file.name);
      const ext = path.extname(fileName).toLowerCase();
      if (!UPLOAD_EXTENSIONS.includes(ext))
        return fail(`Only ${UPLOAD_EXTENSIONS.join(" and ")} files are accepted`, 415);
      if (file.size > MAX_UPLOAD_BYTES) return fail("Upload exceeds the 256MB limit", 413);

      const dir = addonDirectory(kind);
      await fsm.mkdir(dir);
      await fsm.write(`${dir}/${fileName}`, Buffer.from(await file.arrayBuffer()));
      const [row] = await db
        .insert(minecraftAddons)
        .values({
          serviceId: svc.id,
          kind,
          name: fileName.replace(/\.(jar|zip)$/i, ""),
          fileName,
          sizeBytes: file.size,
          provider: "manual",
        })
        .returning();
      await appendConsole(svc.id, `Uploaded ${kind} ${fileName} - restart to load it`);
      await audit({
        userId: user.id,
        serviceId: svc.id,
        action: `minecraft.${kind}.upload`,
        detail: fileName,
      });
      return { addons: [row], warnings: [] };
    }

    /* --------------------------- Modrinth install -------------------------- */
    const payload = await body<{
      op?: "plan" | "install";
      projectId?: string;
      versionId?: string;
    }>(req);
    if (!payload.projectId) return fail("projectId is required");

    const kind = addonKind(mc.software);
    if (kind === "none")
      return fail(`${mc.software} servers do not load plugins or mods`, 400);

    try {
      const { steps, warnings } = await resolveInstallPlan({
        projectId: payload.projectId,
        versionId: payload.versionId,
        software: mc.software,
        gameVersion: mc.version,
      });

      if (payload.op === "plan") return { kind, steps, warnings };

      const dir = addonDirectory(kind);
      await fsm.mkdir(dir);
      const installed: Array<typeof minecraftAddons.$inferSelect> = [];

      for (const step of steps) {
        const existing = await db
          .select()
          .from(minecraftAddons)
          .where(
            and(
              eq(minecraftAddons.serviceId, svc.id),
              eq(minecraftAddons.projectId, step.projectId),
            ),
          )
          .limit(1);

        const buffer = await downloadStep(step);
        const fileName = safeFileName(step.fileName);
        await fsm.write(`${dir}/${fileName}`, buffer);

        if (existing[0]) {
          // Replacing an add-on: drop the previous jar so both do not load.
          if (existing[0].fileName !== fileName) {
            await fsm.remove(`${dir}/${existing[0].fileName}`).catch(() => undefined);
            await fsm.remove(`${dir}/${existing[0].fileName}.disabled`).catch(() => undefined);
          }
          const [row] = await db
            .update(minecraftAddons)
            .set({
              kind,
              name: step.title,
              version: step.versionNumber,
              fileName,
              enabled: true,
              sizeBytes: buffer.byteLength,
              provider: "modrinth",
              versionId: step.versionId,
              iconUrl: step.iconUrl,
              sourceUrl: step.url,
              dependency: existing[0].dependency && step.dependency,
            })
            .where(eq(minecraftAddons.id, existing[0].id))
            .returning();
          installed.push(row);
          continue;
        }

        const [row] = await db
          .insert(minecraftAddons)
          .values({
            serviceId: svc.id,
            kind,
            name: step.title,
            version: step.versionNumber,
            fileName,
            sizeBytes: buffer.byteLength,
            provider: "modrinth",
            projectId: step.projectId,
            versionId: step.versionId,
            iconUrl: step.iconUrl,
            sourceUrl: step.url,
            summary: null,
            dependency: step.dependency,
          })
          .returning();
        installed.push(row);
      }

      const names = installed.map((a) => a.name).join(", ");
      await appendConsole(svc.id, `Installed ${kind}: ${names} - restart to load`);
      await audit({
        userId: user.id,
        serviceId: svc.id,
        action: `minecraft.${kind}.install`,
        detail: names,
      });
      return { addons: installed, warnings };
    } catch (err) {
      if (err instanceof ModrinthError) return fail(err.message, err.status);
      throw err;
    }
  });
}
