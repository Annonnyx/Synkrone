import { and, desc, eq } from "drizzle-orm";
import { db } from "@/db";
import { consoleLines, containers, envVars, metricSamples, services } from "@/db/schema";
import { ContainerManager, type ContainerSpec } from "@/lib/docker/adapter";
import { computeCpuPercent, cpuSampleReady, DockerUnavailableError } from "@/lib/docker/engine";
import { decryptSecret } from "@/lib/crypto";
import { FilesystemManager } from "@/lib/filesystem/manager";
import { MOUNT_POINT, serviceVolume, type ServiceType } from "@/lib/paths";
import type {
  LifecycleState,
  ResourceStats,
  RuntimeProvider,
  RuntimeTemplate,
  ServiceRecord,
  ServiceStatus,
} from "./types";
import { crashReasonFromLogs, isConfigFatalLogs } from "./crash";
import { mergeContainerEnv } from "./env";

export { crashReasonFromLogs } from "./crash";

export async function appendConsole(
  serviceId: string,
  message: string,
  stream: "system" | "stdout" | "stderr" | "command" = "system",
) {
  await db.insert(consoleLines).values({ serviceId, message, stream });
}

export async function setServiceState(
  serviceId: string,
  state: LifecycleState,
  lastError?: string | null,
) {
  await db
    .update(services)
    .set({ state, lastError: lastError ?? null, updatedAt: new Date() })
    .where(eq(services.id, serviceId));
}

export async function currentContainer(serviceId: string) {
  const rows = await db
    .select()
    .from(containers)
    .where(eq(containers.serviceId, serviceId))
    .orderBy(desc(containers.createdAt))
    .limit(1);
  return rows[0] ?? null;
}

export async function serviceEnvironment(serviceId: string): Promise<Record<string, string>> {
  const rows = await db.select().from(envVars).where(eq(envVars.serviceId, serviceId));
  const out: Record<string, string> = {};
  for (const row of rows) {
    const value = decryptSecret(row.valueEnc);
    if (value !== null) out[row.key] = value;
  }
  return out;
}

export abstract class BaseRuntimeProvider implements RuntimeProvider {
  abstract readonly type: ServiceType;
  abstract scaffold(service: ServiceRecord): Promise<void>;
  /** Runtime-family specific container description. */
  protected abstract template(service: ServiceRecord): Promise<RuntimeTemplate>;
  protected abstract extraEnv(service: ServiceRecord): Promise<Record<string, string>>;
  protected async ports(_service: ServiceRecord): Promise<ContainerSpec["ports"]> {
    return [];
  }

  fs(serviceId: string) {
    return new FilesystemManager(this.type, serviceId);
  }

  protected containerName(service: ServiceRecord): string {
    return `${this.type}-${service.slug}-${service.id.slice(0, 8)}`;
  }

  async create(service: ServiceRecord) {
    const tpl = await this.template(service);
    const volume = serviceVolume(this.type, service.id);
    const name = this.containerName(service);

    await appendConsole(service.id, `Pulling image ${tpl.image}...`);
    await ContainerManager.pullImage(tpl.image);

    const env = mergeContainerEnv(
      tpl.environment,
      await serviceEnvironment(service.id),
      await this.extraEnv(service),
    );

    const spec: ContainerSpec = {
      name,
      image: tpl.image,
      cmd: tpl.command,
      env,
      workdir: tpl.mountPath,
      volumeHostPath: volume,
      volumeMountPath: tpl.mountPath ?? MOUNT_POINT[this.type],
      networks: tpl.networks,
      cpuMillicores: service.cpuLimit,
      memoryMb: service.memoryLimitMb,
      ports: await this.ports(service),
      restartPolicy: (service.restartPolicy as ContainerSpec["restartPolicy"]) ?? "on-failure",
      maxRestarts: service.maxRestarts,
      user: tpl.user,
      labels: {
        "orbital.service.id": service.id,
        "orbital.service.type": this.type,
        "orbital.owner.id": service.ownerId,
      },
    };

    await appendConsole(service.id, `Creating container ${name}...`);
    const containerId = await ContainerManager.createContainer(spec);

    await db.insert(containers).values({
      serviceId: service.id,
      dockerContainerId: containerId,
      containerName: name,
      image: tpl.image,
      network: tpl.networks[0],
      status: "STOPPED",
      cpuLimit: service.cpuLimit,
      memoryLimitMb: service.memoryLimitMb,
      restartPolicy: service.restartPolicy,
    });
    await appendConsole(service.id, `Container created (${containerId.slice(0, 12)})`);
    return { containerId, image: tpl.image };
  }

