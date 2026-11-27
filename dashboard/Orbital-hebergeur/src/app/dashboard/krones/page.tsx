"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/client";
import { useI18n, useT } from "@/lib/i18n";
import { usePoll } from "@/lib/use-poll";
import { ErrorText } from "@/components/panel";
import { PageHeader } from "@/components/ui";
import { Table, Td, Th } from "@/components/ui/table";
import { LedgerChart } from "@/components/charts";

type Wallet = {
  balance: number;
  plan: string;
  linkedDiscord: boolean;
  unlimited?: boolean;
  privilege?: string | null;
  lowBalance?: boolean;
  ledger: Array<{ id: string; type: string; amount: number; reason: string; at: number; balanceAfter: number }>;
};

export default function KronesPage() {
  const t = useT();
  const { locale } = useI18n();
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setWallet(await api<Wallet>("/api/krones", { silent: true }));
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  usePoll(load, 15000);

  const loc = locale === "en" ? "en-GB" : "fr-FR";

  return (
    <div>
      <PageHeader title={t("krones.title")} subtitle={t("krones.subtitle")} />
      <ErrorText error={error} />
      {wallet?.lowBalance && !wallet.unlimited && (
        <div
          className="mb-4 border px-3 py-3 text-sm"
          style={{
            borderRadius: 4,
            borderColor: "var(--ambre)",
            background: "var(--ambre-clair)",
            color: "var(--text)",
          }}
        >
          <p>{t("krones.lowBalance")}</p>
          <a href="/krones" className="btn btn-primary mt-2" target="_top">
            {t("krones.shop")}
          </a>
        </div>
      )}
      <div className="mb-6 grid gap-3 md:grid-cols-3">
        <div className="panel p-4">
          <div className="label">{t("krones.balance")}</div>
          <div className="mt-1 font-serif text-3xl text-[var(--gold)]">
            {wallet?.unlimited ? t("krones.unlimited") : `${(wallet?.balance ?? 0).toLocaleString(loc)} ₭`}
          </div>
          <p className="hint mt-1">{t("krones.plan", { name: wallet?.plan || t("common.none") })}</p>
          {wallet?.privilege === "admin" && <p className="hint">{t("krones.privilegeAdmin")}</p>}
          {wallet?.privilege === "dev" && <p className="hint">{t("krones.privilegeDev")}</p>}
        </div>
        <div className="panel p-4">
          <div className="label">{t("krones.identity")}</div>
          <p className="mt-2 text-sm leading-relaxed text-[var(--muted)]">
            {wallet?.linkedDiscord ? t("krones.linked") : t("krones.unlinked")}
          </p>
          {!wallet?.linkedDiscord && (
            <Link href="/dashboard/account/profile" className="btn mt-3">
              {t("krones.linkDiscord")}
            </Link>
          )}
        </div>
        <div className="panel p-4">
          <div className="label">{t("krones.publicSite")}</div>
          <p className="mt-2 text-sm leading-relaxed text-[var(--muted)]">{t("krones.shopHint")}</p>
          <a href="/krones" className="btn btn-primary mt-3" target="_top">
            {t("krones.shop")}
          </a>
        </div>
      </div>

      {wallet && wallet.ledger.length > 1 && (
        <LedgerChart rows={wallet.ledger} label={t("krones.ledger")} locale={locale} />
      )}

      <div className="mb-6">
        <h2 className="mb-3 text-sm font-semibold">{t("krones.packs")}</h2>
        <p className="mb-3 text-sm text-[var(--muted)]">{t("krones.shopHint")}</p>
        <a href="/krones" className="btn btn-primary" target="_top">
          {t("krones.shop")}
        </a>
      </div>

      <h2 className="mb-3 text-sm font-semibold">{t("krones.ledger")}</h2>
      <div className="panel p-0">
        <Table>
          <thead>
            <tr>
              <Th>{t("krones.date")}</Th>
              <Th>{t("krones.type")}</Th>
              <Th>{t("krones.amount")}</Th>
              <Th>{t("krones.reason")}</Th>
              <Th>{t("krones.balance")}</Th>
            </tr>
          </thead>
          <tbody>
            {(wallet?.ledger ?? []).slice(0, 30).map((row) => (
              <tr key={row.id}>
                <Td>{new Date(row.at).toLocaleString(loc)}</Td>
                <Td>{row.type}</Td>
                <Td>{row.amount.toLocaleString(loc)}</Td>
                <Td>{row.reason}</Td>
                <Td>{row.balanceAfter.toLocaleString(loc)}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
        {(wallet?.ledger ?? []).length === 0 && (
          <p className="hint px-3 py-4">{t("krones.empty")}</p>
        )}
      </div>
    </div>
  );
}
