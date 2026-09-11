import { NextRequest } from "next/server";
import { fail, rateLimit, route } from "@/lib/api";
import { requireUser } from "@/lib/auth";
import { ModrinthError, getProject, projectVersions } from "@/lib/minecraft/modrinth";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(req: NextRequest, ctx: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await ctx.params;
  const url = new URL(req.url);
  return route(async () => {
    const user = await requireUser();
    rateLimit(`mods:project:${user.id}`, 180);
    if (!/^[A-Za-z0-9._-]{1,64}$/.test(projectId)) return fail("Invalid project id", 400);

    const software = url.searchParams.get("software") ?? undefined;
    const gameVersion = url.searchParams.get("gameVersion") ?? undefined;

    try {
      const [project, compatible, all] = await Promise.all([
        getProject(projectId),
        projectVersions(projectId, { software, gameVersion }),
        projectVersions(projectId, { software }),
      ]);
      return {
        project: {
          projectId: project.id,
          slug: project.slug,
          title: project.title,
          description: project.description,
          iconUrl: project.icon_url,
          categories: project.categories,
          gameVersions: project.game_versions,
          loaders: project.loaders,
          pageUrl: `https://modrinth.com/project/${project.slug}`,
        },
        // Falls back to every loader-compatible build so the user can still pick
        // one when nothing matches the exact game version.
        exactMatch: compatible.length > 0,
        versions: (compatible.length ? compatible : all).slice(0, 60).map((v) => ({
          versionId: v.id,
          name: v.name,
          versionNumber: v.version_number,
          type: v.version_type,
          loaders: v.loaders,
          gameVersions: v.game_versions,
          downloads: v.downloads,
          publishedAt: v.date_published,
          requiredDependencies: (v.dependencies ?? []).filter(
            (d) => d.dependency_type === "required",
          ).length,
        })),
      };
    } catch (err) {
      if (err instanceof ModrinthError) return fail(err.message, err.status, { offline: true });
      throw err;
    }
  });
}
