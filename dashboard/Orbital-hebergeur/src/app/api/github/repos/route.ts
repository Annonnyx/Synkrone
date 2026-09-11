import { route } from "@/lib/api";
import { requireUser } from "@/lib/auth";
import { githubLinkStatus, listGithubRepos } from "@/lib/oauth/github";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return route(async () => {
    const user = await requireUser();
    const status = await githubLinkStatus(user.id);
    if (!status.configured || !status.linked) {
      return { ...status, repos: [] };
    }
    return { ...status, repos: await listGithubRepos(user.id) };
  });
}
