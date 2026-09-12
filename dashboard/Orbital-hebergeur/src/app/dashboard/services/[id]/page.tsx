"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import { Play, RefreshCw, RotateCcw, Square, Trash2, Zap } from "lucide-react";
import { api, fmtBytesMb, fmtUptime } from "@/lib/client";
import { useT } from "@/lib/i18n";
import { usePoll } from "@/lib/use-poll";
import { Bar, ErrorText, SecretBanner, Skeleton, StateBadge, TypeIcon } from "@/components/panel";
import { SftpFields, SftpHowTo, SftpPasswordHint } from "@/components/sftp-connect";
import { useToast } from "@/components/toast";
import { Console } from "@/components/console";
import { FileManager } from "@/components/files";
import { DiscordInviteLink, DiscordTokenPanel } from "@/components/discord-token";
import { DiscordDefaultConfig } from "@/components/discord-default-config";
import { DiscordGuildConfig } from "@/components/discord-guild-config";
import { IntentPicker, PrivilegedPortalChecklist } from "@/components/discord-intents";
import { isPrivilegedIntent, mergeIntentsForModules } from "@/lib/discord/intents";
import { COMMAND_CATALOG, customCategories, flavorFromModules, officialBot } from "@/lib/discord/catalog";
import { SoftwarePicker, VersionPicker } from "@/components/mc-runtime";
import { MinecraftProperties } from "@/components/mc-properties";
import { Addons } from "@/components/mods";
import { DomainRecords } from "@/components/domain-records";
import type { DnsRecord } from "@/lib/domains/public";

type Detail = {
  service: {
    id: string;
    name: string;
    type: string;
    slug: string;
    state: string;
    description: string | null;
    memoryLimitMb: number;
    cpuLimit: number;
    storageLimitMb: number;
    restartPolicy: string;
    lastError: string | null;
  };
  container: {
    containerName: string;
    dockerContainerId: string | null;
    image: string;
    network: string;
    status: string;
    restartCount: number;
  } | null;
  discord?: {
    flavor?: string;
    prefix: string;
    slashCommands: boolean;
    modules: string[];
    intents: string[];
    hasToken: boolean;
    tokenUnreadable?: boolean;
    tokenFingerprint: string | null;
    applicationId: string | null;
    commands: Array<{ name: string; module: string; enabled: boolean; cooldown: number; description: string }>;
  } | null;
  minecraft?: {
    software: string;
    version: string;
    javaPort: number;
    bedrockEnabled: boolean;
    bedrockPort: number;
    eulaAccepted: boolean;
    properties: Record<string, string>;
  } | null;
  addons?: Array<{ id: string; kind: string; name: string; fileName: string; enabled: boolean; sizeBytes: number }>;
  web?: {
    template: string;
    source: string;
    repoUrl: string | null;
    branch: string;
    port: number;
    autoDeploy: boolean;
    installCommand: string | null;
    buildCommand: string | null;
    startCommand: string | null;
  } | null;
  deployments?: Array<{
    id: string;
    number: number;
    status: string;
    trigger: string;
    commitSha: string | null;
    isCurrent: boolean;
    logs: string;
    startedAt: string;
  }>;
  domains?: Array<{
    id: string;
    hostname: string;
    https: boolean;
    status: string;
    kind?: string;
    records?: DnsRecord[];
  }>;
  domainHints?: {
    suggestedHostname: string;
    publicBaseDomain: string;
    domainPendingPurchase: boolean;
    records: DnsRecord[];
    ttlHint: number;
  };
  env: Array<{ id: string; key: string; secret: boolean }>;
  backups: Array<{ id: string; fileName: string; sizeBytes: number; status: string; createdAt: string }>;
  sftp: { username: string; host: string; port: number; chroot: string } | null;
  databases: Array<{ id: string; dbName: string; dbUser: string; host: string; port: number; engine: string }>;
};

type Stats = {
  cpuPercent: number;
  memoryMb: number;
  memoryLimitMb: number;
  networkRxKb: number;
  networkTxKb: number;
  diskMb: number;
  uptimeSeconds: number;
  restartCount: number;
  available: boolean;
  reason?: string;
};

