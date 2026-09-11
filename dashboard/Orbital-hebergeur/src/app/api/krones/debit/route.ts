import { NextRequest } from "next/server";
import { body, route } from "@/lib/api";
import { HttpError, requireUser } from "@/lib/auth";
import { debitWallet } from "@/lib/krones/store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  return route(async () => {
    const user = await requireUser();
    const { amount, reason } = await body<{ amount?: number; reason?: string }>(req);
    if (!Number.isFinite(amount) || Number(amount) <= 0) throw new HttpError(400, "Montant invalide.");
    return debitWallet(user.id, Number(amount), reason || "debit");
  });
}
