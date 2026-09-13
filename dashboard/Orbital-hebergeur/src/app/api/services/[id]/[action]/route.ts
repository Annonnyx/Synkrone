import { NextRequest, NextResponse } from "next/server";
import path from "node:path";
import fs from "node:fs/promises";
import { and, asc, desc, eq, gte } from "drizzle-orm";
import { db } from "@/db";
import {
  backups,
  consoleLines,
  deployments,
  discordBots,
  domains,
  envVars,
  metricSamples,
  minecraftAddons,
  minecraftServers,
  serviceDatabases,
  sftpCredentials,
  webProjects,
} from "@/db/schema";
import { body, fail, rateLimit, route } from "@/lib/api";
import { audit } from "@/lib/audit";
import { HttpError, requireUser, type SessionUser } from "@/lib/auth";
import { decryptSecret, encryptSecret, fingerprint } from "@/lib/crypto";
import { FilesystemManager } from "@/lib/filesystem/manager";
import { createLineGate, createLineSplitter, isConsoleNoise } from "@/lib/console/line-gate";
import { consoleLineFields } from "@/lib/console/docker-log";
import { getWallet } from "@/lib/krones/store";
import { canEditCommandSources, isProtectedBotSource, isVolumeRoot } from "@/lib/discord/source-lock";
import { authorizeService, getProvider, toRecord, type AuthorizedService } from "@/lib/runtime";
import { appendConsole } from "@/lib/runtime/base";
import { MINECRAFT_SOFTWARE, resolveGatewayIntents } from "@/lib/runtime/templates";
import { parseProperties, serializeProperties } from "@/lib/runtime/minecraft";
import { normalizeProperties } from "@/lib/minecraft/properties";
import { applicationIdFromToken, isDiscordToken } from "@/lib/discord/token";
import { normalizeBotPrefix } from "@/lib/discord/prefix";
import { withRequiredConfigCommand } from "@/lib/discord/ensure-config";
import { backupsDir, type ServiceType } from "@/lib/paths";
import { createJob, dispatch } from "@/lib/jobs/queue";
import {
  BACKUP_STEPS,
  DEPLOY_STEPS,
  RESTORE_STEPS,
  createBackupJob,
  deployWeb,
  restoreBackupJob,
} from "@/lib/jobs/handlers";
import { DatabaseManager } from "@/lib/database/manager";
import { SFTPManager, publicSftpEndpoint } from "@/lib/sftp/manager";
import { dnsRecordsFor, normalizeHostname } from "@/lib/domains/public";
import { syncTraefikConfig } from "@/lib/domains/traefik";
import { touchOwnerActivity, clearSuspension } from "@/lib/services/lifecycle";
import { assertServiceWriteFits, refreshStorageOverflow } from "@/lib/services/storage-enforce";
import { STORAGE_QUOTA_ERROR } from "@/lib/services/storage-quota";
import { isPerServiceSftpSecret } from "@/lib/sftp/password";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";
export const maxDuration = 60;

type Ctx = { params: Promise<{ id: string; action: string }> };

async function ctxService(
  id: string,
  minRole: "viewer" | "member" | "admin" | "owner" = "member",
): Promise<{ user: SessionUser; svc: AuthorizedService }> {
  const user = await requireUser();
  const svc = await authorizeService(id, user.id, minRole);
  return { user, svc };
}

function fsFor(svc: AuthorizedService) {
  return new FilesystemManager(svc.type as ServiceType, svc.id);
}

async function assertCommandSourceAccess(
  userId: string,
  svc: AuthorizedService,
  paths: Array<string | undefined>,
  opts: { tree?: boolean } = {},
) {
  if (svc.type !== "discord") return;
  const locked = paths.some((item) => {
    if (item == null) return false;
    if (isProtectedBotSource(item)) return true;
    return Boolean(opts.tree && isVolumeRoot(item));
  });
  if (!locked) return;
  const wallet = await getWallet(userId);
  if (canEditCommandSources(wallet)) return;
  throw new HttpError(403, "COMMAND_SOURCES_LOCKED");
}

/* ----------------------------------- GET ---------------------------------- */

