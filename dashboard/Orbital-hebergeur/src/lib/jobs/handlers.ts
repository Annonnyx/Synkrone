import { execFile } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import { promisify } from "node:util";
import { desc, eq } from "drizzle-orm";
import { db } from "@/db";
import { backups, containers, deployments, services, webProjects } from "@/db/schema";
import { appendConsole, setServiceState } from "@/lib/runtime/base";
import { getProvider, toRecord } from "@/lib/runtime";
import { FilesystemManager } from "@/lib/filesystem/manager";
import { backupsDir, type ServiceType } from "@/lib/paths";
import { runJob, type StepRunner } from "./queue";
import { getValidAccessToken } from "@/lib/oauth/accounts";
import { githubCloneUrl, parseGithubRepo, redactSecrets } from "@/lib/oauth/urls";

const exec = promisify(execFile);

async function loadService(serviceId: string) {
  const [svc] = await db.select().from(services).where(eq(services.id, serviceId)).limit(1);
  if (!svc) throw new Error("Service not found");
  return svc;
}

export const PROVISION_STEPS = [
  "Preparing volume",
  "Writing service files",
  "Pulling image",
  "Creating container",
  "Starting service",
];

/** CREATE_CONTAINER — full provisioning pipeline for any runtime family. */
export function provisionService(jobId: string, serviceId: string, autoStart: boolean) {
  return runJob(jobId, async (r: StepRunner) => {
    const svc = await loadService(serviceId);
    const provider = getProvider(svc.type);
    const record = toRecord(svc);

    await r.step("Preparing volume", async () => {
      const fsm = new FilesystemManager(svc.type as ServiceType, svc.id);
      await fsm.mkdir("/");
      await r.note("Preparing volume", fsm.root);
      await appendConsole(serviceId, `Volume ready at ${fsm.root}`);
    });

    await r.step("Writing service files", async () => {
      await provider.scaffold(record);
      await appendConsole(serviceId, "Service files written to the volume");
    });

    let created: { containerId: string; image: string } | null = null;
    try {
      await r.step("Pulling image", async () => {
        await appendConsole(serviceId, "Contacting Docker Engine...");
      });
      await r.step("Creating container", async () => {
        created = await provider.create(record);
        await r.note("Creating container", created.containerId.slice(0, 12));
      });
    } catch (err) {
      const message = (err as Error).message;
      await setServiceState(serviceId, "ERROR", message);
      await appendConsole(serviceId, `Container creation failed: ${message}`, "stderr");
      throw err;
    }

    await r.step("Starting service", async () => {
      if (!autoStart) {
        await setServiceState(serviceId, "STOPPED");
        return;
      }
      await provider.start(serviceId);
    });
  });
}

/** DELETE_CONTAINER — removes the container then the volume. */
export function deleteServiceJob(jobId: string, serviceId: string) {
  return runJob(jobId, async (r) => {
    const svc = await loadService(serviceId);
    const provider = getProvider(svc.type);
    await r.step("Removing container", async () => {
      try {
        await provider.remove(serviceId);
      } catch (err) {
        await r.note("Removing container", (err as Error).message);
      }
    });
    await r.step("Deleting volume", async () => {
      const fsm = new FilesystemManager(svc.type as ServiceType, svc.id);
      await fs.rm(fsm.root, { recursive: true, force: true });
    });
    await r.step("Removing records", async () => {
      await db.delete(services).where(eq(services.id, serviceId));
    });
  });
}

export const DEPLOY_STEPS = [
  "Fetching source",
  "Installing dependencies",
  "Building project",
  "Recreating container",
  "Starting deployment",
];

async function appendDeployLog(deploymentId: string, line: string) {
  const [row] = await db
    .select({ logs: deployments.logs })
    .from(deployments)
    .where(eq(deployments.id, deploymentId))
    .limit(1);
  const stamped = `[${new Date().toISOString().slice(11, 19)}] ${line}`;
  await db
    .update(deployments)
    .set({ logs: `${row?.logs ?? ""}${stamped}\n` })
    .where(eq(deployments.id, deploymentId));
}

