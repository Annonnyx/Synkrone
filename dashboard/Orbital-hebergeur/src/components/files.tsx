"use client";

import dynamic from "next/dynamic";
import { useCallback, useRef, useState } from "react";
import {
  ArrowUp,
  Download,
  File as FileIcon,
  Folder,
  FolderPlus,
  Save,
  Trash2,
  Upload,
} from "lucide-react";
import { api } from "@/lib/client";
import { useT } from "@/lib/i18n";
import { useTheme } from "@/lib/theme";
import { withPanelBase } from "@/lib/panel-base";
import { usePoll } from "@/lib/use-poll";
import { ErrorText } from "@/components/panel";
import { useToast } from "@/components/toast";

const MonacoEditor = dynamic(() => import("@monaco-editor/react"), { ssr: false });

type Entry = {
  name: string;
  path: string;
  type: "file" | "directory";
  size: number;
  modifiedAt: string;
};

export function FileManager({ serviceId }: { serviceId: string }) {
  const t = useT();
  const { theme } = useTheme();
  const toast = useToast();
  const [cwd, setCwd] = useState("/");
  const [entries, setEntries] = useState<Entry[]>([]);
  const [openFile, setOpenFile] = useState<string | null>(null);
  const [content, setContent] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [plainEditor, setPlainEditor] = useState(false);
  const uploadRef = useRef<HTMLInputElement>(null);

  const list = useCallback(
    async (dir: string) => {
      try {
        const res = await api<{ entries: Entry[] }>(
          `/api/services/${serviceId}/files?path=${encodeURIComponent(dir)}`,
        );
        setEntries(res.entries);
        setCwd(dir);
        setError(null);
      } catch (err) {
        setError((err as Error).message);
      }
    },
    [serviceId],
  );

  const loadRoot = useCallback(() => list("/"), [list]);
  usePoll(loadRoot, undefined, serviceId);

  const open = async (entry: Entry) => {
    if (entry.type === "directory") return list(entry.path);
    try {
      const res = await api<{ content: string }>(
        `/api/services/${serviceId}/files?op=read&path=${encodeURIComponent(entry.path)}`,
      );
      setOpenFile(entry.path);
      setContent(res.content);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const save = async () => {
    if (!openFile) return;
    try {
      await api(`/api/services/${serviceId}/files`, {
        json: { op: "write", path: openFile, content },
      });
      toast.success(t("files.saved", { path: openFile }));
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const remove = async (entry: Entry) => {
    if (!confirm(t("files.deleteConfirm", { name: entry.name }))) return;
    try {
      await api(`/api/services/${serviceId}/files?path=${encodeURIComponent(entry.path)}`, {
        method: "DELETE",
      });
      if (openFile === entry.path) setOpenFile(null);
      toast.success(t("toast.deleted"));
      await list(cwd);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const upload = async (file: File) => {
    const form = new FormData();
    form.append("file", file);
    form.append("path", cwd);
    try {
      const res = await fetch(withPanelBase(`/api/services/${serviceId}/files`), { method: "POST", body: form });
      if (!res.ok) throw new Error((await res.json()).error ?? t("files.uploadFailed"));
      toast.success(t("files.uploaded"));
      await list(cwd);
    } catch (err) {
      setError((err as Error).message);
    }
  };

  const parent = cwd === "/" ? null : `/${cwd.split("/").filter(Boolean).slice(0, -1).join("/")}`;
  const language = openFile?.endsWith(".json")
    ? "json"
    : openFile?.endsWith(".ts")
      ? "typescript"
      : openFile?.endsWith(".js")
        ? "javascript"
        : openFile?.endsWith(".html")
          ? "html"
          : openFile?.endsWith(".css")
            ? "css"
            : openFile?.endsWith(".yml") || openFile?.endsWith(".yaml")
              ? "yaml"
              : "plaintext";

  return (
    <div className="grid gap-4 lg:grid-cols-[340px_1fr]">
      <div className="panel flex flex-col">
        <div className="flex items-center gap-1 border-b border-[var(--line)] px-3 py-2">
          <button className="btn" disabled={!parent} onClick={() => parent !== null && list(parent || "/")}>
            <ArrowUp size={13} />
          </button>
          <span className="truncate font-mono text-xs text-[var(--muted)]">{cwd}</span>
          <div className="ml-auto flex gap-1">
            <button
              className="btn"
              onClick={async () => {
                const name = prompt(t("files.folderName"));
                if (!name) return;
                await api(`/api/services/${serviceId}/files`, {
                  json: { op: "mkdir", path: `${cwd}/${name}` },
                });
                toast.success(t("files.folderCreated"));
                await list(cwd);
              }}
            >
              <FolderPlus size={13} />
            </button>
            <button className="btn" onClick={() => uploadRef.current?.click()}>
              <Upload size={13} />
            </button>
            <input
              ref={uploadRef}
              type="file"
              className="hidden"
              onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])}
            />
          </div>
        </div>
        <div className="scroll max-h-[460px] overflow-y-auto">
          {entries.map((entry) => (
            <div
              key={entry.path}
              className="flex items-center gap-2 border-b border-[var(--line)] px-3 py-1.5 text-xs"
            >
              <button className="flex flex-1 items-center gap-2 text-left" onClick={() => open(entry)}>
                {entry.type === "directory" ? (
                  <Folder size={13} className="text-[var(--accent)]" />
                ) : (
                  <FileIcon size={13} className="text-[var(--muted)]" />
                )}
                <span className="truncate">{entry.name}</span>
              </button>
              <span className="text-[10px] text-[var(--muted)]">
                {entry.type === "file" ? `${(entry.size / 1024).toFixed(1)} KB` : ""}
              </span>
              <a
                className="text-[var(--muted)] hover:text-[var(--text)]"
                href={withPanelBase(`/api/services/${serviceId}/files?op=download&path=${encodeURIComponent(entry.path)}`)}
              >
                <Download size={13} />
              </a>
              <button className="text-[var(--danger)]" onClick={() => remove(entry)}>
                <Trash2 size={13} />
              </button>
            </div>
          ))}
          {entries.length === 0 && (
            <div className="px-3 py-4 text-xs text-[var(--muted)]">{t("files.emptyDir")}</div>
          )}
        </div>
      </div>

      <div className="panel flex flex-col">
        <div className="flex items-center gap-2 border-b border-[var(--line)] px-3 py-2">
          <span className="truncate font-mono text-xs">{openFile ?? t("files.noFileOpen")}</span>
          <div className="ml-auto flex items-center gap-2">
            <label className="flex items-center gap-1 text-[11px] text-[var(--muted)]">
              <input
                type="checkbox"
                checked={plainEditor}
                onChange={(e) => setPlainEditor(e.target.checked)}
              />
              {t("files.plainEditor")}
            </label>
            <button className="btn btn-primary" disabled={!openFile} onClick={save}>
              <Save size={13} /> {t("common.save")}
            </button>
          </div>
        </div>
        <div className="p-3">
          <ErrorText error={error} />
          {openFile ? (
            plainEditor ? (
              <textarea
                className="textarea font-mono"
                rows={22}
                value={content}
                onChange={(e) => setContent(e.target.value)}
              />
            ) : (
              <MonacoEditor
                height="460px"
                theme={theme === "dark" ? "vs-dark" : "vs"}
                language={language}
                value={content}
                onChange={(v) => setContent(v ?? "")}
                options={{ minimap: { enabled: false }, fontSize: 12.5 }}
              />
            )
          ) : (
            <div className="p-6 text-xs text-[var(--muted)]">{t("files.selectFile")}</div>
          )}
        </div>
      </div>
    </div>
  );
}
