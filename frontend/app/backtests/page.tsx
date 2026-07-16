"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { api } from "@/lib/api";
import { dt, num, pct } from "@/lib/format";
import type { BacktestDetail, BacktestSummary, EquityPoint, TradeRow } from "@/types";
import { DrawdownChart, EquityChart } from "@/components/charts";
import { Badge, Button, Card, ErrorNote, Input, Spinner, Table } from "@/components/ui";

const formSchema = z.object({
  start: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Use YYYY-MM-DD"),
  end: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, "Use YYYY-MM-DD"),
  starting_capital: z.coerce.number().positive("Must be positive"),
  universe: z.string().min(1, "At least one symbol"),
  benchmark_symbol: z.string().min(1),
  rebalance_frequency: z.enum(["weekly", "monthly"]),
  commission_per_trade: z.coerce.number().min(0),
  spread_bps: z.coerce.number().min(0),
  slippage_bps: z.coerce.number().min(0),
});

type FormValues = z.infer<typeof formSchema>;

const METRIC_LABELS: [string, string, "pct" | "num"][] = [
  ["total_return", "Total return", "pct"],
  ["annualized_return", "Annualized return", "pct"],
  ["annualized_volatility", "Volatility (ann.)", "pct"],
  ["sharpe_ratio", "Sharpe", "num"],
  ["sortino_ratio", "Sortino", "num"],
  ["max_drawdown", "Max drawdown", "pct"],
  ["calmar_ratio", "Calmar", "num"],
  ["win_rate", "Win rate", "pct"],
  ["profit_factor", "Profit factor", "num"],
  ["turnover", "Turnover", "num"],
  ["number_of_trades", "Trades", "num"],
  ["average_holding_period_days", "Avg holding (days)", "num"],
  ["best_month", "Best month", "pct"],
  ["worst_month", "Worst month", "pct"],
  ["pct_time_invested", "Time invested", "pct"],
  ["benchmark_return", "Benchmark return", "pct"],
  ["excess_return", "Excess return", "pct"],
  ["tracking_error", "Tracking error", "pct"],
  ["beta", "Beta", "num"],
  ["alpha_annualized", "Alpha (ann.)", "pct"],
];

function BacktestForm({ onCreated }: { onCreated: (id: string) => void }) {
  const queryClient = useQueryClient();
  const today = new Date();
  const yearAgo = new Date(today.getTime() - 365 * 864e5);
  const iso = (d: Date) => d.toISOString().slice(0, 10);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      start: iso(yearAgo),
      end: iso(new Date(today.getTime() - 864e5)),
      starting_capital: 100000,
      universe: "SPY, QQQ, IWM, EFA, AGG, GLD, VNQ, XLE",
      benchmark_symbol: "SPY",
      rebalance_frequency: "weekly",
      commission_per_trade: 0,
      spread_bps: 2,
      slippage_bps: 5,
    },
  });

  const create = useMutation({
    mutationFn: (payload: FormValues) =>
      api.post<{ id: string }>("/api/backtests", {
        ...payload,
        universe: payload.universe
          .split(/[\s,]+/)
          .map((s) => s.trim().toUpperCase())
          .filter(Boolean),
        benchmark_symbol: payload.benchmark_symbol.toUpperCase(),
        strategy_name: "weekly_multi_factor_trend",
      }),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["backtests"] });
      onCreated(result.id);
    },
  });

  const field = (label: string, name: keyof FormValues, type = "text") => (
    <label className="block text-sm">
      <span className="mb-1 block text-xs uppercase tracking-wider text-ink-muted">
        {label}
      </span>
      <Input type={type} step="any" {...register(name)} />
      {errors[name] && (
        <span className="text-xs text-delta-down">{String(errors[name]?.message)}</span>
      )}
    </label>
  );

  return (
    <Card title="Run a backtest">
      <form
        onSubmit={handleSubmit((values) => create.mutate(values))}
        className="grid gap-3 md:grid-cols-3"
      >
        {field("Start date", "start")}
        {field("End date", "end")}
        {field("Starting capital ($)", "starting_capital", "number")}
        <label className="block text-sm md:col-span-2">
          <span className="mb-1 block text-xs uppercase tracking-wider text-ink-muted">
            Universe (comma-separated symbols)
          </span>
          <Input {...register("universe")} />
          {errors.universe && (
            <span className="text-xs text-delta-down">{String(errors.universe.message)}</span>
          )}
        </label>
        {field("Benchmark", "benchmark_symbol")}
        <label className="block text-sm">
          <span className="mb-1 block text-xs uppercase tracking-wider text-ink-muted">
            Rebalance
          </span>
          <select
            {...register("rebalance_frequency")}
            className="w-full rounded-lg border border-edge bg-black/30 px-3.5 py-2 text-sm text-ink transition-colors duration-150 hover:border-edge-strong focus:border-accent-500 focus:outline-none focus:ring-2 focus:ring-accent-500/25"
          >
            <option value="weekly">Weekly</option>
            <option value="monthly">Monthly</option>
          </select>
        </label>
        {field("Commission/trade ($)", "commission_per_trade", "number")}
        {field("Spread (bps)", "spread_bps", "number")}
        {field("Slippage (bps)", "slippage_bps", "number")}
        <div className="flex items-end md:col-span-2">
          <Button type="submit" disabled={create.isPending}>
            {create.isPending ? "Running backtest…" : "Run backtest"}
          </Button>
        </div>
      </form>
      {create.isError && (
        <div className="mt-3">
          <ErrorNote message={(create.error as Error).message} />
        </div>
      )}
    </Card>
  );
}

