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
from models.business_context import ContextSource, BusinessContextCanonical, BusinessTerm, ContextReview
from models.schema_review import GlobalCanonicalSchema
from services.llm_client import get_llm_client
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


class TermRead(BaseModel):
    term_id: UUID4
    term: str
    description: str | None = None
    synonyms: list[str] | None = None
    examples: list[str] | None = None
    constraints: list[str] | None = None

    class Config:
        from_attributes = True


@router.get("/terms", response_model=list[TermRead])
def list_terms(
    tenant_id: str,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
):
    check_auth_and_tenant(credentials, tenant_id)
    query = db.query(BusinessTerm).filter(BusinessTerm.tenant_id == tenant_id)
    if q:
        ql = f"%{q.lower()}%"
        query = query.filter(BusinessTerm.normalized_term.ilike(ql))
    rows = query.order_by(BusinessTerm.created_at.desc()).offset(offset).limit(limit).all()
    return rows


class TermPatch(BaseModel):
    term: str | None = None
    description: str | None = None
    synonyms: list[str] | None = None
    examples: list[str] | None = None
    constraints: list[str] | None = None


@router.patch("/terms/{term_id}", response_model=TermRead)
def update_term(
    tenant_id: str,
    term_id: str,
    body: TermPatch,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
):
    check_auth_and_tenant(credentials, tenant_id)
    term = db.query(BusinessTerm).filter(BusinessTerm.tenant_id == tenant_id, BusinessTerm.term_id == term_id).first()
    if not term:
        raise HTTPException(status_code=404, detail="Term not found")
    if body.term is not None:
        t = body.term.strip()
        if not t:
            raise HTTPException(status_code=400, detail="term cannot be empty")
        term.term = t
        term.normalized_term = t.lower()
    if body.description is not None:
        term.description = body.description
    if body.synonyms is not None:
        term.synonyms = body.synonyms
    if body.examples is not None:
        term.examples = body.examples
    if body.constraints is not None:
        term.constraints = body.constraints
    db.commit()
    return TermRead.model_validate(term)


# ----- LLM Review: normalize terms and propose mappings -----
class CreateBCReviewRequest(BaseModel):
    max_terms: int | None = None


@router.post("/reviews")
def create_bc_review(
    tenant_id: str,
    body: CreateBCReviewRequest,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
):
    check_auth_and_tenant(credentials, tenant_id)
    # Load terms
    q = db.query(BusinessTerm).filter(BusinessTerm.tenant_id == tenant_id)
    terms = q.order_by(BusinessTerm.created_at.desc()).all()
    if not terms:
        raise HTTPException(status_code=400, detail="No glossary terms imported yet")
    if body.max_terms:
        terms = terms[: body.max_terms]
    # Load latest global canonical entities/fields
    latest = db.query(GlobalCanonicalSchema).filter_by(tenant_id=tenant_id).order_by(GlobalCanonicalSchema.version.desc()).first()
    if not latest:
        raise HTTPException(status_code=400, detail="Global canonical not available. Run Data Relationships first.")
    canonical = latest.canonical_graph or {}
    entities = canonical.get("unified_entities", [])

    provider, model, client = get_llm_client()
    import json
    snapshot = {
        "terms": [
            {
                "term": t.term,
                "description": t.description,
                "synonyms": t.synonyms or [],
            }
            for t in terms
        ],
        "entities": [
            {
                "name": e.get("name"),
                "fields": [
                    {
                        "name": f.get("name"),
                        "semantic_type": f.get("semantic_type"),
                        "data_type": f.get("data_type"),
                        "nullable": f.get("nullable"),
                    }
                    for f in (e.get("fields") or [])
                ],
            }
            for e in entities
        ],
    }
    system = "You are a precise business glossary assistant. Return ONLY valid JSON matching the output schema."
    output_hint = {
        "terms": [
            {
                "term": "string",
                "normalized_term": "string",
                "description": "string",
                "synonyms": ["string"],
                "mappings": [
                    {"entity_name": "string", "field_name": "string", "metric_def": "string", "rationale": "string", "confidence": 0.0}
                ],
            }
        ]
    }
    prompt = (
        "Given the business glossary terms and the available entities/fields below (with semantic_type/data_type), normalize terms, expand synonyms, and propose mappings.\n"
        "RULES:\n"
        "1) Use entity/field names exactly as provided.\n"
        "2) When a term implies a computable rule (e.g., 'sales > 100000', 'top 10%', 'count of orders'), include a metric_def that expresses the computation explicitly, including the numeric threshold and aggregation, e.g.:\n"
        "   'metric_def': 'SUM(Order.total_amount) > 100000' or 'COUNT(Order.order_id) >= 5'.\n"
        "3) Prefer fields whose semantic_type suggests the correct measure (amount, currency, count, date).\n"
        "Return valid JSON only matching: " + json.dumps(output_hint) + "\n\n"
        "Glossary terms JSON:\n" + json.dumps(snapshot["terms"]) + "\n\n" +
        "Entities JSON:\n" + json.dumps(snapshot["entities"]) + "\n"
    )
    review = ContextReview(
        tenant_id=tenant_id,
        provider=provider,
        model=model,
        status="pending",
        input_snapshot=snapshot,
    )
    db.add(review)
    db.flush()
    try:
        parsed, usage = client.review_schema(prompt=prompt, system=system)
        review.suggestions = parsed
        review.status = "succeeded"
        review.token_usage = usage
        from datetime import datetime as dt
        review.completed_at = dt.utcnow()
        db.commit()
    except Exception as e:
        review.status = "failed"
        review.suggestions = None
        review.token_usage = None
        db.commit()
        raise HTTPException(status_code=500, detail=f"LLM review failed: {e}")
    return {
        "review_id": str(review.review_id),
        "suggestions": review.suggestions,
        "input_snapshot": snapshot,
        "status": review.status,
        "provider": review.provider,
        "model": review.model,
    }


