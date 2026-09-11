import { createHash } from "node:crypto";
import { loaderCompat, type MinecraftSoftware } from "./software";

export { addonDirectory, addonKind, loaderCompat } from "./software";

/**
 * Modrinth v2 client. Modrinth is used rather than CurseForge because its API
 * is public and needs no API key, and because it exposes an explicit dependency
 * graph per version, which is what the installer walks.
 */

const API = "https://api.modrinth.com/v2";
const TIMEOUT_MS = 12_000;
const DOWNLOAD_TIMEOUT_MS = 120_000;
const MAX_FILE_BYTES = 256 * 1024 * 1024;
const ALLOWED_DOWNLOAD_HOSTS = new Set(["cdn.modrinth.com"]);
const USER_AGENT = "Orbital-Panel/1.0 (+https://github.com/orbital)";

export class ModrinthError extends Error {
  status: number;
  constructor(message: string, status = 502) {
    super(message);
    this.status = status;
  }
}

export type ModrinthHit = {
  project_id: string;
  slug: string;
  title: string;
  description: string;
  author: string;
  categories: string[];
  display_categories?: string[];
  downloads: number;
  follows: number;
  icon_url: string | null;
  versions: string[];
  latest_version?: string;
  project_type: string;
  client_side: string;
  server_side: string;
  date_modified: string;
};

export type ModrinthFile = {
  url: string;
  filename: string;
  primary: boolean;
  size: number;
  hashes: { sha1?: string; sha512?: string };
};

export type ModrinthVersion = {
  id: string;
  project_id: string;
  name: string;
  version_number: string;
  version_type: string;
  loaders: string[];
  game_versions: string[];
  downloads: number;
  date_published: string;
  files: ModrinthFile[];
  dependencies: Array<{
    project_id: string | null;
    version_id: string | null;
    file_name: string | null;
    dependency_type: "required" | "optional" | "incompatible" | "embedded";
  }>;
};

export type InstallStep = {
  projectId: string;
  versionId: string;
  title: string;
  versionNumber: string;
  fileName: string;
  url: string;
  size: number;
  sha1: string | null;
  iconUrl: string | null;
  /** Pulled in to satisfy another add-on rather than picked by the user. */
  dependency: boolean;
};

async function call<T>(path: string, timeout = TIMEOUT_MS): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, {
      headers: { "User-Agent": USER_AGENT, Accept: "application/json" },
      signal: AbortSignal.timeout(timeout),
      cache: "no-store",
    });
  } catch (err) {
    throw new ModrinthError(`Modrinth is unreachable: ${(err as Error).message}`, 503);
  }
  if (res.status === 404) throw new ModrinthError("Not found on Modrinth", 404);
  if (res.status === 429) throw new ModrinthError("Modrinth rate limit reached, retry shortly", 429);
  if (!res.ok) throw new ModrinthError(`Modrinth responded ${res.status}`, 502);
  return (await res.json()) as T;
}

function facets(groups: string[][]): string {
  return encodeURIComponent(JSON.stringify(groups.filter((g) => g.length > 0)));
}

export async function search(params: {
  query?: string;
  software?: string;
  gameVersion?: string;
  category?: string;
  offset?: number;
  limit?: number;
  index?: string;
}): Promise<{ hits: ModrinthHit[]; total_hits: number; offset: number; limit: number }> {
  const loaders = loaderCompat(params.software ?? "");
  const groups: string[][] = [];
  if (loaders.length) groups.push(loaders.map((l) => `categories:${l}`));
  if (params.gameVersion) groups.push([`versions:${params.gameVersion}`]);
  if (params.category) groups.push([`categories:${params.category}`]);
  groups.push(["project_type:mod", "project_type:plugin"]);

  const limit = Math.min(Math.max(params.limit ?? 20, 1), 50);
  const offset = Math.max(params.offset ?? 0, 0);
  const index = ["relevance", "downloads", "follows", "newest", "updated"].includes(
    params.index ?? "",
  )
    ? params.index
    : "relevance";

  const qs = new URLSearchParams({
    query: params.query ?? "",
    limit: String(limit),
    offset: String(offset),
    index: String(index),
  });
  return call(`/search?${qs.toString()}&facets=${facets(groups)}`);
}

export async function projectVersions(
  projectId: string,
  opts: { software?: string; gameVersion?: string } = {},
): Promise<ModrinthVersion[]> {
  const qs: string[] = [];
  const loaders = loaderCompat(opts.software ?? "");
  if (loaders.length) qs.push(`loaders=${encodeURIComponent(JSON.stringify(loaders))}`);
  if (opts.gameVersion)
    qs.push(`game_versions=${encodeURIComponent(JSON.stringify([opts.gameVersion]))}`);
  const versions = await call<ModrinthVersion[]>(
    `/project/${encodeURIComponent(projectId)}/version${qs.length ? `?${qs.join("&")}` : ""}`,
  );
  return versions.sort(
    (a, b) => Date.parse(b.date_published) - Date.parse(a.date_published),
  );
}