export async function GET(req: NextRequest, ctx: Ctx) {
  const { id, action } = await ctx.params;
  const url = new URL(req.url);

  if (action === "stream") {
    try {
      const { svc } = await ctxService(id, "viewer");
      return streamConsole(svc);
    } catch (err) {
      return fail((err as Error).message, err instanceof HttpError ? err.status : 500);
    }
  }

  return route(async () => {
    const { user, svc } = await ctxService(id, "viewer");
    const provider = getProvider(svc.type);

    switch (action) {
      case "status":
        return provider.status(id);
      case "stats":
        return provider.stats(id);
      case "metrics": {
        const rows = await db
          .select()
          .from(metricSamples)
          .where(eq(metricSamples.serviceId, id))
          .orderBy(desc(metricSamples.createdAt))
          .limit(60);
        return { samples: rows.reverse() };
      }
      case "logs": {
        const tail = Number(url.searchParams.get("tail") ?? 300);
        try {
          return { source: "docker", logs: await provider.logs(id, tail) };
        } catch (err) {
          const rows = await db
            .select()
            .from(consoleLines)
            .where(eq(consoleLines.serviceId, id))
            .orderBy(desc(consoleLines.createdAt))
            .limit(tail);
          return {
            source: "panel",
            reason: (err as Error).message,
            logs: rows
              .reverse()
              .map((l) => `[${l.createdAt.toISOString().slice(11, 19)}] ${l.message}`)
              .join("\n"),
          };
        }
      }
      case "files": {
        const op = url.searchParams.get("op") ?? "list";
        const target = url.searchParams.get("path") ?? "/";
        const fsm = fsFor(svc);
        if (op === "read") {
          await assertCommandSourceAccess(user.id, svc, [target]);
          return { path: target, content: await fsm.read(target) };
        }
        if (op === "download") {
          await assertCommandSourceAccess(user.id, svc, [target]);
          const buffer = await fsm.readBuffer(target);
          return new NextResponse(new Uint8Array(buffer), {
            headers: {
              "Content-Type": "application/octet-stream",
              "Content-Disposition": `attachment; filename="${path.basename(target)}"`,
            },
          });
        }
        if (op === "archive") {
          await assertCommandSourceAccess(user.id, svc, [target], { tree: true });
          const { name, buffer } = await fsm.zip(target);
          return new NextResponse(new Uint8Array(buffer), {
            headers: {
              "Content-Type": "application/gzip",
              "Content-Disposition": `attachment; filename="${name}"`,
            },
          });
        }
        return { path: target, entries: await fsm.list(target) };
      }
      case "deployments":
        return {
          deployments: await db
            .select()
            .from(deployments)
            .where(eq(deployments.serviceId, id))
            .orderBy(desc(deployments.number)),
        };
      case "addons":
        return {
          addons: await db
            .select()
            .from(minecraftAddons)
            .where(eq(minecraftAddons.serviceId, id)),
        };
      case "minecraft": {
        const fsm = fsFor(svc);
        const raw = (await fsm.exists("server.properties"))
          ? await fsm.read("server.properties")
          : "";
        const [mc] = await db
          .select()
          .from(minecraftServers)
          .where(eq(minecraftServers.serviceId, id));
        return { raw, parsed: parseProperties(raw), server: mc ?? null };
      }
      case "sftp": {
        const [row] = await db
          .select()
          .from(sftpCredentials)
          .where(eq(sftpCredentials.serviceId, id));
        const plain = row ? decryptSecret(row.passwordEnc) : null;
        return {
          sftp: row
            ? {
                ...row,
                passwordEnc: undefined,
                hasPassword: isPerServiceSftpSecret(plain),
                ...publicSftpEndpoint(),
              }
            : null,
        };
      }
      case "backups":
        return {
          backups: await db
            .select()
            .from(backups)
            .where(eq(backups.serviceId, id))
            .orderBy(desc(backups.createdAt)),
        };
      default:
        return fail(`Unknown action: ${action}`, 404);
    }
  });
}

