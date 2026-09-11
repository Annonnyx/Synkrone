import { route } from "@/lib/api";
import { requireUser } from "@/lib/auth";
import { getCatalog } from "@/lib/krones/store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return route(async () => {
    await requireUser();
    return getCatalog();
  });
}
