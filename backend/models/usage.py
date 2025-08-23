from __future__ import annotations
from typing import Any
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import Text, DateTime, Integer, Boolean
from models.base import Base


class UsageEvent(Base):
    __tablename__ = 'usage_events'

    event_id: Mapped[Any] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[Any] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    occurred_at: Mapped[Any] = mapped_column(DateTime(timezone=True), nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    operation: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    thread_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    route: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_attempt: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cache_hit: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    metadata: Mapped[Any] = mapped_column(JSONB, nullable=True)