function streamConsole(svc: AuthorizedService) {
  const provider = getProvider(svc.type);
  const encoder = new TextEncoder();
  const abort = new AbortController();

  // Assigned by start() and invoked by cancel(): without it the poll below keeps
  // querying the database and the engine long after the client is gone, and every
  // reconnect stacks another one on top.
  let stop = () => abort.abort();

  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      let closed = false;
      let poll: ReturnType<typeof setInterval> | undefined;
      let deadline: ReturnType<typeof setTimeout> | undefined;

      stop = () => {
        if (closed) return;
        closed = true;
        clearInterval(poll);
        clearTimeout(deadline);
        abort.abort();
        try {
          controller.close();
        } catch {
          /* already closed */
        }
      };

      const send = (payload: unknown) => {
        if (closed) return;
        try {
          controller.enqueue(encoder.encode(`data: ${JSON.stringify(payload)}\n\n`));
        } catch {
          stop();
        }
      };

      const history = (
        await db
          .select()
          .from(consoleLines)
          .where(eq(consoleLines.serviceId, svc.id))
          .orderBy(desc(consoleLines.createdAt))
          .limit(200)
      ).reverse();

      // Postgres keeps microseconds on these timestamps while a JS Date only
      // keeps milliseconds, so a bound built from a Date re-selects the rows it
      // was supposed to exclude. The ids already delivered in that millisecond
      // are tracked instead of relying on the truncated bound alone.
      let lastSeen = history.length ? history[history.length - 1].createdAt : new Date(0);
      let delivered = new Set(
        history.filter((l) => l.createdAt.getTime() >= lastSeen.getTime()).map((l) => l.id),
      );
      for (const line of history) {
        if (isConsoleNoise(line.message)) continue;
        const fields = consoleLineFields(line.message, line.createdAt);
        if (isConsoleNoise(fields.message)) continue;
        send({ type: "line", stream: line.stream, message: fields.message, at: fields.at });
      }

      const gate = createLineGate(240, 1000);
      let lastDropNotice = 0;
      const emitLive = (stream: string, message: string) => {
        const fields = consoleLineFields(message);
        if (isConsoleNoise(fields.message)) return;
        if (gate.allow(1) < 1) return;
        send({ type: "line", stream, message: fields.message, at: fields.at });
      };
      const splitter = createLineSplitter(emitLive);

      try {
        const iterable = await provider.followLogs(svc.id, abort.signal);
        send({ type: "info", message: "Attached to container stdout/stderr" });
        void (async () => {
          try {
            for await (const piece of iterable) {
              splitter.push(piece.stream, piece.text);
              const dropped = gate.takeDropped();
              const now = Date.now();
              if (dropped > 0 && now - lastDropNotice > 2500) {
                lastDropNotice = now;
                send({
                  type: "info",
                  message: `Condensed ${dropped} log lines`,
                });
              }
            }
          } catch {
            /* stream closed */
          } finally {
            splitter.flush();
          }
        })();
      } catch (err) {
        send({ type: "info", message: `Container output unavailable: ${(err as Error).message}` });
      }

      let lastState: string | undefined;
      const emitStatus = async () => {
        const status = await provider.status(svc.id);
        if (status.state === lastState) return;
        lastState = status.state;
        send({ type: "status", status });
      };
      void emitStatus();

      poll = setInterval(async () => {
        if (closed) return;
        try {
          const rows = await db
            .select()
            .from(consoleLines)
            .where(and(eq(consoleLines.serviceId, svc.id), gte(consoleLines.createdAt, lastSeen)))
            .orderBy(asc(consoleLines.createdAt))
            .limit(100);
          for (const line of rows) {
            if (delivered.has(line.id)) continue;
            if (line.createdAt.getTime() > lastSeen.getTime()) lastSeen = line.createdAt;
            if (isConsoleNoise(line.message)) continue;
            const fields = consoleLineFields(line.message, line.createdAt);
            if (isConsoleNoise(fields.message)) continue;
            send({ type: "line", stream: line.stream, message: fields.message, at: fields.at });
          }
          delivered = new Set(
            rows.filter((l) => l.createdAt.getTime() >= lastSeen.getTime()).map((l) => l.id),
          );
          await emitStatus();
        } catch {
          /* keep the stream alive */
        }
      }, 3000);

      deadline = setTimeout(stop, 30 * 60 * 1000);
    },
    cancel() {
      stop();
    },
  });

  return new NextResponse(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}

/* ---------------------------------- POST ---------------------------------- */