  protected async requireContainer(serviceId: string) {
    const row = await currentContainer(serviceId);
    if (!row?.dockerContainerId) {
      throw new DockerUnavailableError(
        "no container is registered for this service - run Create/Deploy first",
      );
    }
    return row;
  }

  async start(serviceId: string) {
    const row = await this.requireContainer(serviceId);
    await setServiceState(serviceId, "STARTING");
    await appendConsole(serviceId, "Starting container...");
    await ContainerManager.startContainer(row.dockerContainerId!);
    await db
      .update(containers)
      .set({ status: "RUNNING", startedAt: new Date(), lastError: null })
      .where(eq(containers.id, row.id));
    await setServiceState(serviceId, "RUNNING");
    await appendConsole(serviceId, "Container started");
  }

  async stop(serviceId: string) {
    const row = await this.requireContainer(serviceId);
    await setServiceState(serviceId, "STOPPING");
    await appendConsole(serviceId, "Stopping container...");
    await ContainerManager.stopContainer(row.dockerContainerId!);
    await db.update(containers).set({ status: "STOPPED" }).where(eq(containers.id, row.id));
    await setServiceState(serviceId, "STOPPED");
    await appendConsole(serviceId, "Container stopped");
  }

  async restart(serviceId: string) {
    const row = await this.requireContainer(serviceId);
    await setServiceState(serviceId, "RESTARTING");
    await appendConsole(serviceId, "Restarting container...");
    await ContainerManager.restartContainer(row.dockerContainerId!);
    await setServiceState(serviceId, "RUNNING");
    await appendConsole(serviceId, "Container restarted");
  }

  async kill(serviceId: string) {
    const row = await this.requireContainer(serviceId);
    await appendConsole(serviceId, "Killing container (SIGKILL)...");
    await ContainerManager.killContainer(row.dockerContainerId!);
    await db.update(containers).set({ status: "STOPPED" }).where(eq(containers.id, row.id));
    await setServiceState(serviceId, "STOPPED");
  }

  async remove(serviceId: string) {
    const row = await currentContainer(serviceId);
    await setServiceState(serviceId, "DELETING");
    if (row?.dockerContainerId) {
      try {
        await ContainerManager.removeContainer(row.dockerContainerId);
      } catch {
        /* container may already be gone; the DB stays the source of truth */
      }
    }
    await db.delete(containers).where(eq(containers.serviceId, serviceId));
  }