function BacktestResults({ id }: { id: string }) {
  const detail = useQuery<BacktestDetail>({
    queryKey: ["backtest", id],
    queryFn: () => api.get(`/api/backtests/${id}`),
  });
  const equity = useQuery<EquityPoint[]>({
    queryKey: ["backtest-equity", id],
    queryFn: () => api.get(`/api/backtests/${id}/equity`),
  });
  const trades = useQuery<TradeRow[]>({
    queryKey: ["backtest-trades", id],
    queryFn: () => api.get(`/api/backtests/${id}/trades`),
  });
  const [showAllTrades, setShowAllTrades] = useState(false);

  if (detail.isLoading || equity.isLoading) return <Spinner />;
  if (!detail.data) return null;
  const metrics = detail.data.metrics ?? {};
  const tradeRows = showAllTrades ? trades.data ?? [] : (trades.data ?? []).slice(0, 25);

  return (
    <div className="space-y-4">
      {detail.data.warnings.length > 0 && (
        <Card title="Warnings">
          <ul className="list-inside list-disc space-y-1 text-sm text-status-warning">
            {detail.data.warnings.map((warning, i) => (
              <li key={i}>{warning}</li>
            ))}
          </ul>
        </Card>
      )}
      <Card
        title="Equity curve vs benchmark"
        actions={
          <a
            href={`/api/backtests/${id}/trades?export=csv`}
            className="text-xs text-accent-400 hover:underline"
          >
            Export trades CSV
          </a>
        }
      >
        <EquityChart data={equity.data ?? []} />
      </Card>
      <Card title="Drawdown">
        <DrawdownChart data={equity.data ?? []} />
      </Card>
      <Card title="Performance statistics">
        <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm md:grid-cols-4">
          {METRIC_LABELS.map(([key, label, kind]) => (
            <div key={key} className="flex justify-between border-b border-edge/40 py-1">
              <span className="text-ink-muted">{label}</span>
              <span className="font-medium text-ink-secondary">
                {kind === "pct" ? pct(metrics[key]) : num(metrics[key])}
              </span>
            </div>
          ))}
        </div>
      </Card>
      <Card title={`Trades (${trades.data?.length ?? 0})`}>
        <Table headers={["Date", "Symbol", "Side", "Qty", "Price", "Commission", "Reason"]}>
          {tradeRows.map((t, i) => (
            <tr key={i}>
              <td className="px-2 py-1.5">{t.date}</td>
              <td className="px-2 py-1.5 font-semibold">{t.symbol}</td>
              <td className="px-2 py-1.5">
                <Badge tone={t.side === "buy" ? "good" : "bad"}>{t.side}</Badge>
              </td>
              <td className="px-2 py-1.5">{num(t.quantity, 4)}</td>
              <td className="px-2 py-1.5">{num(t.price)}</td>
              <td className="px-2 py-1.5">{num(t.commission)}</td>
              <td className="px-2 py-1.5 text-xs text-ink-muted">{t.reason}</td>
            </tr>
          ))}
        </Table>
        {(trades.data?.length ?? 0) > 25 && (
          <Button
            variant="secondary"
            className="mt-3"
            onClick={() => setShowAllTrades((v) => !v)}
          >
            {showAllTrades ? "Show fewer" : `Show all ${trades.data?.length}`}
          </Button>
        )}
      </Card>
    </div>
  );
}

export default function BacktestsPage() {
  const [selected, setSelected] = useState<string | null>(null);
  const listing = useQuery<BacktestSummary[]>({
    queryKey: ["backtests"],
    queryFn: () => api.get("/api/backtests"),
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight text-ink">Backtests</h1>
      <p className="max-w-3xl text-sm text-ink-muted">
        Backtests are educational simulations against historical (or synthetic mock)
        data. Past performance — simulated or real — does not guarantee future
        results.
      </p>
      <BacktestForm onCreated={setSelected} />

      <Card title="Previous runs">
        {listing.isLoading ? (
          <Spinner />
        ) : (listing.data ?? []).length === 0 ? (
          <p className="py-4 text-sm text-ink-muted">No backtests yet.</p>
        ) : (
          <Table headers={["Created", "Strategy", "Status", "Total return", "Max DD", ""]}>
            {(listing.data ?? []).map((run) => (
              <tr key={run.id}>
                <td className="px-2 py-2">{dt(run.created_at)}</td>
                <td className="px-2 py-2">
                  {run.strategy_name}{" "}
                  <span className="text-ink-muted">v{run.strategy_version}</span>
                </td>
                <td className="px-2 py-2">
                  <Badge tone={run.status === "completed" ? "good" : "bad"}>
                    {run.status}
                  </Badge>
                </td>
                <td className="px-2 py-2">{pct(run.total_return)}</td>
                <td className="px-2 py-2">{pct(run.max_drawdown)}</td>
                <td className="px-2 py-2">
                  <button
                    className="text-accent-400 hover:underline"
                    onClick={() => setSelected(run.id)}
                  >
                    View
                  </button>
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      {selected && <BacktestResults id={selected} />}
    </div>
  );
}
