"""
Business Context API (pilot): upload/list sources, import glossary, validate/save canonical.
Ingestion and embeddings are stubbed for pilot; implementers can wire real processors.
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import List, Optional
import os
import jwt
from db import get_db
from models.business_context import ContextSource, BusinessContextCanonical, BusinessTerm
from models.tenant import Tenant
from pydantic import BaseModel, UUID4

router = APIRouter(prefix="/tenants/{tenant_id}/business-context", tags=["Business Context"])

JWT_SECRET = os.getenv("JWT_SECRET", "insecure-placeholder-change-in-env")
JWT_ALGORITHM = "HS256"


def check_auth_and_tenant(credentials: HTTPAuthorizationCredentials, tenant_id: str) -> dict:
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
    if "tenant" not in payload or "tenant_id" not in payload["tenant"] or str(payload["tenant"]["tenant_id"]) != str(tenant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant mismatch")
    return {"tenant_id": payload["tenant"]["tenant_id"], "user": payload.get("user")}


class SourceRead(BaseModel):
    source_id: UUID4
    type: str
    uri: str
    status: str

    class Config:
        from_attributes = True


@router.get("/sources", response_model=List[SourceRead])
def list_sources(tenant_id: str, db: Session = Depends(get_db), credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    check_auth_and_tenant(credentials, tenant_id)
    rows = db.query(ContextSource).filter(ContextSource.tenant_id == tenant_id).order_by(ContextSource.created_at.desc()).all()
    return rows


@router.post("/sources")
def create_source(
    tenant_id: str,
    type: str = Form(...),  # file|url|glossary
    url: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
):
    check_auth_and_tenant(credentials, tenant_id)
    if type not in ("file", "url", "glossary"):
        raise HTTPException(status_code=400, detail="Invalid source type")
    uri = None
    if type in ("url", "glossary"):
        if not url:
            raise HTTPException(status_code=400, detail="url required")
        uri = url
    else:
        if not file:
            raise HTTPException(status_code=400, detail="file required")
        # Pilot: store under /tmp; in prod, use S3
        content = file.file.read()
        path = f"/tmp/{tenant_id}_{file.filename}"
        with open(path, "wb") as f:
            f.write(content)
        uri = path
    row = ContextSource(tenant_id=tenant_id, type=type, uri=uri, status="pending")
    db.add(row)
    db.commit()
    return {"source_id": str(row.source_id), "status": row.status}


class ImportGlossaryResult(BaseModel):
    imported_rows: int


@router.post("/glossary/import", response_model=ImportGlossaryResult)
def import_glossary(tenant_id: str, file: UploadFile = File(...), db: Session = Depends(get_db), credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    check_auth_and_tenant(credentials, tenant_id)
    # Expect 2 columns: Term, Description
    import pandas as pd
    import io
    content = file.file.read()
    try:
        df = pd.read_excel(io.BytesIO(content))
    except Exception:
        df = pd.read_csv(io.BytesIO(content))
    term_col = None
    desc_col = None
    for c in df.columns:
        lc = str(c).strip().lower()
        if lc == "term" and term_col is None:
            term_col = c
        if lc.startswith("description") and desc_col is None:
            desc_col = c
    if term_col is None or desc_col is None:
        raise HTTPException(status_code=400, detail="Expected columns: Term, Description")
    imported = 0
    for _, row in df.iterrows():
        term = str(row[term_col]).strip()
        if not term:
            continue
        desc = str(row[desc_col]).strip() if not pd.isna(row[desc_col]) else ""
        bt = BusinessTerm(
            tenant_id=tenant_id,
            term=term,
            normalized_term=term.lower(),
            description=desc,
            synonyms=[],
            examples=[],
            constraints=[],
            source_ids=[],
        )
        db.add(bt)
        imported += 1
    db.commit()
    return ImportGlossaryResult(imported_rows=imported)


