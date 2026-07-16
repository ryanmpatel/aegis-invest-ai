"""AI analysis provider protocol.

Providers analyze news and return validated AIAnalysisResult objects. They
have no access to broker clients, account data, or order state — by
construction they cannot place orders or see anything sensitive.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.schemas.ai import AIAnalysisResult
from app.schemas.market_data import NewsItem


@runtime_checkable
class AIAnalysisProvider(Protocol):
    name: str

    async def analyze_news(self, symbol: str, article: NewsItem) -> AIAnalysisResult | None:
        """Return a validated analysis, or None when analysis is unavailable
        (treated as neutral by the risk overlay)."""
        ...
