import { NextRequest } from "next/server";
import { fail, rateLimit, route } from "@/lib/api";
import { requireUser } from "@/lib/auth";
import { versionCatalog } from "@/lib/minecraft/versions";
import { MINECRAFT_SOFTWARE, type MinecraftSoftware } from "@/lib/runtime/templates";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  return route(async () => {
    const user = await requireUser();
    rateLimit(`mc:versions:${user.id}`, 120);
    const software = url.searchParams.get("software") ?? "paper";
    if (!MINECRAFT_SOFTWARE.some((s) => s.id === software))
      return fail(`Unknown Minecraft software: ${software}`, 400);
    return versionCatalog(software as MinecraftSoftware);
  });
}
