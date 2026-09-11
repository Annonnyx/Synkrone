import { route } from "@/lib/api";
import { requireUser } from "@/lib/auth";
import { readPlatformSettings } from "@/lib/platform-settings";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return route(async () => {
    await requireUser();
    return readPlatformSettings();
  });
}
