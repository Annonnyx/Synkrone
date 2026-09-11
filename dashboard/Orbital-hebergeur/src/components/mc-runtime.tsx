"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { CloudOff, RefreshCw } from "lucide-react";
import { api } from "@/lib/client";
import { usePoll } from "@/lib/use-poll";
import { MINECRAFT_SOFTWARE } from "@/lib/minecraft/software";

export type VersionCatalog = {
  software: string;
  versions: string[];
  latest: string | null;
  loader: string | null;
  kind: "plugin" | "mod" | "none";
  source: "live" | "cache" | "stale" | "fallback";
  fetchedAt: string;
  error?: string;
};

const SOURCE_LABEL: Record<VersionCatalog["source"], string> = {
  live: "fetched from the publisher",
  cache: "cached",
  stale: "cached copy, refresh failed",
  fallback: "offline list",
};

/** Groups 1.21.4 under "1.21" and the newer 26.x scheme under "26". */
function family(version: string): string {
  const parts = version.split(".");
  return parts[0] === "1" && parts.length > 1 ? `${parts[0]}.${parts[1]}` : parts[0];
}

export function SoftwarePicker({
  value,
  onChange,
}: {
  value: string;
  onChange: (software: string) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
      {MINECRAFT_SOFTWARE.map((s) => (
        <button
          key={s.id}
          type="button"
          className="btn flex-col items-start"
          style={{
            borderColor: value === s.id ? "var(--accent)" : "var(--line)",
            color: value === s.id ? "var(--text)" : "var(--muted)",
          }}
          onClick={() => onChange(s.id)}
        >
          <span>{s.label}</span>
          <span className="text-[10px] font-normal text-[var(--muted)]">
            {s.kind === "none" ? "no add-ons" : `${s.kind}s`}
          </span>
        </button>
      ))}
    </div>
  );
}

export function VersionPicker({
  software,
  value,
  onChange,
}: {
  software: string;
  value: string;
  onChange: (version: string) => void;
}) {
  const [catalog, setCatalog] = useState<VersionCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [custom, setCustom] = useState(false);

  // Kept in refs so refreshing the catalogue does not restart on every keystroke.
  const valueRef = useRef(value);
  const customRef = useRef(custom);
  const onChangeRef = useRef(onChange);
  useEffect(() => {
    valueRef.current = value;
    customRef.current = custom;
    onChangeRef.current = onChange;
  });

  const load = useCallback(async () => {
    try {
      const next = await api<VersionCatalog>(
        `/api/minecraft/versions?software=${encodeURIComponent(software)}`,
      );
      setCatalog(next);
      setError(null);
      if (
        !customRef.current &&
        next.latest &&
        !next.versions.includes(valueRef.current)
      ) {
        onChangeRef.current(next.latest);
      }
    } catch (err) {
      setError((err as Error).message);
    }
  }, [software]);

  usePoll(load, undefined, software);

  const versions = catalog?.versions ?? [];
  const families = [...new Set(versions.map(family))];
  const degraded = catalog?.source === "fallback" || catalog?.source === "stale";

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {custom ? (
          <input
            className="input"
            value={value}
            placeholder="1.21.1, 25w05a, ..."
            onChange={(e) => onChange(e.target.value)}
          />
        ) : (
          <select
            className="select"
            value={versions.includes(value) ? value : ""}
            onChange={(e) => onChange(e.target.value)}
            disabled={!catalog}
          >
            <option value="" disabled>
              {catalog ? "Select a version" : "Loading versions…"}
            </option>
            {families.map((f) => (
              <optgroup key={f} label={`${f}.x`}>
                {versions
                  .filter((v) => family(v) === f)
                  .map((v) => (
                    <option key={v} value={v}>
                      {v}
                      {v === catalog?.latest ? "  (latest)" : ""}
                    </option>
                  ))}
              </optgroup>
            ))}
          </select>
        )}
        <button className="btn" type="button" onClick={() => void load()} title="Refresh the list">
          <RefreshCw size={13} />
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-3 text-[11px] text-[var(--muted)]">
        <label className="flex items-center gap-1.5">
          <input
            type="checkbox"
            checked={custom}
            onChange={(e) => setCustom(e.target.checked)}
          />
          custom version (snapshots, release candidates)
        </label>
        {catalog && (
          <span>
            {versions.length} releases · {SOURCE_LABEL[catalog.source]}
          </span>
        )}
        {degraded && (
          <span className="inline-flex items-center gap-1 text-[var(--warning)]">
            <CloudOff size={12} /> {catalog?.error ?? "version index unavailable"}
          </span>
        )}
        {error && <span className="text-[var(--danger)]">{error}</span>}
      </div>
    </div>
  );
}
