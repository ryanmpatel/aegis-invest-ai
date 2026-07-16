"""Mock AI provider: deterministic, neutral, keyword-driven.

Lets the whole application (and test suite) run with no AI API key.
"""

from __future__ import annotations

from app.schemas.ai import (
    AIAnalysisResult,
    AIEventType,
    AIRiskLevel,
    AITimeHorizon,
)
from app.schemas.market_data import NewsItem
from app.utils.timeutils import utcnow

_NEGATIVE_KEYWORDS = {
    "lawsuit": (AIEventType.LEGAL, -0.5, AIRiskLevel.HIGH),
    "investigation": (AIEventType.REGULATORY, -0.5, AIRiskLevel.HIGH),
    "fraud": (AIEventType.LEGAL, -0.8, AIRiskLevel.CRITICAL),
    "bankruptcy": (AIEventType.MACRO, -0.9, AIRiskLevel.CRITICAL),
    "recall": (AIEventType.PRODUCT, -0.4, AIRiskLevel.MEDIUM),
    "resigns": (AIEventType.MANAGEMENT, -0.3, AIRiskLevel.MEDIUM),
    "misses": (AIEventType.EARNINGS, -0.3, AIRiskLevel.MEDIUM),
}


class MockAIAnalysisProvider:
    name = "mock"

    async def analyze_news(self, symbol: str, article: NewsItem) -> AIAnalysisResult | None:
        text = f"{article.headline} {article.summary} {article.content}".lower()
        event_type, sentiment, risk = AIEventType.OTHER, 0.0, AIRiskLevel.LOW
        matched: list[str] = []
        for keyword, (etype, score, level) in _NEGATIVE_KEYWORDS.items():
            if keyword in text:
                matched.append(keyword)
                if score < sentiment:
                    event_type, sentiment, risk = etype, score, level
        return AIAnalysisResult(
            symbol=symbol,
            analysis_timestamp=utcnow(),
            event_type=event_type,
            sentiment=sentiment,
            confidence=0.9 if matched else 0.5,
            time_horizon=AITimeHorizon.SHORT,
            risk_level=risk,
            summary=(
                f"Mock analysis of '{article.headline[:80]}'"
                + (f" (keywords: {', '.join(matched)})" if matched else " (neutral)")
            ),
            positive_factors=[],
            negative_factors=[f"keyword: {k}" for k in matched],
            uncertainties=["Mock provider output; not a real analysis."],
            source_ids=[article.external_id],
            model_name="mock",
            prompt_version="mock-v1",
        )