@router.get("/reviews/{review_id}")
def get_bc_review(tenant_id: str, review_id: str, db: Session = Depends(get_db), credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    check_auth_and_tenant(credentials, tenant_id)
    r = db.query(ContextReview).filter(ContextReview.tenant_id == tenant_id, ContextReview.review_id == review_id).first()
    if not r:
        raise HTTPException(status_code=404, detail="Review not found")
    return {
        "review_id": str(r.review_id),
        "suggestions": r.suggestions,
        "status": r.status,
        "provider": r.provider,
        "model": r.model,
    }


# ----- Canonical validate/save/latest (optimistic concurrency) -----
class ValidateBody(BaseModel):
    canonical_context: dict


@router.post("/canonical/validate")
def validate_canonical(tenant_id: str, body: ValidateBody, credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    check_auth_and_tenant(credentials, tenant_id)
    g = body.canonical_context or {}
    errs: list[dict] = []

    def err(path: str, msg: str):
        errs.append({"path": path, "message": msg})

    max_terms = int(os.getenv("CONTEXT_MAX_TERMS", "2000"))
    max_maps = int(os.getenv("CONTEXT_MAX_MAPPINGS", "5000"))
    terms = g.get("terms") or []
    if not isinstance(terms, list):
        err("/terms", "must be a list")
    else:
        if len(terms) > max_terms:
            err("/terms", f"too many terms (>{max_terms})")
        seen = set()
        for i, t in enumerate(terms):
            nm = (t.get("normalized_term") or t.get("term") or "").strip().lower()
            if not nm:
                err(f"/terms[{i}]/normalized_term", "required")
            if nm in seen:
                err(f"/terms[{i}]/normalized_term", "duplicate term")
            seen.add(nm)
            maps = t.get("mappings") or []
            if not isinstance(maps, list):
                err(f"/terms[{i}]/mappings", "must be a list")
    # rough total mapping limit
    total_maps = sum(len(t.get("mappings") or []) for t in (terms if isinstance(terms, list) else []))
    if total_maps > max_maps:
        err("/terms/*/mappings", f"too many mappings (>{max_maps})")

    if errs:
        return {"ok": False, "errors": errs}
    return {"ok": True}


class SaveCanonicalBody(BaseModel):
    user_edits: dict
    note: Optional[str] = None
    expected_version: Optional[int] = None


@router.get("/canonical/latest")
def get_latest_canonical(tenant_id: str, db: Session = Depends(get_db), credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    check_auth_and_tenant(credentials, tenant_id)
    latest = db.query(BusinessContextCanonical).filter_by(tenant_id=tenant_id).order_by(BusinessContextCanonical.version.desc()).first()
    if not latest:
        raise HTTPException(status_code=404, detail="No business context found")
    return {
        "context_id": str(latest.context_id),
        "version": latest.version,
        "canonical_context": latest.canonical_context,
        "created_at": latest.created_at.isoformat(),
    }


@router.post("/canonical")
def save_canonical(tenant_id: str, body: SaveCanonicalBody, db: Session = Depends(get_db), credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer())):
    ctx = check_auth_and_tenant(credentials, tenant_id)
    latest = db.query(BusinessContextCanonical).filter_by(tenant_id=tenant_id).order_by(BusinessContextCanonical.version.desc()).first()
    latest_version = latest.version if latest else 0
    if body.expected_version is not None and int(body.expected_version) != int(latest_version):
        raise HTTPException(status_code=409, detail={"message": "Version conflict", "latest_version": latest_version, "latest": {"version": latest_version, "canonical_context": latest.canonical_context if latest else None}})
    next_version = 1 if not latest else latest.version + 1
    from datetime import datetime as dt
    row = BusinessContextCanonical(
        tenant_id=tenant_id,
        version=next_version,
        canonical_context=body.user_edits,
        created_at=dt.utcnow(),
        approved_by_user_id=(ctx.get("user") or {}).get("user_id"),
        approved_at=dt.utcnow(),
    )
    db.add(row)
    db.commit()
    return {"version": row.version, "canonical_context": row.canonical_context, "created_at": row.created_at.isoformat()}


