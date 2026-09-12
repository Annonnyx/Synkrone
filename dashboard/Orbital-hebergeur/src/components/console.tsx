"use client";

import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { Check, Copy, Download, Eraser, Search, WrapText } from "lucide-react";
import { api } from "@/lib/client";
import { withPanelBase } from "@/lib/panel-base";
import { notify } from "@/lib/notify";
import { useT } from "@/lib/i18n";
import { formatConsoleClock } from "@/lib/console/docker-log";
import { StateBadge } from "@/components/panel";
import {
  clearHistory,
  commitHistoryEntry,
  readHistory,
  searchHistory,
  writeHistory,
} from "@/lib/console/history";
import {
  FONT_CHOICES,
  HEIGHT_CHOICES,
  getConsolePrefsServerSnapshot,
  getConsolePrefsSnapshot,
  parseConsolePrefs,
  subscribeConsolePrefs,
  writeConsolePrefs,
} from "@/lib/console/prefs";
import { MINECRAFT_CONSOLE_COMMANDS, tabCompleteMinecraft } from "@/lib/console/mc-commands";
import { discordBotPortalUrl } from "@/lib/discord/intents";

const MAX_LINES = 2000;
const STREAMS = ["stdout", "stderr", "command", "system"] as const;
type StreamName = (typeof STREAMS)[number];

type Line = { id: number; stream: string; message: string; at?: string };

type StreamPayload =
  | { type: "line"; stream: string; message: string; at?: string }
  | { type: "status"; status: { state: string } }
  | { type: "info"; message: string };

function nearBottom(el: HTMLElement) {
  return el.scrollHeight - el.scrollTop - el.clientHeight < 32;
}

function subscribeHash(onStoreChange: () => void) {
  window.addEventListener("hashchange", onStoreChange);
  return () => window.removeEventListener("hashchange", onStoreChange);
}

