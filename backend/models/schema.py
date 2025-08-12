"""
Schema DB Model
Production-grade: type-safe, linted, SQLAlchemy 2.0+ ORM style.
Stores the most recent fetched schema per connector and tenant.
"""
from __future__ import annotations
import uuid
from typing import Any
from sqlalchemy import Column, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime
from .base import Base

class Schema(Base):
    __tablename__ = "schemas"

    schema_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    connector_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("connectors.connector_id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False)
    raw_schema: Mapped[Any] = mapped_column(JSONB, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    connector = relationship("Connector", back_populates="schemas")

    def __repr__(self) -> str:
        return f"<Schema id={self.schema_id} connector_id={self.connector_id} fetched_at={self.fetched_at.isoformat()}>"
