export type GithubRepoRef = {
  owner: string;
  repo: string;
  httpsUrl: string;
  fullName: string;
};

const GH_HOST = "github.com";

export function parseGithubRepo(input: string | null | undefined): GithubRepoRef | null {
  if (!input) return null;
  const raw = input.trim();
  const shorthand = raw.match(/^([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]+?)(?:\.git)?$/);
  if (shorthand && !raw.includes(":") && !raw.includes(" ")) {
    return toRef(shorthand[1], shorthand[2]);
  }
  const ssh = raw.match(/^git@github\.com:([A-Za-z0-9_.-]+)\/([A-Za-z0-9_.-]+?)(?:\.git)?$/i);
  if (ssh) return toRef(ssh[1], ssh[2]);
  try {
    const withProto = /^https?:\/\//i.test(raw) ? raw : `https://${raw}`;
    const url = new URL(withProto);
    if (url.hostname !== GH_HOST && url.hostname !== `www.${GH_HOST}`) return null;
    const parts = url.pathname.replace(/^\/+|\/+$/g, "").split("/");
    if (parts.length < 2) return null;
    return toRef(parts[0], parts[1].replace(/\.git$/i, ""));
  } catch {
    return null;
  }
}

function toRef(owner: string, repo: string): GithubRepoRef | null {
  if (!owner || !repo || owner === "." || repo === ".") return null;
  return {
    owner,
    repo,
    fullName: `${owner}/${repo}`,
    httpsUrl: `https://github.com/${owner}/${repo}.git`,
  };
}

/** Authenticated clone URL. Never log the return value. */
export function githubCloneUrl(repoUrl: string, token: string): string | null {
  const parsed = parseGithubRepo(repoUrl);
  if (!parsed) return null;
  const url = new URL(parsed.httpsUrl);
  url.username = "x-access-token";
  url.password = token;
  return url.toString();
}

export function redactSecrets(text: string): string {
  return text
    .replace(/x-access-token:[^@\s]+@/gi, "x-access-token:***@")
    .replace(/ghp_[A-Za-z0-9_]+/g, "ghp_***")
    .replace(/gho_[A-Za-z0-9_]+/g, "gho_***")
    .replace(/github_pat_[A-Za-z0-9_]+/g, "github_pat_***");
}
