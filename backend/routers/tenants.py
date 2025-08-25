"""
FastAPI router for Tenant onboarding & management.
"""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID
from models.tenant import Tenant
from models.user import User
from schemas.tenant import TenantCreate, TenantWithRootUserRead, TenantRead
from schemas.user import UserRead
from db import get_db
from constants import TENANT_LIST_LIMIT, TENANT_SETTINGS_DEFAULT
import re
from sqlalchemy.exc import SQLAlchemyError
from passlib.context import CryptContext
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/tenants", tags=["Tenants"])
# Public router (no auth via middleware) for signup-only endpoint
public_router = APIRouter(prefix="/api/v1", tags=["Tenants"])

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Helper: password complexity check
password_regex = re.compile(r"^(?=.*[A-Za-z])(?=.*\d)(?=.*[^A-Za-z\d]).{8,}$")

def verify_password_complexity(password: str) -> bool:
    return bool(password_regex.match(password))

@router.post("/", response_model=TenantWithRootUserRead, status_code=status.HTTP_201_CREATED)
def create_tenant(payload: TenantCreate, db: Session = Depends(get_db)) -> TenantWithRootUserRead:
    """Create a new tenant (onboard with root user)."""
    # Check password complexity
    if not verify_password_complexity(payload.root_user_password):
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters, include at least one letter, one number, and one symbol.")

    tenant = Tenant(
        name=payload.name,
        plan=payload.plan,
        credit_balance=payload.credit_balance,
        settings=payload.settings or TENANT_SETTINGS_DEFAULT.copy(),
    )
    hashed_pw = pwd_context.hash(payload.root_user_password)
    root_user = User(
        tenant_id=None,  # Set after tenant commit
        name=payload.root_user_name,
        email=payload.root_user_email,
        hashed_password=hashed_pw,
        is_root=True,
    )
    try:
        db.add(tenant)
        db.flush()  # to get tenant.tenant_id
        root_user.tenant_id = tenant.tenant_id
        db.add(root_user)
        db.commit()
        db.refresh(tenant)
        db.refresh(root_user)
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not create tenant and root user: " + str(e))
    return TenantWithRootUserRead(
        tenant_id=tenant.tenant_id,
        name=tenant.name,
        plan=tenant.plan,
        credit_balance=tenant.credit_balance,
        settings=tenant.settings,
        root_user=UserRead.model_validate(root_user),
    )


@public_router.post("/register-new-tenant", response_model=TenantWithRootUserRead, status_code=status.HTTP_201_CREATED)
def register_new_tenant(payload: TenantCreate, db: Session = Depends(get_db)) -> TenantWithRootUserRead:
    """Public signup endpoint: create a new tenant with a root user (no auth required)."""
    if not verify_password_complexity(payload.root_user_password):
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters, include at least one letter, one number, and one symbol.")

    tenant = Tenant(
        name=payload.name,
        plan=payload.plan,
        credit_balance=payload.credit_balance,
        settings=payload.settings or TENANT_SETTINGS_DEFAULT.copy(),
    )
    hashed_pw = pwd_context.hash(payload.root_user_password)
    root_user = User(
        tenant_id=None,
        name=payload.root_user_name,
        email=payload.root_user_email,
        hashed_password=hashed_pw,
        is_root=True,
    )
    try:
        db.add(tenant)
        db.flush()
        root_user.tenant_id = tenant.tenant_id
        db.add(root_user)
        db.commit()
        db.refresh(tenant)
        db.refresh(root_user)
    except SQLAlchemyError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Could not create tenant and root user: " + str(e))
    return TenantWithRootUserRead(
        tenant_id=tenant.tenant_id,
        name=tenant.name,
        plan=tenant.plan,
        credit_balance=tenant.credit_balance,
        settings=tenant.settings,
        root_user=UserRead.model_validate(root_user),
    )

@router.get("/{tenant_id}", response_model=TenantRead)
def get_tenant(tenant_id: UUID, db: Session = Depends(get_db)) -> TenantRead:
    """Fetch a single tenant by UUID."""
    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return TenantRead.model_validate(tenant)

@router.get("/", response_model=List[TenantRead])
def list_tenants(db: Session = Depends(get_db)) -> List[TenantRead]:
    """List all tenants (for onboarding/admin)."""
    tenants = db.query(Tenant).order_by(Tenant.name).limit(TENANT_LIST_LIMIT).all()
    return [TenantRead.model_validate(t) for t in tenants]


class TenantSettingsRead(BaseModel):
    settings: dict


class TenantSettingsUpdate(BaseModel):
    settings: dict


@router.get("/{tenant_id}/settings", response_model=TenantSettingsRead)
def get_tenant_settings(tenant_id: UUID, db: Session = Depends(get_db)) -> TenantSettingsRead:
    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return TenantSettingsRead(settings=tenant.settings or TENANT_SETTINGS_DEFAULT)


@router.put("/{tenant_id}/settings", response_model=TenantSettingsRead)
def update_tenant_settings(tenant_id: UUID, payload: TenantSettingsUpdate, db: Session = Depends(get_db)) -> TenantSettingsRead:
    tenant = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    tenant.settings = payload.settings or {}
    db.commit()
    db.refresh(tenant)
    return TenantSettingsRead(settings=tenant.settings)