function ServiceDetail() {
  const { id } = useParams<{ id: string }>();
  const search = useSearchParams();
  const router = useRouter();
  const t = useT();
  const toast = useToast();
  const [tab, setTab] = useState(search.get("tab") ?? "overview");
  const [data, setData] = useState<Detail | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [secret, setSecret] = useState<{ label: string; value: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setData(await api<Detail>(`/api/services/${id}`, { silent: true }));
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
    try {
      setStats(await api<Stats>(`/api/services/${id}/stats`, { silent: true }));
    } catch {
      setStats(null);
    }
  }, [id]);

  usePoll(load, 8000, id);

  const SUCCESS: Record<string, string> = {
    start: t("service.started"),
    stop: t("service.stopped"),
    restart: t("service.restarted"),
    kill: t("service.killed"),
    recreate: t("service.recreated"),
    deploy: t("service.deployed"),
    backups: t("service.backupCreated"),
    database: t("service.dbProvisioned"),
    domains: t("service.domainAdded"),
  };

  const act = async (action: string, json?: unknown) => {
    setBusy(true);
    setError(null);
    try {
      const res = await api<Record<string, unknown>>(`/api/services/${id}/${action}`, {
        json: json ?? {},
      });
      const title =
        action === "backups" && (json as { op?: string } | undefined)?.op === "restore"
          ? t("service.backupRestored")
          : (SUCCESS[action] ?? t("service.actionOk"));
      toast.success(title);
      await load();
      return res;
    } catch (err) {
      setError((err as Error).message);
      return null;
    } finally {
      setBusy(false);
    }
  };

  if (!data) {
    return (
      <div>
        <ErrorText error={error} />
        {!error && (
          <div className="space-y-3">
            <Skeleton className="h-10 w-80" />
            <Skeleton className="h-48" />
            <p className="text-sm text-[var(--muted)]">{t("service.loading")}</p>
          </div>
        )}
      </div>
    );
  }

  const svc = data.service;
  const tabs = [
    "overview",
    "console",
    "files",
    ...(svc.type === "discord" ? ["token", "modules", "commands", "config"] : []),
    ...(svc.type === "minecraft" ? ["version", "properties", "addons"] : []),
    ...(svc.type === "web" ? ["deployments", "domains"] : []),
    "environment",
    "backups",
    "database",
    "sftp",
    "settings",
  ];

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <TypeIcon type={svc.type} size={20} />
        <h1 className="text-2xl font-bold">{svc.name}</h1>
        <StateBadge state={svc.state} />
        <div className="ml-auto flex flex-wrap gap-2">
          {svc.type === "discord" && data.discord?.applicationId && (
            <DiscordInviteLink applicationId={data.discord.applicationId} compact />
          )}
          <button className="btn" disabled={busy} onClick={() => act("start")}>
            {busy ? <span className="spinner" /> : <Play size={14} />} {t("service.start")}
          </button>
          <button className="btn" disabled={busy} onClick={() => act("stop")}>
            <Square size={14} /> {t("service.stop")}
          </button>
          <button className="btn" disabled={busy} onClick={() => act("restart")}>
            <RotateCcw size={14} /> {t("service.restart")}
          </button>
          <button className="btn btn-danger" disabled={busy} onClick={() => act("kill")}>
            <Zap size={14} /> {t("service.kill")}
          </button>
          <button className="btn" disabled={busy} onClick={() => void load()}>
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      <ErrorText error={error} />
      {secret && (
        <SecretBanner
          label={secret.label}
          value={secret.value}
          onClose={() => setSecret(null)}
        />
      )}
      {svc.lastError && (
        <div className="mb-3">
          <ErrorText error={svc.lastError} />
        </div>
      )}

      <div className="mb-4 flex flex-wrap gap-1 border-b border-[var(--line)] pb-2">
        {tabs.map((tabId) => (
          <button
            key={tabId}
            className="tab"
            data-active={tab === tabId}
            onClick={() => {
              setTab(tabId);
              const hash = tabId === "console" ? "#console" : "";
              window.history.replaceState(
                window.history.state,
                "",
                `/dashboard/services/${id}?tab=${tabId}${hash}`,
              );
            }}
          >
            {t(`tabs.${tabId}`)}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="panel p-4 lg:col-span-2">
            <div className="label">{t("service.resources")}</div>
            <div className="mt-3 space-y-3 text-xs">
              <div>
                <div className="flex justify-between">
                  <span>{t("service.cpu")}</span>
                  <span>
                    {t("service.coresOf", {
                      used: (stats?.cpuPercent ?? 0).toFixed(1),
                      cores: (svc.cpuLimit / 1000).toFixed(1),
                    })}
                  </span>
                </div>
                <Bar value={stats?.cpuPercent ?? 0} max={100} />
              </div>
              <div>
                <div className="flex justify-between">
                  <span>{t("service.ram")}</span>
                  <span>
                    {fmtBytesMb(stats?.memoryMb ?? 0)} / {fmtBytesMb(svc.memoryLimitMb)}
                  </span>
                </div>
                <Bar value={stats?.memoryMb ?? 0} max={svc.memoryLimitMb} />
              </div>
              <div>
                <div className="flex justify-between">
                  <span>{t("service.storage")}</span>
                  <span>
                    {fmtBytesMb(stats?.diskMb ?? 0)} / {fmtBytesMb(svc.storageLimitMb)}
                  </span>
                </div>
                <Bar value={stats?.diskMb ?? 0} max={svc.storageLimitMb} />
              </div>
              <div className="grid grid-cols-2 gap-2 pt-2 text-[var(--muted)] md:grid-cols-4">
                <div>
                  {t("service.rx")} {((stats?.networkRxKb ?? 0) / 1024).toFixed(2)} MB
                </div>
                <div>
                  {t("service.tx")} {((stats?.networkTxKb ?? 0) / 1024).toFixed(2)} MB
                </div>
                <div>
                  {t("service.uptime")} {fmtUptime(stats?.uptimeSeconds ?? 0)}
                </div>
                <div>
                  {t("service.restarts")} {stats?.restartCount ?? data.container?.restartCount ?? 0}
                </div>
              </div>
              {stats && !stats.available && (
                <div className="text-[var(--muted)]">
                  {t("service.statsUnavailable", { reason: stats.reason ?? "" })}
                </div>
              )}
            </div>
          </div>

          <div className="panel p-4 text-xs">
            <div className="label">{t("service.container")}</div>
            <div className="mt-3 space-y-1 font-mono text-[11px] text-[var(--muted)]">
              <div>
                {t("service.name")}: {data.container?.containerName ?? "—"}
              </div>
              <div>
                {t("service.id")}: {data.container?.dockerContainerId?.slice(0, 12) ?? "—"}
              </div>
              <div>
                {t("service.image")}: {data.container?.image ?? "—"}
              </div>
              <div>
                {t("service.network")}: {data.container?.network ?? "—"}
              </div>
              <div>
                {t("service.restartPolicy")}: {svc.restartPolicy}
              </div>
              <div>
                {t("service.volume")}: /data/{svc.type}/{svc.id}
              </div>
            </div>
            {svc.type === "minecraft" && data.minecraft && (
              <div className="mt-3 space-y-1 text-[11px]">
                <div>
                  {t("service.software")}: {data.minecraft.software} {data.minecraft.version}
                </div>
                <div>
                  {t("service.javaPort")}: {data.minecraft.javaPort}
                </div>
                {data.minecraft.bedrockEnabled && (
                  <div>
                    {t("service.bedrockPort")}: {data.minecraft.bedrockPort}
                  </div>
                )}
                {!data.minecraft.eulaAccepted && (
                  <button className="btn mt-2" onClick={() => act("minecraft", { op: "eula" })}>
                    {t("service.acceptEula")}
                  </button>
                )}
              </div>
            )}
            {svc.type === "web" && data.web && (
              <div className="mt-3 space-y-1 text-[11px]">
                <div>
                  {t("service.template")}: {data.web.template}
                </div>
                <div>
                  {t("service.port")}: {data.web.port}
                </div>
                <div>
                  {t("service.source")}: {data.web.source}
                  {data.web.repoUrl ? ` (${data.web.repoUrl}#${data.web.branch})` : ""}
                </div>
                {(data.domains ?? []).length > 0 && (
                  <div>
                    {t("tabs.domains")}: {(data.domains ?? []).map((d) => d.hostname).join(", ")}
                  </div>
                )}
                {data.domainHints && (data.domains ?? []).length === 0 && (
                  <div>
                    {t("service.suggestedDomain")}: {data.domainHints.suggestedHostname}
                  </div>
                )}
              </div>
            )}
            {svc.type === "discord" && data.discord && (
              <div className="mt-3 space-y-1 text-[11px]">
                <div>
                  {t("service.prefix")}: {data.discord.prefix}
                </div>
                <div>
                  {t("service.slashCommands")}:{" "}
                  {data.discord.slashCommands ? t("service.slashOn") : t("service.slashOff")}
                </div>
                <div>
                  {t("service.token")}:{" "}
                  {data.discord.tokenUnreadable
                    ? t("service.tokenUnreadable")
                    : data.discord.hasToken
                      ? t("service.tokenStored", { fp: data.discord.tokenFingerprint ?? "" })
                      : t("service.tokenMissing")}
                </div>
                {data.discord.applicationId && (
                  <div className="pt-2">
                    <DiscordInviteLink applicationId={data.discord.applicationId} />
                  </div>
                )}
              </div>
            )}
            <button className="btn mt-4 w-full justify-center" disabled={busy} onClick={() => act("recreate")}>
              {t("service.recreate")}
            </button>
          </div>
        </div>
      )}

      {tab === "console" && (
        <Console
          key={id}
          serviceId={id}
          canSend
          serviceType={svc.type}
          applicationId={data.discord?.applicationId}
          initialState={svc.state}
        />
      )}
      {tab === "files" && <FileManager serviceId={id} />}

      {tab === "token" && data.discord && (
        <DiscordTokenPanel
          hasToken={data.discord.hasToken}
          tokenUnreadable={data.discord.tokenUnreadable}
          fingerprint={data.discord.tokenFingerprint}
          applicationId={data.discord.applicationId}
          onSubmit={async ({ token: value, applicationId }) => {
            const res = await api(`/api/services/${id}/discord`, {
              json: { op: "token", token: value, applicationId },
            });
            await load();
            return res;
          }}
          onApplicationId={async (value) => {
            const res = await api(`/api/services/${id}/discord`, {
              json: { op: "config", applicationId: value },
            });
            await load();
            return res;
          }}
        />
      )}

      {tab === "modules" && data.discord && (
        <DiscordModules
          modules={data.discord.modules}
          flavor={data.discord.flavor}
          intents={data.discord.intents}
          applicationId={data.discord.applicationId}
          onSave={(payload) => act("discord", { op: "config", ...payload })}
        />
      )}

      {tab === "commands" && data.discord && (
        <DiscordCommands
          commands={data.discord.commands}
          official={Boolean(data.discord.flavor && data.discord.flavor !== "custom")}
          onToggle={(name, enabled) =>
            act("discord", { op: "config", commands: [{ name, enabled }] })
          }
        />
      )}
      {tab === "config" && data.discord && (
        <div className="space-y-4">
          <DiscordDefaultConfig serviceId={id} />
          <DiscordGuildConfig serviceId={id} />
        </div>
      )}

      {tab === "version" && data.minecraft && (
        <MinecraftRuntime
          software={data.minecraft.software}
          version={data.minecraft.version}
          eulaAccepted={data.minecraft.eulaAccepted}
          busy={busy}
          onSave={(payload) => act("minecraft", { op: "runtime", ...payload })}
          onAcceptEula={() => act("minecraft", { op: "eula" })}
        />
      )}

      {tab === "properties" && data.minecraft && (
        <MinecraftProperties serviceId={id} properties={data.minecraft.properties} onSaved={load} />
      )}

      {tab === "addons" && <Addons serviceId={id} />}

      {tab === "deployments" && (
        <div className="space-y-3">
          <button className="btn btn-primary" disabled={busy} onClick={() => act("deploy")}>
            {t("service.deployNow")}
          </button>
          {(data.deployments ?? []).map((d) => (
            <div key={d.id} className="panel p-4 text-xs">
              <div className="flex items-center justify-between">
                <div className="font-semibold">
                  #{d.number} · {d.status} · {d.trigger}
                  {d.isCurrent && (
                    <span className="ml-2 text-[var(--success)]">{t("service.current")}</span>
                  )}
                </div>
                <div className="flex items-center gap-2 text-[var(--muted)]">
                  {d.commitSha && <span className="font-mono">{d.commitSha}</span>}
                  <span>{new Date(d.startedAt).toLocaleString()}</span>
                  <button className="btn" onClick={() => act("deploy", { rollbackTo: d.id })}>
                    {t("service.rollback")}
                  </button>
                </div>
              </div>
              <pre className="console scroll mt-2 max-h-48 overflow-auto p-2 text-[11px]">
                {d.logs || t("service.noLogs")}
              </pre>
            </div>
          ))}
        </div>
      )}

      {tab === "domains" && (
        <div className="space-y-3">
          {data.domainHints && (
            <div className="panel space-y-2 p-4 text-sm">
              <div className="text-sm font-semibold">{t("service.suggestedDomain")}</div>
              <p className="text-[11px] leading-relaxed text-[var(--muted)]">
                {t("service.suggestedDomainHint", { host: data.domainHints.suggestedHostname })}
              </p>
              {data.domainHints.domainPendingPurchase && (
                <p className="text-[11px] leading-relaxed text-[var(--muted)]">
                  {t("service.domainPendingPurchase", { base: data.domainHints.publicBaseDomain })}
                </p>
              )}
              <button
                type="button"
                className="btn"
                disabled={(data.domains ?? []).some((d) => d.hostname === data.domainHints?.suggestedHostname)}
                onClick={() =>
                  act("domains", {
                    hostname: data.domainHints?.suggestedHostname,
                    kind: "default",
                  })
                }
              >
                {t("service.useSuggested")}
              </button>
            </div>
          )}
          <form
            className="flex gap-2"
            onSubmit={async (e) => {
              e.preventDefault();
              const form = e.target as HTMLFormElement;
              const input = form.elements.namedItem("hostname") as HTMLInputElement;
              await act("domains", { hostname: input.value, kind: "custom" });
              input.value = "";
            }}
          >
            <input
              className="input"
              name="hostname"
              placeholder={data.domainHints?.suggestedHostname ?? "www.example.com"}
            />
            <button className="btn btn-primary">{t("service.addDomain")}</button>
          </form>
          <p className="text-[11px] text-[var(--muted)]">{t("service.customDomainHint")}</p>
          <p className="text-[11px] text-[var(--muted)]">{t("service.dnsTtlHint")}</p>
          <div className="space-y-3">
            {(data.domains ?? []).map((d) => (
              <div key={d.id} className="panel space-y-2 p-4 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <span className="font-semibold">{d.hostname}</span>{" "}
                    <span className="text-[var(--muted)]">
                      {d.kind === "default" ? t("service.domainKindDefault") : t("service.domainKindCustom")}
                      {" · "}
                      {d.https ? t("service.httpsTraefik") : "HTTP"} · {d.status}
                    </span>
                  </div>
                  <button
                    type="button"
                    className="btn btn-danger"
                    onClick={async () => {
                      await api(`/api/services/${id}/domains?id=${d.id}`, { method: "DELETE" });
                      toast.success(t("service.domainRemoved"));
                      void load();
                    }}
                  >
                    {t("service.removeDomain")}
                  </button>
                </div>
                <div className="text-[11px] font-semibold text-[var(--muted)]">{t("service.dnsRecords")}</div>
                <DomainRecords records={d.records ?? []} />
                {d.hostname.split(".").length === 2 && (
                  <p className="text-[11px] text-[var(--muted)]">{t("service.dnsApexHint")}</p>
                )}
              </div>
            ))}
            {(data.domains ?? []).length === 0 && (
              <div className="panel px-4 py-3 text-xs text-[var(--muted)]">{t("service.noDomain")}</div>
            )}
          </div>
        </div>
      )}

      {tab === "environment" && (
        <div className="space-y-3">
          <form
            className="flex gap-2"
            onSubmit={async (e) => {
              e.preventDefault();
              const form = e.target as HTMLFormElement;
              const key = (form.elements.namedItem("key") as HTMLInputElement).value;
              const value = (form.elements.namedItem("value") as HTMLInputElement).value;
              await act("env", { key, value });
              form.reset();
            }}
          >
            <input className="input" name="key" placeholder="KEY" />
            <input className="input" name="value" placeholder="value" />
            <button className="btn btn-primary">{t("service.setEnv")}</button>
          </form>
          <div className="panel divide-y divide-[var(--line)] text-xs">
            {data.env.map((e) => (
              <div key={e.id} className="flex items-center justify-between px-4 py-2">
                <span className="font-mono">{e.key}</span>
                <div className="flex items-center gap-3">
                  <span className="text-[var(--muted)]">
                    {e.secret ? t("service.encrypted") : t("service.encryptedAtRest")}
                  </span>
                  <button
                    className="text-[var(--danger)]"
                    onClick={async () => {
                      await api(`/api/services/${id}/env?id=${e.id}`, { method: "DELETE" });
                      void load();
                    }}
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            ))}
          </div>
          <p className="text-[11px] text-[var(--muted)]">{t("service.envHint")}</p>
        </div>
      )}

      {tab === "backups" && (
        <div className="space-y-3">
          <button className="btn btn-primary" disabled={busy} onClick={() => act("backups")}>
            {t("service.createBackup")}
          </button>
          <div className="panel divide-y divide-[var(--line)] text-xs">
            {data.backups.map((b) => (
              <div key={b.id} className="flex items-center justify-between px-4 py-2">
                <span className="font-mono">{b.fileName}</span>
                <div className="flex items-center gap-3 text-[var(--muted)]">
                  <span>{(b.sizeBytes / 1048576).toFixed(1)} MB</span>
                  <span>{b.status}</span>
                  <button className="btn" onClick={() => act("backups", { op: "restore", backupId: b.id })}>
                    {t("service.restore")}
                  </button>
                  <button
                    className="text-[var(--danger)]"
                    onClick={async () => {
                      await api(`/api/services/${id}/backups?id=${b.id}`, { method: "DELETE" });
                      void load();
                    }}
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>
            ))}
            {data.backups.length === 0 && (
              <div className="px-4 py-3 text-[var(--muted)]">{t("service.noBackup")}</div>
            )}
          </div>
        </div>
      )}

      {tab === "database" && (
        <div className="space-y-3">
          <button className="btn btn-primary" disabled={busy} onClick={() => act("database")}>
            {t("service.provisionDb")}
          </button>
          <div className="panel divide-y divide-[var(--line)] text-xs">
            {data.databases.map((d) => (
              <div key={d.id} className="px-4 py-2 font-mono">
                {d.engine}://{d.dbUser}@{d.host}:{d.port}/{d.dbName}
              </div>
            ))}
            {data.databases.length === 0 && (
              <div className="px-4 py-3 text-[var(--muted)]">{t("service.noDb")}</div>
            )}
          </div>
        </div>
      )}

      {tab === "sftp" && (
        <div className="space-y-3">
          <SftpHowTo />
          {data.sftp ? (
            <div className="panel space-y-4 p-4">
              <SftpFields
                host={data.sftp.host}
                port={data.sftp.port}
                username={data.sftp.username}
                chroot={data.sftp.chroot}
              />
              <SftpPasswordHint />
            </div>
          ) : (
            <div className="panel p-4 text-sm text-[var(--muted)]">{t("service.noSftp")}</div>
          )}
        </div>
      )}

      {tab === "settings" && (
        <Settings
          service={svc}
          discord={data.discord}
          busy={busy}
          onSaveBotCommands={async (payload) => {
            setBusy(true);
            setError(null);
            try {
              await api(`/api/services/${id}/discord`, {
                json: { op: "config", ...payload },
              });
              toast.success(t("service.botCommandsSaved"));
              await load();
            } catch (err) {
              setError((err as Error).message);
            } finally {
              setBusy(false);
            }
          }}
          onSave={async (patch) => {
            setBusy(true);
            try {
              await api(`/api/services/${id}`, { method: "PATCH", json: patch });
              toast.success(t("service.settingsSaved"));
              await load();
            } catch (err) {
              setError((err as Error).message);
            } finally {
              setBusy(false);
            }
          }}
          onDelete={async () => {
            if (!confirm(t("service.deleteConfirm"))) return;
            await api(`/api/services/${id}`, { method: "DELETE" });
            router.push("/dashboard");
          }}
        />
      )}
    </div>
  );
}

