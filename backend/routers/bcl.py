from __future__ import annotations

from typing import Any, List
from uuid import UUID as _UUID
import os
import io

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from sqlalchemy import text, bindparam
from sqlalchemy.orm import Session

from db import get_db
from schemas.bcl import (
    ImportGlossaryResponse,
    GlossaryTermRead,
    GlossaryUpdateRequest,
)
from models.bcl import BclTerm
from pgvector.sqlalchemy import Vector


router = APIRouter(prefix="/api/v1/bcl", tags=["Glossary"])


# --- Auth helper: accept JWT or dev API key ---
JWT_SECRET = os.getenv("JWT_SECRET", "insecure-placeholder-change-in-env")
JWT_ALGORITHM = "HS256"
DEV_API_KEY = os.getenv("DEV_API_KEY")


class AuthContext:
    def __init__(self, tenant_id: str, user: dict | None):
        self.tenant_id = tenant_id
        self.user = user


def auth_dependency(credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=False)), tenant_override: str | None = None) -> AuthContext:  # type: ignore[override]
    # Prefer JWT Bearer
    if credentials and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except Exception:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        tenant = payload.get("tenant") or {}
        tenant_id = tenant.get("tenant_id")
        if not tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant missing")
        return AuthContext(tenant_id=tenant_id, user=payload.get("user"))

    # Fallback: X-API-Key + X-Tenant-ID headers
    from fastapi import Request
    def _from_request() -> AuthContext:
        # Local request accessor
        raise RuntimeError("This function should be overwritten by FastAPI dependency injection.")

    # If no bearer provided, inspect request headers manually
    # We can't access Request here directly without explicit dependency. So we provide a second dependency below.
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


from fastapi import Request


def api_key_or_bearer(request: Request, credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer(auto_error=False))) -> AuthContext:
    # Try bearer first
    if credentials and credentials.scheme.lower() == "bearer":
        token = credentials.credentials
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        except Exception:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        tenant = payload.get("tenant") or {}
        tenant_id = tenant.get("tenant_id")
        if not tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant missing")
        return AuthContext(tenant_id=tenant_id, user=payload.get("user"))
    # Fallback to API key in dev
    if DEV_API_KEY:
        provided = request.headers.get("X-API-Key")
        tenant_id = request.headers.get("X-Tenant-ID")
        if provided and tenant_id and provided == DEV_API_KEY:
            return AuthContext(tenant_id=tenant_id, user=None)
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


# Removed document upload; glossary-only


