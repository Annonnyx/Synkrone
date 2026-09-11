"use client";

import { useCallback, useMemo, useState } from "react";
import { Plus, RotateCcw, Save, Search, Trash2 } from "lucide-react";
import { api } from "@/lib/client";
import { usePoll } from "@/lib/use-poll";
import {
  PROPERTY_BY_KEY,
  PROPERTY_CATEGORIES,
  SERVER_PROPERTIES,
  defaultProperties,
  isValidPropertyKey,
  type PropertyDef,
} from "@/lib/minecraft/properties";
import { ErrorText } from "@/components/panel";

const DEFAULTS = defaultProperties();
const CATEGORY_ORDER: string[] = [...PROPERTY_CATEGORIES, "Custom"];

function customDef(key: string): PropertyDef {
  return {
    key,
    kind: "string",
    default: "",
    category: "Custom",
    description: "Not part of the vanilla catalogue: added by a plugin, a mod or by you.",
  };
}

/** Renders the control matching a property type; shared with the creation wizard. */
export function PropertyControl({
  def,
  value,
  onChange,
}: {
  def: PropertyDef;
  value: string;
  onChange: (next: string) => void;
}) {
  if (def.kind === "boolean")
    return (
      <select
        className="select"
        value={value === "true" ? "true" : "false"}
        disabled={def.managed}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="true">true</option>
        <option value="false">false</option>
      </select>
    );
  if (def.kind === "enum")
    return (
      <select
        className="select"
        value={value}
        disabled={def.managed}
        onChange={(e) => onChange(e.target.value)}
      >
        {(def.options ?? [])
          .concat(def.options?.includes(value) || !value ? [] : [value])
          .map((o) => (
            <option key={o} value={o}>
              {o}
            </option>
          ))}
      </select>
    );
  if (def.kind === "integer")
    return (
      <input
        className="input"
        type="number"
        value={value}
        min={def.min}
        max={def.max}
        disabled={def.managed}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  return (
    <input
      className="input"
      value={value}
      disabled={def.managed}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

function PropertyField({
  def,
  value,
  onChange,
  onReset,
  onRemove,
}: {
  def: PropertyDef;
  value: string;
  onChange: (next: string) => void;
  onReset?: () => void;
  onRemove?: () => void;
}) {
  const modified = value !== (DEFAULTS[def.key] ?? def.default);
  return (
    <div className="border-b border-[var(--line)] px-4 py-3 last:border-b-0">
      <div className="flex items-center gap-2">
        <span className="font-mono text-[12px]">{def.key}</span>
        {def.managed && (
          <span className="rounded border border-[var(--line)] px-1.5 py-0.5 text-[10px] text-[var(--muted)]">
            managed
          </span>
        )}
        {modified && !def.managed && (
          <span className="rounded border border-[#3a5bbf] px-1.5 py-0.5 text-[10px] text-[var(--accent)]">
            modified
          </span>
        )}
        <div className="ml-auto flex items-center gap-2">
          {onReset && modified && !def.managed && (
            <button
              type="button"
              className="text-[var(--muted)] hover:text-[var(--text)]"
              title={`Reset to ${DEFAULTS[def.key] ?? def.default ?? "(empty)"}`}
              onClick={onReset}
            >
              <RotateCcw size={13} />
            </button>
          )}
          {onRemove && (
            <button
              type="button"
              className="text-[var(--danger)]"
              title="Remove this property"
              onClick={onRemove}
            >
              <Trash2 size={13} />
            </button>
          )}
        </div>
      </div>
      <div className="mt-2 grid gap-2 md:grid-cols-[280px_1fr] md:items-center">
        <PropertyControl def={def} value={value} onChange={onChange} />
        <p className="text-[11px] text-[var(--muted)]">{def.description}</p>
      </div>
    </div>
  );
}

export function MinecraftProperties({
  serviceId,
  properties,
  onSaved,
}: {
  serviceId: string;
  properties: Record<string, string>;
  onSaved?: () => void;
}) {
  const [props, setProps] = useState<Record<string, string>>({ ...DEFAULTS, ...properties });
  const [removed, setRemoved] = useState<string[]>([]);
  const [raw, setRaw] = useState("");
  const [rawMode, setRawMode] = useState(false);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<string>("all");
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadRaw = useCallback(async () => {
    try {
      const res = await api<{ raw: string; parsed: Record<string, string> }>(
        `/api/services/${serviceId}/minecraft`,
      );
      setRaw(res.raw);
      // The file on disk is the source of truth for keys a plugin added itself.
      if (Object.keys(res.parsed).length) {
        setProps((current) => ({ ...res.parsed, ...current }));
      }
    } catch {
      /* the form still works from the database copy */
    }
  }, [serviceId]);

  usePoll(loadRaw, undefined, serviceId);

  const customKeys = useMemo(
    () => Object.keys(props).filter((k) => !PROPERTY_BY_KEY[k]).sort(),
    [props],
  );

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const all: PropertyDef[] = [...SERVER_PROPERTIES, ...customKeys.map(customDef)];
    return all.filter((def) => {
      if (category !== "all" && def.category !== category) return false;
      if (!needle) return true;
      return (
        def.key.includes(needle) || def.description.toLowerCase().includes(needle)
      );
    });
  }, [query, category, customKeys]);

  const grouped = useMemo(() => {
    const map = new Map<string, PropertyDef[]>();
    for (const def of visible) {
      const list = map.get(def.category) ?? [];
      list.push(def);
      map.set(def.category, list);
    }
    return [...map.entries()].sort((a, b) => CATEGORY_ORDER.indexOf(a[0]) - CATEGORY_ORDER.indexOf(b[0]));
  }, [visible]);

  const modifiedCount = useMemo(
    () => Object.keys(props).filter((k) => props[k] !== (DEFAULTS[k] ?? "")).length,
    [props],
  );

  const set = (key: string, value: string) => setProps((c) => ({ ...c, [key]: value }));

  const save = async () => {
    setBusy(true);
    setError(null);
    setStatus(null);
    try {
      const res = await api<{ properties: Record<string, string> }>(
        `/api/services/${serviceId}/minecraft`,
        {
          json: rawMode
            ? { op: "properties", raw }
            : { op: "properties", properties: props, remove: removed, replace: true },
        },
      );
      setProps(res.properties);
      setRemoved([]);
      setStatus("server.properties written to the volume — restart to apply");
      await loadRaw();
      onSaved?.();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const addCustom = () => {
    const key = prompt("Property name (for example: paper.custom-flag)")?.trim();
    if (!key) return;
    if (!isValidPropertyKey(key)) {
      setError(`"${key}" is not a valid server.properties key`);
      return;
    }
    setRemoved((r) => r.filter((k) => k !== key));
    setProps((c) => ({ ...c, [key]: c[key] ?? "" }));
    setCategory("Custom");
  };

  return (
    <div className="space-y-3">
      <div className="panel flex flex-wrap items-center gap-2 p-3">
        <div className="relative min-w-[200px] flex-1">
          <Search
            size={14}
            className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--muted)]"
          />
          <input
            className="input pl-8"
            placeholder="Filter properties…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            disabled={rawMode}
          />
        </div>
        <select
          className="select w-auto"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          disabled={rawMode}
        >
          <option value="all">All categories</option>
          {CATEGORY_ORDER.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <button className="btn" type="button" onClick={addCustom} disabled={rawMode}>
          <Plus size={13} /> Property
        </button>
        <button
          className="btn"
          type="button"
          disabled={rawMode}
          onClick={() => {
            setProps({ ...DEFAULTS });
            setRemoved(customKeys);
          }}
        >
          <RotateCcw size={13} /> Defaults
        </button>
        <label className="flex items-center gap-1.5 text-[11px] text-[var(--muted)]">
          <input
            type="checkbox"
            checked={rawMode}
            onChange={(e) => setRawMode(e.target.checked)}
          />
          raw file
        </label>
        <button className="btn btn-primary" disabled={busy} onClick={save}>
          <Save size={13} /> {busy ? "Saving…" : "Save"}
        </button>
      </div>

      <ErrorText error={error} />
      {status && <div className="text-xs text-[var(--success)]">{status}</div>}

      {rawMode ? (
        <div className="panel p-3">
          <textarea
            className="textarea font-mono"
            rows={26}
            value={raw}
            onChange={(e) => setRaw(e.target.value)}
          />
          <p className="mt-2 text-[11px] text-[var(--muted)]">
            Saving the raw file replaces every property with what is written here.
          </p>
        </div>
      ) : (
        <>
          <div className="text-[11px] text-[var(--muted)]">
            {Object.keys(props).length} properties · {modifiedCount} differ from the defaults
            {customKeys.length > 0 && ` · ${customKeys.length} custom`}
          </div>
          {grouped.map(([name, defs]) => (
            <div key={name} className="panel">
              <div className="border-b border-[var(--line)] px-4 py-2">
                <span className="label">{name}</span>
                <span className="ml-2 text-[11px] text-[var(--muted)]">{defs.length}</span>
              </div>
              {defs.map((def) => (
                <PropertyField
                  key={def.key}
                  def={def}
                  value={props[def.key] ?? ""}
                  onChange={(v) => set(def.key, v)}
                  onReset={() => set(def.key, DEFAULTS[def.key] ?? def.default)}
                  onRemove={
                    def.category === "Custom"
                      ? () => {
                          setProps((c) => {
                            const next = { ...c };
                            delete next[def.key];
                            return next;
                          });
                          setRemoved((r) => [...new Set([...r, def.key])]);
                        }
                      : undefined
                  }
                />
              ))}
            </div>
          ))}
          {grouped.length === 0 && (
            <div className="panel px-4 py-6 text-center text-xs text-[var(--muted)]">
              No property matches “{query}”.
            </div>
          )}
        </>
      )}
    </div>
  );
}
