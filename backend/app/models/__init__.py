"""All ORM models. Importing this package registers every table on Base.metadata."""

from app.models.backtesting import (
    BacktestDailyResult,
    BacktestPosition,
    BacktestRun,
    BacktestTrade,
)
from app.models.base import Base
from app.models.config import (
    ApprovedUniverse,
    BrokerConnection,
    SchedulerConfig,
    StrategyDefinition,
    StrategyVersion,
    UserSettings,
)
from app.models.config import (
    RiskProfile as RiskProfile,
)
from app.models.market_data import (
    AINewsAnalysis,
    Asset,
    DailyBar,
    MarketCalendarDay,
    NewsArticle,
)
from app.models.trading import (
    AccountSnapshot,
    Fill,
    KillSwitchEvent,
    Order,
    OrderEvent,
    PositionRecord,
    ProposedTrade,
    ReconciliationReport,
    RiskDecision,
    RiskEvent,
    Signal,
    StrategyRun,
    TargetPortfolioRecord,
)

__all__ = [
    "AINewsAnalysis",
    "AccountSnapshot",
    "ApprovedUniverse",
    "Asset",
    "BacktestDailyResult",
    "BacktestPosition",
    "BacktestRun",
    "BacktestTrade",
    "Base",
    "BrokerConnection",
    "DailyBar",
    "Fill",
    "KillSwitchEvent",
    "MarketCalendarDay",
    "NewsArticle",
    "Order",
    "OrderEvent",
    "PositionRecord",
    "ProposedTrade",
    "ReconciliationReport",
    "RiskDecision",
    "RiskEvent",
    "SchedulerConfig",
    "Signal",
    "StrategyDefinition",
    "StrategyRun",
    "StrategyVersion",
    "TargetPortfolioRecord",
    "UserSettings",
]