def _normalize_term(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


@router.post("/glossary/import", response_model=ImportGlossaryResponse)
async def import_glossary(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(api_key_or_bearer),
) -> ImportGlossaryResponse:
    import pandas as pd
    bytes_data = await file.read()
    rows_processed = 0
    terms_upserted = 0
    aliases_created = 0  # kept in response for backward-compat; remains 0 in glossary-only

    # Read CSV/XLSX
    if file.filename and file.filename.lower().endswith(".csv"):
        buf = io.BytesIO(bytes_data)  # type: ignore[name-defined]
        df = pd.read_csv(buf, dtype=str).fillna("")
    else:
        buf = io.BytesIO(bytes_data)  # type: ignore[name-defined]
        df = pd.read_excel(buf, dtype=str).fillna("")

    for _, row in df.iterrows():
        rows_processed += 1
        term = str(row.get("Term") or row.get("term") or "").strip()
        desc = str(row.get("Description") or row.get("description") or "").strip()
        if not term:
            continue
        norm = _normalize_term(term)
        # Upsert term by (tenant_id, normalized_term)
        existing = db.query(BclTerm).filter(
            BclTerm.tenant_id == auth.tenant_id,
            BclTerm.normalized_term == norm,
        ).first()
        if existing:
            existing.term = term
            existing.description = desc or existing.description
            terms_upserted += 1
            term_obj = existing
        else:
            term_obj = BclTerm(
                tenant_id=auth.tenant_id,
                term=term,
                normalized_term=norm,
                description=desc or None,
                created_at=__import__("datetime").datetime.utcnow(),
            )
            db.add(term_obj)
            terms_upserted += 1
            db.flush()

    # Optional embedding of terms (term + description)
    try:
        from services.embeddings import embed_and_log
        # Fetch all updated/new terms for this tenant (simple approach)
        rows = db.query(BclTerm).filter(BclTerm.tenant_id == auth.tenant_id).all()
        texts: List[str] = []
        ids: List[str] = []
        for t in rows:
            txt = f"{t.term} - {t.description or ''}".strip()
            texts.append(txt)
            ids.append(str(t.term_id))
        if texts:
            vecs = embed_and_log(db, auth.tenant_id, texts, category="bcl_glossary")
            # Bulk update – best-effort per row
            for i, v in enumerate(vecs):
                db.execute(text("UPDATE bcl_terms SET embedding = :emb WHERE term_id::text = :id"), {"emb": v, "id": ids[i]})
    except Exception:
        pass

    db.commit()
    return ImportGlossaryResponse(terms_upserted=terms_upserted, aliases_created=aliases_created, rows_processed=rows_processed)


# Removed ground endpoint; glossary-only


# Removed mapping routes


# Removed mapping routes


# Removed mapping routes


# Removed mapping routes


# Removed proposals routes


@router.get("/terms")
def search_terms(q: str = "", top_k: int = 10, db: Session = Depends(get_db), auth: AuthContext = Depends(api_key_or_bearer)):
    q = (q or "").strip()
    results: List[dict] = []
    if not q:
        rows = db.query(BclTerm).filter(BclTerm.tenant_id == auth.tenant_id).order_by(BclTerm.term.asc()).limit(min(int(top_k), 50)).all()
        return {"terms": [{"term_id": str(t.term_id), "term": t.term, "description": t.description} for t in rows]}
    # Try vector
    try:
        from services.embeddings import embed_and_log
        [qvec] = embed_and_log(db, auth.tenant_id, [q], category="bcl_glossary")
        s = text(
            """
            SELECT term_id::text, term, description, 1 - (embedding <=> :qvec) AS score
            FROM bcl_terms
            WHERE tenant_id::text = :tenant AND embedding IS NOT NULL
            ORDER BY embedding <=> :qvec
            LIMIT :k
            """
        ).bindparams(bindparam("qvec", type_=Vector()))
        for r in db.execute(s, {"qvec": qvec, "tenant": str(auth.tenant_id), "k": int(top_k)}):
            results.append(dict(r._mapping))
    except Exception:
        results = []
    # FTS fallback
    if len(results) < int(top_k):
        s2 = text(
            """
            SELECT term_id::text, term, description, 0.5 AS score
            FROM bcl_terms
            WHERE tenant_id::text = :tenant
              AND to_tsvector('english', coalesce(term,'') || ' ' || coalesce(description,'')) @@ plainto_tsquery('english', :q)
            LIMIT :k
            """
        )
        for r in db.execute(s2, {"tenant": str(auth.tenant_id), "q": q, "k": int(top_k) - len(results)}):
            results.append(dict(r._mapping))
    return {"terms": results}


@router.get("/terms/{term_id}", response_model=GlossaryTermRead)
def get_term(term_id: str, db: Session = Depends(get_db), auth: AuthContext = Depends(api_key_or_bearer)) -> GlossaryTermRead:
    try:
        term_uuid = _UUID(term_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid term_id")
    t = db.query(BclTerm).filter(BclTerm.tenant_id == auth.tenant_id, BclTerm.term_id == term_uuid).first()
    if not t:
        raise HTTPException(status_code=404, detail="Term not found")
    return GlossaryTermRead(term_id=str(t.term_id), term=t.term, description=t.description)


@router.put("/terms/{term_id}", response_model=GlossaryTermRead)
def update_term(term_id: str, payload: GlossaryUpdateRequest, db: Session = Depends(get_db), auth: AuthContext = Depends(api_key_or_bearer)) -> GlossaryTermRead:
    try:
        term_uuid = _UUID(term_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid term_id")
    t = db.query(BclTerm).filter(BclTerm.tenant_id == auth.tenant_id, BclTerm.term_id == term_uuid).first()
    if not t:
        raise HTTPException(status_code=404, detail="Term not found")
    if payload.term is not None:
        t.term = payload.term
        t.normalized_term = _normalize_term(payload.term)
    if payload.description is not None:
        t.description = payload.description
    db.commit()
    db.refresh(t)
    return GlossaryTermRead(term_id=str(t.term_id), term=t.term, description=t.description)


@router.delete("/terms/{term_id}", status_code=204)
def delete_term(term_id: str, db: Session = Depends(get_db), auth: AuthContext = Depends(api_key_or_bearer)):
    try:
        term_uuid = _UUID(term_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid term_id")
    t = db.query(BclTerm).filter(BclTerm.tenant_id == auth.tenant_id, BclTerm.term_id == term_uuid).first()
    if not t:
        raise HTTPException(status_code=404, detail="Term not found")
    db.delete(t)
    db.commit()
    return None


