import { body, route } from "@/lib/api";
import { HttpError, requireUser } from "@/lib/auth";
import { allowOpenCredit, creditWallet } from "@/lib/krones/store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: Request) {
  return route(async () => {
    const user = await requireUser();
    if (!allowOpenCredit()) throw new HttpError(403, "Crédit démo désactivé. Utilisez la boutique Krônes.");
    const payload = await body<{ amount?: number; reason?: string }>(req);
    const amount = Number(payload.amount);
    if (!Number.isFinite(amount) || amount <= 0) throw new HttpError(400, "Montant invalide.");
    return creditWallet(user.id, amount, String(payload.reason || "credit"));
  });
}
