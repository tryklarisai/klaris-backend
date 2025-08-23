from __future__ import annotations
from typing import Any, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from db import get_db
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os, jwt


router = APIRouter(prefix="/api/v1/usage", tags=["Usage"])
JWT_SECRET = os.getenv("JWT_SECRET", "insecure-placeholder-change-in-env")
JWT_ALGORITHM = "HS256"


def _get_tenant_from_token(credentials: HTTPAuthorizationCredentials) -> UUID:
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
    tenant = payload.get("tenant") or {}
    tenant_id = tenant.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant context missing from token")
    try:
        return UUID(str(tenant_id))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tenant id in token")


@router.get("/{tenant_id}/events")
def list_events(
    tenant_id: UUID,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
    from_ts: str | None = Query(None, alias="from"),
    to_ts: str | None = Query(None, alias="to"),
    category: str | None = None,
    model: str | None = None,
    operation: str | None = None,
    page: int = 1,
    limit: int = 50,
):
    token_tenant = _get_tenant_from_token(credentials)
    if str(token_tenant) != str(tenant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant mismatch")
    page = max(1, int(page))
    limit = max(1, min(200, int(limit)))
    where = ["tenant_id::text = :tenant"]
    params: dict[str, Any] = {"tenant": str(tenant_id)}
    if from_ts:
        where.append("occurred_at >= :from_ts")
        params["from_ts"] = from_ts
    if to_ts:
        where.append("occurred_at <= :to_ts")
        params["to_ts"] = to_ts
    if category:
        where.append("category = :category")
        params["category"] = category
    if model:
        where.append("model = :model")
        params["model"] = model
    if operation:
        where.append("operation = :operation")
        params["operation"] = operation
    where_sql = " AND ".join(where)
    s = text(f"SELECT * FROM usage_events WHERE {where_sql} ORDER BY occurred_at DESC LIMIT :limit OFFSET :offset")
    params.update({"limit": limit, "offset": (page - 1) * limit})
    rows = [dict(r._mapping) for r in db.execute(s, params)]
    return {"events": rows}


@router.get("/{tenant_id}/series")
def hourly_series(
    tenant_id: UUID,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
    from_ts: str | None = Query(None, alias="from"),
    to_ts: str | None = Query(None, alias="to"),
    category: str | None = None,
    model: str | None = None,
    operation: str | None = None,
):
    token_tenant = _get_tenant_from_token(credentials)
    if str(token_tenant) != str(tenant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant mismatch")
    where = ["tenant_id::text = :tenant"]
    params: dict[str, Any] = {"tenant": str(tenant_id)}
    if from_ts:
        where.append("occurred_at >= :from_ts")
        params["from_ts"] = from_ts
    if to_ts:
        where.append("occurred_at <= :to_ts")
        params["to_ts"] = to_ts
    if category:
        where.append("category = :category")
        params["category"] = category
    if model:
        where.append("model = :model")
        params["model"] = model
    if operation:
        where.append("operation = :operation")
        params["operation"] = operation
    where_sql = " AND ".join(where)
    s = text(
        f"""
        SELECT date_trunc('hour', occurred_at) AS hour,
               coalesce(sum(input_tokens),0) AS input_tokens,
               coalesce(sum(output_tokens),0) AS output_tokens,
               coalesce(sum(total_tokens),0) AS total_tokens
        FROM usage_events
        WHERE {where_sql}
        GROUP BY 1
        ORDER BY 1
        """
    )
    rows = [dict(r._mapping) for r in db.execute(s, params)]
    return {"series": rows}


@router.get("/{tenant_id}/summary")
def usage_summary(
    tenant_id: UUID,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
    from_ts: str | None = Query(None, alias="from"),
    to_ts: str | None = Query(None, alias="to"),
):
    token_tenant = _get_tenant_from_token(credentials)
    if str(token_tenant) != str(tenant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant mismatch")
    where = ["tenant_id::text = :tenant"]
    params: dict[str, Any] = {"tenant": str(tenant_id)}
    if from_ts:
        where.append("occurred_at >= :from_ts")
        params["from_ts"] = from_ts
    if to_ts:
        where.append("occurred_at <= :to_ts")
        params["to_ts"] = to_ts
    where_sql = " AND ".join(where)
    total = db.execute(text(f"SELECT coalesce(sum(input_tokens),0) AS input_tokens, coalesce(sum(output_tokens),0) AS output_tokens, coalesce(sum(total_tokens),0) AS total_tokens FROM usage_events WHERE {where_sql}"), params).first()
    by_category = [dict(r._mapping) for r in db.execute(text(f"SELECT category, coalesce(sum(total_tokens),0) AS total_tokens FROM usage_events WHERE {where_sql} GROUP BY 1 ORDER BY 2 DESC"), params)]
    by_model = [dict(r._mapping) for r in db.execute(text(f"SELECT model, coalesce(sum(total_tokens),0) AS total_tokens FROM usage_events WHERE {where_sql} GROUP BY 1 ORDER BY 2 DESC"), params)]
    return {
        "total": dict(total._mapping) if total else {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        "by_category": by_category,
        "by_model": by_model,
    }


