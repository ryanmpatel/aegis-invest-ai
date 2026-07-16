"""APScheduler-based rebalance scheduler.

Guards, in order: scheduler enabled → kill switch inactive → trading not
frozen → market open → distributed lock (inside the workflow). Failures
notify and record risk events; the scheduler never retries a failed rebalance
automatically within the same window.
"""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import Settings, get_settings
from app.database import get_session_factory
from app.logging import get_logger, log_event
from app.services.ai_analysis.overlay import make_ai_overlay
from app.services.broker.factory import build_broker
from app.services.execution.rebalance import RebalanceAborted, RebalanceWorkflow
from app.services.market_data.mock_provider import MockMarketDataProvider
from app.services.notifications.service import build_notification_service
from app.services.risk.events import is_trading_frozen, record_risk_event
from app.services.risk.kill_switch import is_kill_switch_active
from app.services.strategies.registry import build_strategy

logger = get_logger("workers.scheduler")

_scheduler: AsyncIOScheduler | None = None


def _build_market_data(settings: Settings):
    if settings.market_data_provider == "alpaca":
        from app.services.market_data.alpaca_provider import AlpacaMarketDataProvider

        return AlpacaMarketDataProvider(settings)
    return MockMarketDataProvider()


async def scheduled_rebalance() -> None:
    settings = get_settings()
    notifier = build_notification_service(settings)
    async with get_session_factory()() as session:
        try:
            if await is_kill_switch_active(session):
                log_event(logger, "scheduler_skipped", "Kill switch active; skipping run")
                return
            frozen, reason = await is_trading_frozen(session)
            if frozen:
                log_event(logger, "scheduler_skipped", f"Trading frozen: {reason}")
                return

            workflow = RebalanceWorkflow(
                session=session,
                settings=settings,
                broker=build_broker(settings),
                market_data=_build_market_data(settings),
                strategy=build_strategy("weekly_multi_factor_trend"),
                ai_overlay=make_ai_overlay(settings.ai_min_confidence),
                notifier=notifier.send,
            )
            await workflow.run(mode="paper", actor="scheduler")
        except RebalanceAborted as exc:
            log_event(logger, "scheduler_aborted", str(exc))
        except Exception as exc:
            await record_risk_event(
                session, severity="critical", rule_name="scheduled_job_failure",
                message=f"Scheduled rebalance failed: {exc}",
            )
            await session.commit()
            await notifier.send("Scheduled job FAILED", str(exc))
            raise


def start_scheduler(settings: Settings) -> AsyncIOScheduler | None:
    global _scheduler
    if not settings.scheduler_enabled:
        return None
    if _scheduler is not None:
        return _scheduler
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        scheduled_rebalance,
        CronTrigger.from_crontab(settings.rebalance_cron, timezone="UTC"),
        id="weekly_rebalance",
        coalesce=True,          # collapse missed runs into one
        max_instances=1,        # single-flight at the scheduler level too
        misfire_grace_time=3600,
    )
    scheduler.start()
    _scheduler = scheduler
    log_event(logger, "scheduler_started", f"Scheduler started ({settings.rebalance_cron})")
    return scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def next_run_time() -> str | None:
    if _scheduler is None:
        return None
    job = _scheduler.get_job("weekly_rebalance")
    if job is None or job.next_run_time is None:
        return None
    return job.next_run_time.isoformat()
