"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { RiskStatus } from "@/types";
import { Badge, Button, Card, ErrorNote, Input, Spinner } from "@/components/ui";

interface Providers {
  broker_provider: string;
  market_data_provider: string;
  ai_provider: string;
  alpaca_credentials_present: boolean;
  ai_key_present: boolean;
  live_trading_enabled: boolean;
}

const RISK_FIELDS: [string, string][] = [
  ["min_cash_reserve_pct", "Min cash reserve (fraction)"],
  ["max_invested_pct", "Max invested (fraction)"],
  ["max_daily_turnover_pct", "Max daily turnover (fraction)"],
  ["max_open_positions", "Max open positions"],
  ["max_new_capital_per_rebalance_pct", "Max new capital / rebalance"],
  ["max_position_pct", "Max position (fraction of equity)"],
  ["max_position_notional", "Max position ($)"],
  ["min_order_notional", "Min order ($)"],
  ["max_order_notional", "Max order ($)"],
  ["max_pct_of_avg_daily_volume", "Max fraction of ADV"],
  ["min_price", "Min price ($)"],
  ["daily_loss_limit_pct", "Daily loss limit (fraction)"],
  ["strategy_drawdown_limit_pct", "Drawdown limit (fraction)"],
  ["portfolio_volatility_limit", "Portfolio vol limit (ann.)"],
];

function UniverseCard() {
  const queryClient = useQueryClient();
  const universe = useQuery<{ symbols: string[] }>({
    queryKey: ["universe"],
    queryFn: () => api.get("/api/settings/universe"),
  });
  const [value, setValue] = useState("");
  useEffect(() => {
    if (universe.data) setValue(universe.data.symbols.join(", "));
  }, [universe.data]);

  const save = useMutation({
    mutationFn: (symbols: string[]) => api.put("/api/settings/universe", { symbols }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["universe"] }),
  });

  return (
    <Card title="Approved universe">
      <p className="mb-3 text-sm text-ink-muted">
        Only these symbols can ever be traded. The strategy and the risk engine both
        enforce this list.
      </p>
      <div className="flex gap-2">
        <Input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="SPY, QQQ, IWM…"
        />
        <Button
          onClick={() =>
            save.mutate(value.split(/[\s,]+/).map((s) => s.trim()).filter(Boolean))
          }
          disabled={save.isPending}
        >
          Save
        </Button>
      </div>
      {save.isError && (
        <div className="mt-2">
          <ErrorNote message={(save.error as Error).message} />
        </div>
      )}
    </Card>
  );
}

function RiskLimitsCard() {
  const queryClient = useQueryClient();
  const limits = useQuery<{ name: string; limits: Record<string, number | boolean> }>({
    queryKey: ["risk-limits"],
    queryFn: () => api.get("/api/settings/risk-limits"),
  });
  const [draft, setDraft] = useState<Record<string, string>>({});
  useEffect(() => {
    if (limits.data) {
      const next: Record<string, string> = {};
      for (const [key] of RISK_FIELDS) next[key] = String(limits.data.limits[key] ?? "");
      setDraft(next);
    }
  }, [limits.data]);

  const save = useMutation({
    mutationFn: (payload: Record<string, number>) =>
      api.put("/api/settings/risk-limits", payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["risk-limits"] }),
  });

  if (limits.isLoading) return <Spinner />;

  return (
    <Card title="Risk limits">
      <p className="mb-3 text-sm text-ink-muted">
        Conservative starting values — none are claimed to be optimal. Leverage and
        shorting cannot be enabled.
      </p>
      <div className="grid gap-3 md:grid-cols-2">
        {RISK_FIELDS.map(([key, label]) => (
          <label key={key} className="block text-sm">
            <span className="mb-1 block text-xs uppercase tracking-wider text-ink-muted">
              {label}
            </span>
            <Input
              type="number"
              step="any"
              value={draft[key] ?? ""}
              onChange={(e) => setDraft((d) => ({ ...d, [key]: e.target.value }))}
            />
          </label>
        ))}
      </div>
      <div className="mt-4 flex items-center gap-3">
        <Button
          onClick={() => {
            const payload: Record<string, number> = {};
            for (const [key] of RISK_FIELDS) {
              const parsed = Number(draft[key]);
              if (!Number.isNaN(parsed)) payload[key] = parsed;
            }
            save.mutate(payload);
          }}
          disabled={save.isPending}
        >
          Save limits
        </Button>
        {save.isSuccess && <Badge tone="good">Saved</Badge>}
      </div>
      {save.isError && (
        <div className="mt-2">
          <ErrorNote message={(save.error as Error).message} />
        </div>
      )}
    </Card>
  );
}

