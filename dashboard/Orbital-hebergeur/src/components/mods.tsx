"use client";

import { useCallback, useRef, useState } from "react";
import {
  ArrowDownToLine,
  CloudOff,
  Download,
  ExternalLink,
  Loader2,
  Package,
  Search,
  Trash2,
  Upload,
} from "lucide-react";
import { api } from "@/lib/client";
import { withPanelBase } from "@/lib/panel-base";
import { usePoll } from "@/lib/use-poll";
import { ErrorText } from "@/components/panel";

type Hit = {
  projectId: string;
  slug: string;
  title: string;
  description: string;
  author: string;
  categories: string[];
  downloads: number;
  follows: number;
  iconUrl: string | null;
  serverSide: string;
  updatedAt: string;
  pageUrl: string;
};

type Addon = {
  id: string;
  kind: string;
  name: string;
  version: string | null;
  fileName: string;
  enabled: boolean;
  sizeBytes: number;
  provider: string;
  projectId: string | null;
  iconUrl: string | null;
  sourceUrl: string | null;
  dependency: boolean;
};

type Context = {
  software: string;
  gameVersion: string;
  kind: "plugin" | "mod" | "none";
  loaders: string[];
  directory: string | null;
  addons: Addon[];
};

type InstallStep = {
  projectId: string;
  versionId: string;
  title: string;
  versionNumber: string;
  fileName: string;
  size: number;
  iconUrl: string | null;
  dependency: boolean;
};

type ProjectVersion = {
  versionId: string;
  name: string;
  versionNumber: string;
  type: string;
  loaders: string[];
  gameVersions: string[];
  downloads: number;
  publishedAt: string;
  requiredDependencies: number;
};

const SORTS = [
  { id: "relevance", label: "Relevance" },
  { id: "downloads", label: "Downloads" },
  { id: "follows", label: "Followers" },
  { id: "updated", label: "Recently updated" },
  { id: "newest", label: "Newest" },
];

