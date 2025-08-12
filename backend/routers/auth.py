"""
FastAPI router for authentication and JWT login.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from models.user import User
from models.tenant import Tenant
from schemas.user import UserLogin, UserRead
from schemas.tenant import TenantRead
from db import get_db
import os
from passlib.context import CryptContext
import jwt
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
JWT_SECRET = os.getenv("JWT_SECRET", "insecure-placeholder-change-in-env")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 8

@router.post("/login")
def login(payload: UserLogin, db: Session = Depends(get_db)):
    tenant = db.query(Tenant).filter(Tenant.name == payload.tenant_name).first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tenant not found.")
    user = db.query(User).filter(
        User.tenant_id == tenant.tenant_id,
        User.email == payload.email
    ).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")
    if not pwd_context.verify(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")
    token_data = {
        "sub": str(user.user_id),
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS),
        "user": {
            "user_id": str(user.user_id),
            "name": user.name,
            "email": user.email,
            "is_root": user.is_root,
        },
        "tenant": {
            "tenant_id": str(tenant.tenant_id),
            "name": tenant.name
        }
    }
    token = jwt.encode(token_data, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": JWT_EXPIRE_HOURS * 3600,
        "user": UserRead.model_validate(user),
        "tenant": TenantRead.model_validate(tenant)
    }
