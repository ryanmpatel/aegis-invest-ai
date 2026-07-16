"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { money, num, pct, plClass } from "@/lib/format";
import type { Position, TargetInfo } from "@/types";
import { Badge, Card, Spinner, Table } from "@/components/ui";

export default function PortfolioPage() {
  const positions = useQuery<Position[]>({
    queryKey: ["positions"],
    queryFn: () => api.get("/api/broker/positions"),
  });
  const targets = useQuery<TargetInfo>({
    queryKey: ["targets"],
    queryFn: () => api.get("/api/dashboard/targets"),
  });

  if (positions.isLoading) return <Spinner />;

  const rows = positions.data ?? [];
  const totalValue = rows.reduce((sum, p) => sum + (p.market_value ?? 0), 0);
  const targetMap = new Map(
    (targets.data?.targets ?? []).map((t) => [t.symbol, t.target_weight]),
  );
  const aiFlagged = new Set(
    (targets.data?.ai_adjustments ?? [])
      .map((a) => String((a as { symbol?: string }).symbol ?? ""))
      .filter(Boolean),
  );

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight text-ink">Portfolio</h1>
      <Card>
        {rows.length === 0 ? (
          <p className="py-6 text-center text-sm text-ink-muted">
            No open positions in the paper account.
          </p>
        ) : (
          <Table
            headers={[
              "Symbol", "Qty", "Avg entry", "Price", "Market value", "Weight",
              "Unrealized P/L", "Target weight", "Δ from target", "Flags",
            ]}
          >
            {rows.map((p) => {
              const weight = totalValue > 0 ? (p.market_value ?? 0) / totalValue : 0;
              const target = targetMap.get(p.symbol);
              const delta = target !== undefined ? target - weight : null;
              return (
                <tr key={p.symbol}>
                  <td className="px-2 py-2 font-semibold text-ink">{p.symbol}</td>
                  <td className="px-2 py-2">{num(p.quantity, 4)}</td>
                  <td className="px-2 py-2">{money(p.avg_entry_price)}</td>
                  <td className="px-2 py-2">{money(p.current_price)}</td>
                  <td className="px-2 py-2">{money(p.market_value)}</td>
                  <td className="px-2 py-2">{pct(weight, 1)}</td>
                  <td className={`px-2 py-2 ${plClass(p.unrealized_pl)}`}>
                    {money(p.unrealized_pl)}
                  </td>
                  <td className="px-2 py-2">{target !== undefined ? pct(target, 1) : "—"}</td>
                  <td className="px-2 py-2">{delta !== null ? pct(delta, 1) : "—"}</td>
                  <td className="px-2 py-2">
                    {aiFlagged.has(p.symbol) ? <Badge tone="warn">AI flag</Badge> : "—"}
                  </td>
                </tr>
              );
            })}
          </Table>
        )}
      </Card>

      <Card title="Current target portfolio">
        {targets.data && targets.data.targets.length > 0 ? (
          <Table headers={["Symbol", "Target weight", "Score", "Reasons"]}>
            {targets.data.targets.map((t) => (
              <tr key={t.symbol}>
                <td className="px-2 py-2 font-semibold text-ink">{t.symbol}</td>
                <td className="px-2 py-2">{pct(t.target_weight, 1)}</td>
                <td className="px-2 py-2">{t.score != null ? num(t.score, 3) : "—"}</td>
                <td className="px-2 py-2 text-xs text-ink-secondary">
                  {t.reasons.join("; ")}
                </td>
              </tr>
            ))}
          </Table>
        ) : (
          <p className="py-4 text-sm text-ink-muted">
            No target portfolio yet — run a rebalance or preview from the Strategy page.
          </p>
        )}
        {targets.data?.cash_target != null && targets.data.targets.length > 0 && (
          <p className="mt-2 text-sm text-ink-secondary">
            Cash target: {pct(targets.data.cash_target, 1)}
          </p>
        )}
      </Card>
    </div>
  );
}