function DiscordModules({
  modules,
  flavor,
  intents,
  applicationId,
  onSave,
}: {
  modules: string[];
  flavor?: string;
  intents: string[];
  applicationId?: string | null;
  onSave: (payload: Record<string, unknown>) => void;
}) {
  const t = useT();
  const officialId = flavor && flavor !== "custom" ? flavor : flavorFromModules(modules);
  const official = officialId !== "custom";
  const bot = official ? officialBot(officialId) : null;
  const catalogModules = official
    ? COMMAND_CATALOG.categories
        .filter(
          (c) =>
            !bot || c.commands.some((cmd) => cmd.source.toLowerCase().includes(bot.name.toLowerCase())),
        )
        .map((c) => ({ id: c.id, label: c.name }))
    : customCategories().map((c) => ({ id: c.id, label: c.name }));
  const [selected, setSelected] = useState(modules);
  const [chosenIntents, setChosenIntents] = useState(intents);
  const [showPortalChecklist, setShowPortalChecklist] = useState(false);

  return (
    <div className="space-y-4">
      <div className="panel p-4">
        {official && (
          <p className="mb-3 text-sm leading-relaxed text-[var(--muted)]">{t("service.officialReadOnly")}</p>
        )}
        <div className="label mb-2">{t("tabs.modules")}</div>
        <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
          {catalogModules.map((m) => {
            const active = official || selected.includes(m.id);
            return (
              <button
                key={m.id}
                type="button"
                disabled={official}
                className="btn justify-start"
                style={{
                  borderColor: active ? "var(--accent)" : "var(--line)",
                  color: active ? "var(--text)" : "var(--muted)",
                }}
                onClick={() => {
                  if (official) return;
                  const next = selected.includes(m.id)
                    ? selected.filter((x) => x !== m.id)
                    : [...selected, m.id];
                  setSelected(next);
                  setChosenIntents((prev) => mergeIntentsForModules(prev, next));
                }}
              >
                {m.label}
              </button>
            );
          })}
        </div>
        <div className="mt-4">
          <div className="label mb-2">{t("service.gatewayIntents")}</div>
          <IntentPicker
            selected={chosenIntents}
            modules={selected}
            applicationId={applicationId}
            onToggle={(id) =>
              setChosenIntents((prev) =>
                prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
              )
            }
          />
        </div>
        {showPortalChecklist && (
          <div className="mt-3">
            <PrivilegedPortalChecklist selected={chosenIntents} applicationId={applicationId} />
          </div>
        )}
        <div className="mt-3 flex items-center gap-3">
          <button
            className="btn btn-primary ml-auto"
            onClick={() => {
              onSave({ modules: selected, intents: chosenIntents });
              setShowPortalChecklist(chosenIntents.some(isPrivilegedIntent));
            }}
          >
            {t("service.saveModules")}
          </button>
        </div>
      </div>
    </div>
  );
}

