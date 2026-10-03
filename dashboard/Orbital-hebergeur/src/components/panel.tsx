"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import {
  Activity,
  Bot,
  Boxes,
  Coins,
  Database,
  Gauge,
  Globe,
  HardDrive,
  KeyRound,
  Languages,
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  Plus,
  Server,
  Shield,
  Sun,
} from "lucide-react";
import { api, STATE_COLORS } from "@/lib/client";
import { explainError } from "@/lib/errors";
import { useEngineStatus } from "@/lib/engine-status";
import { useI18n, useT, LOCALES, type Locale } from "@/lib/i18n";
import { useTheme, type Theme } from "@/lib/theme";
import { useCreationFlags } from "@/lib/use-creation-flags";
import { firstCreateHref } from "@/lib/services/creation-flags";

export function Logo({ size = 22 }: { size?: number }) {
  return (
    <img
      src="/logo/Synk_2B9348.png"
      alt="Synkrone"
      width={size}
      height={size}
      draggable={false}
      style={{ borderRadius: 6, objectFit: "contain", background: "var(--panel-2)" }}
    />
  );
}

const LIVE_STATES = new Set(["RUNNING", "STARTING", "RESTARTING"]);

function badgeVariant(state: string): string {
  if (state === "RUNNING") return "badge-success";
  if (state === "STARTING" || state === "RESTARTING" || state === "STOPPING" || state === "CREATING" || state === "SUSPENDED")
    return "badge-warning";
  if (state === "CRASHED" || state === "ERROR" || state === "DELETING") return "badge-danger";
  return "";
}

export function StateBadge({ state, live }: { state: string; live?: boolean }) {
  const t = useT();
  const label = t(`state.${state}`);
  return (
    <span
      className={`badge ${badgeVariant(state)} ${live ?? LIVE_STATES.has(state) ? "badge-live" : ""}`}
      title={state}
    >
      <span className="dot" style={{ color: STATE_COLORS[state] ?? "#8fa096" }} />
      {label === `state.${state}` ? state : label}
    </span>
  );
}

/** Backwards-compatible alias: coloured dot + translated state label. */
export function StateDot({ state }: { state: string }) {
  return <StateBadge state={state} />;
}

export function TypeIcon({ type, size = 16 }: { type: string; size?: number }) {
  if (type === "discord") return <Bot size={size} />;
  if (type === "minecraft") return <Boxes size={size} />;
  return <Globe size={size} />;
}

export function LanguageSelector() {
  const { locale, setLocale, t } = useI18n();
  return (
    <div className="flex items-center gap-1 rounded-lg border border-[var(--line)] bg-[var(--panel-2)] p-0.5">
      <Languages size={13} className="ml-1.5 shrink-0 text-[var(--muted)]" />
      {LOCALES.map((l: Locale) => (
        <button
          key={l}
          type="button"
          onClick={() => setLocale(l)}
          aria-pressed={locale === l}
          title={t(`language.${l}`)}
          className="rounded-md px-2 py-1 text-[11px] font-semibold tracking-wide transition"
          style={{
            background: locale === l ? "var(--accent)" : "transparent",
            color: locale === l ? "#fff" : "var(--muted)",
          }}
        >
          {l}
        </button>
      ))}
    </div>
  );
}

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const t = useT();
  const options: { id: Theme; label: string; Icon: typeof Sun }[] = [
    { id: "light", label: t("theme.light"), Icon: Sun },
    { id: "dark", label: t("theme.dark"), Icon: Moon },
  ];
  return (
    <div
      className="flex items-center gap-1 rounded-lg border border-[var(--line)] bg-[var(--panel-2)] p-0.5"
      role="group"
      aria-label={t("theme.label")}
    >
      {options.map(({ id, label, Icon }) => (
        <button
          key={id}
          type="button"
          onClick={() => setTheme(id)}
          aria-pressed={theme === id}
          title={label}
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-semibold tracking-wide transition"
          style={{
            background: theme === id ? "var(--accent)" : "transparent",
            color: theme === id ? "#fff" : "var(--muted)",
          }}
        >
          <Icon size={13} strokeWidth={1.5} />
          {label}
        </button>
      ))}
    </div>
  );
}