function ScheduleCard() {
  const paper = useQuery<{ rebalance_cron: string }>({
    queryKey: ["paper-status"],
    queryFn: () => api.get("/api/paper-trading/status"),
  });
  const [cron, setCron] = useState("");
  useEffect(() => {
    if (paper.data) setCron(paper.data.rebalance_cron);
  }, [paper.data]);
  const save = useMutation({
    mutationFn: () => api.put("/api/settings/schedule", { rebalance_cron: cron }),
  });

  return (
    <Card title="Rebalance schedule">
      <p className="mb-3 text-sm text-ink-muted">
        Cron expression (UTC). Default runs weekly on Monday at 15:00 UTC. The MVP is
        designed to rebalance at most weekly.
      </p>
      <div className="flex gap-2">
        <Input value={cron} onChange={(e) => setCron(e.target.value)} className="font-mono" />
        <Button onClick={() => save.mutate()} disabled={save.isPending}>
          Save
        </Button>
      </div>
      {save.isError && (
        <div className="mt-2">
          <ErrorNote message={(save.error as Error).message} />
        </div>
      )}
      {save.isSuccess && (
        <p className="mt-2 text-xs text-status-warning">
          Saved. Restart the backend for the scheduler to pick up the new cron.
        </p>
      )}
    </Card>
  );
}

function ProvidersCard() {
  const providers = useQuery<Providers>({
    queryKey: ["providers"],
    queryFn: () => api.get("/api/settings/providers"),
  });
  const test = useMutation({
    mutationFn: () =>
      api.post<{ ok: boolean; error?: string; is_paper?: boolean }>(
        "/api/broker/test-connection",
      ),
  });

  if (providers.isLoading) return <Spinner />;
  const p = providers.data;

  return (
    <Card title="Providers & credentials">
      <div className="space-y-2 text-sm">
        <div className="flex items-center justify-between">
          <span className="text-ink-secondary">Broker</span>
          <span>
            <Badge tone="info">{p?.broker_provider}</Badge>{" "}
            <Badge tone={p?.alpaca_credentials_present ? "good" : "neutral"}>
              {p?.alpaca_credentials_present ? "Alpaca paper keys set" : "no Alpaca keys"}
            </Badge>
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-ink-secondary">Market data</span>
          <Badge tone="info">{p?.market_data_provider}</Badge>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-ink-secondary">AI analysis</span>
          <span>
            <Badge tone="info">{p?.ai_provider}</Badge>{" "}
            <Badge tone={p?.ai_key_present ? "good" : "neutral"}>
              {p?.ai_key_present ? "API key set" : "no key (mock mode)"}
            </Badge>
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-ink-secondary">Live trading</span>
          <Badge tone="bad">permanently disabled</Badge>
        </div>
      </div>
      <p className="mt-3 text-xs text-ink-muted">
        Credentials are configured via environment variables (<code>.env</code>) and
        are never displayed or returned by the API. To use an Alpaca paper account,
        set <code>BROKER_PROVIDER=alpaca_paper</code>,{" "}
        <code>ALPACA_PAPER_API_KEY</code> and <code>ALPACA_PAPER_API_SECRET</code>,
        then restart the backend.
      </p>
      <div className="mt-3 flex items-center gap-3">
        <Button variant="secondary" onClick={() => test.mutate()} disabled={test.isPending}>
          Test broker connection
        </Button>
        {test.data &&
          (test.data.ok ? (
            <Badge tone="good">Connected (paper)</Badge>
          ) : (
            <Badge tone="bad">Failed: {test.data.error}</Badge>
          ))}
      </div>
    </Card>
  );
}

function RiskRecoveryCard() {
  const queryClient = useQueryClient();
  const risk = useQuery<RiskStatus>({
    queryKey: ["risk-status"],
    queryFn: () => api.get("/api/risk/status"),
  });
  const reactivate = useMutation({
    mutationFn: () => api.post("/api/risk/reactivate"),
    onSuccess: () => queryClient.invalidateQueries(),
  });

  if (!risk.data?.trading_frozen) return null;
  return (
    <Card title="Risk recovery">
      <ErrorNote
        message={`Trading is frozen: ${risk.data.frozen_reason || "risk event"}`}
      />
      <p className="my-3 text-sm text-ink-secondary">
        Review the risk events on the Activity page before reactivating. Reactivation
        is deliberate and manual.
      </p>
      <Button
        variant="danger"
        onClick={() => {
          if (window.confirm("Reactivate trading after reviewing the risk events?")) {
            reactivate.mutate();
          }
        }}
        disabled={reactivate.isPending}
      >
        Reactivate trading
      </Button>
    </Card>
  );
}

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight text-ink">Settings</h1>
      <RiskRecoveryCard />
      <UniverseCard />
      <RiskLimitsCard />
      <ScheduleCard />
      <ProvidersCard />
    </div>
  );
}