function DiscordCommands({
  commands,
  official,
  onToggle,
}: {
  commands: Array<{ name: string; module: string; enabled: boolean; cooldown: number; description: string }>;
  official: boolean;
  onToggle: (name: string, enabled: boolean) => void;
}) {
  const t = useT();
  const [query, setQuery] = useState("");
  const q = query.trim().toLowerCase();
  const visible = commands.filter(
    (c) =>
      !q ||
      c.name.toLowerCase().includes(q) ||
      c.description.toLowerCase().includes(q) ||
      c.module.toLowerCase().includes(q),
  );

  return (
    <div className="panel p-4">
      {official && (
        <p className="mb-3 text-sm leading-relaxed text-[var(--muted)]">{t("service.officialReadOnly")}</p>
      )}
      <p className="mb-3 text-sm leading-relaxed text-[var(--muted)]">{t("service.configLocked")}</p>
      <input
        className="input mb-3"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder={t("service.commandSearch")}
      />
      <div className="space-y-2 text-sm">
        {visible.map((c) => (
          <label key={c.name} className="flex items-center gap-3 border-b border-[var(--line)] py-1.5">
            <input
              type="checkbox"
              checked={c.enabled || c.name === "config"}
              disabled={official || c.name === "config"}
              onChange={(e) => onToggle(c.name, e.target.checked)}
            />
            <span className="font-mono">{c.name}</span>
            <span className="text-xs text-[var(--muted)]">{c.description}</span>
            <span className="ml-auto text-[11px] text-[var(--muted)]">
              {c.module} · {t("service.cooldown", { n: c.cooldown })}
            </span>
          </label>
        ))}
        {visible.length === 0 && (
          <p className="text-sm text-[var(--muted)]">{t("service.noCommands")}</p>
        )}
      </div>
    </div>
  );
}

