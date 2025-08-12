"""
Connector DB Model
Production-grade: type-safe, linted, SQLAlchemy 2.0+ ORM style.
"""
from __future__ import annotations
from typing import Any
import uuid
from sqlalchemy import Column, String, Enum, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from .base import Base
from enum import Enum as PyEnum

class ConnectorStatus(PyEnum):
    ACTIVE = "active"
    FAILED = "failed"

class Connector(Base):
    __tablename__ = "connectors"

    connector_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)  # e.g., "postgres", "gdrive"
    config: Mapped[Any] = mapped_column(JSONB, nullable=False)
    status: Mapped[ConnectorStatus] = mapped_column(
        Enum(ConnectorStatus, name="connectorstatus", values_callable=lambda enum: [e.value for e in enum]),
        default=ConnectorStatus.FAILED,
        nullable=False,
    )
    last_schema_fetch: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    schemas = relationship("Schema", back_populates="connector", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Connector id={self.connector_id} type={self.type} status={self.status}>"
