"use client";

import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { EquityPoint } from "@/types";

// Validated dark-surface chart tokens (see docs — palette validated for
// contrast + CVD separation on #1a1a19).
const C = {
  series1: "#3987e5", // strategy
  series2: "#898781", // benchmark (neutral reference)
  down: "#e66767", // drawdown
  grid: "#2c2c2a",
  axis: "#898781",
  ink: "#ffffff",
  inkSecondary: "#c3c2b7",
  surface: "#1a1a19",
};

const AXIS = {
  stroke: C.axis,
  fontSize: 11,
  tickLine: false as const,
  axisLine: { stroke: "#383835" },
};

const TOOLTIP_STYLE = {
  backgroundColor: "rgba(26,26,25,0.97)",
  border: "1px solid rgba(255,255,255,0.12)",
  borderRadius: 10,
  fontSize: 12,
  color: C.inkSecondary,
  boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
  padding: "8px 12px",
} as const;

function ChartLegend({ items }: { items: { label: string; color: string; dashed?: boolean }[] }) {
  return (
    <div className="mb-2 flex items-center gap-4 px-1">
      {items.map((item) => (
        <span key={item.label} className="flex items-center gap-1.5 text-xs text-ink-secondary">
          <svg width="18" height="6" aria-hidden>
            <line
              x1="0"
              y1="3"
              x2="18"
              y2="3"
              stroke={item.color}
              strokeWidth="2"
              strokeDasharray={item.dashed ? "4 3" : undefined}
            />
          </svg>
          {item.label}
        </span>
      ))}
    </div>
  );
}

export function EquityChart({ data }: { data: EquityPoint[] }) {
  const hasBenchmark = data.some((d) => d.benchmark_equity != null);
  return (
    <div>
      <ChartLegend
        items={[
          { label: "Strategy", color: C.series1 },
          ...(hasBenchmark
            ? [{ label: "Benchmark", color: C.series2, dashed: true }]
            : []),
        ]}
      />
      <ResponsiveContainer width="100%" height={320}>
        <AreaChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="equityFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={C.series1} stopOpacity={0.22} />
              <stop offset="100%" stopColor={C.series1} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke={C.grid} strokeDasharray="3 4" vertical={false} />
          <XAxis dataKey="date" {...AXIS} minTickGap={70} />
          <YAxis
            {...AXIS}
            width={52}
            domain={["auto", "auto"]}
            tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`}
          />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            cursor={{ stroke: "rgba(255,255,255,0.2)", strokeDasharray: "3 3" }}
            formatter={(value: number | string, name: string) => [
              `$${Number(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}`,
              name === "equity" ? "Strategy" : "Benchmark",
            ]}
          />
          <Area
            type="monotone"
            dataKey="equity"
            stroke={C.series1}
            strokeWidth={2}
            fill="url(#equityFill)"
            dot={false}
            activeDot={{ r: 4, strokeWidth: 0 }}
            animationDuration={600}
          />
          {hasBenchmark && (
            <Area
              type="monotone"
              dataKey="benchmark_equity"
              stroke={C.series2}
              strokeWidth={1.5}
              strokeDasharray="5 4"
              fill="none"
              dot={false}
              activeDot={{ r: 3, strokeWidth: 0 }}
              animationDuration={600}
            />
          )}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function DrawdownChart({ data }: { data: EquityPoint[] }) {
  return (
    <ResponsiveContainer width="100%" height={180}>
      <AreaChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="ddFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={C.down} stopOpacity={0.03} />
            <stop offset="100%" stopColor={C.down} stopOpacity={0.28} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={C.grid} strokeDasharray="3 4" vertical={false} />
        <XAxis dataKey="date" {...AXIS} minTickGap={70} />
        <YAxis
          {...AXIS}
          width={44}
          tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
        />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          cursor={{ stroke: "rgba(255,255,255,0.2)", strokeDasharray: "3 3" }}
          formatter={(value: number | string) => [
            `${(Number(value) * 100).toFixed(2)}%`,
            "Drawdown",
          ]}
        />
        <Area
          type="monotone"
          dataKey="drawdown"
          stroke={C.down}
          strokeWidth={1.5}
          fill="url(#ddFill)"
          dot={false}
          activeDot={{ r: 3, strokeWidth: 0 }}
          animationDuration={600}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export function PerformanceChart({
  data,
}: {
  data: { at: string | null; equity: number }[];
}) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid stroke={C.grid} strokeDasharray="3 4" vertical={false} />
        <XAxis dataKey="at" {...AXIS} minTickGap={90} />
        <YAxis {...AXIS} width={52} domain={["auto", "auto"]} />
        <Tooltip contentStyle={TOOLTIP_STYLE} />
        <Line
          type="monotone"
          dataKey="equity"
          stroke={C.series1}
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4, strokeWidth: 0 }}
          animationDuration={600}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
