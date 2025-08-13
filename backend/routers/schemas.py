"""
Schemas API router
Provides a secure endpoint to fetch canonical schema information by ID.
Production-grade: tenant isolation, robust error handling, type annotations.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from uuid import UUID
from schemas.schema import SchemaRead
from db import get_db
from models.schema import Schema
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import os
from typing import Any

router = APIRouter(prefix="/schemas", tags=["Schemas"])

# --- Auth Helper (Replace/adapt to your actual get_current_user dependency) ---
JWT_SECRET = os.getenv("JWT_SECRET", "insecure-placeholder-change-in-env")
JWT_ALGORITHM = "HS256"

class UserAuth:
    """
    Minimal JWT auth extractor for pilot. Replace with your main system dependency as needed.
    Expects standard JWT payload with 'tenant' field.
    """
    def __init__(self):
        self.scheme = HTTPBearer()
    def __call__(self, credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())) -> dict:
        token = credentials.credentials
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except Exception:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
        # Basic shape: { ..., "tenant": {"tenant_id": ...}, ... }
        if "tenant" not in payload or "tenant_id" not in payload["tenant"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant context missing from token")
        return {"tenant_id": payload["tenant"]["tenant_id"], "user": payload.get("user")}

auth_dep = UserAuth()

# (Schema route has been removed. Now served under connectors.py.)
