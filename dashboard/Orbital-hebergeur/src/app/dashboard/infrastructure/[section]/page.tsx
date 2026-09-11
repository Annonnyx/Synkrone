"use client";

import { useParams } from "next/navigation";
import { useCallback, useState } from "react";
import { Database as DatabaseIcon, FolderLock } from "lucide-react";
import { api } from "@/lib/client";
import { useT } from "@/lib/i18n";
import { usePoll } from "@/lib/use-poll";
import { useToast } from "@/components/toast";
import { EmptyState, ErrorText, SecretBanner } from "@/components/panel";
import { PageHeader } from "@/components/ui";
import { SftpFields, SftpHowTo, SftpPasswordHint } from "@/components/sftp-connect";

type Database = {
  id: string;
  dbName: string;
  dbUser: string;
  host: string;
  port: number;
  engine: string;
  serviceId: string | null;
};

type SftpAccount = {
  id: string;
  username: string;
  host: string;
  port: number;
  chroot: string;
  serviceName: string;
  serviceType: string;
};

type Engine = {
  docker: { reachable: boolean; version: string | null; error: string | null; socket: string };
  networks: Record<string, string>;
  dataRoot: string;
  imageMode: string;
  counts: { services: number; containers: number };
};

export default function InfrastructurePage() {
  const { section } = useParams<{ section: string }>();
  const t = useT();
  const toast = useToast();
  const [databases, setDatabases] = useState<Database[]>([]);
  const [accounts, setAccounts] = useState<SftpAccount[]>([]);
  const [engine, setEngine] = useState<Engine | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [secret, setSecret] = useState<{ label: string; value: string } | null>(null);

  const load = useCallback(async () => {
    try {
      if (section === "databases")
        setDatabases(
          (await api<{ databases: Database[] }>("/api/databases", { silent: true })).databases,
        );
      if (section === "sftp")
        setAccounts(
          (await api<{ accounts: SftpAccount[] }>("/api/account/sftp", { silent: true })).accounts,
        );
      if (section === "engine") setEngine(await api<Engine>("/api/engine", { silent: true }));
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, [section]);

  usePoll(load, undefined, section);

  const titles: Record<string, string> = {
    databases: t("infra.databases"),
    sftp: t("infra.sftp"),
    engine: t("infra.engine"),
  };
  const hints: Record<string, string> = {
    databases: t("infra.databasesHint"),
    sftp: t("infra.sftpHint"),
    engine: t("infra.engineHint"),
  };

  return (
    <div>
      <PageHeader title={titles[section] ?? section} subtitle={hints[section]} />
      <ErrorText error={error} />
      {secret && (
        <SecretBanner label={secret.label} value={secret.value} onClose={() => setSecret(null)} />
      )}

      {section === "databases" && (
        <div className="space-y-3">
          <form
            className="flex gap-2"
            onSubmit={async (e) => {
              e.preventDefault();
              const form = e.target as HTMLFormElement;
              const input = form.elements.namedItem("name") as HTMLInputElement;
              try {
                const res = await api<{ connectionString: string }>("/api/databases", {
                  json: { name: input.value },
                });
                setSecret({ label: t("infra.connShownOnce"), value: res.connectionString });
                input.value = "";
                toast.success(t("infra.dbCreated"));
                void load();
              } catch (err) {
                setError((err as Error).message);
              }
            }}
          >
            <input className="input" name="name" placeholder={t("infra.dbName")} required />
            <button className="btn btn-primary">{t("infra.createDb")}</button>
          </form>
          <div className="panel divide-y divide-[var(--line)] text-xs">
            {databases.map((d) => (
              <div key={d.id} className="flex items-center justify-between px-4 py-2">
                <span className="font-mono">
                  {d.engine} · {d.dbName} · {t("infra.user")} {d.dbUser} · {d.host}:{d.port}
                </span>
                <div className="flex gap-2">
                  <button
                    className="btn"
                    onClick={async () => {
                      const res = await api<{ connectionString: string }>("/api/databases", {
                        method: "PATCH",
                        json: { id: d.id },
                      });
                      setSecret({ label: t("infra.newCreds"), value: res.connectionString });
                      toast.success(t("infra.passwordReset"));
                    }}
                  >
                    {t("infra.resetPassword")}
                  </button>
                  <button
                    className="btn btn-danger"
                    onClick={async () => {
                      if (!confirm(t("infra.dropConfirm", { name: d.dbName }))) return;
                      await api(`/api/databases?id=${d.id}`, { method: "DELETE" });
                      toast.success(t("infra.dbDeleted"));
                      void load();
                    }}
                  >
                    {t("common.delete")}
                  </button>
                </div>
              </div>
            ))}
            {databases.length === 0 && (
              <EmptyState icon={DatabaseIcon} title={t("infra.noDb")} compact />
            )}
          </div>
        </div>
      )}

      {section === "sftp" && (
        <div className="space-y-3">
          <SftpHowTo />
          <div className="panel p-4">
            <SftpPasswordHint />
          </div>
          {accounts.map((a) => (
            <div key={a.id} className="panel space-y-4 p-4">
              <div>
                <div className="text-sm font-semibold">{a.serviceName}</div>
                <div className="text-[11px] text-[var(--muted)]">{a.serviceType}</div>
              </div>
              <SftpFields host={a.host} port={a.port} username={a.username} chroot={a.chroot} />
            </div>
          ))}
          {accounts.length === 0 && (
            <EmptyState icon={FolderLock} title={t("infra.noSftp")} compact />
          )}
        </div>
      )}

      {section === "engine" && engine && (
        <div className="space-y-3">
          <div className="panel p-4 text-xs">
            <div className="label mb-2">{t("infra.dockerEngine")}</div>
            <div className="space-y-1 font-mono">
              <div>
                {t("infra.socket")}: {engine.docker.socket}
              </div>
              <div>
                {t("infra.reachable")}:{" "}
                <span style={{ color: engine.docker.reachable ? "var(--success)" : "var(--danger)" }}>
                  {engine.docker.reachable ? t("common.yes") : t("common.no")}
                </span>
              </div>
              <div>
                {t("infra.version")}: {engine.docker.version ?? "—"}
              </div>
              {engine.docker.error && (
                <div className="text-[var(--danger)]">
                  {t("infra.error")}: {engine.docker.error}
                </div>
              )}
              <div>
                {t("infra.imageMode")}: {engine.imageMode}
              </div>
              <div>
                {t("infra.dataRoot")}: {engine.dataRoot}
              </div>
              <div>
                {t("infra.servicesCount")}: {engine.counts.services} · {t("infra.containers")}:{" "}
                {engine.counts.containers}
              </div>
            </div>
          </div>
          <div className="panel p-4 text-xs">
            <div className="label mb-2">{t("infra.networks")}</div>
            <div className="grid gap-1 font-mono md:grid-cols-3">
              {Object.entries(engine.networks).map(([k, v]) => (
                <div key={k}>
                  {k}: <span className="text-[var(--accent)]">{v}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
