"""Anthropic-backed AI analysis provider (optional).

Sends ONLY: symbol, article id, sanitized headline/content. Never account
balances, credentials, personal information, or order data — the provider has
no access to them. Output must parse and validate as AIAnalysisResult or it
is rejected (returns None → treated as neutral).
"""

from __future__ import annotations

import json

from pydantic import ValidationError

from app.config import Settings
from app.logging import get_logger, log_event
from app.schemas.ai import AIAnalysisResult
from app.schemas.market_data import NewsItem
from app.services.ai_analysis.sanitize import (
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    build_user_prompt,
    sanitize_article_text,
)

logger = get_logger("ai_analysis.anthropic")


class AnthropicAnalysisProvider:
    name = "anthropic"

    def __init__(self, settings: Settings) -> None:
        api_key = settings.ai_api_key.get_secret_value()
        if not api_key:
            raise RuntimeError("AI_PROVIDER=anthropic requires AI_API_KEY.")
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:  # pragma: no cover - env-dependent
            raise RuntimeError(
                "anthropic package is not installed. Install with: pip install '.[ai]'"
            ) from exc
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = settings.ai_model_name
        self._max_chars = settings.ai_max_article_chars

    async def analyze_news(self, symbol: str, article: NewsItem) -> AIAnalysisResult | None:
        headline = sanitize_article_text(article.headline, 300)
        content = sanitize_article_text(
            article.content or article.summary, self._max_chars
        )
        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": build_user_prompt(
                            symbol, article.external_id, headline, content
                        ),
                    }
                ],
            )
        except Exception:
            log_event(
                logger, "ai_request_failed",
                f"AI request failed for {symbol}; treating as neutral",
                symbol=symbol,
            )
            return None

        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        ).strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
        try:
            payload = json.loads(text)
            payload["model_name"] = self._model
            payload["prompt_version"] = PROMPT_VERSION
            payload["symbol"] = symbol  # never trust the model to pick the symbol
            payload.setdefault("source_ids", [article.external_id])
            result = AIAnalysisResult.model_validate(payload)
        except (json.JSONDecodeError, ValidationError) as exc:
            log_event(
                logger, "ai_output_rejected",
                f"Malformed AI output rejected for {symbol}: {exc.__class__.__name__}",
                symbol=symbol,
            )
            return None
        return result
