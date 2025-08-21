"""
Tenant DB Model
Production-grade: type-safe, linted, uses SQLAlchemy 2.0+ ORM style.
"""
from __future__ import annotations
from typing import Any
import uuid
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
from .base import Base
from constants import (
    TENANT_NAME_MAX_LENGTH,
    TENANT_PLAN_MAX_LENGTH,
    TENANT_DEFAULT_CREDIT,
    TENANT_SETTINGS_DEFAULT,
)



class Tenant(Base):
    __tablename__ = "tenants"

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(TENANT_NAME_MAX_LENGTH), nullable=False)
    plan: Mapped[str] = mapped_column(String(TENANT_PLAN_MAX_LENGTH), nullable=False)
    credit_balance: Mapped[int] = mapped_column(Integer, nullable=False, default=TENANT_DEFAULT_CREDIT)
    settings: Mapped[Any] = mapped_column(JSONB, nullable=False, default=TENANT_SETTINGS_DEFAULT)

    def __repr__(self) -> str:
        return f"<Tenant id={self.tenant_id} name={self.name} plan={self.plan}>"


class ChatThread(Base):
    __tablename__ = "chat_threads"

    thread_id: Mapped[str] = mapped_column(String(32), primary_key=True, unique=True, nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self) -> str:
        return f"<ChatThread id={self.thread_id} tenant={self.tenant_id} title={self.title!r}>"
