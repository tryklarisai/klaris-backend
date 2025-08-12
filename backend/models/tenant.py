"""
Tenant DB Model
Production-grade: type-safe, linted, uses SQLAlchemy 2.0+ ORM style.
"""
from __future__ import annotations
from typing import Any
import uuid
from sqlalchemy import Column, String, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
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
