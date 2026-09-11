import { NextRequest } from "next/server";
import { fail, route } from "@/lib/api";
import { requireUser } from "@/lib/auth";
import { getJob } from "@/lib/jobs/queue";
import { authorizeService } from "@/lib/runtime";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(_req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  return route(async () => {
    const user = await requireUser();
    const job = await getJob(id);
    if (!job) return fail("Job not found", 404);
    if (job.serviceId) {
      await authorizeService(job.serviceId, user.id, "viewer").catch(() => {
        if (job.userId !== user.id) throw new Error("Not allowed");
      });
    } else if (job.userId && job.userId !== user.id) {
      return fail("Not allowed", 403);
    }
    return { job };
  });
}