function compact(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function size(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

export function Addons({ serviceId }: { serviceId: string }) {
  const [ctx, setCtx] = useState<Context | null>(null);
  const [ctxError, setCtxError] = useState<string | null>(null);

  const [query, setQuery] = useState("");
  const [term, setTerm] = useState("");
  const [sort, setSort] = useState("relevance");
  const [anyVersion, setAnyVersion] = useState(false);
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const [plan, setPlan] = useState<{ hit: Hit; steps: InstallStep[]; warnings: string[] } | null>(
    null,
  );
  const [versions, setVersions] = useState<{ projectId: string; list: ProjectVersion[] } | null>(
    null,
  );
  const [working, setWorking] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);
  const uploadRef = useRef<HTMLInputElement>(null);

  const loadContext = useCallback(async () => {
    try {
      setCtx(await api<Context>(`/api/services/${serviceId}/mods`));
      setCtxError(null);
    } catch (err) {
      setCtxError((err as Error).message);
    }
  }, [serviceId]);

  usePoll(loadContext, undefined, serviceId);

  const software = ctx?.software;
  const gameVersion = ctx?.gameVersion;
  const kind = ctx?.kind;

  const runSearch = useCallback(
    async (nextOffset = 0) => {
      if (!software || kind === "none") return;
      setSearching(true);
      setSearchError(null);
      try {
        const params = new URLSearchParams({
          software,
          query: term,
          index: sort,
          offset: String(nextOffset),
          limit: "20",
        });
        if (!anyVersion && gameVersion) params.set("gameVersion", gameVersion);
        const res = await api<{ hits: Hit[]; total: number; offset: number }>(
          `/api/minecraft/mods?${params.toString()}`,
        );
        setHits(res.hits);
        setTotal(res.total);
        setOffset(res.offset);
      } catch (err) {
        setSearchError((err as Error).message);
        setHits([]);
      } finally {
        setSearching(false);
      }
    },
    [software, gameVersion, kind, term, sort, anyVersion],
  );

  const searchFromStart = useCallback(() => runSearch(0), [runSearch]);
  usePoll(
    searchFromStart,
    undefined,
    `${software ?? ""}:${gameVersion ?? ""}:${kind ?? ""}:${term}:${sort}:${anyVersion}`,
  );

  const onQuery = (value: string) => {
    setQuery(value);
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(() => setTerm(value), 400);
  };

  const preparePlan = async (hit: Hit, versionId?: string) => {
    setWorking(hit.projectId);
    setError(null);
    setNotice(null);
    try {
      const res = await api<{ steps: InstallStep[]; warnings: string[] }>(
        `/api/services/${serviceId}/mods`,
        { json: { op: "plan", projectId: hit.projectId, versionId } },
      );
      setVersions(null);
      setPlan({ hit, steps: res.steps, warnings: res.warnings });
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setWorking(null);
    }
  };

  const confirmInstall = async () => {
    if (!plan) return;
    setWorking(plan.hit.projectId);
    setError(null);
    try {
      const res = await api<{ addons: Addon[]; warnings: string[] }>(
        `/api/services/${serviceId}/mods`,
        {
          json: {
            op: "install",
            projectId: plan.hit.projectId,
            versionId: plan.steps[0]?.versionId,
          },
        },
      );
      setNotice(
        `Installed ${res.addons.map((a) => a.name).join(", ")} — restart the server to load it`,
      );
      setPlan(null);
      await loadContext();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setWorking(null);
    }
  };

  const showVersions = async (hit: Hit) => {
    if (!ctx) return;
    setWorking(hit.projectId);
    setError(null);
    try {
      const res = await api<{ versions: ProjectVersion[]; exactMatch: boolean }>(
        `/api/minecraft/mods/${hit.projectId}?software=${ctx.software}&gameVersion=${encodeURIComponent(ctx.gameVersion)}`,
      );
      setPlan(null);
      setVersions({ projectId: hit.projectId, list: res.versions });
      if (!res.exactMatch)
        setNotice(`No build for ${ctx.gameVersion}: showing every ${ctx.software} build.`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setWorking(null);
    }
  };

  const upload = async (files: FileList | File[]) => {
    setError(null);
    setNotice(null);
    for (const file of Array.from(files)) {
      if (!/\.(jar|zip)$/i.test(file.name)) {
        setError(`${file.name}: only .jar and .zip files are accepted`);
        continue;
      }
      setWorking(file.name);
      const form = new FormData();
      form.append("file", file);
      if (ctx?.kind && ctx.kind !== "none") form.append("kind", ctx.kind);
      try {
        const res = await fetch(withPanelBase(`/api/services/${serviceId}/mods`), {
          method: "POST",
          body: form,
        });
        if (!res.ok) throw new Error(((await res.json()) as { error?: string }).error ?? "Upload failed");
        setNotice(`${file.name} uploaded — restart the server to load it`);
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setWorking(null);
      }
    }
    await loadContext();
  };

  const toggle = async (addon: Addon) => {
    await api(`/api/services/${serviceId}/addons`, {
      method: "PUT",
      json: { addonId: addon.id, enabled: !addon.enabled },
    }).catch((err) => setError((err as Error).message));
    await loadContext();
  };

  const remove = async (addon: Addon) => {
    if (!confirm(`Remove ${addon.name}? The file is deleted from the volume.`)) return;
    await api(`/api/services/${serviceId}/addons?id=${addon.id}`, { method: "DELETE" }).catch(
      (err) => setError((err as Error).message),
    );
    await loadContext();
  };

  if (ctxError) return <ErrorText error={ctxError} />;
  if (!ctx) return <div className="text-sm text-[var(--muted)]">Loading add-ons…</div>;

  const label = ctx.kind === "plugin" ? "plugin" : "mod";
  const installed = new Set(ctx.addons.map((a) => a.projectId).filter(Boolean) as string[]);

  return (
    <div className="space-y-4">
      <div
        className="panel p-4"
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (e.dataTransfer.files.length) void upload(e.dataTransfer.files);
        }}
        style={{ borderColor: dragging ? "var(--accent)" : undefined }}
      >
        <div className="flex flex-wrap items-center gap-3">
          <Upload size={16} className="text-[var(--accent)]" />
          <div className="text-sm">
            Drag a <span className="font-mono">.jar</span> or{" "}
            <span className="font-mono">.zip</span> here to install it from your computer
          </div>
          <button className="btn ml-auto" onClick={() => uploadRef.current?.click()}>
            <ArrowDownToLine size={13} /> Choose a file
          </button>
          <input
            ref={uploadRef}
            type="file"
            multiple
            accept=".jar,.zip"
            className="hidden"
            onChange={(e) => e.target.files?.length && void upload(e.target.files)}
          />
        </div>
        <p className="mt-2 text-[11px] text-[var(--muted)]">
          Files land in <span className="font-mono">{ctx.directory ?? "the volume"}/</span> inside
          the server volume. Server runs {ctx.software} {ctx.gameVersion}
          {ctx.loaders.length > 0 && ` · accepts ${ctx.loaders.join(", ")} ${label}s`}.
        </p>
      </div>

      <ErrorText error={error} />
      {notice && <div className="text-xs text-[var(--success)]">{notice}</div>}

      {ctx.kind === "none" ? (
        <div className="panel px-4 py-6 text-sm text-[var(--muted)]">
          A vanilla server does not load plugins or mods. Switch the software to Paper, Purpur or
          Spigot for plugins, or Fabric, Forge, NeoForge or Quilt for mods, from the Overview tab.
          You can still drop files in the volume above.
        </div>
      ) : (
        <div className="panel">
          <div className="flex flex-wrap items-center gap-2 border-b border-[var(--line)] p-3">
            <div className="relative min-w-[220px] flex-1">
              <Search
                size={14}
                className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--muted)]"
              />
              <input
                className="input pl-8"
                placeholder={`Search ${label}s on Modrinth…`}
                value={query}
                onChange={(e) => onQuery(e.target.value)}
              />
            </div>
            <select className="select w-auto" value={sort} onChange={(e) => setSort(e.target.value)}>
              {SORTS.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
            <label className="flex items-center gap-1.5 text-[11px] text-[var(--muted)]">
              <input
                type="checkbox"
                checked={anyVersion}
                onChange={(e) => setAnyVersion(e.target.checked)}
              />
              any game version
            </label>
          </div>

          {searchError && (
            <div className="flex items-center gap-2 border-b border-[var(--line)] px-4 py-3 text-xs text-[var(--warning)]">
              <CloudOff size={14} /> {searchError} — you can still upload a file manually.
            </div>
          )}

          {plan && (
            <div className="border-b border-[var(--line)] bg-[var(--panel-2)] px-4 py-3">
              <div className="text-sm font-semibold">
                Install {plan.hit.title}
                {plan.steps.length > 1 && ` and ${plan.steps.length - 1} dependencies`}
              </div>
              <div className="mt-2 space-y-1 text-xs">
                {plan.steps.map((s) => (
                  <div key={s.versionId} className="flex items-center gap-2">
                    <Package size={12} className="text-[var(--muted)]" />
                    <span>{s.title}</span>
                    <span className="font-mono text-[10px] text-[var(--muted)]">
                      {s.versionNumber}
                    </span>
                    {s.dependency && (
                      <span className="rounded border border-[var(--line)] px-1 text-[10px] text-[var(--muted)]">
                        dependency
                      </span>
                    )}
                    <span className="ml-auto text-[10px] text-[var(--muted)]">{size(s.size)}</span>
                  </div>
                ))}
              </div>
              {plan.warnings.map((w) => (
                <div key={w} className="mt-2 text-[11px] text-[var(--warning)]">
                  {w}
                </div>
              ))}
              <div className="mt-3 flex gap-2">
                <button className="btn btn-primary" disabled={Boolean(working)} onClick={confirmInstall}>
                  {working ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
                  Install {plan.steps.length} file{plan.steps.length > 1 ? "s" : ""}
                </button>
                <button className="btn" onClick={() => setPlan(null)}>
                  Cancel
                </button>
              </div>
            </div>
          )}

          <div className="scroll max-h-[520px] overflow-y-auto">
            {(hits ?? []).map((hit) => (
              <div key={hit.projectId} className="border-b border-[var(--line)] px-4 py-3">
                <div className="flex gap-3">
                  {hit.iconUrl ? (
                    /* eslint-disable-next-line @next/next/no-img-element */
                    <img
                      src={hit.iconUrl}
                      alt=""
                      className="h-10 w-10 shrink-0 rounded-lg border border-[var(--line)] bg-[var(--panel-2)] object-cover"
                    />
                  ) : (
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-[var(--line)] bg-[var(--panel-2)]">
                      <Package size={16} className="text-[var(--muted)]" />
                    </div>
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-semibold">{hit.title}</span>
                      <span className="text-[11px] text-[var(--muted)]">by {hit.author}</span>
                      {installed.has(hit.projectId) && (
                        <span className="rounded border border-[var(--accent)] px-1.5 text-[10px] text-[var(--success)]">
                          installed
                        </span>
                      )}
                      <a
                        className="text-[var(--muted)] hover:text-[var(--text)]"
                        href={hit.pageUrl}
                        target="_blank"
                        rel="noreferrer"
                      >
                        <ExternalLink size={12} />
                      </a>
                    </div>
                    <p className="mt-0.5 line-clamp-2 text-xs text-[var(--muted)]">
                      {hit.description}
                    </p>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-[10px] text-[var(--muted)]">
                      <span>{compact(hit.downloads)} downloads</span>
                      {hit.categories.slice(0, 4).map((c) => (
                        <span key={c} className="rounded border border-[var(--line)] px-1.5">
                          {c}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-col gap-1">
                    <button
                      className="btn btn-primary"
                      disabled={working === hit.projectId}
                      onClick={() => preparePlan(hit)}
                    >
                      {working === hit.projectId ? (
                        <Loader2 size={13} className="animate-spin" />
                      ) : (
                        <Download size={13} />
                      )}
                      Install
                    </button>
                    <button className="btn" onClick={() => showVersions(hit)}>
                      Versions
                    </button>
                  </div>
                </div>

                {versions?.projectId === hit.projectId && (
                  <div className="scroll mt-2 max-h-52 overflow-y-auto rounded-lg border border-[var(--line)]">
                    {versions.list.map((v) => (
                      <div
                        key={v.versionId}
                        className="flex items-center gap-2 border-b border-[var(--line)] px-3 py-1.5 text-[11px] last:border-b-0"
                      >
                        <span className="font-mono">{v.versionNumber}</span>
                        <span className="text-[var(--muted)]">{v.type}</span>
                        <span className="truncate text-[var(--muted)]">
                          {v.gameVersions.slice(0, 4).join(", ")}
                          {v.gameVersions.length > 4 ? "…" : ""}
                        </span>
                        <button
                          className="btn ml-auto"
                          onClick={() => preparePlan(hit, v.versionId)}
                        >
                          Select
                        </button>
                      </div>
                    ))}
                    {versions.list.length === 0 && (
                      <div className="px-3 py-2 text-[11px] text-[var(--muted)]">
                        No build published for {ctx.software}.
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}

            {searching && (
              <div className="px-4 py-6 text-center text-xs text-[var(--muted)]">Searching…</div>
            )}
            {!searching && hits && hits.length === 0 && !searchError && (
              <div className="px-4 py-6 text-center text-xs text-[var(--muted)]">
                No {label} found for {ctx.software} {anyVersion ? "" : ctx.gameVersion}.
              </div>
            )}
          </div>

          {total > 20 && (
            <div className="flex items-center gap-2 border-t border-[var(--line)] px-4 py-2 text-xs">
              <button
                className="btn"
                disabled={offset === 0 || searching}
                onClick={() => void runSearch(Math.max(0, offset - 20))}
              >
                Previous
              </button>
              <span className="text-[var(--muted)]">
                {offset + 1}–{Math.min(offset + 20, total)} of {total}
              </span>
              <button
                className="btn ml-auto"
                disabled={offset + 20 >= total || searching}
                onClick={() => void runSearch(offset + 20)}
              >
                Next
              </button>
            </div>
          )}
        </div>
      )}

      <div className="panel">
        <div className="border-b border-[var(--line)] px-4 py-2">
          <span className="label">Installed</span>
          <span className="ml-2 text-[11px] text-[var(--muted)]">{ctx.addons.length}</span>
        </div>
        {ctx.addons.map((addon) => (
          <div
            key={addon.id}
            className="flex flex-wrap items-center gap-3 border-b border-[var(--line)] px-4 py-2 text-xs last:border-b-0"
          >
            <span className="font-semibold">{addon.name}</span>
            {addon.version && (
              <span className="font-mono text-[10px] text-[var(--muted)]">{addon.version}</span>
            )}
            {addon.dependency && (
              <span className="rounded border border-[var(--line)] px-1.5 text-[10px] text-[var(--muted)]">
                dependency
              </span>
            )}
            {!addon.enabled && (
              <span className="rounded border border-[var(--danger)] px-1.5 text-[10px] text-[var(--danger)]">
                disabled
              </span>
            )}
            <span className="truncate font-mono text-[10px] text-[var(--muted)]">
              {addon.fileName}
            </span>
            <div className="ml-auto flex items-center gap-3 text-[var(--muted)]">
              <span>{size(addon.sizeBytes)}</span>
              <span className="text-[10px]">{addon.provider}</span>
              <button className="btn" onClick={() => toggle(addon)}>
                {addon.enabled ? "Disable" : "Enable"}
              </button>
              <button className="text-[var(--danger)]" onClick={() => remove(addon)}>
                <Trash2 size={13} />
              </button>
            </div>
          </div>
        ))}
        {ctx.addons.length === 0 && (
          <div className="px-4 py-4 text-xs text-[var(--muted)]">No {label} installed yet.</div>
        )}
      </div>
    </div>
  );
}