export async function getVersion(versionId: string): Promise<ModrinthVersion> {
  return call<ModrinthVersion>(`/version/${encodeURIComponent(versionId)}`);
}

export async function getProject(projectId: string): Promise<{
  id: string;
  slug: string;
  title: string;
  description: string;
  icon_url: string | null;
  project_type: string;
  categories: string[];
  game_versions: string[];
  loaders: string[];
}> {
  return call(`/project/${encodeURIComponent(projectId)}`);
}

function primaryFile(version: ModrinthVersion): ModrinthFile {
  const file = version.files.find((f) => f.primary) ?? version.files[0];
  if (!file) throw new ModrinthError(`Version ${version.id} has no downloadable file`, 422);
  return file;
}

function toStep(
  version: ModrinthVersion,
  title: string,
  iconUrl: string | null,
  dependency: boolean,
): InstallStep {
  const file = primaryFile(version);
  return {
    projectId: version.project_id,
    versionId: version.id,
    title,
    versionNumber: version.version_number,
    fileName: file.filename,
    url: file.url,
    size: file.size,
    sha1: file.hashes?.sha1 ?? null,
    iconUrl,
    dependency,
  };
}

/**
 * Walks the required-dependency graph breadth first. Optional, embedded and
 * incompatible dependencies are ignored: only hard requirements are installed.
 */
export async function resolveInstallPlan(opts: {
  projectId: string;
  versionId?: string;
  software: string;
  gameVersion?: string;
  maxDepth?: number;
}): Promise<{ steps: InstallStep[]; warnings: string[] }> {
  const warnings: string[] = [];
  const steps: InstallStep[] = [];
  const seenProjects = new Set<string>();
  const maxDepth = opts.maxDepth ?? 4;

  type Pending = { projectId: string; versionId?: string; depth: number };
  const queue: Pending[] = [{ projectId: opts.projectId, versionId: opts.versionId, depth: 0 }];

  while (queue.length) {
    const item = queue.shift()!;
    if (seenProjects.has(item.projectId)) continue;

    let version: ModrinthVersion | null = null;
    if (item.versionId) {
      version = await getVersion(item.versionId).catch(() => null);
    }
    if (!version) {
      const candidates = await projectVersions(item.projectId, {
        software: opts.software,
        gameVersion: opts.gameVersion,
      }).catch(() => [] as ModrinthVersion[]);
      version =
        candidates.find((v) => v.version_type === "release") ??
        candidates[0] ??
        // Relax the game version constraint before giving up on a dependency.
        (
          await projectVersions(item.projectId, { software: opts.software }).catch(
            () => [] as ModrinthVersion[],
          )
        )[0] ??
        null;
    }

    if (!version) {
      const label = item.depth === 0 ? "this add-on" : `dependency ${item.projectId}`;
      if (item.depth === 0)
        throw new ModrinthError(
          `No compatible version of ${label} for ${opts.software} ${opts.gameVersion ?? ""}`.trim(),
          422,
        );
      warnings.push(`No compatible version found for ${label}; skipped.`);
      continue;
    }

    if (seenProjects.has(version.project_id)) continue;
    seenProjects.add(item.projectId);
    seenProjects.add(version.project_id);
    const project = await getProject(version.project_id).catch(() => null);
    steps.push(
      toStep(version, project?.title ?? version.name, project?.icon_url ?? null, item.depth > 0),
    );

    if (item.depth >= maxDepth) continue;
    for (const dep of version.dependencies ?? []) {
      if (dep.dependency_type !== "required") continue;
      const depProject = dep.project_id;
      if (!depProject) {
        if (dep.version_id) queue.push({ projectId: dep.version_id, versionId: dep.version_id, depth: item.depth + 1 });
        continue;
      }
      if (seenProjects.has(depProject)) continue;
      queue.push({
        projectId: depProject,
        versionId: dep.version_id ?? undefined,
        depth: item.depth + 1,
      });
    }
  }

  return { steps, warnings };
}

export async function downloadStep(step: InstallStep): Promise<Buffer> {
  const url = new URL(step.url);
  if (url.protocol !== "https:" || !ALLOWED_DOWNLOAD_HOSTS.has(url.host))
    throw new ModrinthError(`Refusing to download from ${url.host}`, 400);

  let res: Response;
  try {
    res = await fetch(url, {
      headers: { "User-Agent": USER_AGENT },
      signal: AbortSignal.timeout(DOWNLOAD_TIMEOUT_MS),
      cache: "no-store",
    });
  } catch (err) {
    throw new ModrinthError(`Download failed: ${(err as Error).message}`, 503);
  }
  if (!res.ok) throw new ModrinthError(`Download failed with status ${res.status}`, 502);

  const buffer = Buffer.from(await res.arrayBuffer());
  if (buffer.byteLength > MAX_FILE_BYTES)
    throw new ModrinthError("Downloaded file exceeds the 256MB limit", 413);
  if (step.sha1) {
    const digest = createHash("sha1").update(buffer).digest("hex");
    if (digest !== step.sha1) throw new ModrinthError("Checksum mismatch on the downloaded file", 502);
  }
  return buffer;
}