  async status(serviceId: string): Promise<ServiceStatus> {
    const row = await currentContainer(serviceId);
    const svc = (
      await db.select().from(services).where(eq(services.id, serviceId)).limit(1)
    )[0];
    if (!row?.dockerContainerId) {
      return {
        state: (svc?.state as LifecycleState) ?? "CREATING",
        message: svc?.lastError ?? "No container registered yet",
      };
    }
    try {
      const inspect = await ContainerManager.inspect(row.dockerContainerId);
      const s = inspect.State;
      let state: LifecycleState = "STOPPED";
      if (s.Restarting) state = "RESTARTING";
      else if (s.Running) state = "RUNNING";
      else if (s.Status === "exited" && s.ExitCode !== 0) state = "CRASHED";
      else if (s.Status === "exited" && svc?.state === "CRASHED") state = "CRASHED";
      else if (s.Status === "created") state = "STOPPED";

      let prefetchedLogs: string | null = null;
      const maybeConfigFatal =
        state === "RESTARTING" ||
        (s.Status === "exited" &&
          !!svc &&
          (svc.state === "STARTING" || svc.state === "RUNNING" || svc.state === "RESTARTING"));
      if (maybeConfigFatal) {
        prefetchedLogs = await ContainerManager.getContainerLogs(row.dockerContainerId!, 80).catch(
          () => "",
        );
        if (isConfigFatalLogs(prefetchedLogs)) {
          if (s.Restarting || s.Running) {
            await ContainerManager.stopContainer(row.dockerContainerId!).catch(() => undefined);
          }
          state = "CRASHED";
        }
      }

      await db
        .update(containers)
        .set({ status: state, restartCount: inspect.RestartCount ?? 0 })
        .where(eq(containers.id, row.id));
      if (svc && svc.state !== state && svc.state !== "DELETING") {
        // A stop we initiated ends with a non-zero exit (SIGTERM/SIGKILL). That is
        // not a crash — leave the service STOPPED instead of flipping to CRASHED.
        if (svc?.state === "SUSPENDED" && !s.Running && !s.Restarting) {
          return { state: "SUSPENDED", dockerStatus: s.Status, exitCode: s.ExitCode };
        }
        if (
          state === "CRASHED" &&
          (svc.state === "STOPPING" ||
            svc.state === "STOPPED" ||
            svc.state === "SUSPENDED" ||
            svc.state === "RESTARTING")
        ) {
          // docker stop/restart ends with SIGTERM (143) or SIGKILL (137).
          if (svc.state === "RESTARTING") {
            return { state: "RESTARTING", dockerStatus: s.Status, exitCode: s.ExitCode };
          }
          await setServiceState(serviceId, "STOPPED");
          await db.update(containers).set({ status: "STOPPED" }).where(eq(containers.id, row.id));
          return { state: "STOPPED", dockerStatus: s.Status, exitCode: s.ExitCode };
        }
        let crashReason: string | null = null;
        if (state === "CRASHED") {
          const logs =
            prefetchedLogs ??
            (await ContainerManager.getContainerLogs(row.dockerContainerId!, 80).catch(() => ""));
          crashReason = crashReasonFromLogs(logs, s.ExitCode, s.OOMKilled, s.Error);
          await setServiceState(serviceId, state, crashReason);
          await appendConsole(
            serviceId,
            `Service stopped unexpectedly (exit ${s.ExitCode})${crashReason ? `: ${crashReason}` : ""}`,
            "stderr",
          );
        } else {
          await setServiceState(serviceId, state);
        }
      }
      return {
        state,
        dockerStatus: s.Status,
        exitCode: s.ExitCode,
        restartCount: inspect.RestartCount,
        startedAt: s.StartedAt,
      };
    } catch (err) {
      return {
        state: (svc?.state as LifecycleState) ?? "ERROR",
        message: (err as Error).message,
      };
    }
  }

  async logs(serviceId: string, tail = 300) {
    const row = await this.requireContainer(serviceId);
    return ContainerManager.getContainerLogs(row.dockerContainerId!, tail);
  }

  async followLogs(serviceId: string, signal?: AbortSignal) {
    const row = await this.requireContainer(serviceId);
    return ContainerManager.followContainerLogs(row.dockerContainerId!, signal);
  }

