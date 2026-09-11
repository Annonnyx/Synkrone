import { SOFTWARE_KIND, SOFTWARE_LOADER, type MinecraftSoftware } from "./software";

/**
 * Game versions available per server software.
 *
 * Each family publishes its own index, so we query the authoritative source
 * instead of guessing from a single manifest:
 *   vanilla/spigot -> Mojang version manifest (Spigot builds from vanilla jars)
 *   paper          -> PaperMC fill API v3
 *   purpur         -> PurpurMC API v2
 *   fabric/quilt   -> loader meta endpoints (game versions with a stable flag)
 *   forge/neoforge -> Maven indexes, whose loader versions encode the game version
 *
 * Results are cached in memory; the last successful payload is kept and served
 * as a stale fallback so an offline panel still shows a usable list.
 */

const TTL_MS = 6 * 60 * 60 * 1000;
const TIMEOUT_MS = 8000;
const USER_AGENT = "Orbital-Panel/1.0 (+https://github.com/orbital)";

export type VersionCatalog = {
  software: MinecraftSoftware;
  versions: string[];
  latest: string | null;
  /** Modrinth loader id matching this software, when it accepts add-ons. */
  loader: string | null;
  kind: "plugin" | "mod" | "none";
  source: "live" | "cache" | "stale" | "fallback";
  fetchedAt: string;
  error?: string;
};

type CacheEntry = { at: number; versions: string[] };
const cache = new Map<string, CacheEntry>();

/** Curated offline fallback: enough to create a server without network access. */
const FALLBACK: string[] = [
  "1.21.4",
  "1.21.1",
  "1.21",
  "1.20.6",
  "1.20.4",
  "1.20.1",
  "1.19.4",
  "1.19.2",
  "1.18.2",
  "1.17.1",
  "1.16.5",
  "1.12.2",
  "1.8.8",
];

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url, {
    headers: { "User-Agent": USER_AGENT, Accept: "application/json" },
    signal: AbortSignal.timeout(TIMEOUT_MS),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`${new URL(url).host} responded ${res.status}`);
  return (await res.json()) as T;
}

/** Release versions only: pre-releases, release candidates and snapshots are noise here. */
function isRelease(version: string): boolean {
  return /^\d+(\.\d+)*$/.test(version);
}

function compareVersions(a: string, b: string): number {
  const pa = a.split(".").map((n) => Number.parseInt(n, 10) || 0);
  const pb = b.split(".").map((n) => Number.parseInt(n, 10) || 0);
  for (let i = 0; i < Math.max(pa.length, pb.length); i += 1) {
    const diff = (pb[i] ?? 0) - (pa[i] ?? 0);
    if (diff !== 0) return diff;
  }
  return 0;
}

function tidy(versions: string[]): string[] {
  return [...new Set(versions.filter(isRelease))].sort(compareVersions);
}

/**
 * Forge and NeoForge publish loader versions, not game versions.
 * `A.B.C.D` maps to game version `A.B[.C]` (current scheme) and the legacy
 * three-part `A.B.C` maps to `1.A[.B]`.
 */
function gameVersionFromLoader(loaderVersion: string): string | null {
  const parts = loaderVersion.split(".");
  if (parts.length === 4) {
    const [major, minor, patch] = parts;
    return patch === "0" ? `${major}.${minor}` : `${major}.${minor}.${patch}`;
  }
  if (parts.length === 3) {
    const [major, minor] = parts;
    return minor === "0" ? `1.${major}` : `1.${major}.${minor}`;
  }
  return null;
}

async function mojangReleases(): Promise<string[]> {
  const data = await getJson<{ versions: Array<{ id: string; type: string }> }>(
    "https://launchermeta.mojang.com/mc/game/version_manifest_v2.json",
  );
  return data.versions.filter((v) => v.type === "release").map((v) => v.id);
}

async function fetchVersions(software: MinecraftSoftware): Promise<string[]> {
  switch (software) {
    case "vanilla":
    case "spigot":
      return mojangReleases();
    case "paper": {
      const data = await getJson<{ versions: Record<string, string[]> }>(
        "https://fill.papermc.io/v3/projects/paper",
      );
      return Object.values(data.versions).flat();
    }
    case "purpur": {
      const data = await getJson<{ versions: string[] }>("https://api.purpurmc.org/v2/purpur");
      return data.versions;
    }
    case "fabric": {
      const data = await getJson<Array<{ version: string; stable: boolean }>>(
        "https://meta.fabricmc.net/v2/versions/game",
      );
      return data.filter((v) => v.stable).map((v) => v.version);
    }
    case "quilt": {
      const data = await getJson<Array<{ version: string; stable: boolean }>>(
        "https://meta.quiltmc.org/v3/versions/game",
      );
      return data.filter((v) => v.stable).map((v) => v.version);
    }
    case "forge": {
      const data = await getJson<{ promos: Record<string, string> }>(
        "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json",
      );
      return Object.keys(data.promos).map((k) => k.replace(/-(latest|recommended)$/, ""));
    }
    case "neoforge": {
      const data = await getJson<{ versions: string[] }>(
        "https://maven.neoforged.net/api/maven/versions/releases/net/neoforged/neoforge",
      );
      return data.versions
        .filter((v) => /^\d+(\.\d+){2,3}$/.test(v))
        .map(gameVersionFromLoader)
        .filter((v): v is string => Boolean(v));
    }
    default:
      return mojangReleases();
  }
}

export async function versionCatalog(software: MinecraftSoftware): Promise<VersionCatalog> {
  const base = {
    software,
    loader: SOFTWARE_LOADER[software] ?? null,
    kind: SOFTWARE_KIND[software] ?? "none",
  };
  const cached = cache.get(software);
  if (cached && Date.now() - cached.at < TTL_MS) {
    return {
      ...base,
      versions: cached.versions,
      latest: cached.versions[0] ?? null,
      source: "cache",
      fetchedAt: new Date(cached.at).toISOString(),
    };
  }

  try {
    const versions = tidy(await fetchVersions(software));
    if (!versions.length) throw new Error("Upstream returned no release version");
    cache.set(software, { at: Date.now(), versions });
    return {
      ...base,
      versions,
      latest: versions[0] ?? null,
      source: "live",
      fetchedAt: new Date().toISOString(),
    };
  } catch (err) {
    const message = (err as Error).message;
    if (cached) {
      return {
        ...base,
        versions: cached.versions,
        latest: cached.versions[0] ?? null,
        source: "stale",
        fetchedAt: new Date(cached.at).toISOString(),
        error: message,
      };
    }
    return {
      ...base,
      versions: FALLBACK,
      latest: FALLBACK[0],
      source: "fallback",
      fetchedAt: new Date().toISOString(),
      error: message,
    };
  }
}
