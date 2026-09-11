import { HttpError } from "@/lib/auth";
import { getOAuthAccount, getValidAccessToken } from "./accounts";
import { getProviderConfig } from "./providers";
import type { GithubRepo } from "./types";
import { parseGithubRepo, type GithubRepoRef } from "./urls";

export type { GithubRepo };

function githubHeaders(token: string): HeadersInit {
  return {
    Accept: "application/vnd.github+json",
    Authorization: `Bearer ${token}`,
    "User-Agent": "Synkrone-Panel",
    "X-GitHub-Api-Version": "2022-11-28",
  };
}

export async function githubLinkStatus(userId: string) {
  const configured = Boolean(getProviderConfig("github"));
  const row = await getOAuthAccount(userId, "github");
  return {
    configured,
    linked: Boolean(row),
    login: row?.providerLogin ?? null,
  };
}

export async function listGithubRepos(userId: string): Promise<GithubRepo[]> {
  const status = await githubLinkStatus(userId);
  if (!status.configured) {
    throw new HttpError(503, "GitHub OAuth is not configured", "GITHUB_NOT_CONFIGURED");
  }
  if (!status.linked) {
    throw new HttpError(403, "Link a GitHub account before importing a repository", "GITHUB_NOT_LINKED");
  }
  const token = await getValidAccessToken(userId, "github");
  const res = await fetch(
    "https://api.github.com/user/repos?per_page=100&sort=updated&affiliation=owner,collaborator,organization_member",
    { headers: githubHeaders(token), cache: "no-store" },
  );
  if (res.status === 401) {
    throw new HttpError(401, "GitHub token expired — link the account again", "OAUTH_TOKEN_EXPIRED");
  }
  if (!res.ok) throw new HttpError(502, `GitHub API error (${res.status})`, "GITHUB_API");
  const rows = (await res.json()) as Array<{
    full_name: string;
    html_url: string;
    clone_url: string;
    default_branch: string;
    private: boolean;
    description: string | null;
  }>;
  return rows.map((r) => ({
    fullName: r.full_name,
    htmlUrl: r.html_url,
    cloneUrl: r.clone_url,
    defaultBranch: r.default_branch,
    private: r.private,
    description: r.description,
  }));
}

export async function assertGithubRepoAccess(userId: string, repoUrl: string): Promise<GithubRepoRef> {
  const status = await githubLinkStatus(userId);
  if (!status.configured) {
    throw new HttpError(503, "GitHub OAuth is not configured", "GITHUB_NOT_CONFIGURED");
  }
  if (!status.linked) {
    throw new HttpError(403, "Link a GitHub account before importing a repository", "GITHUB_NOT_LINKED");
  }
  const parsed = parseGithubRepo(repoUrl);
  if (!parsed) throw new HttpError(400, "Only github.com repositories can be imported");
  const token = await getValidAccessToken(userId, "github");
  const res = await fetch(`https://api.github.com/repos/${parsed.owner}/${parsed.repo}`, {
    headers: githubHeaders(token),
    cache: "no-store",
  });
  if (res.status === 404) {
    throw new HttpError(403, "GitHub did not grant access to that repository", "GITHUB_REPO_FORBIDDEN");
  }
  if (res.status === 401) {
    throw new HttpError(401, "GitHub token expired — link the account again", "OAUTH_TOKEN_EXPIRED");
  }
  if (!res.ok) throw new HttpError(502, `GitHub API error (${res.status})`, "GITHUB_API");
  return parsed;
}
