import { headers } from "next/headers";
import { db } from "@/db";
import { auditLogs } from "@/db/schema";

export async function audit(entry: {
  userId?: string | null;
  projectId?: string | null;
  serviceId?: string | null;
  action: string;
  result?: "success" | "failure";
  detail?: string;
}) {
  let ip: string | null = null;
  try {
    ip = (await headers()).get("x-forwarded-for");
  } catch {
    ip = null;
  }
  await db.insert(auditLogs).values({
    userId: entry.userId ?? null,
    projectId: entry.projectId ?? null,
    serviceId: entry.serviceId ?? null,
    action: entry.action,
    result: entry.result ?? "success",
    detail: entry.detail ?? null,
    ip,
  });
}
