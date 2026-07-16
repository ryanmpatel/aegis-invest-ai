"use client";

import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "@/lib/api";
import { dt, money, num } from "@/lib/format";
import type { ActivityEntry, Decision } from "@/types";
import { Badge, Card, Spinner, Table } from "@/components/ui";

const TYPE_TONES: Record<string, "info" | "good" | "warn" | "bad" | "neutral"> = {
  strategy_run: "info",
  order: "good",
  fill: "good",
  risk_event: "warn",
};

export default function ActivityPage() {
  const [filter, setFilter] = useState<string>("all");
  const activity = useQuery<ActivityEntry[]>({
    queryKey: ["activity"],
    queryFn: () => api.get("/api/activity?limit=200"),
  });
  const decisions = useQuery<Decision[]>({
    queryKey: ["decisions"],
    queryFn: () => api.get("/api/decisions?limit=100"),
  });

  const entries = (activity.data ?? []).filter(
    (entry) => filter === "all" || entry.type === filter,
  );
  const types = ["all", "strategy_run", "order", "fill", "risk_event"];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold tracking-tight text-ink">Activity</h1>

      <Card
        title="Audit log"
        actions={
          <div className="flex gap-1">
            {types.map((t) => (
              <button
                key={t}
                onClick={() => setFilter(t)}
                className={
                  filter === t
                    ? "rounded-full bg-accent-500/15 px-2.5 py-0.5 text-xs text-accent-300"
                    : "rounded-full px-2.5 py-0.5 text-xs text-ink-muted hover:text-ink-secondary"
                }
              >
                {t.replace("_", " ")}
              </button>
            ))}
          </div>
        }
      >
        {activity.isLoading ? (
          <Spinner />
        ) : entries.length === 0 ? (
          <p className="py-6 text-center text-sm text-ink-muted">No activity yet.</p>
        ) : (
          <ul className="divide-y divide-edge">
            {entries.map((entry, i) => (
              <li key={i} className="flex items-start gap-3 py-2.5">
                <Badge tone={TYPE_TONES[entry.type] ?? "neutral"}>
                  {entry.type.replace("_", " ")}
                </Badge>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm text-ink-secondary">{entry.summary}</div>
                  <div className="text-xs text-ink-muted">{dt(entry.at)}</div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="Risk decisions">
        {decisions.isLoading ? (
          <Spinner />
        ) : (decisions.data ?? []).length === 0 ? (
          <p className="py-6 text-center text-sm text-ink-muted">
            No risk decisions recorded yet.
          </p>
        ) : (
          <Table
            headers={[
              "When", "Symbol", "Side", "Proposed", "Decision", "Approved",
              "Rule", "Actual", "Limit",
            ]}
          >
            {(decisions.data ?? []).map((d) => (
              <tr key={d.id}>
                <td className="px-2 py-2 text-xs">{dt(d.created_at)}</td>
                <td className="px-2 py-2 font-semibold">{d.symbol}</td>
                <td className="px-2 py-2">{d.side}</td>
                <td className="px-2 py-2">{money(d.proposed_notional)}</td>
                <td className="px-2 py-2">
                  <Badge
                    tone={
                      d.decision === "approve"
                        ? "good"
                        : d.decision === "resize"
                          ? "warn"
                          : "bad"
                    }
                  >
                    {d.decision}
                  </Badge>
                </td>
                <td className="px-2 py-2">{money(d.approved_notional)}</td>
                <td className="px-2 py-2 font-mono text-xs">{d.rule_name || "—"}</td>
                <td className="px-2 py-2">{d.actual_value != null ? num(d.actual_value) : "—"}</td>
                <td className="px-2 py-2">{d.limit_value != null ? num(d.limit_value) : "—"}</td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </div>
  );
}