export async function POST(req: NextRequest, ctx: Ctx) {
  const { id, action } = await ctx.params;

  return route(async () => {
    const { user, svc } = await ctxService(id, "member");
    const provider = getProvider(svc.type);
    rateLimit(`svc:${user.id}:${action}`, 180);

    switch (action) {
      case "activity": {
        await touchOwnerActivity(id);
        return { ok: true };
      }
      case "resume":
      case "start":
      case "stop":
      case "restart":
      case "kill": {
        if (action === "start" || action === "resume" || action === "restart") {
          if (svc.storageOverflowAt) throw new HttpError(403, STORAGE_QUOTA_ERROR);
        }
        if (action === "start" || action === "resume") {
          if (svc.suspendedAt || svc.state === "SUSPENDED") await clearSuspension(id);
        }
        const op = (action === "resume" ? "start" : action) as "start" | "stop" | "restart" | "kill";
        await provider[op](id);
        await touchOwnerActivity(id);
        await audit({ userId: user.id, serviceId: id, action: `service.${op}` });
        return { ok: true, status: await provider.status(id) };
      }
      case "recreate": {
        if (svc.storageOverflowAt) throw new HttpError(403, STORAGE_QUOTA_ERROR);
        if (svc.suspendedAt || svc.state === "SUSPENDED") await clearSuspension(id);
        await provider.remove(id);
        const created = await provider.create(toRecord(svc));
        await provider.start(id);
        await touchOwnerActivity(id);
        await audit({ userId: user.id, serviceId: id, action: "service.recreate" });
        return { ok: true, container: created.containerId };
      }
      case "command": {
        const { command } = await body<{ command: string }>(req);
        if (!command?.trim()) return fail("command is required");
        const output = await provider.sendCommand(id, command.trim());
        await touchOwnerActivity(id);
        await audit({ userId: user.id, serviceId: id, action: "service.command", detail: command });
        return { output };
      }
      case "files": {
        const contentType = req.headers.get("content-type") ?? "";
        const fsm = fsFor(svc);
        if (contentType.includes("multipart/form-data")) {
          const form = await req.formData();
          const file = form.get("file");
          const dir = String(form.get("path") ?? "/");
          if (!(file instanceof File)) return fail("file is required");
          if (file.size > 512 * 1024 * 1024) return fail("Upload exceeds the 512MB limit", 413);
          const dest = path.posix.join(dir, path.basename(file.name));
          await assertCommandSourceAccess(user.id, svc, [dir, dest]);
          const buffer = Buffer.from(await file.arrayBuffer());
          await assertServiceWriteFits(svc, buffer.length);
          await fsm.write(dest, buffer);
          await touchOwnerActivity(id);
          await audit({ userId: user.id, serviceId: id, action: "files.upload", detail: file.name });
          return { ok: true, name: file.name, size: file.size };
        }
        const payload = await body<{
          op: string;
          path?: string;
          content?: string;
          from?: string;
          to?: string;
          destination?: string;
        }>(req);
        switch (payload.op) {
          case "write":
            if (!payload.path) return fail("path is required");
            await assertCommandSourceAccess(user.id, svc, [payload.path]);
            await assertServiceWriteFits(svc, Buffer.byteLength(payload.content ?? "", "utf8"));
            await fsm.write(payload.path, payload.content ?? "");
            await touchOwnerActivity(id);
            await audit({ userId: user.id, serviceId: id, action: "files.write", detail: payload.path });
            return { ok: true };
          case "mkdir":
            if (!payload.path) return fail("path is required");
            await assertCommandSourceAccess(user.id, svc, [payload.path]);
            await assertServiceWriteFits(svc, 4096);
            await fsm.mkdir(payload.path);
            await touchOwnerActivity(id);
            return { ok: true };
          case "rename":
            if (!payload.from || !payload.to) return fail("from and to are required");
            await assertCommandSourceAccess(user.id, svc, [payload.from, payload.to]);
            await fsm.rename(payload.from, payload.to);
            await touchOwnerActivity(id);
            return { ok: true };
          case "copy":
            if (!payload.from || !payload.to) return fail("from and to are required");
            await assertCommandSourceAccess(user.id, svc, [payload.from, payload.to]);
            await assertServiceWriteFits(svc, await fsm.sizeOf(payload.from));
            await fsm.copy(payload.from, payload.to);
            await touchOwnerActivity(id);
            return { ok: true };
          case "unzip":
            if (!payload.path) return fail("path is required");
            await assertCommandSourceAccess(user.id, svc, [payload.path, payload.destination ?? "/"], {
              tree: true,
            });
            await assertServiceWriteFits(svc, await fsm.sizeOf(payload.path));
            await fsm.unzip(payload.path, payload.destination ?? "/");
            await touchOwnerActivity(id);
            return { ok: true };
          default:
            return fail(`Unknown file operation: ${payload.op}`);
        }
      }
      case "env": {
        const { key, value, secret } = await body<{
          key: string;
          value: string;
          secret?: boolean;
        }>(req);
        if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key ?? ""))
          return fail("Invalid environment variable name");
        await db
          .insert(envVars)
          .values({
            serviceId: id,
            key,
            valueEnc: encryptSecret(value ?? ""),
            secret: secret ?? /token|secret|password|key/i.test(key),
          })
          .onConflictDoUpdate({
            target: [envVars.serviceId, envVars.key],
            set: { valueEnc: encryptSecret(value ?? "") },
          });
        await audit({ userId: user.id, serviceId: id, action: "env.set", detail: key });
        return { ok: true, note: "Recreate the container to apply the new environment" };
      }
      case "backups": {
        const payload = await body<{ op?: string; backupId?: string }>(req);
        if (payload.op === "restore" && payload.backupId) {
          const jobId = await createJob({
            type: "RESTORE_BACKUP",
            serviceId: id,
            userId: user.id,
            steps: RESTORE_STEPS,
          });
          dispatch(restoreBackupJob(jobId, id, payload.backupId));
          await audit({ userId: user.id, serviceId: id, action: "backup.restore" });
          return { jobId };
        }
        const fileName = `backup-${new Date().toISOString().replace(/[:.]/g, "-")}.tar.gz`;
        const [backup] = await db
          .insert(backups)
          .values({ serviceId: id, fileName, status: "PENDING" })
          .returning();
        const jobId = await createJob({
          type: "CREATE_BACKUP",
          serviceId: id,
          userId: user.id,
          steps: BACKUP_STEPS,
        });
        dispatch(createBackupJob(jobId, id, backup.id));
        await audit({ userId: user.id, serviceId: id, action: "backup.create" });
        return { jobId, backup };
      }
      case "deploy": {
        if (svc.type !== "web") return fail("Deployments are only available for web projects");
        const payload = await body<{ rollbackTo?: string }>(req);
        let commitSha: string | null = null;
        let trigger = "manual";
        if (payload.rollbackTo) {
          const [target] = await db
            .select()
            .from(deployments)
            .where(and(eq(deployments.id, payload.rollbackTo), eq(deployments.serviceId, id)))
            .limit(1);
          if (!target) return fail("Deployment not found", 404);
          commitSha = target.commitSha;
          trigger = `rollback:#${target.number}`;
        }
        const [last] = await db
          .select({ n: deployments.number })
          .from(deployments)
          .where(eq(deployments.serviceId, id))
          .orderBy(desc(deployments.number))
          .limit(1);
        const [deployment] = await db
          .insert(deployments)
          .values({
            serviceId: id,
            number: (last?.n ?? 0) + 1,
            trigger: payload.rollbackTo ? "rollback" : "manual",
            commitSha,
          })
          .returning();
        const jobId = await createJob({
          type: "DEPLOY_WEB",
          serviceId: id,
          userId: user.id,
          steps: DEPLOY_STEPS,
        });
        dispatch(deployWeb(jobId, id, deployment.id, trigger));
        await audit({ userId: user.id, serviceId: id, action: "web.deploy", detail: trigger });
        return { jobId, deployment };
      }
      case "discord": {
        const payload = await body<{
          op: "config" | "token";
          token?: string;
          applicationId?: string;
          prefix?: string;
          slashCommands?: boolean;
          modules?: string[];
          intents?: string[];
          commands?: Array<{
            name: string;
            enabled: boolean;
            cooldown?: number;
            response?: string;
          }>;
        }>(req);
        const [bot] = await db.select().from(discordBots).where(eq(discordBots.serviceId, id));
        if (!bot) return fail("Not a Discord service", 400);

        if (payload.op === "token") {
          const token = (payload.token ?? "").trim();
          if (token === "") {
            await db
              .update(discordBots)
              .set({ tokenEnc: null, tokenFingerprint: null })
              .where(eq(discordBots.id, bot.id));
            await audit({ userId: user.id, serviceId: id, action: "discord.token.clear" });
            return { ok: true, hasToken: false, note: "Token removed. The bot cannot log in." };
          }
          if (!isDiscordToken(token))
            return fail(
              "That does not look like a bot token. Copy it from Developer Portal > Bot > Reset Token.",
            );
          const applicationId =
            payload.applicationId?.trim() ||
            bot.applicationId ||
            applicationIdFromToken(token);
          const tokenEnc = encryptSecret(token);
          if (decryptSecret(tokenEnc) !== token) {
            return fail(
              "BOT_TOKEN could not be encrypted with the current server key. Check PLATFORM_SECRET_KEY.",
              500,
            );
          }
          await db
            .update(discordBots)
            .set({
              tokenEnc,
              tokenFingerprint: fingerprint(token),
              applicationId,
            })
            .where(eq(discordBots.id, bot.id));
          await audit({ userId: user.id, serviceId: id, action: "discord.token.rotate" });
          return {
            ok: true,
            hasToken: true,
            fingerprint: fingerprint(token),
            note: "Stored encrypted. Recreate the container to inject the new token.",
          };
        }

        const commands = withRequiredConfigCommand(
          (bot.commands ?? []).map((c) => {
            const update = payload.commands?.find((p) => p.name === c.name);
            return update
              ? {
                  ...c,
                  enabled: update.enabled,
                  cooldown: update.cooldown ?? c.cooldown,
                  response: update.response ?? c.response,
                }
              : c;
          }),
        );
        const modules = payload.modules ?? bot.modules;
        if (payload.applicationId !== undefined && !/^\d{0,25}$/.test(payload.applicationId.trim()))
          return fail("The application ID is the numeric snowflake of your Discord application");
        let prefix = bot.prefix;
        if (payload.prefix !== undefined) {
          const parsed = normalizeBotPrefix(payload.prefix);
          if (!parsed) return fail("Prefix must be 1–10 characters, without line breaks.");
          prefix = parsed;
        }
        const intents = payload.intents
          ? resolveGatewayIntents(payload.intents, modules)
          : payload.modules
            ? resolveGatewayIntents(undefined, modules)
            : bot.intents;
        const onlyRuntime =
          payload.modules === undefined &&
          payload.intents === undefined &&
          payload.commands === undefined;
        await db
          .update(discordBots)
          .set({
            prefix,
            slashCommands: true,
            applicationId:
              payload.applicationId !== undefined
                ? payload.applicationId.trim() || null
                : bot.applicationId,
            modules,
            intents,
            commands,
          })
          .where(eq(discordBots.id, bot.id));
        const provider = getProvider("discord");
        const record = toRecord(svc);
        if (onlyRuntime && typeof provider.syncPlatformRuntime === "function") {
          await provider.syncPlatformRuntime(record);
          await appendConsole(id, "Bot prefix and slash settings updated - restart to apply");
        } else {
          await provider.scaffold(record);
          await appendConsole(id, "Bot configuration regenerated - restart to apply");
        }
        await audit({ userId: user.id, serviceId: id, action: "discord.config" });
        return { ok: true };
      }
      case "minecraft": {
        const payload = await body<{
          op: "properties" | "eula" | "runtime";
          properties?: Record<string, string>;
          remove?: string[];
          raw?: string;
          replace?: boolean;
          software?: string;
          version?: string;
        }>(req);
        const [mc] = await db
          .select()
          .from(minecraftServers)
          .where(eq(minecraftServers.serviceId, id));
        if (!mc) return fail("Not a Minecraft service", 400);
        if (payload.op === "eula") {
          await db
            .update(minecraftServers)
            .set({ eulaAccepted: true })
            .where(eq(minecraftServers.id, mc.id));
          await fsFor(svc).write("eula.txt", "eula=true\n");
          return { ok: true };
        }
        if (payload.op === "runtime") {
          const software = payload.software ?? mc.software;
          const version = (payload.version ?? mc.version).trim();
          if (!MINECRAFT_SOFTWARE.some((s) => s.id === software))
            return fail(`Unknown Minecraft software: ${software}`);
          if (!/^[0-9][0-9A-Za-z.\-_]{0,31}$/.test(version)) return fail("Invalid version");
          await db
            .update(minecraftServers)
            .set({ software, version })
            .where(eq(minecraftServers.id, mc.id));
          await appendConsole(id, `Server software set to ${software} ${version}`);
          await audit({
            userId: user.id,
            serviceId: id,
            action: "minecraft.runtime",
            detail: `${software} ${version}`,
          });
          return {
            ok: true,
            software,
            version,
            note: "Recreate the container to download and run this build.",
          };
        }
        const submitted = normalizeProperties(
          payload.raw ? parseProperties(payload.raw) : (payload.properties ?? {}),
        );
        const base = payload.replace || payload.raw ? {} : (mc.properties ?? {});
        const next: Record<string, string> = { ...base, ...submitted };
        for (const key of payload.remove ?? []) delete next[key];
        // The Java port belongs to the platform's allocation, never to the form.
        next["server-port"] = String(mc.javaPort);
        await db
          .update(minecraftServers)
          .set({ properties: next })
          .where(eq(minecraftServers.id, mc.id));
        await fsFor(svc).write("server.properties", serializeProperties(next));
        await audit({ userId: user.id, serviceId: id, action: "minecraft.properties" });
        return { ok: true, properties: next };
      }
      case "addons": {
        const form = await req.formData();
        const file = form.get("file");
        const kind = String(form.get("kind") ?? "plugin") as "plugin" | "mod";
        if (!(file instanceof File)) return fail("file is required");
        if (!file.name.endsWith(".jar")) return fail("Only .jar files are accepted");
        const dir = kind === "plugin" ? "plugins" : "mods";
        const buffer = Buffer.from(await file.arrayBuffer());
        await assertServiceWriteFits(svc, buffer.length);
        await fsFor(svc).write(`${dir}/${path.basename(file.name)}`, buffer);
        const [row] = await db
          .insert(minecraftAddons)
          .values({
            serviceId: id,
            kind,
            name: file.name.replace(/\.jar$/, ""),
            fileName: path.basename(file.name),
            sizeBytes: file.size,
          })
          .returning();
        await audit({ userId: user.id, serviceId: id, action: `minecraft.${kind}.upload` });
        return { addon: row };
      }
      case "sftp": {
        const creds = await SFTPManager.rotate(id);
        await touchOwnerActivity(id);
        await audit({ userId: user.id, serviceId: id, action: "sftp.rotate" });
        return creds;
      }
      case "database": {
        const provisioned = await DatabaseManager.create(svc.slug.replace(/-/g, "_"));
        const [row] = await db
          .insert(serviceDatabases)
          .values({
            ownerId: user.id,
            serviceId: id,
            engine: "postgres",
            dbName: provisioned.dbName,
            dbUser: provisioned.dbUser,
            passwordEnc: encryptSecret(provisioned.password),
            host: provisioned.host,
            port: provisioned.port,
          })
          .returning();
        const conn = DatabaseManager.connectionString(provisioned);
        await db
          .insert(envVars)
          .values({
            serviceId: id,
            key: "DATABASE_URL",
            valueEnc: encryptSecret(conn),
            secret: true,
          })
          .onConflictDoUpdate({
            target: [envVars.serviceId, envVars.key],
            set: { valueEnc: encryptSecret(conn) },
          });
        await audit({ userId: user.id, serviceId: id, action: "database.create" });
        return {
          database: { ...row, passwordEnc: undefined },
          password: provisioned.password,
          connectionString: conn,
        };
      }
      case "domains": {
        if (svc.type !== "web") return fail("Domains are only available on web services", 400);
        const { hostname: rawHost, https, kind } = await body<{
          hostname: string;
          https?: boolean;
          kind?: "default" | "custom";
        }>(req);
        const hostname = normalizeHostname(rawHost);
        if (!hostname) return fail("Invalid hostname");
        const [taken] = await db.select().from(domains).where(eq(domains.hostname, hostname)).limit(1);
        if (taken) return fail("This hostname is already in use", 409);
        const [row] = await db
          .insert(domains)
          .values({
            serviceId: id,
            hostname,
            kind: kind === "default" ? "default" : "custom",
            https: https ?? true,
            status: "PENDING",
          })
          .returning();
        const [web] = await db.select().from(webProjects).where(eq(webProjects.serviceId, id));
        const written = await syncTraefikConfig(id);
        await audit({ userId: user.id, serviceId: id, action: "domain.add", detail: hostname });
        return {
          domain: { ...row, records: dnsRecordsFor(hostname) },
          traefikWritten: written,
          traefik: {
            router: `orbital-${svc.slug}`,
            rule: `Host(\`${hostname}\`)`,
            entrypoint: https === false ? "web" : "websecure",
            port: web?.port ?? 3000,
          },
        };
      }
      default:
        return fail(`Unknown action: ${action}`, 404);
    }
  });
}

