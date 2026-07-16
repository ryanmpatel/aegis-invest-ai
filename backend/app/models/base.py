"""Declarative base and shared column helpers.

Conventions: UUID primary keys, aware-UTC timestamps, JSON columns kept
portable across PostgreSQL and SQLite (tests).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    type_annotation_map = {  # noqa: RUF012 - SQLAlchemy class-level config, not state
        uuid.UUID: Uuid(as_uuid=True),
        datetime: DateTime(timezone=True),
    }


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(primary_key=True, default=uuid.uuid4)


def created_at_col() -> Mapped[datetime]:
    # Client-side default gives microsecond precision (SQLite CURRENT_TIMESTAMP
    # is second-resolution, which breaks ordering of rapid event sequences);
    # server_default remains as a fallback for non-ORM inserts.
    return mapped_column(
        default=lambda: datetime.now(UTC), server_default=func.now(), nullable=False
    )
