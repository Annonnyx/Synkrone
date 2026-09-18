import { NextRequest, NextResponse } from "next/server";
import { eq } from "drizzle-orm";
import { db } from "@/db";
import { sessions } from "@/db/schema";
import { sha256 } from "@/lib/crypto";
import { HttpError } from "@/lib/auth";
import { requireInternalAdmin } from "@/lib/internal-admin";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/**
 * Révoque une session panel par son token brut. Appelé par le site
 * principal au logout pour une déconnexion symétrique (les 2 ou aucun).
 */
export async function POST(req: NextRequest) {
  try {
    requireInternalAdmin(req);
    const body = (await req.json()) as { token?: string };
    const token = String(body.token || "").trim();
    if (token) {
      await db.delete(sessions).where(eq(sessions.tokenHash, sha256(token)));
    }
    return NextResponse.json({ ok: true });
  } catch (err) {
    const status = err instanceof HttpError ? err.status : 500;
    return NextResponse.json({ error: err instanceof Error ? err.message : "revoke_failed" }, { status });
  }
}
