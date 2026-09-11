import { createHmac, timingSafeEqual } from "node:crypto";
import { NextRequest } from "next/server";
import { desc, eq } from "drizzle-orm";
import { db } from "@/db";
import { deployments, services, webProjects } from "@/db/schema";
import { fail, ok, route } from "@/lib/api";
import { audit } from "@/lib/audit";
import { decryptSecret } from "@/lib/crypto";
import { createJob, dispatch } from "@/lib/jobs/queue";
import { DEPLOY_STEPS, deployWeb } from "@/lib/jobs/handlers";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** GitHub push webhook → automatic deployment (§65). */
export async function POST(req: NextRequest, ctx: { params: Promise<{ serviceId: string }> }) {
  const { serviceId } = await ctx.params;
  return route(async () => {
    const [svc] = await db.select().from(services).where(eq(services.id, serviceId)).limit(1);
    if (!svc || svc.type !== "web") return fail("Unknown web service", 404);
    const [web] = await db
      .select()
      .from(webProjects)
      .where(eq(webProjects.serviceId, serviceId))
      .limit(1);
    if (!web) return fail("Unknown web service", 404);

    const raw = await req.text();
    const secret = decryptSecret(web.webhookSecretEnc);
    const signature = req.headers.get("x-hub-signature-256");
    if (secret) {
      const expected = `sha256=${createHmac("sha256", secret).update(raw).digest("hex")}`;
      const a = Buffer.from(expected);
      const b = Buffer.from(signature ?? "");
      if (a.length !== b.length || !timingSafeEqual(a, b)) {
        await audit({ serviceId, action: "github.webhook", result: "failure", detail: "bad signature" });
        return fail("Invalid signature", 401);
      }
    }

    if (!web.autoDeploy) return ok({ ok: true, skipped: "auto deploy disabled" });

    const payload = JSON.parse(raw || "{}") as { ref?: string; after?: string };
    if (payload.ref && !payload.ref.endsWith(`/${web.branch}`)) {
      return ok({ ok: true, skipped: `ref ${payload.ref} != ${web.branch}` });
    }

    const [last] = await db
      .select({ n: deployments.number })
      .from(deployments)
      .where(eq(deployments.serviceId, serviceId))
      .orderBy(desc(deployments.number))
      .limit(1);
    const [deployment] = await db
      .insert(deployments)
      .values({
        serviceId,
        number: (last?.n ?? 0) + 1,
        trigger: "github",
        commitSha: payload.after?.slice(0, 12) ?? null,
      })
      .returning();
    const jobId = await createJob({
      type: "DEPLOY_WEB",
      serviceId,
      steps: DEPLOY_STEPS,
    });
    dispatch(deployWeb(jobId, serviceId, deployment.id, "github-push"));
    await audit({ serviceId, action: "github.webhook", detail: payload.after ?? "push" });
    return { ok: true, jobId, deployment: deployment.number };
  });
}
