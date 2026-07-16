"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { api, clearCsrfToken } from "@/lib/api";
import type { SystemStatus } from "@/types";
import {
  IconChartPie,
  IconFlask,
  IconGear,
  IconHome,
  IconLogout,
  IconPower,
  IconPulse,
  IconShield,
  IconTarget,
} from "@/components/icons";
import { Badge, Button } from "@/components/ui";

const NAV = [
  { href: "/", label: "Overview", icon: IconHome },
  { href: "/portfolio", label: "Portfolio", icon: IconChartPie },
  { href: "/strategy", label: "Strategy", icon: IconTarget },
  { href: "/backtests", label: "Backtests", icon: IconFlask },
  { href: "/activity", label: "Activity", icon: IconPulse },
  { href: "/settings", label: "Settings", icon: IconGear },
];

function KillSwitchBanner({ status }: { status: SystemStatus }) {
  const queryClient = useQueryClient();
  const deactivate = useMutation({
    mutationFn: () =>
      api.post("/api/kill-switch/deactivate", {
        reason: "Deactivated from dashboard banner",
      }),
    onSuccess: () => queryClient.invalidateQueries(),
  });
  if (!status.kill_switch_active) return null;
  return (
    <div className="sticky top-0 z-50 flex animate-fade-in items-center justify-between gap-4 border-b border-status-critical/50 bg-[#2a0f0f]/95 px-6 py-3 backdrop-blur">
      <div className="flex items-center gap-3 text-sm font-medium text-[#f2a1a1]">
        <span className="flex h-2.5 w-2.5">
          <span className="absolute inline-flex h-2.5 w-2.5 animate-ping rounded-full bg-status-critical opacity-60" />
          <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-status-critical" />
        </span>
        Kill switch active — all order submissions are blocked.
        {status.kill_switch_reason && (
          <span className="font-normal text-[#d98080]">
            {status.kill_switch_reason}
          </span>
        )}
      </div>
      <Button
        variant="secondary"
        onClick={() => deactivate.mutate()}
        disabled={deactivate.isPending}
      >
        Deactivate
      </Button>
    </div>
  );
}

function FrozenBanner({ status }: { status: SystemStatus }) {
  if (!status.trading_frozen) return null;
  return (
    <div className="animate-fade-in border-b border-status-warning/40 bg-[#2a230f]/90 px-6 py-2.5 text-sm text-status-warning backdrop-blur">
      Trading is frozen: {status.frozen_reason || "risk event"} — manual reactivation
      required in Settings.
    </div>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data: status } = useQuery<SystemStatus>({
    queryKey: ["system-status"],
    queryFn: () => api.get("/api/system/status"),
    refetchInterval: 15_000,
    enabled: pathname !== "/login",
  });

  const killSwitch = useMutation({
    mutationFn: () =>
      api.post("/api/kill-switch/activate", {
        reason: "Activated from dashboard sidebar",
      }),
    onSuccess: () => queryClient.invalidateQueries(),
  });

  if (pathname === "/login") return <>{children}</>;

  return (
    <div className="min-h-screen">
      {status && <KillSwitchBanner status={status} />}
      {status && <FrozenBanner status={status} />}
      <div className="flex">
        <aside className="sticky top-0 flex h-screen w-60 shrink-0 flex-col border-r border-edge bg-panel/60 px-4 py-5 backdrop-blur-md">
          {/* Brand */}
          <div className="mb-7 px-2">
            <div className="flex items-center gap-2.5">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-accent-500 to-accent-700 text-white shadow-glow">
                <IconShield className="h-5 w-5" />
              </div>
              <div>
                <div className="text-[15px] font-semibold tracking-tight text-ink">
                  AegisInvest
                </div>
                <div className="-mt-0.5 text-[11px] font-medium tracking-wide text-ink-muted">
                  AI RESEARCH
                </div>
              </div>
            </div>
            <div className="mt-3.5 flex items-center gap-1.5">
              <Badge tone="info">Paper</Badge>
              {status?.market_open != null && (
                <Badge tone={status.market_open ? "good" : "neutral"}>
                  {status.market_open ? "Market open" : "Closed"}
                </Badge>
              )}
            </div>
          </div>

          {/* Nav */}
          <nav className="flex flex-col gap-0.5">
            {NAV.map((item) => {
              const active = pathname === item.href;
              const Icon = item.icon;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={clsx(
                    "group relative flex items-center gap-3 rounded-lg px-3 py-2 text-sm",
                    "transition-all duration-150",
                    active
                      ? "bg-white/[0.07] font-medium text-ink"
                      : "text-ink-muted hover:bg-white/[0.04] hover:text-ink-secondary",
                  )}
                >
                  <span
                    className={clsx(
                      "absolute left-0 top-1/2 h-4 w-0.5 -translate-y-1/2 rounded-full bg-accent-500",
                      "transition-all duration-200",
                      active ? "opacity-100" : "opacity-0 group-hover:opacity-40",
                    )}
                  />
                  <Icon
                    className={clsx(
                      "h-[18px] w-[18px] transition-colors",
                      active ? "text-accent-400" : "text-ink-muted group-hover:text-ink-secondary",
                    )}
                  />
                  {item.label}
                </Link>
              );
            })}
          </nav>

          {/* Footer actions */}
          <div className="mt-auto space-y-2">
            {!status?.kill_switch_active && (
              <button
                onClick={() => {
                  if (
                    window.confirm(
                      "Activate the kill switch? All order submissions will be blocked and scheduled trading disabled.",
                    )
                  ) {
                    killSwitch.mutate();
                  }
                }}
                className={clsx(
                  "flex w-full items-center gap-3 rounded-lg border border-status-critical/30 px-3 py-2",
                  "text-sm font-medium text-[#f28b8b] transition-all duration-150",
                  "hover:border-status-critical/60 hover:bg-status-critical/10 active:scale-[0.98]",
                )}
              >
                <IconPower className="h-[18px] w-[18px]" />
                Kill switch
              </button>
            )}
            <button
              className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-ink-muted transition-colors hover:bg-white/[0.04] hover:text-ink-secondary"
              onClick={async () => {
                await api.post("/api/auth/logout");
                clearCsrfToken();
                router.replace("/login");
              }}
            >
              <IconLogout className="h-[18px] w-[18px]" />
              Sign out
            </button>
            <p className="px-3 pt-1 text-[10px] leading-relaxed text-ink-muted/70">
              Educational software. Paper trading only — not investment advice; no
              strategy is guaranteed to be profitable.
            </p>
          </div>
        </aside>

        <main className="min-w-0 flex-1 px-8 py-7">
          <div key={pathname} className="page-enter mx-auto max-w-6xl">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
