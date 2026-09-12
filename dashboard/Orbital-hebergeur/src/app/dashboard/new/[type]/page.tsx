"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import type { GithubRepo } from "@/lib/oauth/types";
import { Check, ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import { api } from "@/lib/client";
import { useT } from "@/lib/i18n";
import { ErrorText } from "@/components/panel";
import { useToast } from "@/components/toast";
import { TokenField } from "@/components/discord-token";
import { SoftwarePicker, VersionPicker } from "@/components/mc-runtime";
import { PropertyControl } from "@/components/mc-properties";
import { PROPERTY_BY_KEY, defaultProperties } from "@/lib/minecraft/properties";
import { mergeIntentsForModules, suggestedPrivilegedIntents } from "@/lib/discord/intents";
import { IntentPicker } from "@/components/discord-intents";
import { COMMAND_COGS, customCategories } from "@/lib/discord/catalog";
import { hostingCost } from "@/lib/krones/pricing";
import { activeDiscounts, type PromoDiscount } from "@/lib/krones/discounts";
import { withPanelBase } from "@/lib/panel-base";
import { PageHeader } from "@/components/ui";
import { isCreationEnabled } from "@/lib/services/creation-flags";

const CREATE_TYPES = ["discord", "minecraft", "web"] as const;
type CreateType = (typeof CREATE_TYPES)[number];

function resolveCreateType(raw: unknown): CreateType {
  const value = Array.isArray(raw) ? raw[0] : raw;
  return CREATE_TYPES.includes(value as CreateType) ? (value as CreateType) : "discord";
}

const CUSTOM_CATEGORIES = customCategories();

/** Keys offered during creation; every other property is editable afterwards. */
const WIZARD_PROPERTIES = [
  "motd",
  "gamemode",
  "difficulty",
  "max-players",
  "pvp",
  "hardcore",
  "online-mode",
  "white-list",
  "allow-flight",
  "spawn-protection",
  "view-distance",
  "simulation-distance",
  "level-name",
  "level-seed",
  "level-type",
  "enable-command-block",
];

const WEB_TEMPLATES = [
  { id: "static", label: "Static HTML" },
  { id: "javascript", label: "JavaScript" },
  { id: "typescript", label: "TypeScript" },
  { id: "react", label: "React" },
  { id: "next", label: "Next.js" },
  { id: "node", label: "Node.js" },
];

type Job = {
  status: string;
  progress: number;
  error: string | null;
  steps: Array<{ id: string; label: string; status: string; detail: string | null }>;
};

export default function CreateServicePage() {
  const router = useRouter();
  const params = useParams<{ type: string }>();
  const t = useT();
  const toast = useToast();
  const type = resolveCreateType(params.type);

  useEffect(() => {
    const raw = Array.isArray(params.type) ? params.type[0] : params.type;
    if (raw && raw !== type) router.replace(`/dashboard/new/${type}`);
  }, [params.type, type, router]);

  const [step, setStep] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [serviceId, setServiceId] = useState<string | null>(null);

  // shared
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [memoryMb, setMemoryMb] = useState(type === "minecraft" ? 4096 : 512);
  const [cpu, setCpu] = useState(type === "minecraft" ? 2000 : 1000);
  const [storageMb, setStorageMb] = useState(type === "minecraft" ? 20480 : 5120);
  const [platform, setPlatform] = useState<{
    discordEnabled: boolean;
    minecraftEnabled: boolean;
    webEnabled: boolean;
    maxCpuMillicores: number;
    maxMemoryMb: number;
    maxStorageMb: number;
    limits: Record<string, { cpuMillicores: number; memoryMb: number; storageMb: number }>;
    discounts?: PromoDiscount[];
  } | null>(null);

  useEffect(() => {
    void api<NonNullable<typeof platform>>("/api/platform", { silent: true })
      .then((data) => {
        setPlatform(data);
        const cap = data.limits?.[type] || {
          cpuMillicores: data.maxCpuMillicores,
          memoryMb: data.maxMemoryMb,
          storageMb: data.maxStorageMb,
        };
        setMemoryMb((cur) => Math.min(cur, cap.memoryMb));
        setCpu((cur) => Math.min(cur, cap.cpuMillicores));
        setStorageMb((cur) => Math.min(cur, cap.storageMb));
      })
      .catch(() => setPlatform(null));
  }, [type]);

  const typeLimits = platform?.limits?.[type];
  const ramPresets = [512, 1024, 2048, 4096, 8192, 16384].filter((m) => m <= (typeLimits?.memoryMb ?? 16384));
  const cpuPresets = [500, 1000, 2000, 4000].filter((c) => c <= (typeLimits?.cpuMillicores ?? 4000));
  const [envText, setEnvText] = useState("");

  // discord
  const [token, setToken] = useState("");
  const [applicationId, setApplicationId] = useState("");
  const [prefix, setPrefix] = useState("!");
  const [slash, setSlash] = useState(true);
  const [botSource, setBotSource] = useState<"catalog" | "ticket">("catalog");
  const [supportInvite, setSupportInvite] = useState("https://discord.gg/p768u2Pgp3");
  const [modules, setModules] = useState<string[]>(["moderation", "public"]);
  const [commands, setCommands] = useState<string[]>(["ban", "kick", "ping"]);
  const [intents, setIntents] = useState<string[]>(() => mergeIntentsForModules([], ["moderation", "public"]));
  const [cmdQuery, setCmdQuery] = useState("");

  useEffect(() => {
    void fetch("/api/config")
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (typeof data?.supportInvite === "string" && data.supportInvite.startsWith("http")) {
          setSupportInvite(data.supportInvite);
        }
      })
      .catch(() => undefined);
  }, []);

  const STEPS = useMemo(() => {
    if (type === "discord") {
      return botSource === "ticket"
        ? ["botSource"]
        : ["botSource", "general", "commands", "discord", "resources", "review"];
    }
    if (type === "minecraft") {
      return ["basic", "software", "version", "resources", "network", "properties", "review"];
    }
    return ["basic", "template", "source", "build", "resources", "environment", "review"];
  }, [type, botSource]);

  const stepLabel = (id: string) => t(`create.step${id[0].toUpperCase()}${id.slice(1)}`);

  useEffect(() => {
    if (step >= STEPS.length) setStep(STEPS.length - 1);
  }, [STEPS, step]);

  // minecraft
  const [software, setSoftware] = useState("paper");
  const [version, setVersion] = useState("");
  const [bedrock, setBedrock] = useState(false);
  const [eula, setEula] = useState(false);
  const [mcProps, setMcProps] = useState<Record<string, string>>(() => {
    const defaults = defaultProperties();
    return Object.fromEntries(WIZARD_PROPERTIES.map((k) => [k, defaults[k] ?? ""]));
  });

  // web
  const [template, setTemplate] = useState("static");
  const [source, setSource] = useState<"empty" | "github">("empty");
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("main");
  const [installCommand, setInstallCommand] = useState("npm install");
  const [buildCommand, setBuildCommand] = useState("");
  const [startCommand, setStartCommand] = useState("npm run start");
  const [autoDeploy, setAutoDeploy] = useState(false);
  const [github, setGithub] = useState<{
    configured: boolean;
    linked: boolean;
    login: string | null;
    repos: GithubRepo[];
  } | null>(null);
  const [githubLoading, setGithubLoading] = useState(type === "web");

  useEffect(() => {
    if (type !== "web") return;
    let cancelled = false;
    void api<{
      configured: boolean;
      linked: boolean;
      login: string | null;
      repos: GithubRepo[];
    }>("/api/github/repos", { silent: true })
      .then((res) => {
        if (!cancelled) setGithub(res);
      })
      .catch(() => {
        if (!cancelled) setGithub({ configured: false, linked: false, login: null, repos: [] });
      })
      .finally(() => {
        if (!cancelled) setGithubLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [type]);

  useEffect(() => {
    if (!jobId) return;
    const t = setInterval(async () => {
      try {
        const { job: j } = await api<{ job: Job }>(`/api/jobs/${jobId}`, { silent: true });
        setJob(j);
        if (j.status === "SUCCESS" || j.status === "FAILED") clearInterval(t);
      } catch {
        clearInterval(t);
      }
    }, 900);
    return () => clearInterval(t);
  }, [jobId]);

  const toggle = (list: string[], setList: (v: string[]) => void, value: string) =>
    setList(list.includes(value) ? list.filter((v) => v !== value) : [...list, value]);

  const parseEnv = () =>
    Object.fromEntries(
      envText
        .split("\n")
        .map((l) => l.trim())
        .filter((l) => l && !l.startsWith("#") && l.includes("="))
        .map((l) => [l.slice(0, l.indexOf("=")).trim(), l.slice(l.indexOf("=") + 1).trim()]),
    );

  const cost = hostingCost(
    type,
    {
      memoryMb,
      cpuMillicores: cpu,
      storageMb,
    },
    platform?.discounts,
  );
  const livePromos = activeDiscounts(platform?.discounts).filter((row) =>
    row.targets.some((target) => target === "all" || target === type || target === "ram" || target === "cpu" || target === "storage"),
  );
  const privilegedHint = type === "discord" ? suggestedPrivilegedIntents(modules) : [];

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const payload: Record<string, unknown> = {
        type,
        name,
        description,
        cpuMillicores: cpu,
        memoryMb,
        storageMb,
        autoStart: true,
        env: parseEnv(),
      };
      if (type === "discord")
        payload.discord = {
          token: token.trim() || undefined,
          applicationId: applicationId.trim() || undefined,
          prefix,
          slashCommands: slash,
          flavor: "custom",
          modules,
          commands,
          intents,
        };
      if (type === "minecraft")
        payload.minecraft = {
          software,
          version,
          bedrockEnabled: bedrock,
          eulaAccepted: eula,
          properties: mcProps,
        };
      if (type === "web")
        payload.web = {
          template,
          source,
          repoUrl: repoUrl || undefined,
          branch,
          installCommand,
          buildCommand,
          startCommand,
          autoDeploy,
        };

      const res = await api<{ service: { id: string }; jobId: string }>("/api/services", {
        json: payload,
      });
      setServiceId(res.service.id);
      setJobId(res.jobId);
      toast.success(t("toast.serviceCreated"), t("toast.serviceCreatedBody"));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (jobId) {
    return (
      <div className="mx-auto max-w-xl">
        <h1 className="text-2xl font-bold">{t("create.creating")}</h1>
        <p className="mb-5 text-xs text-[var(--muted)]">{t("create.creatingHint")}</p>
        <div className="panel p-5">
          <div className="mb-3 h-2 w-full overflow-hidden rounded-full bg-[var(--panel-3)]">
            <div
              className="h-full rounded-full bg-[var(--accent)] transition-all"
              style={{ width: `${job?.progress ?? 0}%` }}
            />
          </div>
          <div className="space-y-2 text-sm">
            {(job?.steps ?? []).map((s) => (
              <div key={s.id} className="flex items-center gap-2">
                {s.status === "DONE" ? (
                  <Check size={15} className="text-[var(--success)]" />
                ) : s.status === "RUNNING" ? (
                  <Loader2 size={15} className="animate-spin text-[var(--accent)]" />
                ) : s.status === "FAILED" ? (
                  <span className="text-[var(--danger)]">×</span>
                ) : (
                  <span className="text-[var(--muted)]">○</span>
                )}
                <span className={s.status === "FAILED" ? "text-[var(--danger)]" : ""}>{s.label}</span>
                {s.detail && (
                  <span className="font-mono text-[10px] text-[var(--muted)]">{s.detail}</span>
                )}
              </div>
            ))}
          </div>
          {job?.error && (
            <div className="mt-4">
              <ErrorText error={job.error} />
            </div>
          )}
          <div className="mt-5 flex gap-2">
            <button
              className="btn btn-primary"
              disabled={!serviceId}
              onClick={() => router.push(`/dashboard/services/${serviceId}`)}
            >
              {t("create.openService")}
            </button>
            <button className="btn" onClick={() => router.push("/dashboard")}>
              {t("create.backDashboard")}
            </button>
          </div>
        </div>
      </div>
    );
  }

  const field = (label: string, node: React.ReactNode) => (
    <div>
      <div className="label mb-1">{label}</div>
      {node}
    </div>
  );

  const checkboxGrid = (
    items: string[],
    selected: string[],
    setSelected: (v: string[]) => void,
  ) => (
    <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
      {items.map((m) => (
        <button
          key={m}
          type="button"
          onClick={() => toggle(selected, setSelected, m)}
          className="btn justify-start text-left"
          style={{
            borderColor: selected.includes(m) ? "var(--accent)" : "var(--line)",
            color: selected.includes(m) ? "var(--text)" : "var(--muted)",
          }}
        >
          {m}
        </button>
      ))}
    </div>
  );

  const content = () => {
    const key = `${type}:${STEPS[step]}`;
    switch (key) {
      case "discord:general":
      case "minecraft:basic":
      case "web:basic":
        return (
          <div className="space-y-3">
            {field(t("create.name"), <input className="input" value={name} onChange={(e) => setName(e.target.value)} />)}
            {field(
              t("create.description"),
              <textarea
                className="textarea"
                rows={3}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />,
            )}
          </div>
        );
      case "discord:discord":
        return (
          <div className="space-y-3">
            <TokenField
              token={token}
              onToken={setToken}
              applicationId={applicationId}
              onApplicationId={setApplicationId}
            />
            {field(
              t("create.prefix"),
              <div className="space-y-1">
                <div className="flex flex-wrap gap-2">
                  {["!", "?", ".", "$", "-"].map((p) => (
                    <button key={p} type="button" className="btn font-mono" onClick={() => setPrefix(p)}
                      style={{ borderColor: prefix === p ? "var(--accent)" : "var(--line)" }}>
                      {p}
                    </button>
                  ))}
                  <input
                    className="input max-w-[12rem] font-mono"
                    value={prefix}
                    maxLength={10}
                    onChange={(e) => setPrefix(e.target.value.slice(0, 10))}
                    spellCheck={false}
                  />
                </div>
                <p className="text-[11px] text-[var(--muted)]">{t("service.prefixHint")}</p>
              </div>,
            )}
            <div>
              <div className="label mb-1">{t("service.slashCommands")}</div>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className="btn"
                  style={{ borderColor: slash ? "var(--accent)" : "var(--line)" }}
                  onClick={() => setSlash(true)}
                >
                  {t("service.slashOn")}
                </button>
                <button
                  type="button"
                  className="btn"
                  style={{ borderColor: !slash ? "var(--accent)" : "var(--line)" }}
                  onClick={() => setSlash(false)}
                >
                  {t("service.slashOff")}
                </button>
              </div>
              <p className="mt-1 text-[11px] text-[var(--muted)]">{t("create.slashEnable")}</p>
            </div>
            {privilegedHint.length > 0 && (
              <p className="text-sm leading-relaxed text-[var(--muted)]">
                {t("create.suggestedPrivileged", { list: privilegedHint.join(", ") })}
              </p>
            )}
          </div>
        );
      case "discord:botSource":
        return (
          <div className="space-y-4">
            <p className="text-sm leading-relaxed text-[var(--muted)]">{t("create.botSourceIntro")}</p>
            <div className="grid gap-2 md:grid-cols-2">
              <button
                type="button"
                className="panel panel-hover p-4 text-left"
                style={{ borderColor: botSource === "catalog" ? "var(--accent)" : "var(--line)" }}
                onClick={() => setBotSource("catalog")}
              >
                <div className="font-semibold">{t("create.botSourceCatalog")}</div>
                <div className="mt-1 text-sm text-[var(--muted)]">{t("create.botSourceCatalogHint")}</div>
              </button>
              <button
                type="button"
                className="panel panel-hover p-4 text-left"
                style={{ borderColor: botSource === "ticket" ? "var(--accent)" : "var(--line)" }}
                onClick={() => setBotSource("ticket")}
              >
                <div className="font-semibold">{t("create.botSourceTicket")}</div>
                <div className="mt-1 text-sm text-[var(--muted)]">{t("create.botSourceTicketHint")}</div>
              </button>
            </div>
            {botSource === "ticket" && (
              <a href={supportInvite} target="_blank" rel="noopener noreferrer" className="btn btn-primary">
                {t("create.openTickets")}
              </a>
            )}
          </div>
        );
      case "discord:modules":
      case "discord:commands": {
        const q = cmdQuery.trim().toLowerCase();
        return (
          <div className="space-y-4">
            <input
              className="input"
              value={cmdQuery}
              onChange={(e) => setCmdQuery(e.target.value)}
              placeholder={t("create.searchCommands")}
            />
            <div>
              <div className="label mb-2">{t("create.stepModules")}</div>
              {checkboxGrid(
                CUSTOM_CATEGORIES.map((c) => c.name),
                CUSTOM_CATEGORIES.filter((c) => modules.includes(c.id)).map((c) => c.name),
                (names) => {
                  const next = CUSTOM_CATEGORIES.filter((c) => names.includes(c.name)).map((c) => c.id);
                  setModules(next);
                  setIntents((prev) => mergeIntentsForModules(prev, next));
                },
              )}
            </div>
            {modules.map((m) => {
              const cat = CUSTOM_CATEGORIES.find((c) => c.id === m);
              if (!cat) return null;
              const visible = cat.commands.filter(
                (c) =>
                  COMMAND_COGS[c.id]?.file &&
                  (!q || c.name.toLowerCase().includes(q) || c.description.toLowerCase().includes(q)),
              );
              if (visible.length === 0) return null;
              return (
                <div key={m}>
                  <div className="label mb-2">{cat.name}</div>
                  {checkboxGrid(
                    visible.map((c) => c.name),
                    commands,
                    setCommands,
                  )}
                </div>
              );
            })}
            {modules.length === 0 && (
              <p className="text-sm text-[var(--muted)]">{t("create.enableModuleFirst")}</p>
            )}
          </div>
        );
      }
      case "discord:intents":
        return (
          <IntentPicker
            selected={intents}
            modules={modules}
            onToggle={(id) =>
              setIntents((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
            }
          />
        );
      case "minecraft:software":
        return (
          <div className="space-y-3">
            <SoftwarePicker value={software} onChange={setSoftware} />
            <p className="text-xs text-[var(--muted)]">{t("create.softwareHint")}</p>
          </div>
        );
      case "minecraft:version":
        return (
          <div className="space-y-3">
            <div className="label">{t("create.versionFor", { software })}</div>
            <VersionPicker software={software} value={version} onChange={setVersion} />
            <p className="text-xs text-[var(--muted)]">{t("create.versionHint")}</p>
          </div>
        );
      case "minecraft:network":
        return (
          <div className="space-y-3">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={bedrock} onChange={(e) => setBedrock(e.target.checked)} />
              {t("create.bedrock")}
            </label>
            <p className="text-xs text-[var(--muted)]">{t("create.bedrockHint")}</p>
          </div>
        );
      case "minecraft:properties":
        return (
          <div className="space-y-3">
            <div className="grid gap-3 md:grid-cols-2">
              {WIZARD_PROPERTIES.map((key) => {
                const def = PROPERTY_BY_KEY[key];
                if (!def) return null;
                return (
                  <div key={key}>
                    <div className="label mb-1">{key}</div>
                    <PropertyControl
                      def={def}
                      value={mcProps[key] ?? ""}
                      onChange={(v) => setMcProps((c) => ({ ...c, [key]: v }))}
                    />
                    <p className="mt-1 text-[11px] text-[var(--muted)]">{def.description}</p>
                  </div>
                );
              })}
            </div>
            <p className="text-xs text-[var(--muted)]">{t("create.otherPropsHint")}</p>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={eula} onChange={(e) => setEula(e.target.checked)} />
              {t("create.acceptEula")}
            </label>
          </div>
        );
      case "web:template":
        return (
          <div className="grid grid-cols-2 gap-2 md:grid-cols-3">
            {WEB_TEMPLATES.map((t) => (
              <button
                key={t.id}
                type="button"
                className="btn justify-center"
                style={{ borderColor: template === t.id ? "var(--accent)" : "var(--line)" }}
                onClick={() => setTemplate(t.id)}
              >
                {t.label}
              </button>
            ))}
          </div>
        );
      case "web:source":
        return (
          <div className="space-y-3">
            <div className="flex gap-2">
              {(["empty", "github"] as const).map((s) => (
                <button
                  key={s}
                  type="button"
                  className="btn"
                  style={{ borderColor: source === s ? "var(--accent)" : "var(--line)" }}
                  onClick={() => setSource(s)}
                >
                  {s === "empty" ? t("create.emptyProject") : t("create.githubRepo")}
                </button>
              ))}
            </div>
            {source === "github" && (
              <>
                {githubLoading && (
                  <p className="text-xs text-[var(--muted)]">{t("create.githubReposLoading")}</p>
                )}
                {github && !github.configured && (
                  <p className="text-xs text-[var(--muted)]">{t("create.githubNotConfigured")}</p>
                )}
                {github && github.configured && !github.linked && (
                  <div className="space-y-2 rounded-[9px] border border-[var(--line)] p-3">
                    <p className="text-sm">{t("create.githubRequired")}</p>
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() => {
                        window.location.assign(
                          withPanelBase(
                            "/api/auth/oauth/github?intent=link&returnTo=/dashboard/new/web",
                          ),
                        );
                      }}
                    >
                      {t("create.githubLinkNow")}
                    </button>
                  </div>
                )}
                {github?.linked && (
                  <>
                    {field(
                      t("create.githubRepos"),
                      <select
                        className="select"
                        value={repoUrl}
                        onChange={(e) => {
                          const repo = github.repos.find((r) => r.cloneUrl === e.target.value);
                          setRepoUrl(e.target.value);
                          if (repo) setBranch(repo.defaultBranch);
                        }}
                      >
                        <option value="">{t("create.githubPickRepo")}</option>
                        {github.repos.map((r) => (
                          <option key={r.fullName} value={r.cloneUrl}>
                            {r.fullName}
                            {r.private ? ` (${t("create.githubPrivate")})` : ""}
                          </option>
                        ))}
                      </select>,
                    )}
                    {github.repos.length === 0 && (
                      <p className="text-xs text-[var(--muted)]">{t("create.githubReposEmpty")}</p>
                    )}
                    {field(
                      t("create.githubManualUrl"),
                      <input
                        className="input"
                        placeholder="https://github.com/user/repo.git"
                        value={repoUrl}
                        onChange={(e) => setRepoUrl(e.target.value)}
                      />,
                    )}
                    {field(t("create.branch"), <input className="input" value={branch} onChange={(e) => setBranch(e.target.value)} />)}
                    <label className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={autoDeploy}
                        onChange={(e) => setAutoDeploy(e.target.checked)}
                      />
                      {t("create.autoDeploy")}
                    </label>
                  </>
                )}
              </>
            )}
          </div>
        );
      case "web:build":
        return (
          <div className="space-y-3">
            {field(t("create.installCmd"), <input className="input" value={installCommand} onChange={(e) => setInstallCommand(e.target.value)} />)}
            {field(t("create.buildCmd"), <input className="input" value={buildCommand} onChange={(e) => setBuildCommand(e.target.value)} />)}
            {field(t("create.startCmd"), <input className="input" value={startCommand} onChange={(e) => setStartCommand(e.target.value)} />)}
          </div>
        );
      case "discord:resources":
      case "minecraft:resources":
      case "web:resources":
        return (
          <div className="space-y-4">
            <div>
              <div className="label mb-1">{t("create.ram")}</div>
              <div className="flex flex-wrap gap-2">
                {ramPresets.map((m) => (
                  <button
                    key={m}
                    type="button"
                    className="btn"
                    style={{ borderColor: memoryMb === m ? "var(--accent)" : "var(--line)" }}
                    onClick={() => setMemoryMb(m)}
                  >
                    {m >= 1024 ? `${m / 1024} GB` : `${m} MB`}
                  </button>
                ))}
                <input
                  className="input w-32"
                  type="number"
                  value={memoryMb}
                  max={typeLimits?.memoryMb}
                  onChange={(e) => setMemoryMb(Number(e.target.value))}
                />
              </div>
            </div>
            <div>
              <div className="label mb-1">{t("create.cpu")}</div>
              <div className="flex flex-wrap gap-2">
                {cpuPresets.map((c) => (
                  <button
                    key={c}
                    type="button"
                    className="btn"
                    style={{ borderColor: cpu === c ? "var(--accent)" : "var(--line)" }}
                    onClick={() => setCpu(c)}
                  >
                    {t("create.cores", { n: c / 1000, s: c > 1000 ? "s" : "" })}
                  </button>
                ))}
                <input
                  className="input w-32"
                  type="number"
                  value={cpu}
                  max={typeLimits?.cpuMillicores}
                  onChange={(e) => setCpu(Number(e.target.value))}
                />
              </div>
            </div>
            {field(
              t("create.storageMb"),
              <input
                className="input"
                type="number"
                value={storageMb}
                max={typeLimits?.storageMb}
                onChange={(e) => setStorageMb(Number(e.target.value))}
              />,
            )}
            <p className="text-sm text-[var(--muted)]">{t("create.limitsHint")}</p>
            <p className="text-sm">
              {t("create.monthlyCost", { n: cost })} — {t("create.costHint")}
            </p>
          </div>
        );
      case "web:environment":
        return field(
          t("create.envVars"),
          <textarea
            className="textarea font-mono"
            rows={8}
            value={envText}
            onChange={(e) => setEnvText(e.target.value)}
            placeholder={"NODE_ENV=production\nAPI_KEY=..."}
          />,
        );
      default:
        return (
          <div className="space-y-3 text-sm">
            <div>
              <span className="label">{t("create.name")}</span>
              <div className="mt-1">{name || t("create.required")}</div>
            </div>
            <div>
              <span className="label">{t("create.stepResources")}</span>
              <div className="mt-1">
                {memoryMb} MB · {(cpu / 1000).toFixed(1)} CPU · {storageMb} MB — {t("create.monthlyCost", { n: cost })}
              </div>
            </div>
            {type === "discord" && (
              <>
                <div>
                  <span className="label">{t("create.stepBotSource")}</span>
                  <div className="mt-1">{t("create.botSourceCatalog")}</div>
                </div>
                <div>
                  <span className="label">{t("create.prefix")}</span>
                  <div className="mt-1">
                    {prefix} · {t("create.slashEnable")}: {String(slash)}
                  </div>
                </div>
                <div>
                  <span className="label">{t("create.stepCommands")}</span>
                  <div className="mt-1">{commands.join(", ") || t("create.none")}</div>
                </div>
                <div>
                  <span className="label">{t("discord.botToken")}</span>
                  <div className="mt-1">{token.trim() ? t("create.tokenProvided") : t("create.tokenNotSet")}</div>
                </div>
              </>
            )}
            {type === "minecraft" && (
              <>
                <div>
                  {software} {version || t("create.pickVersion")} · bedrock: {String(bedrock)}
                </div>
                <div>EULA: {String(eula)}</div>
              </>
            )}
            {type === "web" && (
              <>
                <div>
                  {template} · {source}
                </div>
                {source === "github" && (
                  <div>
                    {repoUrl}#{branch}
                  </div>
                )}
                <div>
                  {t("create.suggestedHostPreview", {
                    host: `${(name || "service").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "service"}.example.com`,
                  })}
                </div>
              </>
            )}
          </div>
        );
    }
  };

  if (platform && !isCreationEnabled(platform, type)) {
    return (
      <div className="mx-auto max-w-3xl">
        <PageHeader title={t("create.title", { type: t(`nav.${type}`) })} subtitle={t("create.disabledHint")} />
        <ErrorText error={t("create.disabled", { label: t(`nav.${type}`) })} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title={t("create.title", { type: t(`nav.${type}`) })} subtitle={t("create.costHint")} />
      <div className="mb-4 flex flex-wrap gap-2">
        {CREATE_TYPES.filter((kind) => isCreationEnabled(platform, kind)).map((kind) => (
          <button
            key={kind}
            type="button"
            className={kind === type ? "btn btn-primary" : "btn"}
            onClick={() => {
              if (kind !== type) router.push(`/dashboard/new/${kind}`);
            }}
          >
            {kind === "discord" ? t("services.newDiscord") : kind === "minecraft" ? t("services.newMinecraft") : t("services.newWeb")}
          </button>
        ))}
      </div>
      {livePromos.length > 0 && (
        <p className="mb-3 text-sm text-[var(--gold)]">
          {livePromos.map((row) => `${row.label} −${row.percent} %`).join(" · ")}
        </p>
      )}
      <div className="mb-5 mt-3 flex flex-wrap gap-1 overflow-x-auto">
        {STEPS.map((s, i) => (
          <button
            key={s}
            className="tab"
            data-active={i === step}
            onClick={() => setStep(i)}
          >
            {String(i + 1).padStart(2, "0")} {stepLabel(s)}
          </button>
        ))}
      </div>

      <div className="panel p-5">{content()}</div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
        <button className="btn" disabled={step === 0} onClick={() => setStep(step - 1)}>
          <ChevronLeft size={14} /> {t("common.back")}
        </button>
        <ErrorText error={error} />
        {error && /insuffisant|INSUFFICIENT_KRONES/i.test(error) && (
          <a href="/krones" className="btn btn-primary" target="_top">
            {t("krones.shop")}
          </a>
        )}
        {type === "discord" && botSource === "ticket" ? (
          <a href={supportInvite} target="_blank" rel="noopener noreferrer" className="btn btn-primary">
            {t("create.openTickets")}
          </a>
        ) : step < STEPS.length - 1 ? (
          <button className="btn btn-primary" onClick={() => setStep(step + 1)}>
            {t("create.next")} <ChevronRight size={14} />
          </button>
        ) : (
          <button
            className="btn btn-primary"
            disabled={
              busy ||
              !name ||
              (type === "minecraft" && !version) ||
              (type === "web" && source === "github" && (!repoUrl || !github?.linked))
            }
            onClick={submit}
          >
            {busy ? (
              <>
                <span className="spinner" /> {t("create.creatingBusy")}
              </>
            ) : (
              t("create.create")
            )}
          </button>
        )}
      </div>
    </div>
  );
}