/** DEPLOY_WEB — GitHub clone → install → build → new container version. */
export function deployWeb(
  jobId: string,
  serviceId: string,
  deploymentId: string,
  trigger: string,
) {
  return runJob(jobId, async (r) => {
    const svc = await loadService(serviceId);
    const [web] = await db
      .select()
      .from(webProjects)
      .where(eq(webProjects.serviceId, serviceId))
      .limit(1);
    const provider = getProvider("web");
    const fsm = new FilesystemManager("web", serviceId);
    await db.update(deployments).set({ status: "RUNNING" }).where(eq(deployments.id, deploymentId));
    await appendDeployLog(deploymentId, `Deployment triggered (${trigger})`);

    try {
      await r.step("Fetching source", async () => {
        if (web?.source === "github" && web.repoUrl) {
          const parsed = parseGithubRepo(web.repoUrl);
          const publicRef = parsed ? `${parsed.fullName}#${web.branch}` : `#${web.branch}`;
          await appendDeployLog(deploymentId, `Cloning ${publicRef}`);
          await fs.rm(fsm.root, { recursive: true, force: true });
          await fs.mkdir(fsm.root, { recursive: true });
          let cloneUrl = web.repoUrl;
          try {
            const token = await getValidAccessToken(svc.ownerId, "github");
            cloneUrl = githubCloneUrl(web.repoUrl, token) ?? web.repoUrl;
          } catch {
            await appendDeployLog(
              deploymentId,
              "No usable GitHub token — cloning the public URL. Link GitHub on the account page for private repos.",
            );
          }
          try {
            const { stdout, stderr } = await exec(
              "git",
              ["clone", "--depth", "1", "--branch", web.branch, cloneUrl, fsm.root],
              { env: { ...process.env, GIT_TERMINAL_PROMPT: "0" } },
            );
            await appendDeployLog(deploymentId, redactSecrets(stdout || stderr || "clone complete"));
          } catch (err) {
            const message = redactSecrets(err instanceof Error ? err.message : "clone failed");
            throw new Error(message);
          }
          const sha = await exec("git", ["-C", fsm.root, "rev-parse", "HEAD"]).catch(() => null);
          if (sha)
            await db
              .update(deployments)
              .set({ commitSha: sha.stdout.trim().slice(0, 12) })
              .where(eq(deployments.id, deploymentId));
        } else {
          await appendDeployLog(deploymentId, "Using files already present in the volume");
        }
        await provider.scaffold(toRecord(svc));
      });

      await r.step("Installing dependencies", async () => {
        await appendDeployLog(
          deploymentId,
          web?.installCommand
            ? `Install command delegated to the runtime container: ${web.installCommand}`
            : "No install command configured",
        );
      });

      await r.step("Building project", async () => {
        await appendDeployLog(
          deploymentId,
          web?.buildCommand
            ? `Build command delegated to the runtime container: ${web.buildCommand}`
            : "No build step configured",
        );
      });

      await r.step("Recreating container", async () => {
        await appendDeployLog(deploymentId, "Removing previous container version");
        await provider.remove(serviceId);
        const created = await provider.create(toRecord(svc));
        await appendDeployLog(deploymentId, `Created container ${created.containerId.slice(0, 12)}`);
        await db
          .update(deployments)
          .set({ image: created.image })
          .where(eq(deployments.id, deploymentId));
      });

      await r.step("Starting deployment", async () => {
        await provider.start(serviceId);
        await appendDeployLog(deploymentId, "Container started");
      });

      await db
        .update(deployments)
        .set({ isCurrent: false })
        .where(eq(deployments.serviceId, serviceId));
      await db
        .update(deployments)
        .set({ status: "SUCCESS", isCurrent: true, finishedAt: new Date() })
        .where(eq(deployments.id, deploymentId));
    } catch (err) {
      await appendDeployLog(deploymentId, `FAILED: ${(err as Error).message}`);
      await db
        .update(deployments)
        .set({ status: "FAILED", finishedAt: new Date() })
        .where(eq(deployments.id, deploymentId));
      await setServiceState(serviceId, "ERROR", (err as Error).message);
      throw err;
    }
  });
}

export const BACKUP_STEPS = ["Snapshotting volume", "Writing archive", "Recording backup"];

export function createBackupJob(jobId: string, serviceId: string, backupId: string) {
  return runJob(jobId, async (r) => {
    const svc = await loadService(serviceId);
    const fsm = new FilesystemManager(svc.type as ServiceType, serviceId);
    const [backup] = await db.select().from(backups).where(eq(backups.id, backupId)).limit(1);
    const dest = path.join(backupsDir(serviceId), backup.fileName);
    let size = 0;
    await r.step("Snapshotting volume", async () => {
      await appendConsole(serviceId, "Creating backup snapshot...");
    });
    await r.step("Writing archive", async () => {
      size = await fsm.archiveTo(dest);
    });
    await r.step("Recording backup", async () => {
      await db
        .update(backups)
        .set({ status: "READY", sizeBytes: size })
        .where(eq(backups.id, backupId));
      await appendConsole(serviceId, `Backup ready (${(size / 1048576).toFixed(1)} MB)`);
    });
  }).catch(async (err) => {
    await db
      .update(backups)
      .set({ status: "FAILED", note: (err as Error).message })
      .where(eq(backups.id, backupId));
  });
}

export const RESTORE_STEPS = ["Stopping service", "Restoring archive", "Restarting service"];

export function restoreBackupJob(jobId: string, serviceId: string, backupId: string) {
  return runJob(jobId, async (r) => {
    const svc = await loadService(serviceId);
    const provider = getProvider(svc.type);
    const [backup] = await db.select().from(backups).where(eq(backups.id, backupId)).limit(1);
    const src = path.join(backupsDir(serviceId), backup.fileName);
    const fsm = new FilesystemManager(svc.type as ServiceType, serviceId);
    const [container] = await db
      .select()
      .from(containers)
      .where(eq(containers.serviceId, serviceId))
      .orderBy(desc(containers.createdAt))
      .limit(1);

    await r.step("Stopping service", async () => {
      if (container?.dockerContainerId) {
        await provider.stop(serviceId).catch(() => undefined);
      }
    });
    await r.step("Restoring archive", async () => {
      await fsm.restoreFrom(src);
      await appendConsole(serviceId, `Restored backup ${backup.fileName}`);
    });
    await r.step("Restarting service", async () => {
      if (container?.dockerContainerId) {
        await provider.start(serviceId).catch(() => undefined);
      }
    });
  });
}
