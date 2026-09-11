import { NextRequest } from "next/server";
import { fail, rateLimit, route } from "@/lib/api";
import { requireUser } from "@/lib/auth";
import { ModrinthError, addonKind, search } from "@/lib/minecraft/modrinth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  return route(async () => {
    const user = await requireUser();
    rateLimit(`mods:search:${user.id}`, 120);

    const software = url.searchParams.get("software") ?? "paper";
    const kind = addonKind(software);
    if (kind === "none")
      return fail(`${software} servers do not load plugins or mods`, 400, { kind });

    try {
      const result = await search({
        query: url.searchParams.get("query") ?? "",
        software,
        gameVersion: url.searchParams.get("gameVersion") ?? undefined,
        category: url.searchParams.get("category") ?? undefined,
        index: url.searchParams.get("index") ?? undefined,
        offset: Number(url.searchParams.get("offset") ?? 0),
        limit: Number(url.searchParams.get("limit") ?? 20),
      });
      return {
        kind,
        total: result.total_hits,
        offset: result.offset,
        limit: result.limit,
        hits: result.hits.map((h) => ({
          projectId: h.project_id,
          slug: h.slug,
          title: h.title,
          description: h.description,
          author: h.author,
          categories: h.display_categories ?? h.categories,
          downloads: h.downloads,
          follows: h.follows,
          iconUrl: h.icon_url,
          serverSide: h.server_side,
          updatedAt: h.date_modified,
          pageUrl: `https://modrinth.com/${h.project_type === "plugin" ? "plugin" : "mod"}/${h.slug}`,
        })),
      };
    } catch (err) {
      if (err instanceof ModrinthError) return fail(err.message, err.status, { offline: true });
      throw err;
    }
  });
}
