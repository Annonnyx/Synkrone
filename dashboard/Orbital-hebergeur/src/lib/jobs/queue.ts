import { asc, eq } from "drizzle-orm";
import { db } from "@/db";
import { jobSteps, jobs } from "@/db/schema";

/**
 * Postgres-backed job queue.
 *
 * Design note (documented in docs/architecture.md): the platform ships with a
 * transactional Postgres queue instead of Redis/BullMQ so a single-node install
 * has zero extra infrastructure. `runJob` is the exact function executed by the
 * standalone worker processes in /workers - the API just triggers it in-process
 * when no external worker is registered.
 */

export type JobType =
  | "CREATE_CONTAINER"
  | "DELETE_CONTAINER"
  | "INSTALL_MINECRAFT"
  | "INSTALL_ADDON"
  | "DEPLOY_WEB"
  | "CLONE_GITHUB"
  | "CREATE_BACKUP"
  | "RESTORE_BACKUP";

export type StepRunner = {
  step<T>(label: string, fn: () => Promise<T>): Promise<T>;
  note(label: string, detail: string): Promise<void>;
};

export async function createJob(input: {
  type: JobType;
  serviceId?: string;
  userId?: string;
  steps: string[];
  payload?: Record<string, unknown>;
}): Promise<string> {
  const [job] = await db
    .insert(jobs)
    .values({
      type: input.type,
      serviceId: input.serviceId,
      userId: input.userId,
      payload: input.payload ?? {},
    })
    .returning({ id: jobs.id });
  await db.insert(jobSteps).values(
    input.steps.map((label, position) => ({ jobId: job.id, label, position })),
  );
  return job.id;
}

export async function getJob(jobId: string) {
  const [job] = await db.select().from(jobs).where(eq(jobs.id, jobId)).limit(1);
  if (!job) return null;
  const steps = await db
    .select()
    .from(jobSteps)
    .where(eq(jobSteps.jobId, jobId))
    .orderBy(asc(jobSteps.position));
  return { ...job, steps };
}

/** Executes the job body, tracking real per-step progress in Postgres. */
export async function runJob(
  jobId: string,
  body: (runner: StepRunner) => Promise<void>,
): Promise<void> {
  await db.update(jobs).set({ status: "RUNNING" }).where(eq(jobs.id, jobId));
  const allSteps = await db
    .select()
    .from(jobSteps)
    .where(eq(jobSteps.jobId, jobId))
    .orderBy(asc(jobSteps.position));
  const total = Math.max(1, allSteps.length);
  let done = 0;

  const findStep = (label: string) => allSteps.find((s) => s.label === label);

  const runner: StepRunner = {
    async step<T>(label: string, fn: () => Promise<T>): Promise<T> {
      const row = findStep(label);
      if (row) await db.update(jobSteps).set({ status: "RUNNING" }).where(eq(jobSteps.id, row.id));
      try {
        const result = await fn();
        done += 1;
        if (row)
          await db.update(jobSteps).set({ status: "DONE" }).where(eq(jobSteps.id, row.id));
        await db
          .update(jobs)
          .set({ progress: Math.round((done / total) * 100) })
          .where(eq(jobs.id, jobId));
        return result;
      } catch (err) {
        if (row)
          await db
            .update(jobSteps)
            .set({ status: "FAILED", detail: (err as Error).message })
            .where(eq(jobSteps.id, row.id));
        throw err;
      }
    },
    async note(label: string, detail: string) {
      const row = findStep(label);
      if (row) await db.update(jobSteps).set({ detail }).where(eq(jobSteps.id, row.id));
    },
  };

  try {
    await body(runner);
    await db
      .update(jobs)
      .set({ status: "SUCCESS", progress: 100, finishedAt: new Date() })
      .where(eq(jobs.id, jobId));
  } catch (err) {
    await db
      .update(jobs)
      .set({ status: "FAILED", error: (err as Error).message, finishedAt: new Date() })
      .where(eq(jobs.id, jobId));
  }
}

/** Fire-and-forget helper used by route handlers. */
export function dispatch(promise: Promise<unknown>): void {
  void promise.catch((err) => console.error("[worker] job failed", err));
}
