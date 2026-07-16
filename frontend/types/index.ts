export interface SystemStatus {
  mode: string;
  live_trading_enabled: boolean;
  broker_provider: string;
  market_data_provider: string;
  ai_provider: string;
  broker_reachable: boolean;
  market_open: boolean | null;
  kill_switch_active: boolean;
  kill_switch_reason: string;
  trading_frozen: boolean;
  frozen_reason: string;
  scheduler_enabled: boolean;
  next_scheduled_run: string | null;
}

export interface DashboardSummary {
  equity: number | null;
  cash: number | null;
  buying_power: number | null;
  daily_pl: number | null;
  daily_pl_pct: number | null;
  total_pl: number | null;
  total_pl_pct: number | null;
  current_drawdown: number | null;
  broker_reachable: boolean;
  kill_switch_active: boolean;
  active_strategy: {
    name: string;
    version: string;
    last_run_status: string;
    last_run_at: string | null;
  } | null;
}

export interface Position {
  symbol: string;
  quantity: number;
  avg_entry_price: number;
  current_price: number | null;
  market_value: number | null;
  unrealized_pl: number | null;
}

export interface TargetInfo {
  as_of?: string | null;
  targets: {
    symbol: string;
    target_weight: number;
    score: number | null;
    reasons: string[];
  }[];
  cash_target: number | null;
  ai_adjustments: Record<string, unknown>[];
}

export interface Signal {
  id: string;
  strategy_run_id: string;
  created_at: string | null;
  symbol: string;
  eligible: boolean;
  exclusion_reasons: string[];
  indicators: Record<string, number | string | null>;
  score: number | null;
  score_breakdown: Record<string, number>;
}

export interface BacktestSummary {
  id: string;
  created_at: string | null;
  strategy_name: string;
  strategy_version: string;
  status: string;
  parameters: Record<string, unknown>;
  total_return: number | null;
  max_drawdown: number | null;
}

export interface BacktestDetail {
  id: string;
  status: string;
  error: string;
  strategy_name: string;
  strategy_version: string;
  parameters: Record<string, unknown>;
  metrics: Record<string, number | null>;
  warnings: string[];
}

export interface EquityPoint {
  date: string;
  equity: number;
  cash: number;
  invested_value: number;
  daily_return: number | null;
  drawdown: number;
  benchmark_equity: number | null;
}

export interface TradeRow {
  date: string;
  symbol: string;
  side: string;
  quantity: number;
  price: number;
  commission: number;
  slippage_cost: number;
  reason: string;
}

export interface ActivityEntry {
  type: string;
  at: string | null;
  summary: string;
  detail: Record<string, unknown>;
}

export interface RiskStatus {
  kill_switch_active: boolean;
  trading_frozen: boolean;
  frozen_reason: string;
  open_critical_events: {
    rule_name: string;
    message: string;
    created_at: string | null;
  }[];
}

export interface PaperStatus {
  enabled: boolean;
  trading_allowed: boolean;
  frozen: boolean;
  frozen_reason: string;
  rebalance_cron: string;
  next_scheduled_run: string | null;
  kill_switch_active: boolean;
  last_run: {
    id: string;
    status: string;
    as_of: string | null;
    error: string;
  } | null;
}

export interface Decision {
  id: string;
  created_at: string | null;
  strategy_run_id: string;
  symbol: string;
  side: string;
  proposed_notional: number;
  decision: string;
  approved_notional: number;
  rule_name: string;
  actual_value: number | null;
  limit_value: number | null;
  message: string;
}