/* --------------------------------- DELETE --------------------------------- */

export async function DELETE(req: NextRequest, ctx: Ctx) {
  const { id, action } = await ctx.params;
  const url = new URL(req.url);

  return route(async () => {
    const { user, svc } = await ctxService(id, "member");
    const target = url.searchParams.get("path");
    const rowId = url.searchParams.get("id");

    switch (action) {
      case "files": {
        if (!target) return fail("path is required");
        await assertCommandSourceAccess(user.id, svc, [target], { tree: true });
        await fsFor(svc).remove(target);
        await refreshStorageOverflow(svc).catch(() => undefined);
        await audit({ userId: user.id, serviceId: id, action: "files.delete", detail: target });
        return { ok: true };
      }
      case "env": {
        if (!rowId) return fail("id is required");
        await db.delete(envVars).where(and(eq(envVars.serviceId, id), eq(envVars.id, rowId)));
        return { ok: true };
      }
      case "backups": {
        if (!rowId) return fail("id is required");
        const [backup] = await db
          .select()
          .from(backups)
          .where(and(eq(backups.serviceId, id), eq(backups.id, rowId)))
          .limit(1);
        if (!backup) return fail("Backup not found", 404);
        await fs.rm(path.join(backupsDir(id), backup.fileName), { force: true });
        await db.delete(backups).where(eq(backups.id, backup.id));
        return { ok: true };
      }
      case "addons": {
        if (!rowId) return fail("id is required");
        const [addon] = await db
          .select()
          .from(minecraftAddons)
          .where(and(eq(minecraftAddons.serviceId, id), eq(minecraftAddons.id, rowId)))
          .limit(1);
        if (!addon) return fail("Addon not found", 404);
        const dir = addon.kind === "plugin" ? "plugins" : "mods";
        await fsFor(svc)
          .remove(`${dir}/${addon.fileName}`)
          .catch(() => undefined);
        await db.delete(minecraftAddons).where(eq(minecraftAddons.id, addon.id));
        return { ok: true };
      }
      case "database": {
        if (!rowId) return fail("id is required");
        const [row] = await db
          .select()
          .from(serviceDatabases)
          .where(and(eq(serviceDatabases.serviceId, id), eq(serviceDatabases.id, rowId)))
          .limit(1);
        if (!row) return fail("Database not found", 404);
        await DatabaseManager.drop(row.dbName, row.dbUser);
        await db.delete(serviceDatabases).where(eq(serviceDatabases.id, row.id));
        return { ok: true };
      }
      case "domains": {
        if (!rowId) return fail("id is required");
        const [row] = await db
          .select()
          .from(domains)
          .where(and(eq(domains.serviceId, id), eq(domains.id, rowId)))
          .limit(1);
        if (!row) return fail("Domain not found", 404);
        await db.delete(domains).where(eq(domains.id, row.id));
        await syncTraefikConfig(id);
        await audit({ userId: user.id, serviceId: id, action: "domain.remove", detail: row.hostname });
        return { ok: true };
      }
      default:
        return fail(`Unknown action: ${action}`, 404);
    }
  });
}

/* ----------------------------------- PUT ---------------------------------- */

export async function PUT(req: NextRequest, ctx: Ctx) {
  const { id, action } = await ctx.params;
  return route(async () => {
    const { svc } = await ctxService(id, "member");
    if (action === "addons") {
      const { addonId, enabled } = await body<{ addonId: string; enabled: boolean }>(req);
      const [addon] = await db
        .select()
        .from(minecraftAddons)
        .where(and(eq(minecraftAddons.serviceId, id), eq(minecraftAddons.id, addonId)))
        .limit(1);
      if (!addon) return fail("Addon not found", 404);
      const dir = addon.kind === "plugin" ? "plugins" : "mods";
      const fsm = fsFor(svc);
      const active = `${dir}/${addon.fileName}`;
      const disabled = `${active}.disabled`;
      if (enabled && (await fsm.exists(disabled))) await fsm.rename(disabled, active);
      if (!enabled && (await fsm.exists(active))) await fsm.rename(active, disabled);
      await db.update(minecraftAddons).set({ enabled }).where(eq(minecraftAddons.id, addon.id));
      return { ok: true };
    }
    return fail(`Unknown action: ${action}`, 404);
  });
}
