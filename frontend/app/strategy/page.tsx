"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { num } from "@/lib/format";
import type { Signal, TargetInfo } from "@/types";
import { Badge, Button, Card, ErrorNote, Spinner, Table } from "@/components/ui";

interface StrategyList {
  available_engines: string[];
  strategies: {
    id: string;
    name: string;
    description: string;
    is_active: boolean;
  }[];
}

function fmtIndicator(value: number | string | null | undefined): string {
  if (value == null) return "—";
  if (typeof value === "string") return value;
  return Math.abs(value) > 1000
    ? value.toLocaleString("en-US", { maximumFractionDigits: 0 })
    : num(value, 3);
}

export default function StrategyPage() {
  const queryClient = useQueryClient();
  const strategies = useQuery<StrategyList>({
    queryKey: ["strategies"],
    queryFn: () => api.get("/api/strategies"),
  });
  const signals = useQuery<Signal[]>({
    queryKey: ["signals"],
    queryFn: () => api.get("/api/signals?limit=100"),
  });
  const universe = useQuery<{ symbols: string[] }>({
    queryKey: ["universe"],
    queryFn: () => api.get("/api/settings/universe"),
  });
  const targets = useQuery<TargetInfo>({
    queryKey: ["targets"],
    queryFn: () => api.get("/api/dashboard/targets"),
  });

  const preview = useMutation({
    mutationFn: (id: string) => api.post(`/api/strategies/${id}/preview`),
    onSuccess: () => queryClient.invalidateQueries(),
  });

  // Latest run's signals only.
  const latestRunId = signals.data?.[0]?.strategy_run_id;
  const latest = (signals.data ?? []).filter(
    (s) => s.strategy_run_id === latestRunId,
  );
  const included = latest
    .filter((s) => s.eligible)
    .sort((a, b) => (b.score ?? 0) - (a.score ?? 0));
  const excluded = latest.filter((s) => !s.eligible);
  const active = strategies.data?.strategies.find((s) => s.is_active);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Strategy</h1>
        {active && (
          <Button
            onClick={() => preview.mutate(active.id)}
            disabled={preview.isPending}
          >
            {preview.isPending ? "Previewing…" : "Preview (no orders)"}
          </Button>
        )}
      </div>
      {preview.isError && (
        <ErrorNote message={`Preview failed: ${(preview.error as Error).message}`} />
      )}

      <Card title="Definition">
        {strategies.isLoading ? (
          <Spinner />
        ) : active ? (
          <div className="space-y-2 text-sm">
            <div className="text-base font-semibold text-ink">{active.name}</div>
            <p className="text-ink-secondary">{active.description}</p>
            <div className="text-ink-muted">
              Approved universe:{" "}
              {(universe.data?.symbols ?? []).map((s) => (
                <span key={s} className="mr-1 font-mono text-xs text-ink-secondary">
                  {s}
                </span>
              ))}
            </div>
          </div>
        ) : (
          <p className="text-sm text-ink-muted">
            No strategy seeded yet. Run <code>make seed</code>.
          </p>
        )}
      </Card>

      <Card title="Ranked securities (latest run)">
        {signals.isLoading ? (
          <Spinner />
        ) : included.length === 0 ? (
          <p className="py-4 text-sm text-ink-muted">
            No eligible securities in the latest run (or no run yet).
          </p>
        ) : (
          <Table
            headers={[
              "Symbol", "Score", "Momentum 63d", "Momentum 126d", "Trend",
              "Vol penalty", "DD penalty", "Price", "SMA200",
            ]}
          >
            {included.map((s) => (
              <tr key={s.id}>
                <td className="px-2 py-2 font-semibold text-ink">{s.symbol}</td>
                <td className="px-2 py-2">
                  <Badge tone="info">{num(s.score, 3)}</Badge>
                </td>
                <td className="px-2 py-2">{fmtIndicator(s.score_breakdown?.momentum_medium)}</td>
                <td className="px-2 py-2">{fmtIndicator(s.score_breakdown?.momentum_long)}</td>
                <td className="px-2 py-2">{fmtIndicator(s.score_breakdown?.trend_strength)}</td>
                <td className="px-2 py-2">{fmtIndicator(s.score_breakdown?.volatility_penalty)}</td>
                <td className="px-2 py-2">{fmtIndicator(s.score_breakdown?.drawdown_penalty)}</td>
                <td className="px-2 py-2">{fmtIndicator(s.indicators?.latest_price)}</td>
                <td className="px-2 py-2">{fmtIndicator(s.indicators?.sma_200)}</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      <Card title="Excluded securities (latest run)">
        {excluded.length === 0 ? (
          <p className="py-4 text-sm text-ink-muted">Nothing excluded.</p>
        ) : (
          <Table headers={["Symbol", "Exclusion reasons"]}>
            {excluded.map((s) => (
              <tr key={s.id}>
                <td className="px-2 py-2 font-semibold text-ink">{s.symbol}</td>
                <td className="px-2 py-2 text-xs text-ink-secondary">
                  {s.exclusion_reasons.join("; ")}
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Card>

      {targets.data && targets.data.ai_adjustments.length > 0 && (
        <Card title="AI risk adjustments (latest run)">
          <Table headers={["Symbol", "Action", "Risk level", "Original", "New"]}>
            {targets.data.ai_adjustments.map((a, i) => {
              const adj = a as Record<string, string | number>;
              return (
                <tr key={i}>
                  <td className="px-2 py-2 font-semibold">{String(adj.symbol)}</td>
                  <td className="px-2 py-2">
                    <Badge tone={adj.action === "veto" ? "bad" : "warn"}>
                      {String(adj.action)}
                    </Badge>
                  </td>
                  <td className="px-2 py-2">{String(adj.risk_level)}</td>
                  <td className="px-2 py-2">{num(Number(adj.original_weight), 3)}</td>
                  <td className="px-2 py-2">{num(Number(adj.new_weight), 3)}</td>
                </tr>
              );
            })}
          </Table>
        </Card>
      )}
    </div>
  );
}
