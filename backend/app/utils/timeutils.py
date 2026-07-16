"""UTC time helpers. All timestamps in the system are timezone-aware UTC."""

from __future__ import annotations

from datetime import UTC, date, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(dt: datetime) -> datetime:
    """Coerce a datetime to aware-UTC (naive datetimes are assumed UTC)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def to_date(dt: datetime) -> date:
    return as_utc(dt).date()
