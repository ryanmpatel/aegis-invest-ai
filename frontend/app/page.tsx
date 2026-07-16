"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { dt, money, pct, plClass } from "@/lib/format";
import type { DashboardSummary, PaperStatus, RiskStatus, SystemStatus } from "@/types";
import { Badge, Button, Card, ErrorNote, Spinner, Stat } from "@/components/ui";

export default function OverviewPage() {
  const queryClient = useQueryClient();
  const summary = useQuery<DashboardSummary>({
    queryKey: ["dashboard-summary"],
    queryFn: () => api.get("/api/dashboard/summary"),
  });
  const system = useQuery<SystemStatus>({
    queryKey: ["system-status"],
    queryFn: () => api.get("/api/system/status"),
  });
  const paper = useQuery<PaperStatus>({
    queryKey: ["paper-status"],
    queryFn: () => api.get("/api/paper-trading/status"),
  });
  const risk = useQuery<RiskStatus>({
    queryKey: ["risk-status"],
    queryFn: () => api.get("/api/risk/status"),
  });

  const runOnce = useMutation({
    mutationFn: () => api.post("/api/paper-trading/run-once"),
    onSuccess: () => queryClient.invalidateQueries(),
  });
  const toggleScheduler = useMutation({
    mutationFn: (enable: boolean) =>
      api.post(`/api/paper-trading/${enable ? "start" : "stop"}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["paper-status"] }),
  });

  if (summary.isLoading) return <Spinner />;

  const s = summary.data;
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Overview</h1>
        <div className="flex items-center gap-2">
          <Button
            onClick={() => {
              if (
                window.confirm(
                  "Run one paper-trading rebalance now? Simulated orders may be submitted to the paper account.",
                )
              ) {
                runOnce.mutate();
              }
            }}
            disabled={runOnce.isPending || system.data?.kill_switch_active}
          >
            {runOnce.isPending ? "Running…" : "Run rebalance once"}
          </Button>
          {paper.data && (
            <Button
              variant="secondary"
              onClick={() => toggleScheduler.mutate(!paper.data!.enabled)}
              disabled={toggleScheduler.isPending}
            >
              {paper.data.enabled ? "Stop scheduled trading" : "Start scheduled trading"}
            </Button>
          )}
        </div>
      </div>

      {runOnce.isError && (
        <ErrorNote message={`Rebalance failed: ${(runOnce.error as Error).message}`} />
      )}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Paper account value" value={money(s?.equity)} />
        <Stat label="Cash" value={money(s?.cash)} />
        <Stat label="Buying power" value={money(s?.buying_power)} />
        <Stat
          label="Current drawdown"
          value={pct(s?.current_drawdown)}
          tone={s?.current_drawdown && s.current_drawdown < -0.05 ? "warn" : "default"}
        />
        <Stat
          label="Daily P/L"
          value={<span className={plClass(s?.daily_pl)}>{money(s?.daily_pl)}</span>}
          sub={pct(s?.daily_pl_pct)}
        />
        <Stat
          label="Total P/L"
          value={<span className={plClass(s?.total_pl)}>{money(s?.total_pl)}</span>}
          sub={pct(s?.total_pl_pct)}
        />
        <Stat
          label="Trading status"
          value={
            system.data?.kill_switch_active ? (
              <Badge tone="bad">Kill switch</Badge>
            ) : system.data?.trading_frozen ? (
              <Badge tone="warn">Frozen</Badge>
            ) : paper.data?.enabled ? (
              <Badge tone="good">Scheduled</Badge>
            ) : (
              <Badge>Manual</Badge>
            )
          }
          sub={
            system.data?.next_scheduled_run
              ? `Next run: ${dt(system.data.next_scheduled_run)}`
              : "No scheduled run"
          }
        />
        <Stat
          label="Broker"
          value={
            s?.broker_reachable ? (
              <Badge tone="good">Connected</Badge>
            ) : (
              <Badge tone="bad">Unreachable</Badge>
            )
          }
          sub={`${system.data?.broker_provider ?? "—"} (paper)`}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Active strategy">
          {s?.active_strategy ? (
            <div className="space-y-1 text-sm">
              <div className="text-base font-semibold text-ink">
                {s.active_strategy.name}{" "}
                <span className="text-ink-muted">v{s.active_strategy.version}</span>
              </div>
              <div className="text-ink-secondary">
                Last run: {s.active_strategy.last_run_status} at{" "}
                {dt(s.active_strategy.last_run_at)}
              </div>
            </div>
          ) : (
            <p className="text-sm text-ink-muted">
              No strategy has run yet. Use “Run rebalance once” or run a backtest.
            </p>
          )}
        </Card>
        <Card title="Risk status">
          {risk.data ? (
            <div className="space-y-2 text-sm">
              <div className="flex gap-2">
                <Badge tone={risk.data.kill_switch_active ? "bad" : "good"}>
                  Kill switch {risk.data.kill_switch_active ? "ACTIVE" : "inactive"}
                </Badge>
                <Badge tone={risk.data.trading_frozen ? "warn" : "good"}>
                  {risk.data.trading_frozen ? "Trading frozen" : "Trading allowed"}
                </Badge>
              </div>
              {risk.data.open_critical_events.length > 0 ? (
                <ul className="space-y-1 text-[#f2a1a1]">
                  {risk.data.open_critical_events.map((event, i) => (
                    <li key={i}>
                      <span className="font-mono text-xs">{event.rule_name}</span>:{" "}
                      {event.message}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-ink-muted">No open critical risk events.</p>
              )}
            </div>
          ) : (
            <Spinner />
          )}
        </Card>
      </div>

      <p className="text-xs text-ink-muted/70">
        AegisInvest AI is educational software operating in paper-trading mode only.
        Nothing shown here is investment advice, and no strategy is guaranteed to be
        profitable.
      </p>
    </div>
  );
}
