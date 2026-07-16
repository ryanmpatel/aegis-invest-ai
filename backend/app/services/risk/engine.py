"""Deterministic risk engine.

Every proposed trade passes through ``review_trade``. The engine can approve,
resize, reject, or freeze. Its verdict overrides strategy and AI output —
there is no code path around it: the execution engine requires a RiskVerdict
with action APPROVE/RESIZE to construct an ApprovedOrder.

The engine is pure/deterministic: same inputs → same verdicts. It performs no
I/O; callers supply AccountState and MarketContext snapshots.
"""

from __future__ import annotations

import math
from datetime import UTC

from app.schemas.risk import (
    AccountState,
    MarketContext,
    RiskAction,
    RiskLimits,
    RiskVerdict,
    RuleCheck,
    TradeIntent,
)


class RiskEngine:
    def __init__(self, limits: RiskLimits | None = None) -> None:
        self.limits = limits or RiskLimits()

    # ------------------------------------------------------------------
    # Pre-trade freeze conditions (account-level, evaluated before any trade)
    # ------------------------------------------------------------------

    def check_freeze_conditions(
        self, account: AccountState, market: MarketContext
    ) -> list[RuleCheck]:
        """Return failed checks that must freeze the whole run."""
        limits = self.limits
        failures: list[RuleCheck] = []

        def fail(rule: str, actual: float | None, limit: float | None, msg: str) -> None:
            failures.append(
                RuleCheck(
                    rule_name=rule, passed=False,
                    actual_value=actual, limit_value=limit, message=msg,
                )
            )

        if account.daily_pl_pct <= -limits.daily_loss_limit_pct:
            fail(
                "daily_loss_limit", account.daily_pl_pct, -limits.daily_loss_limit_pct,
                f"Daily loss {account.daily_pl_pct:.2%} breaches limit "
                f"{limits.daily_loss_limit_pct:.2%}",
            )
        if account.drawdown_pct <= -limits.strategy_drawdown_limit_pct:
            fail(
                "strategy_drawdown_limit", account.drawdown_pct,
                -limits.strategy_drawdown_limit_pct,
                f"Drawdown {account.drawdown_pct:.2%} breaches limit "
                f"{limits.strategy_drawdown_limit_pct:.2%}",
            )
        if (
            account.portfolio_volatility is not None
            and account.portfolio_volatility > limits.portfolio_volatility_limit
        ):
            fail(
                "portfolio_volatility_limit", account.portfolio_volatility,
                limits.portfolio_volatility_limit, "Portfolio volatility above limit",
            )
        if account.consecutive_errors >= limits.max_consecutive_errors:
            fail(
                "consecutive_error_limit", account.consecutive_errors,
                limits.max_consecutive_errors, "Too many consecutive errors",
            )
        if account.consecutive_rejected_orders >= limits.max_consecutive_rejected_orders:
            fail(
                "consecutive_rejected_order_limit", account.consecutive_rejected_orders,
                limits.max_consecutive_rejected_orders, "Too many consecutive rejected orders",
            )
        for value, name in ((account.equity, "equity"), (account.cash, "cash")):
            if not math.isfinite(value):
                fail("non_finite_account_value", None, None, f"Account {name} is not finite")
        if market.now.tzinfo is None or market.now.utcoffset() != UTC.utcoffset(None):
            fail("clock_not_utc", None, None, "Market context clock must be aware UTC")
        return failures

    # ------------------------------------------------------------------
    # Per-trade review
    # ------------------------------------------------------------------

    def review_trade(
        self,
        intent: TradeIntent,
        account: AccountState,
        market: MarketContext,
        *,
        planned_buy_notional_before: float = 0.0,
        planned_turnover_before: float = 0.0,
    ) -> RiskVerdict:
        """Review one trade. ``planned_*_before`` carry the cumulative notional
        of already-approved trades in this rebalance so batch limits hold."""
        limits = self.limits
        checks: list[RuleCheck] = []

        def check(
            rule: str, passed: bool, actual: float | None = None,
            limit: float | None = None, msg: str = "",
        ) -> bool:
            checks.append(
                RuleCheck(
                    rule_name=rule, passed=passed,
                    actual_value=actual, limit_value=limit, message=msg,
                )
            )
            return passed

        def reject(rule: str) -> RiskVerdict:
            failed = next(c for c in reversed(checks) if c.rule_name == rule)
            return RiskVerdict(
                action=RiskAction.REJECT, intent=intent, rule_name=rule,
                actual_value=failed.actual_value, limit_value=failed.limit_value,
                checks=checks, message=failed.message,
            )

        # --- freeze conditions first: they override everything -----------
        freeze_failures = self.check_freeze_conditions(account, market)
        if freeze_failures:
            first = freeze_failures[0]
            return RiskVerdict(
                action=RiskAction.FREEZE, intent=intent, rule_name=first.rule_name,
                actual_value=first.actual_value, limit_value=first.limit_value,
                checks=freeze_failures, message=first.message,
            )

        symbol = intent.symbol
        price = market.prices.get(symbol)
        quantity = intent.quantity
        notional = intent.notional

        # --- validity checks ---------------------------------------------
        if not check(
            "finite_values",
            all(math.isfinite(v) for v in (quantity, notional, intent.reference_price)),
            msg="Trade contains non-finite values",
        ):
            return reject("finite_values")

        if not check(
            "known_price", price is not None and price > 0,
            msg=f"No current price for {symbol}",
        ):
            return reject("known_price")
        assert price is not None

        ts = market.price_timestamps.get(symbol)
        stale = ts is None or (market.now - ts).total_seconds() > (
            limits.stale_data_max_age_minutes * 60
        )
        # Daily-bar platform: a price as-of the last close is acceptable when
        # the timestamp is recent relative to trading days (max ~3.5 days).
        if ts is not None and stale:
            stale = (market.now - ts).total_seconds() > 3.5 * 86400
        if not check("stale_price", not stale, msg=f"Stale or missing price for {symbol}"):
            return reject("stale_price")

        if not check(
            "approved_universe", symbol in market.approved_universe,
            msg=f"{symbol} not in approved universe",
        ):
            return reject("approved_universe")

        if not check(
            "tradable_asset", market.tradable.get(symbol, False),
            msg=f"{symbol} is not tradable",
        ):
            return reject("tradable_asset")

        if not check(
            "min_price", price >= limits.min_price, price, limits.min_price,
            f"{symbol} price {price:.2f} below minimum {limits.min_price:.2f}",
        ):
            return reject("min_price")

        # --- no shorting / no leverage ------------------------------------
        if intent.side == "sell":
            held = account.positions.get(symbol, 0.0)
            if not check(
                "no_shorting", quantity <= held + 1e-9, quantity, held,
                f"Sell {quantity} exceeds held {held} for {symbol}",
            ):
                # Resize sells down to the held quantity rather than rejecting,
                # unless nothing is held.
                if held > 0:
                    resized_qty = held
                    return RiskVerdict(
                        action=RiskAction.RESIZE, intent=intent,
                        approved_quantity=resized_qty,
                        approved_notional=resized_qty * price,
                        rule_name="no_shorting", actual_value=quantity, limit_value=held,
                        checks=checks, message="Sell resized to held quantity",
                    )
                return reject("no_shorting")
            # Sells passed all applicable rules.
            return RiskVerdict(
                action=RiskAction.APPROVE, intent=intent,
                approved_quantity=quantity, approved_notional=notional,
                checks=checks, message="Sell approved",
            )

        # --- buy-side sizing rules -----------------------------------------
        max_affordable = account.cash + 0.0  # long-only: never exceed cash
        allowed_notional = notional

        # Max % of ADV
        adv = market.avg_daily_volumes.get(symbol)
        if adv is not None and adv > 0:
            max_adv_shares = adv * limits.max_pct_of_avg_daily_volume
            if quantity > max_adv_shares:
                allowed_notional = min(allowed_notional, max_adv_shares * price)
                check(
                    "max_pct_adv", False, quantity, max_adv_shares,
                    "Order size above allowed fraction of average daily volume",
                )
            else:
                check("max_pct_adv", True, quantity, max_adv_shares)

        # Position concentration (existing value + new notional)
        existing_value = account.position_values.get(symbol, 0.0)
        if account.equity > 0:
            max_position_notional = min(
                limits.max_position_pct * account.equity - existing_value,
                limits.max_position_notional - existing_value,
            )
        else:
            max_position_notional = 0.0
        if allowed_notional > max_position_notional:
            check(
                "max_position_size", False, existing_value + allowed_notional,
                min(limits.max_position_pct * account.equity, limits.max_position_notional),
                "Position size limit reached",
            )
            allowed_notional = max_position_notional
        else:
            check("max_position_size", True)

        # Max order value
        if allowed_notional > limits.max_order_notional:
            check(
                "max_order_value", False, allowed_notional, limits.max_order_notional,
                "Order value above maximum",
            )
            allowed_notional = limits.max_order_notional
        else:
            check("max_order_value", True, allowed_notional, limits.max_order_notional)

        # Cash reserve / max invested / no leverage
        invested = sum(account.position_values.values())
        max_total_invested = limits.max_invested_pct * account.equity
        headroom_invested = max_total_invested - invested - planned_buy_notional_before
        cash_after_reserve = (
            account.cash
            - limits.min_cash_reserve_pct * account.equity
            - planned_buy_notional_before
        )
        headroom = max(0.0, min(headroom_invested, cash_after_reserve, max_affordable))
        if allowed_notional > headroom:
            check(
                "cash_and_exposure_headroom", False, allowed_notional, headroom,
                "Buy exceeds cash reserve / max-invested headroom",
            )
            allowed_notional = headroom
        else:
            check("cash_and_exposure_headroom", True, allowed_notional, headroom)

        # New capital deployed per rebalance
        max_new_capital = limits.max_new_capital_per_rebalance_pct * account.equity
        new_capital_headroom = max_new_capital - planned_buy_notional_before
        if allowed_notional > new_capital_headroom:
            check(
                "max_new_capital_per_rebalance", False,
                planned_buy_notional_before + allowed_notional, max_new_capital,
                "New capital per rebalance limit reached",
            )
            allowed_notional = max(0.0, new_capital_headroom)
        else:
            check("max_new_capital_per_rebalance", True)

        # Daily turnover
        max_turnover = limits.max_daily_turnover_pct * account.equity
        turnover_headroom = max_turnover - planned_turnover_before
        if allowed_notional > turnover_headroom:
            check(
                "max_daily_turnover", False,
                planned_turnover_before + allowed_notional, max_turnover,
                "Daily turnover limit reached",
            )
            allowed_notional = max(0.0, turnover_headroom)
        else:
            check("max_daily_turnover", True)

        # Max open positions (new symbols only)
        if account.positions.get(symbol, 0.0) <= 0:
            open_positions = sum(1 for q in account.positions.values() if q > 0)
            if not check(
                "max_open_positions", open_positions < limits.max_open_positions,
                open_positions, limits.max_open_positions,
                "Maximum number of open positions reached",
            ):
                return reject("max_open_positions")

        # Minimum order value (applied after all reductions)
        if not check(
            "min_order_value", allowed_notional >= limits.min_order_notional,
            allowed_notional, limits.min_order_notional,
            "Remaining allowed order value below minimum — trade not worth placing",
        ):
            return reject("min_order_value")

        approved_quantity = allowed_notional / price
        if allowed_notional >= notional - 1e-6:
            return RiskVerdict(
                action=RiskAction.APPROVE, intent=intent,
                approved_quantity=quantity, approved_notional=notional,
                checks=checks, message="Buy approved",
            )
        resize_rule = next(
            (c.rule_name for c in checks if not c.passed), "resized",
        )
        failed = next((c for c in checks if not c.passed), None)
        return RiskVerdict(
            action=RiskAction.RESIZE, intent=intent,
            approved_quantity=approved_quantity, approved_notional=allowed_notional,
            rule_name=resize_rule,
            actual_value=failed.actual_value if failed else None,
            limit_value=failed.limit_value if failed else None,
            checks=checks,
            message=f"Buy resized from {notional:.2f} to {allowed_notional:.2f}",
        )