function MinecraftRuntime({
  software,
  version,
  eulaAccepted,
  busy,
  onSave,
  onAcceptEula,
}: {
  software: string;
  version: string;
  eulaAccepted: boolean;
  busy: boolean;
  onSave: (payload: { software: string; version: string }) => void;
  onAcceptEula: () => void;
}) {
  const t = useT();
  const [nextSoftware, setNextSoftware] = useState(software);
  const [nextVersion, setNextVersion] = useState(version);
  const changed = nextSoftware !== software || nextVersion !== version;

  return (
    <div className="space-y-4">
      <div className="panel space-y-3 p-4">
        <div className="label">{t("service.serverSoftware")}</div>
        <SoftwarePicker value={nextSoftware} onChange={setNextSoftware} />
        <div className="label pt-1">{t("service.mcVersion")}</div>
        <VersionPicker software={nextSoftware} value={nextVersion} onChange={setNextVersion} />
        <div className="flex flex-wrap items-center gap-3 pt-1">
          <button
            className="btn btn-primary"
            disabled={busy || !changed || !nextVersion}
            onClick={() => onSave({ software: nextSoftware, version: nextVersion })}
          >
            {t("service.saveRuntime")}
          </button>
          <span className="text-[11px] text-[var(--muted)]">
            {t("service.runtimeHint", { software, version })}
          </span>
        </div>
      </div>

      <div className="panel p-4 text-xs">
        <div className="label mb-2">{t("service.eula")}</div>
        {eulaAccepted ? (
          <div className="text-[var(--success)]">{t("service.eulaAccepted")}</div>
        ) : (
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-[var(--muted)]">{t("service.eulaRequired")}</span>
            <button className="btn" disabled={busy} onClick={onAcceptEula}>
              {t("service.acceptTheEula")}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

const PREFIX_PRESETS = ["!", "?", ".", "$", "-"];

function DiscordRuntimeSettings({
  prefix,
  busy,
  onSave,
}: {
  prefix: string;
  busy: boolean;
  onSave: (payload: { prefix: string; slashCommands: boolean }) => void;
}) {
  const t = useT();
  const [nextPrefix, setNextPrefix] = useState(prefix);

  useEffect(() => {
    setNextPrefix(prefix);
  }, [prefix]);

  const trimmed = nextPrefix.trim();
  const valid = trimmed.length >= 1 && trimmed.length <= 10 && !/[\u0000-\u001F\u007F]/.test(trimmed);
  const dirty = trimmed !== prefix;

  return (
    <div className="panel space-y-4 p-4">
      <div>
        <div className="label">{t("service.botCommands")}</div>
      </div>
      <div>
        <div className="label mb-1">{t("service.prefix")}</div>
        <div className="flex flex-wrap items-center gap-2">
          {PREFIX_PRESETS.map((item) => (
            <button
              key={item}
              type="button"
              className="btn font-mono"
              style={{ borderColor: nextPrefix === item ? "var(--accent)" : "var(--line)" }}
              onClick={() => setNextPrefix(item)}
            >
              {item}
            </button>
          ))}
          <input
            className="input max-w-[12rem] font-mono"
            value={nextPrefix}
            maxLength={10}
            onChange={(e) => setNextPrefix(e.target.value.slice(0, 10))}
            spellCheck={false}
          />
        </div>
        <p className="mt-1 text-[11px] text-[var(--muted)]">{t("service.prefixHint")}</p>
      </div>
      <p className="text-sm leading-relaxed text-[var(--muted)]">{t("service.slashHint")}</p>
      <button
        className="btn btn-primary"
        disabled={busy || !valid || !dirty}
        onClick={() => onSave({ prefix: trimmed, slashCommands: true })}
      >
        {t("service.saveBotCommands")}
      </button>
    </div>
  );
}

function Settings({
  service,
  discord,
  busy,
  onSaveBotCommands,
  onSave,
  onDelete,
}: {
  service: Detail["service"];
  discord?: Detail["discord"];
  busy: boolean;
  onSaveBotCommands: (payload: { prefix: string; slashCommands: boolean }) => void;
  onSave: (patch: Record<string, unknown>) => void;
  onDelete: () => void;
}) {
  const t = useT();
  const [name, setName] = useState(service.name);
  const [memoryMb, setMemoryMb] = useState(service.memoryLimitMb);
  const [cpu, setCpu] = useState(service.cpuLimit);
  const [restartPolicy, setRestartPolicy] = useState(service.restartPolicy);

  return (
    <div className="space-y-4">
      {discord && (
        <DiscordRuntimeSettings
          prefix={discord.prefix}
          busy={busy}
          onSave={onSaveBotCommands}
        />
      )}
      <div className="panel space-y-3 p-4">
        <div>
          <div className="label mb-1">{t("common.name")}</div>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          <div>
            <div className="label mb-1">{t("service.memoryMb")}</div>
            <input
              className="input"
              type="number"
              value={memoryMb}
              onChange={(e) => setMemoryMb(Number(e.target.value))}
            />
          </div>
          <div>
            <div className="label mb-1">{t("service.cpuMillicores")}</div>
            <input
              className="input"
              type="number"
              value={cpu}
              onChange={(e) => setCpu(Number(e.target.value))}
            />
          </div>
          <div>
            <div className="label mb-1">{t("service.restartPolicyLabel")}</div>
            <select
              className="select"
              value={restartPolicy}
              onChange={(e) => setRestartPolicy(e.target.value)}
            >
              <option value="no">{t("service.never")}</option>
              <option value="on-failure">{t("service.onFailure")}</option>
              <option value="always">{t("service.always")}</option>
            </select>
          </div>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => onSave({ name, memoryMb, cpuMillicores: cpu, restartPolicy })}
        >
          {t("service.saveSettings")}
        </button>
      </div>
      <div className="panel p-4">
        <div className="label mb-2">{t("service.danger")}</div>
        <button className="btn btn-danger" onClick={onDelete}>
          <Trash2 size={14} /> {t("service.deleteService")}
        </button>
      </div>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense>
      <ServiceDetail />
    </Suspense>
  );
}