  async stats(serviceId: string): Promise<ResourceStats> {
    const fsm = this.fs(serviceId);
    const diskMb = await fsm.diskUsageMb();
    const row = await currentContainer(serviceId);
    const svc = (
      await db.select().from(services).where(eq(services.id, serviceId)).limit(1)
    )[0];
    if (svc) {
      void import("@/lib/services/storage-enforce")
        .then(async ({ refreshStorageOverflow }) => {
          const over = await refreshStorageOverflow(svc, diskMb);
          if (over && svc.state === "RUNNING") {
            await this.stop(serviceId).catch(() => undefined);
            const { STORAGE_QUOTA_ERROR } = await import("@/lib/services/storage-quota");
            await db
              .update(services)
              .set({ lastError: STORAGE_QUOTA_ERROR, updatedAt: new Date() })
              .where(eq(services.id, serviceId));
          }
        })
        .catch(() => undefined);
    }
    const base: ResourceStats = {
      cpuPercent: 0,
      memoryMb: 0,
      memoryLimitMb: svc?.memoryLimitMb ?? 0,
      networkRxKb: 0,
      networkTxKb: 0,
      diskMb,
      uptimeSeconds: 0,
      restartCount: row?.restartCount ?? 0,
      available: false,
      reason: "container not running",
    };
    if (!row?.dockerContainerId) return base;
    try {
      const raw = await ContainerManager.getContainerStats(row.dockerContainerId);
      const nets = Object.values(raw.networks ?? {});
      const inspect = await ContainerManager.inspect(row.dockerContainerId);
      const started = Date.parse(inspect.State.StartedAt);
      const stats: ResourceStats = {
        cpuPercent: cpuSampleReady(raw) ? Math.round(computeCpuPercent(raw) * 10) / 10 : 0,
        memoryMb: Math.round(((raw.memory_stats?.usage ?? 0) / (1024 * 1024)) * 10) / 10,
        memoryLimitMb: Math.round((raw.memory_stats?.limit ?? 0) / (1024 * 1024)),
        networkRxKb: Math.round(nets.reduce((a, n) => a + (n.rx_bytes ?? 0), 0) / 1024),
        networkTxKb: Math.round(nets.reduce((a, n) => a + (n.tx_bytes ?? 0), 0) / 1024),
        diskMb,
        uptimeSeconds:
          inspect.State.Running && !Number.isNaN(started)
            ? Math.max(0, Math.round((Date.now() - started) / 1000))
            : 0,
        restartCount: inspect.RestartCount ?? 0,
        available: true,
      };
      await db.insert(metricSamples).values({
        serviceId,
        cpuPercent: Math.round(stats.cpuPercent),
        memoryMb: Math.round(stats.memoryMb),
        networkRxKb: stats.networkRxKb,
        networkTxKb: stats.networkTxKb,
        diskMb: Math.round(stats.diskMb),
      });
      return stats;
    } catch (err) {
      return { ...base, reason: (err as Error).message };
    }
  }

  /** Default: run the command inside the container via docker exec. */
  async sendCommand(serviceId: string, command: string): Promise<string> {
    const row = await this.requireContainer(serviceId);
    await appendConsole(serviceId, `$ ${command}`, "command");
    let result;
    try {
      result = await ContainerManager.execCommand(row.dockerContainerId!, ["sh", "-lc", command]);
    } catch (err) {
      await appendConsole(serviceId, (err as Error).message, "stderr");
      throw err;
    }
    if (result.stdout.trim()) await appendConsole(serviceId, result.stdout.trim(), "stdout");
    if (result.stderr.trim()) await appendConsole(serviceId, result.stderr.trim(), "stderr");
    // A silent non-zero exit is the most confusing console outcome: the command
    // ran, printed nothing, and the user has no way to tell it failed.
    if (result.exitCode) {
      await appendConsole(serviceId, `Command exited with code ${result.exitCode}`, "stderr");
    }
    return result.combined;
  }
}

export async function loadServiceRecord(serviceId: string): Promise<ServiceRecord | null> {
  const rows = await db
    .select()
    .from(services)
    .where(and(eq(services.id, serviceId)))
    .limit(1);
  if (!rows.length) return null;
  const s = rows[0];
  return {
    id: s.id,
    type: s.type as ServiceType,
    name: s.name,
    slug: s.slug,
    ownerId: s.ownerId,
    projectId: s.projectId,
    cpuLimit: s.cpuLimit,
    memoryLimitMb: s.memoryLimitMb,
    storageLimitMb: s.storageLimitMb,
    restartPolicy: s.restartPolicy,
    maxRestarts: s.maxRestarts,
  };
}