type WalletSummary = {
  balance: number;
  unlimited?: boolean;
  lowBalance?: boolean;
  privilege?: string | null;
};

function useWalletSummary() {
  const [wallet, setWallet] = useState<WalletSummary | null>(null);
  useEffect(() => {
    let stop = false;
    const load = () => {
      void api<WalletSummary>("/api/krones", { silent: true })
        .then((w) => {
          if (!stop) setWallet(w);
        })
        .catch(() => undefined);
    };
    load();
    const t = setInterval(load, 20000);
    return () => {
      stop = true;
      clearInterval(t);
    };
  }, []);
  return wallet;
}

export function ShopKronesLink({
  className,
  children,
}: {
  className?: string;
  children?: React.ReactNode;
}) {
  const t = useT();
  return (
    <a href="/krones" className={className || "btn btn-primary"} target="_top">
      {children || t("krones.shop")}
    </a>
  );
}

function KronesPill() {
  const t = useT();
  const wallet = useWalletSummary();
  const label = wallet?.unlimited ? t("krones.unlimited") : `${(wallet?.balance ?? 0).toLocaleString("fr-FR")} ₭`;
  return (
    <Link href="/dashboard/krones" className="badge badge-gold w-full justify-center">
      {label}
    </Link>
  );
}

export function LowBalanceBanner() {
  const t = useT();
  const wallet = useWalletSummary();
  if (!wallet || wallet.unlimited || !wallet.lowBalance) return null;
  return (
    <div
      className="rounded-lg border px-3 py-2 text-xs"
      style={{
        borderColor: "rgba(184, 130, 61, 0.45)",
        background: "rgba(184, 130, 61, 0.14)",
        color: "#e3b675",
      }}
      role="status"
    >
      <div className="font-semibold">{t("krones.lowBalance")}</div>
      <ShopKronesLink className="btn mt-2 w-full justify-center" />
    </div>
  );
}

function EngineStatusPill() {
  const t = useT();
  const engine = useEngineStatus();

  if (!engine) return null;
  return (
    <div
      className={`badge w-full justify-center ${engine.reachable ? "badge-success" : "badge-danger"}`}
      title={engine.reachable ? t("engine.online") : t("engine.offline")}
    >
      <span className="dot" />
      {engine.reachable ? t("engine.online") : t("engine.offline")}
    </div>
  );
}

function navItemActive(
  href: string,
  pathname: string,
  searchParams: { get: (key: string) => string | null },
) {
  const [path, query] = href.split("?");
  const wantedType = query ? new URLSearchParams(query).get("type") : null;
  const currentType = searchParams.get("type");
  if (wantedType) return pathname === path && currentType === wantedType;
  if (path === "/dashboard/services") return pathname === path && !currentType;
  return pathname === path;
}