function getHashSnapshot() {
  return window.location.hash.replace(/^#/, "");
}

function getHashServerSnapshot() {
  return "";
}

export function Console({
  serviceId,
  canSend,
  serviceType,
  applicationId,
  initialState,
}: {
  serviceId: string;
  canSend: boolean;
  serviceType?: string;
  applicationId?: string | null;
  initialState?: string;
}) {
  const t = useT();
  const [lines, setLines] = useState<Line[]>([]);
  const [state, setState] = useState(initialState ?? "UNKNOWN");
  const [command, setCommand] = useState("");
  const [sending, setSending] = useState(false);
  const [filter, setFilter] = useState("");
  const [streamFilter, setStreamFilter] = useState<"all" | StreamName>("all");
  const [autoScroll, setAutoScroll] = useState(true);
  const [connected, setConnected] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [historyQuery, setHistoryQuery] = useState("");
  const [historyCursor, setHistoryCursor] = useState(0);
  const [historyList, setHistoryList] = useState<string[]>([]);
  const [copiedId, setCopiedId] = useState<number | null>(null);
  const [copiedAll, setCopiedAll] = useState(false);
  const [intentsBannerDismissed, setIntentsBannerDismissed] = useState(false);
  const prefsRaw = useSyncExternalStore(
    subscribeConsolePrefs,
    getConsolePrefsSnapshot,
    getConsolePrefsServerSnapshot,
  );
  const prefs = parseConsolePrefs(prefsRaw || null);
  const hashLine = useSyncExternalStore(subscribeHash, getHashSnapshot, getHashServerSnapshot);
  const boxRef = useRef<HTMLDivElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const historySearchRef = useRef<HTMLInputElement>(null);
  const nextId = useRef(0);
  const historyRef = useRef<string[]>([]);
  const historyIndexRef = useRef(-1);
  const draftRef = useRef("");
  const echoesRef = useRef<Array<{ msg: string; until: number }>>([]);
  const tabOriginRef = useRef<string | null>(null);
  const tabCycleRef = useRef(0);
  const skipTabReset = useRef(false);

  useEffect(() => {
    historyRef.current = readHistory(serviceId);
    historyIndexRef.current = -1;
    draftRef.current = "";
  }, [serviceId]);

  useEffect(() => {
    document.getElementById("console")?.scrollIntoView({ block: "nearest" });
  }, []);

  const pendingRef = useRef<Line[]>([]);
  const flushScheduled = useRef(false);

  const rememberEcho = (message: string) => {
    echoesRef.current.push({ msg: message, until: Date.now() + 5000 });
  };

  const isEchoDup = (message: string) => {
    const now = Date.now();
    echoesRef.current = echoesRef.current.filter((entry) => entry.until > now);
    return echoesRef.current.some((entry) => entry.msg === message);
  };

  const append = (stream: string, message: string, at?: string) => {
    if (isEchoDup(message)) return;
    nextId.current += 1;
    pendingRef.current.push({
      id: nextId.current,
      stream,
      message,
      at,
    });
    if (flushScheduled.current) return;
    flushScheduled.current = true;
    requestAnimationFrame(() => {
      flushScheduled.current = false;
      const batch = pendingRef.current;
      pendingRef.current = [];
      if (batch.length === 0) return;
      setLines((prev) => [...prev, ...batch].slice(-MAX_LINES));
    });
  };
  const appendRef = useRef(append);
  useEffect(() => {
    appendRef.current = append;
  });

  useEffect(() => {
    let source: EventSource | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;
    let delay = 1000;
    let stopped = false;
    let generation = 0;

    const connect = () => {
      if (stopped) return;
      const gen = ++generation;
      source?.close();
      const es = new EventSource(withPanelBase(`/api/services/${serviceId}/stream`));
      source = es;
      es.onopen = () => {
        if (gen !== generation) return;
        delay = 1000;
        setConnected(true);
      };
      es.onmessage = (event) => {
        if (gen !== generation) return;
        let payload: StreamPayload;
        try {
          payload = JSON.parse(event.data) as StreamPayload;
        } catch {
          return;
        }
        if (payload.type === "line") appendRef.current(payload.stream, payload.message, payload.at);
        if (payload.type === "info") appendRef.current("system", payload.message);
        if (payload.type === "status") setState(payload.status.state);
      };
      es.onerror = () => {
        if (gen !== generation) return;
        setConnected(false);
        es.close();
        if (source === es) source = null;
        if (stopped) return;
        retry = setTimeout(connect, delay);
        delay = Math.min(delay * 2, 30_000);
      };
    };
    connect();
    return () => {
      stopped = true;
      generation += 1;
      source?.close();
      if (retry) clearTimeout(retry);
    };
  }, [serviceId]);

  useEffect(() => {
    if (autoScroll && boxRef.current) boxRef.current.scrollTop = boxRef.current.scrollHeight;
  }, [lines, autoScroll]);

  const visible = useMemo(() => {
    const byStream =
      streamFilter === "all" ? lines : lines.filter((line) => line.stream === streamFilter);
    if (!filter) return byStream;
    const q = filter.toLowerCase();
    return byStream.filter((line) => line.message.toLowerCase().includes(q));
  }, [lines, filter, streamFilter]);

  const fillInput = (value: string) => {
    setCommand(value);
    requestAnimationFrame(() => {
      const el = inputRef.current;
      if (!el) return;
      const n = value.length;
      el.setSelectionRange(n, n);
    });
  };

  const recall = (direction: -1 | 1) => {
    const hist = historyRef.current;
    let idx = historyIndexRef.current;
    if (direction < 0) {
      if (hist.length === 0) return;
      if (idx === -1) {
        draftRef.current = inputRef.current?.value ?? "";
        idx = hist.length - 1;
      } else if (idx > 0) {
        idx -= 1;
      } else {
        return;
      }
      historyIndexRef.current = idx;
      fillInput(hist[idx]!);
      return;
    }
    if (idx === -1) return;
    if (idx < hist.length - 1) {
      idx += 1;
      historyIndexRef.current = idx;
      fillInput(hist[idx]!);
      return;
    }
    historyIndexRef.current = -1;
    fillInput(draftRef.current);
  };

  const commitHistory = (cmd: string) => {
    const next = commitHistoryEntry(historyRef.current, cmd);
    historyRef.current = next;
    setHistoryList(next);
    writeHistory(serviceId, next);
    historyIndexRef.current = -1;
    draftRef.current = "";
  };

  const running = state === "RUNNING";
  const sendEnabled = canSend && running && !sending;

  const send = async () => {
    if (!sendEnabled || !command.trim()) return;
    const cmd = command.trim();
    commitHistory(cmd);
    setCommand("");
    setSending(true);
    rememberEcho(`> ${cmd}`);
    rememberEcho(`$ ${cmd}`);
    append("command", `> ${cmd}`);
    try {
      await api(`/api/services/${serviceId}/command`, { json: { command: cmd }, silent: true });
    } catch (err) {
      const message = (err as Error).message;
      append("stderr", `${cmd}: ${message}`);
      notify({
        kind: "error",
        title: t("console.commandFailed"),
        message,
      });
    } finally {
      setSending(false);
    }
  };

  const historyMatches = useMemo(
    () => searchHistory(historyList, historyQuery),
    [historyList, historyQuery],
  );

  const pickHistory = (entry: string) => {
    setHistoryOpen(false);
    setHistoryQuery("");
    fillInput(entry);
    inputRef.current?.focus();
  };

  const copyLine = async (line: Line) => {
    await navigator.clipboard.writeText(line.message);
    setCopiedId(line.id);
    window.setTimeout(() => setCopiedId((id) => (id === line.id ? null : id)), 1600);
  };

  const copyLastCommand = async () => {
    const last = historyRef.current.at(-1);
    if (!last) return;
    await navigator.clipboard.writeText(last);
    fillInput(last);
  };

  const wipeHistory = () => {
    historyRef.current = [];
    setHistoryList([]);
    clearHistory(serviceId);
    historyIndexRef.current = -1;
    setHistoryQuery("");
  };

  const completeMinecraft = () => {
    const origin = tabOriginRef.current ?? command;
    if (tabOriginRef.current === null) {
      tabOriginRef.current = command;
      tabCycleRef.current = 0;
    }
    const next = tabCompleteMinecraft(origin, tabCycleRef.current);
    if (next === null) return;
    skipTabReset.current = true;
    tabCycleRef.current += 1;
    fillInput(next);
  };

  const sawDisallowedIntents =
    serviceType === "discord" &&
    !intentsBannerDismissed &&
    lines.some((line) => /disallowed intents/i.test(line.message));

  const text = visible.map((line) => line.message).join("\n");
  const listId = serviceType === "minecraft" ? `mc-cmds-${serviceId}` : undefined;

  const copyAll = async () => {
    await navigator.clipboard.writeText(text);
    setCopiedAll(true);
    window.setTimeout(() => setCopiedAll(false), 1600);
  };

  return (
    <div
      ref={rootRef}
      id="console"
      tabIndex={-1}
      className="outline-none"
      onKeyDown={(e) => {
        const target = e.target as HTMLElement;
        const inField = target.tagName === "INPUT" || target.tagName === "TEXTAREA";
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "l" && !e.shiftKey) {
          e.preventDefault();
          setLines([]);
          return;
        }
        if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "c") {
          e.preventDefault();
          void copyLastCommand();
          return;
        }
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "r") {
          e.preventDefault();
          setHistoryOpen(true);
          setHistoryList([...historyRef.current]);
          setHistoryCursor(0);
          requestAnimationFrame(() => historySearchRef.current?.focus());
          return;
        }
        if (!inField && e.key === "/") {
          e.preventDefault();
          inputRef.current?.focus();
        }
      }}
    >
      {sawDisallowedIntents && (
        <div className="mb-3 rounded-xl border border-[var(--warning)]/40 bg-[var(--warning)]/10 px-3 py-2 text-xs">
          <p className="font-medium text-[var(--warning)]">{t("console.intentsBanner")}</p>
          <p className="mt-1 text-[var(--muted)]">{t("console.intentsBannerHint")}</p>
          <div className="mt-2 flex flex-wrap gap-2">
            <a
              className="btn btn-primary"
              href={discordBotPortalUrl(applicationId)}
              target="_blank"
              rel="noreferrer"
            >
              {t("console.openPortal")}
            </a>
            <button type="button" className="btn" onClick={() => setIntentsBannerDismissed(true)}>
              {t("common.close")}
            </button>
          </div>
        </div>
      )}

      <div className="mb-2 flex flex-wrap items-center gap-2">
        <StateBadge state={state} />
        <span className="text-[11px] text-[var(--muted)]">
          {connected ? t("console.connected") : t("console.reconnecting")}
        </span>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1 rounded-lg border border-[var(--line)] px-2">
            <Search size={13} className="text-[var(--muted)]" />
            <input
              className="bg-transparent py-1 text-xs outline-none"
              placeholder={t("console.search")}
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
          </div>
          <select
            className="input w-auto py-1 text-xs"
            value={streamFilter}
            onChange={(e) => setStreamFilter(e.target.value as "all" | StreamName)}
            aria-label={t("console.streamFilter")}
          >
            <option value="all">{t("console.streamAll")}</option>
            {STREAMS.map((name) => (
              <option key={name} value={name}>
                {t(`console.stream.${name}`)}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-1 text-[11px] text-[var(--muted)]">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
            />
            {t("console.autoScroll")}
          </label>
          <button
            type="button"
            className="btn"
            title={t("console.wrap")}
            onClick={() => writeConsolePrefs({ ...prefs, wrap: !prefs.wrap })}
          >
            <WrapText size={13} /> {prefs.wrap ? t("console.wrap") : t("console.nowrap")}
          </button>
          <select
            className="input w-auto py-1 text-xs"
            value={prefs.fontPx}
            onChange={(e) => writeConsolePrefs({ ...prefs, fontPx: Number(e.target.value) })}
            aria-label={t("console.fontSize")}
          >
            {FONT_CHOICES.map((px) => (
              <option key={px} value={px}>
                {px}px
              </option>
            ))}
          </select>
          <select
            className="input w-auto py-1 text-xs"
            value={prefs.heightPx}
            onChange={(e) => writeConsolePrefs({ ...prefs, heightPx: Number(e.target.value) })}
            aria-label={t("console.height")}
          >
            {HEIGHT_CHOICES.map((px) => (
              <option key={px} value={px}>
                {px}px
              </option>
            ))}
          </select>
          <button type="button" className="btn" onClick={() => setLines([])}>
            <Eraser size={13} /> {t("console.clear")}
          </button>
          <button
            type="button"
            className={`btn ${copiedAll ? "btn-copied" : ""}`}
            onClick={() => void copyAll()}
          >
            {copiedAll ? <Check size={13} /> : <Copy size={13} />}
            {copiedAll ? t("common.copied") : t("common.copy")}
          </button>
          <button
            type="button"
            className="btn"
            onClick={() => {
              const blob = new Blob([text], { type: "text/plain" });
              const url = URL.createObjectURL(blob);
              const a = document.createElement("a");
              a.href = url;
              a.download = `console-${serviceId}.log`;
              a.click();
              URL.revokeObjectURL(url);
            }}
          >
            <Download size={13} /> {t("common.download")}
          </button>
        </div>
      </div>

      <div
        ref={boxRef}
        className={`console scroll overflow-auto p-3 ${prefs.wrap ? "whitespace-pre-wrap break-all" : "whitespace-pre"}`}
        style={{ height: prefs.heightPx, fontSize: prefs.fontPx }}
        onScroll={(e) => {
          const atBottom = nearBottom(e.currentTarget);
          setAutoScroll((on) => {
            if (!atBottom && on) return false;
            if (atBottom && !on) return true;
            return on;
          });
        }}
      >
        {visible.map((line) => (
          <div
            key={line.id}
            id={`console-L${line.id}`}
            className={`group flex gap-2 ${hashLine === `console-L${line.id}` ? "bg-[#2a332e]" : ""}`}
            style={{
              color:
                line.stream === "stderr"
                  ? "#e8a090"
                  : line.stream === "command"
                    ? "#9ad1af"
                    : line.stream === "system"
                      ? "#8fa096"
                      : "#eef0ea",
            }}
          >
            <span className="min-w-0 flex-1">
              {line.at ? `[${formatConsoleClock(line.at)}] ` : ""}
              {line.message}
            </span>
            <button
              type="button"
              className={`shrink-0 text-[11px] ${
                copiedId === line.id
                  ? "text-[var(--success)] opacity-100"
                  : "text-[var(--muted)] opacity-0 group-hover:opacity-100"
              }`}
              title={t("console.copyLine")}
              onClick={() => void copyLine(line)}
            >
              {copiedId === line.id ? t("common.copied") : <Copy size={11} />}
            </button>
          </div>
        ))}
        {visible.length === 0 && (
          <div className="text-[var(--muted)]">{t("console.noOutput")}</div>
        )}
      </div>

      {historyOpen && (
        <div className="mt-2 rounded-xl border border-[var(--line)] bg-[var(--panel)] p-2">
          <div className="mb-1 flex items-center justify-between gap-2 text-[11px] text-[var(--muted)]">
            <span>{t("console.historySearch")}</span>
            <button type="button" className="btn" onClick={wipeHistory}>
              {t("console.clearHistory")}
            </button>
          </div>
          <input
            ref={historySearchRef}
            className="input font-mono"
            value={historyQuery}
            placeholder={t("console.historyPlaceholder")}
            onChange={(e) => {
              setHistoryQuery(e.target.value);
              setHistoryCursor(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                e.preventDefault();
                setHistoryOpen(false);
                inputRef.current?.focus();
                return;
              }
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setHistoryCursor((i) => Math.min(i + 1, Math.max(historyMatches.length - 1, 0)));
                return;
              }
              if (e.key === "ArrowUp") {
                e.preventDefault();
                setHistoryCursor((i) => Math.max(i - 1, 0));
                return;
              }
              if (e.key === "Enter") {
                e.preventDefault();
                const pick = historyMatches[historyCursor];
                if (pick) pickHistory(pick);
              }
            }}
          />
          <ul className="mt-1 max-h-40 overflow-auto text-xs">
            {historyMatches.length === 0 && (
              <li className="px-2 py-1 text-[var(--muted)]">{t("console.historyEmpty")}</li>
            )}
            {historyMatches.slice(0, 40).map((entry, i) => (
              <li key={`${entry}-${i}`}>
                <button
                  type="button"
                  className="w-full rounded px-2 py-1 text-left font-mono"
                  style={{ background: i === historyCursor ? "var(--line)" : undefined }}
                  onClick={() => pickHistory(entry)}
                >
                  {entry}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-2 flex gap-2">
        <span className="self-center font-mono text-[var(--muted)]">&gt;</span>
        {listId && (
          <datalist id={listId}>
            {MINECRAFT_CONSOLE_COMMANDS.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
        )}
        <input
          ref={inputRef}
          className="input font-mono"
          list={listId}
          placeholder={
            !canSend
              ? t("console.readOnly")
              : !running
                ? t("console.notRunning")
                : t("console.sendPlaceholder")
          }
          value={command}
          autoComplete="off"
          autoCorrect="off"
          autoCapitalize="off"
          spellCheck={false}
          onChange={(e) => {
            if (!skipTabReset.current) {
              tabOriginRef.current = null;
              tabCycleRef.current = 0;
            }
            skipTabReset.current = false;
            setCommand(e.target.value);
          }}
          onKeyDown={(e) => {
            if (e.key === "Tab" && serviceType === "minecraft") {
              e.preventDefault();
              e.stopPropagation();
              completeMinecraft();
              return;
            }
            if (e.key === "ArrowUp" && !historyOpen) {
              e.preventDefault();
              e.stopPropagation();
              recall(-1);
              return;
            }
            if (e.key === "ArrowDown" && !historyOpen) {
              e.preventDefault();
              e.stopPropagation();
              recall(1);
              return;
            }
            if (e.key !== "Enter") return;
            e.preventDefault();
            e.stopPropagation();
            void send();
          }}
          disabled={!canSend || sending || !running}
        />
        <button
          type="button"
          className="btn btn-primary"
          disabled={!sendEnabled}
          onClick={() => void send()}
        >
          {sending ? t("console.sending") : t("console.send")}
        </button>
      </div>
      <p className="mt-1 text-[10px] text-[var(--muted)]">{t("console.shortcuts")}</p>
    </div>
  );
}
