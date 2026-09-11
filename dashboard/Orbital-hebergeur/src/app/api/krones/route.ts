import { route } from "@/lib/api";
import { requireUser } from "@/lib/auth";
import { getWallet } from "@/lib/krones/store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return route(async () => {
    const user = await requireUser();
    return getWallet(user.id);
  });
}
