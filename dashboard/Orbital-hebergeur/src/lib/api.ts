import { NextResponse } from "next/server";
import { HttpError } from "@/lib/auth";
import { isDatabaseUnavailable } from "@/lib/db-errors";
import { DockerApiError, DockerUnavailableError } from "@/lib/docker/engine";
import { DockerPolicyError } from "@/lib/docker/adapter";
import { FilesystemError } from "@/lib/filesystem/manager";

export function ok<T>(data: T, init?: number) {
  return NextResponse.json(data as object, { status: init ?? 200 });
}

export function fail(message: string, status = 400, extra?: Record<string, unknown>) {
  return NextResponse.json({ error: message, ...extra }, { status });
}

export function handleError(err: unknown) {
  if (err instanceof HttpError) return fail(err.message, err.status, err.code ? { code: err.code } : undefined);
  if (err instanceof FilesystemError) return fail(err.message, err.status);
  if (isDatabaseUnavailable(err))
    return fail("The database is unreachable", 503, { code: "DATABASE_UNAVAILABLE" });
  if (err instanceof DockerUnavailableError)
    return fail(err.message, 503, { code: "DOCKER_UNAVAILABLE" });
  if (err instanceof DockerPolicyError)
    return fail(err.message, 400, { code: "DOCKER_POLICY" });
  if (err instanceof DockerApiError)
    return fail(`Docker: ${err.message}`, err.status >= 400 ? err.status : 500);
  const message = err instanceof Error ? err.message : "Unexpected error";
  if (err instanceof Error && (err as Error & { code?: string }).code === "INSUFFICIENT_KRONES") {
    return fail(message, 403, { code: "INSUFFICIENT_KRONES" });
  }
  console.error("[api]", err);
  return fail(message, 500);
}

export async function route<T>(fn: () => Promise<T>) {
  try {
    const result = await fn();
    if (result instanceof NextResponse) return result;
    return ok(result);
  } catch (err) {
    return handleError(err);
  }
}

export async function body<T = Record<string, unknown>>(req: Request): Promise<T> {
  try {
    return (await req.json()) as T;
  } catch {
    return {} as T;
  }
}

/** Very small in-memory rate limiter for sensitive endpoints (§67). */
const buckets = new Map<string, { count: number; reset: number }>();
export function rateLimit(key: string, limit = 20, windowMs = 60_000) {
  const now = Date.now();
  const bucket = buckets.get(key);
  if (!bucket || bucket.reset < now) {
    buckets.set(key, { count: 1, reset: now + windowMs });
    return;
  }
  bucket.count += 1;
  if (bucket.count > limit) throw new HttpError(429, "Too many requests, slow down");
}