export function Sidebar({
  user,
  open = false,
  onNavigate,
}: {
  user: { name: string; email: string };
  open?: boolean;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const t = useT();
  const flags = useCreationFlags();
  const createHref = firstCreateHref(flags);

  const NAV = [
    { section: null, items: [{ href: "/dashboard", label: t("nav.dashboard"), icon: LayoutDashboard }] },
    {
      section: t("nav.projects"),
      items: [
        { href: "/dashboard/services", label: t("nav.allServices"), icon: Server },
        ...(createHref ? [{ href: createHref, label: t("nav.newService"), icon: Plus }] : []),
        { href: "/dashboard/krones", label: t("nav.krones"), icon: Coins },
      ],
    },
    {
      section: t("nav.account"),
      items: [
        { href: "/dashboard/account/profile", label: t("nav.profile"), icon: Activity },
        { href: "/dashboard/account/api-keys", label: t("nav.apiKeys"), icon: KeyRound },
        { href: "/dashboard/account/audit", label: t("nav.auditLog"), icon: Shield },
      ],
    },
    {
      section: t("nav.advanced"),
      items: [
        { href: "/dashboard/services?type=discord", label: t("nav.discord"), icon: Bot },
        { href: "/dashboard/services?type=minecraft", label: t("nav.minecraft"), icon: Boxes },
        { href: "/dashboard/services?type=web", label: t("nav.web"), icon: Globe },
        { href: "/dashboard/infrastructure/databases", label: t("nav.databases"), icon: Database },
        { href: "/dashboard/infrastructure/sftp", label: t("nav.sftp"), icon: HardDrive },
        { href: "/dashboard/infrastructure/engine", label: t("nav.engine"), icon: Gauge },
      ],
    },
  ];

  return (
    <aside
      className={`fixed inset-y-0 left-0 z-50 flex w-60 shrink-0 flex-col border-r border-[var(--line)] bg-[var(--panel)] transition-transform md:static md:translate-x-0 ${
        open ? "translate-x-0" : "-translate-x-full"
      }`}
    >
      <div className="flex items-center gap-2.5 border-b border-[var(--line)] px-4 py-4">
        <Logo />
        <div className="min-w-0 flex-1">
          <div className="font-serif text-lg font-bold leading-none tracking-tight">Synkrone</div>
          <div className="text-[11px] text-[var(--muted)]">
            {t("nav.tagline")}
          </div>
        </div>
      </div>
      <div className="border-b border-[var(--line)] px-3 py-2">
        <a
          href="/"
          target="_top"
          className="flex items-center gap-2 rounded-lg px-3 py-2 text-[13px] text-[var(--muted)] transition hover:bg-[var(--panel-2)] hover:text-[var(--text)]"
        >
          <Globe size={15} />
          {t("nav.publicSite")}
        </a>
      </div>
      <nav className="scroll flex-1 overflow-y-auto px-2 py-3 text-sm">
        {NAV.map((group, i) => (
          <div key={i} className="mb-3">
            {group.section && (
              <div className="px-3 pb-1 text-[11px] font-medium text-[var(--muted)]">
                {group.section}
              </div>
            )}
            {group.items.map((item) => {
              const active = navItemActive(item.href, pathname, searchParams);
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={onNavigate}
                  className="flex items-center gap-2 rounded-lg px-3 py-2 text-[13px] transition"
                  style={{
                    background: active ? "var(--panel-2)" : "transparent",
                    color: active ? "var(--text)" : "var(--muted)",
                    borderLeft: active
                      ? "2px solid var(--accent)"
                      : "2px solid transparent",
                  }}
                >
                  <Icon size={15} />
                  {item.label}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>
      <div className="space-y-2 border-t border-[var(--line)] p-3">
        <KronesPill />
        <LowBalanceBanner />
        <EngineStatusPill />
        <div className="min-w-0 truncate text-xs text-[var(--muted)]" title={user.email}>
          {user.email}
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <ThemeToggle />
          <LanguageSelector />
        </div>
        <button
          className="btn w-full justify-center"
          onClick={async () => {
            await api("/api/auth/logout", { method: "POST", silent: true });
            router.push("/login");
            router.refresh();
          }}
        >
          <LogOut size={14} /> {t("nav.signOut")}
        </button>
      </div>
    </aside>
  );
}

export function DashboardShell({
  user,
  children,
}: {
  user: { name: string; email: string };
  children: React.ReactNode;
}) {
  const t = useT();
  const [open, setOpen] = useState(false);
  return (
    <div className="flex h-[100dvh] flex-col overflow-hidden md:flex-row">
      <header className="space-y-2 border-b border-[var(--line)] bg-[var(--panel)] px-3 py-2 md:hidden">
        <div className="flex items-center justify-between gap-2">
          <button type="button" className="btn" onClick={() => setOpen(true)} aria-expanded={open}>
            <Menu size={16} /> Menu
          </button>
          <KronesPill />
        </div>
        <LowBalanceBanner />
      </header>
      {open && (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          aria-label={t("common.close")}
          onClick={() => setOpen(false)}
        />
      )}
      <Suspense fallback={null}>
        <Sidebar user={user} open={open} onNavigate={() => setOpen(false)} />
      </Suspense>
      <div className="scroll min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-[1600px] px-4 py-4 md:px-6 md:py-6 xl:px-8">{children}</div>
      </div>
    </div>
  );
}

export function EngineBanner() {
  const t = useT();
  const engine = useEngineStatus();

  if (!engine || engine.reachable) return null;
  return (
    <div
      className="mb-4 rounded-xl border px-4 py-3 text-xs"
      style={{
        borderColor: "rgba(168, 70, 47, 0.45)",
        background: "rgba(168, 70, 47, 0.14)",
        color: "var(--danger)",
      }}
      role="alert"
    >
      <b>{t("engine.bannerTitle")}</b> {engine.error}
      <div className="mt-1 text-[var(--muted)]">{t("engine.bannerBody")}</div>
    </div>
  );
}

export function Stat({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div className="panel px-4 py-3">
      <div className="label">{label}</div>
      <div className="mt-1 text-xl font-bold">{value}</div>
      {sub && <div className="text-xs text-[var(--muted)]">{sub}</div>}
    </div>
  );
}

export function Bar({ value, max }: { value: number; max: number }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-sm bg-[var(--panel-3)]">
      <div
        className="h-full rounded-sm transition-[width] duration-500"
        style={{
          width: `${pct}%`,
          background: pct > 85 ? "var(--danger)" : "var(--accent)",
        }}
      />
    </div>
  );
}

/** Inline form error, run through explainError so causes and fixes are readable. */
export function ErrorText({ error }: { error: string | null }) {
  const { locale } = useI18n();
  if (!error) return null;
  const explained = explainError(error, locale);
  return (
    <div
      className="rounded-lg border px-3 py-2 text-xs"
      style={{
        borderColor: "rgba(168, 70, 47, 0.45)",
        background: "rgba(168, 70, 47, 0.14)",
        color: "var(--danger)",
      }}
      role="alert"
    >
      <div className="font-semibold">{explained.title}</div>
      <div className="mt-0.5 opacity-90">{explained.explanation}</div>
      {explained.action && <div className="mt-1 text-[var(--text)]">{explained.action}</div>}
      {/INSUFFICIENT_KRONES|Solde insuffisant|COMMAND_SOURCES_LOCKED/i.test(error) && (
        <ShopKronesLink className="btn btn-primary mt-2" />
      )}
    </div>
  );
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden="true" />;
}

/** One-time secret display (API keys, connection strings) with copy button. */
export function SecretBanner({
  label,
  value,
  onClose,
}: {
  label: string;
  value: string;
  onClose: () => void;
}) {
  const t = useT();
  const [copied, setCopied] = useState(false);
  return (
    <div
      className="mb-3 rounded-lg border px-3 py-2"
      style={{
        borderColor: "rgba(63, 107, 82, 0.45)",
        background: "rgba(63, 107, 82, 0.16)",
      }}
      role="status"
    >
      <div className="mb-1 text-[11px] font-semibold text-[var(--success)]">
        {label}
      </div>
      <div className="flex items-center gap-2">
        <code className="scroll min-w-0 flex-1 overflow-x-auto whitespace-nowrap font-mono text-xs text-[#9ad1af]">
          {value}
        </code>
        <button
          className="btn shrink-0 px-2 py-1 text-[11px]"
          onClick={async () => {
            await navigator.clipboard.writeText(value).catch(() => undefined);
            setCopied(true);
            setTimeout(() => setCopied(false), 1500);
          }}
        >
          {copied ? t("common.copied") : t("common.copy")}
        </button>
        <button className="btn btn-ghost shrink-0 px-2 py-1 text-[11px]" onClick={onClose}>
          {t("common.close")}
        </button>
      </div>
    </div>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  hint,
  action,
  compact = false,
}: {
  icon?: typeof Server;
  title: string;
  hint?: string;
  action?: React.ReactNode;
  /** Render inside an existing panel: no border, reduced padding. */
  compact?: boolean;
}) {
  return (
    <div
      className={`flex flex-col items-center justify-center gap-2 text-center ${
        compact ? "px-6 py-8" : "panel px-6 py-12"
      }`}
    >
      {Icon && (
        <div
          className={`flex items-center justify-center rounded-full ${compact ? "h-9 w-9" : "mb-1 h-11 w-11"}`}
          style={{ background: "var(--panel-2)", color: "var(--accent)" }}
        >
          <Icon size={compact ? 16 : 20} />
        </div>
      )}
      <div className="text-sm font-semibold">{title}</div>
      {hint && <div className="hint max-w-sm">{hint}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
