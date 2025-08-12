"""
Pydantic Schemas for Tenant
Validated input/output for Tenant endpoints.
"""
from typing import Any, Dict, Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator
from constants import (
    TENANT_NAME_MAX_LENGTH,
    TENANT_PLAN_MAX_LENGTH,
    TENANT_ALLOWED_PLANS,
    TENANT_DEFAULT_CREDIT,
    TENANT_SETTINGS_DEFAULT,
)

class TenantBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=TENANT_NAME_MAX_LENGTH)
    plan: str = Field(..., min_length=1, max_length=TENANT_PLAN_MAX_LENGTH)  # Validated further below
    credit_balance: int = Field(TENANT_DEFAULT_CREDIT, ge=0)
    settings: Dict[str, Any] = Field(default_factory=lambda: TENANT_SETTINGS_DEFAULT.copy())

    @field_validator('plan')
    @classmethod
    def validate_plan(cls, v: str) -> str:
        if v not in TENANT_ALLOWED_PLANS:
            raise ValueError(f"Invalid plan. Must be one of: {', '.join(sorted(TENANT_ALLOWED_PLANS))}")
        return v

from schemas.user import UserRead

class TenantCreate(TenantBase):
    root_user_name: str = Field(..., min_length=2, max_length=80)
    root_user_email: str = Field(...)
    root_user_password: str = Field(..., min_length=8)

class TenantWithRootUserRead(TenantBase):
    tenant_id: UUID
    root_user: UserRead

    class Config:
        from_attributes = True

class TenantRead(TenantBase):
    tenant_id: UUID

    class Config:
        from_attributes = True
