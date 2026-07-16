"""AI analysis structured output. Strictly validated; malformed output is rejected."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class AIEventType(StrEnum):
    EARNINGS = "earnings"
    LEGAL = "legal"
    REGULATORY = "regulatory"
    MANAGEMENT = "management"
    PRODUCT = "product"
    MACRO = "macro"
    OTHER = "other"


class AITimeHorizon(StrEnum):
    SHORT = "short"
    MEDIUM = "medium"
    LONG = "long"


class AIRiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AIAnalysisResult(BaseModel):
    """The only shape the AI layer may emit. ``extra="forbid"`` rejects
    hallucinated fields; enum/range constraints reject malformed values."""

    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(min_length=1, max_length=16)
    analysis_timestamp: datetime
    event_type: AIEventType
    sentiment: float = Field(ge=-1.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    time_horizon: AITimeHorizon
    risk_level: AIRiskLevel
    summary: str = Field(max_length=2000)
    positive_factors: list[str] = Field(default_factory=list, max_length=20)
    negative_factors: list[str] = Field(default_factory=list, max_length=20)
    uncertainties: list[str] = Field(default_factory=list, max_length=20)
    source_ids: list[str] = Field(default_factory=list, max_length=50)
    model_name: str = ""
    prompt_version: str = ""
