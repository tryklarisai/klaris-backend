from __future__ import annotations

from typing import Any, List
from uuid import UUID
from datetime import datetime
import os
import io

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from sqlalchemy import text, bindparam
from sqlalchemy.orm import Session

from db import get_db
from schemas.bcl import (
    DocumentUploadResponse,
    GroundRequest,
    GroundResponse,
    TermRead,
    EvidenceSnippet,
    ImportGlossaryResponse,
    CreateMappingRequest,
    MappingUpdateRequest,
    TermMappingRead,
    ProposeMappingsResponse,
    ProposalRead,
    ListProposalsResponse,
    AcceptRejectResponse,
)
from services.bcl_ingestion import ingest_document
from models.bcl import BclDocument, BclChunk, BclTerm, BclTermAlias, BclTermMapping, BclMappingProposal
from pgvector.sqlalchemy import Vector
from services.bcl_proposer import propose_mappings_for_all_terms


router = APIRouter(prefix="/api/v1/bcl", tags=["BCL"])


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


@router.post("/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(api_key_or_bearer),
) -> DocumentUploadResponse:
    content = await file.read()
    uri = f"upload://{file.filename}"
    result = ingest_document(
        db,
        auth.tenant_id,
        uri=uri,
        filename=file.filename,
        mime_type=file.content_type,
        content=content,
    )
    return DocumentUploadResponse(**result)


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
    aliases_created = 0

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
        aliases = str(row.get("Aliases") or row.get("aliases") or "").strip()
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
                created_at=datetime.utcnow(),
            )
            db.add(term_obj)
            terms_upserted += 1
            db.flush()

        # Aliases
        if aliases:
            alias_list = [a.strip() for a in aliases.split(",") if a.strip()]
            for a in alias_list:
                na = _normalize_term(a)
                exists_alias = db.query(BclTermAlias).filter(
                    BclTermAlias.tenant_id == auth.tenant_id,
                    BclTermAlias.normalized_alias == na,
                ).first()
                if exists_alias:
                    continue
                alias_obj = BclTermAlias(
                    tenant_id=auth.tenant_id,
                    term_id=term_obj.term_id,
                    alias=a,
                    normalized_alias=na,
                    created_at=datetime.utcnow(),
                )
                db.add(alias_obj)
                aliases_created += 1

    db.commit()
    return ImportGlossaryResponse(terms_upserted=terms_upserted, aliases_created=aliases_created, rows_processed=rows_processed)


@router.post("/ground", response_model=GroundResponse)
async def ground(
    payload: GroundRequest,
    db: Session = Depends(get_db),
    auth: AuthContext = Depends(api_key_or_bearer),
) -> GroundResponse:
    from services.embeddings import get_embeddings_client
    client = get_embeddings_client()
    [query_vec] = client.embed([payload.query])

    # Terms by vector + FTS hybrid
    top_k_terms = max(1, int(payload.top_k_terms))
    term_rows: List[dict] = []
    # Vector first
    q1 = text(
        """
        SELECT t.term_id::text, t.term, t.normalized_term, t.description,
               1 - (t.embedding <=> :qvec) AS score
        FROM bcl_terms t
        WHERE t.tenant_id::text = :tenant
          AND t.embedding IS NOT NULL
        ORDER BY t.embedding <=> :qvec
        LIMIT :k
        """
    ).bindparams(bindparam("qvec", type_=Vector()))
    for r in db.execute(q1, {"qvec": query_vec, "tenant": str(auth.tenant_id), "k": top_k_terms}):
        term_rows.append(dict(r._mapping))
    # FTS fallback if not enough
    if len(term_rows) < top_k_terms:
        q2 = text(
            """
            SELECT t.term_id::text, t.term, t.normalized_term, t.description,
                   0.5 AS score
            FROM bcl_terms t
            WHERE t.tenant_id::text = :tenant
              AND to_tsvector('english', coalesce(t.term,'') || ' ' || coalesce(t.description,'')) @@ plainto_tsquery('english', :q)
            LIMIT :k
            """
        )
        for r in db.execute(q2, {"tenant": str(auth.tenant_id), "q": payload.query, "k": top_k_terms - len(term_rows)}):
            term_rows.append(dict(r._mapping))

    # Load aliases and mappings for each term
    terms: List[TermRead] = []
    for tr in term_rows:
        t_id = tr["term_id"]
        aliases = [a.alias for a in db.query(BclTermAlias).filter(BclTermAlias.term_id == t_id).all()]
        mappings = [
            TermMappingRead(
                mapping_id=str(m.mapping_id),
                target_kind=m.target_kind,
                entity_name=m.entity_name,
                field_name=m.field_name,
                expression=m.expression,
                filter=m.filter,
                rationale=m.rationale,
                confidence=m.confidence,
            ) for m in db.query(BclTermMapping).filter(BclTermMapping.term_id == t_id).all()
        ]
        terms.append(
            TermRead(
                term_id=t_id,
                term=tr["term"],
                normalized_term=tr["normalized_term"],
                description=tr.get("description"),
                aliases=aliases,
                mappings=mappings,
                score=float(tr.get("score") or 0.0),
            )
        )

    # Evidence from chunks
    top_k_evidence = max(1, int(payload.top_k_evidence))
    evidences: List[EvidenceSnippet] = []
    q3 = text(
        """
        SELECT c.chunk_id::text, c.text, 1 - (c.embedding <=> :qvec) AS score,
               c.document_id::text AS document_id,
               d.uri AS document_uri,
               c.metadata
        FROM bcl_chunks c
        JOIN bcl_documents d ON d.document_id = c.document_id
        WHERE c.tenant_id::text = :tenant
        ORDER BY c.embedding <=> :qvec
        LIMIT :k
        """
    ).bindparams(bindparam("qvec", type_=Vector()))
    for r in db.execute(q3, {"qvec": query_vec, "tenant": str(auth.tenant_id), "k": top_k_evidence}):
        m = dict(r._mapping)
        evidences.append(
            EvidenceSnippet(
                chunk_id=m["chunk_id"],
                text=m["text"],
                score=float(m["score"]),
                document_id=m["document_id"],
                document_uri=m.get("document_uri"),
                metadata=m.get("metadata"),
            )
        )

    return GroundResponse(terms=terms, evidence=evidences)


@router.get("/terms/{term_id}/mappings", response_model=List[TermMappingRead])
def list_mappings(term_id: UUID, db: Session = Depends(get_db), auth: AuthContext = Depends(api_key_or_bearer)) -> List[TermMappingRead]:
    rows = db.query(BclTermMapping).filter(
        BclTermMapping.term_id == term_id,
        BclTermMapping.tenant_id == auth.tenant_id,
    ).all()
    return [
        TermMappingRead(
            mapping_id=str(m.mapping_id),
            target_kind=m.target_kind,
            entity_name=m.entity_name,
            field_name=m.field_name,
            expression=m.expression,
            filter=m.filter,
            rationale=m.rationale,
            confidence=m.confidence,
        ) for m in rows
    ]


@router.post("/terms/{term_id}/mappings", response_model=TermMappingRead)
def create_mapping(term_id: UUID, payload: CreateMappingRequest, db: Session = Depends(get_db), auth: AuthContext = Depends(api_key_or_bearer)) -> TermMappingRead:
    term = db.query(BclTerm).filter(BclTerm.term_id == term_id, BclTerm.tenant_id == auth.tenant_id).first()
    if not term:
        raise HTTPException(status_code=404, detail="Term not found")
    m = BclTermMapping(
        tenant_id=auth.tenant_id,
        term_id=term.term_id,
        target_kind=payload.target_kind,
        entity_name=payload.entity_name,
        field_name=payload.field_name,
        expression=payload.expression,
        filter=payload.filter,
        rationale=payload.rationale,
        confidence=payload.confidence,
        created_at=datetime.utcnow(),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return TermMappingRead(
        mapping_id=str(m.mapping_id),
        target_kind=m.target_kind,
        entity_name=m.entity_name,
        field_name=m.field_name,
        expression=m.expression,
        filter=m.filter,
        rationale=m.rationale,
        confidence=m.confidence,
    )


@router.put("/mappings/{mapping_id}", response_model=TermMappingRead)
def update_mapping(mapping_id: UUID, payload: MappingUpdateRequest, db: Session = Depends(get_db), auth: AuthContext = Depends(api_key_or_bearer)) -> TermMappingRead:
    m = db.query(BclTermMapping).filter(BclTermMapping.mapping_id == mapping_id, BclTermMapping.tenant_id == auth.tenant_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Mapping not found")
    for field in ["target_kind", "entity_name", "field_name", "expression", "filter", "rationale", "confidence"]:
        val = getattr(payload, field)
        if val is not None:
            setattr(m, field, val)
    db.commit()
    db.refresh(m)
    return TermMappingRead(
        mapping_id=str(m.mapping_id),
        target_kind=m.target_kind,
        entity_name=m.entity_name,
        field_name=m.field_name,
        expression=m.expression,
        filter=m.filter,
        rationale=m.rationale,
        confidence=m.confidence,
    )


@router.delete("/mappings/{mapping_id}", status_code=204, response_class=Response)
def delete_mapping(mapping_id: UUID, db: Session = Depends(get_db), auth: AuthContext = Depends(api_key_or_bearer)) -> Response:
    m = db.query(BclTermMapping).filter(BclTermMapping.mapping_id == mapping_id, BclTermMapping.tenant_id == auth.tenant_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Mapping not found")
    db.delete(m)
    db.commit()
    return Response(status_code=204)


@router.post("/propose-mappings", response_model=ProposeMappingsResponse)
def propose_mappings(db: Session = Depends(get_db), auth: AuthContext = Depends(api_key_or_bearer)) -> ProposeMappingsResponse:
    result = propose_mappings_for_all_terms(db, auth.tenant_id)
    return ProposeMappingsResponse(**result)


@router.get("/proposals", response_model=ListProposalsResponse)
def list_proposals(db: Session = Depends(get_db), auth: AuthContext = Depends(api_key_or_bearer)) -> ListProposalsResponse:
    rows = db.query(BclMappingProposal, BclTerm).join(BclTerm, BclTerm.term_id == BclMappingProposal.term_id).filter(
        BclMappingProposal.tenant_id == auth.tenant_id
    ).order_by(BclMappingProposal.created_at.desc()).all()
    items: List[ProposalRead] = []
    for mp, term in rows:
        items.append(ProposalRead(
            proposal_id=str(mp.proposal_id),
            term_id=str(term.term_id),
            term=term.term,
            target_kind=mp.target_kind,
            entity_name=mp.entity_name,
            field_name=mp.field_name,
            expression=mp.expression,
            filter=mp.filter,
            rationale=mp.rationale,
            confidence=mp.confidence,
            evidence=mp.evidence,
            created_at=mp.created_at.isoformat() + "Z",
        ))
    return ListProposalsResponse(proposals=items)


@router.post("/proposals/{proposal_id}/accept", response_model=AcceptRejectResponse)
def accept_proposal(proposal_id: UUID, db: Session = Depends(get_db), auth: AuthContext = Depends(api_key_or_bearer)) -> AcceptRejectResponse:
    mp = db.query(BclMappingProposal).filter(
        BclMappingProposal.proposal_id == proposal_id,
        BclMappingProposal.tenant_id == auth.tenant_id,
    ).first()
    if not mp:
        raise HTTPException(status_code=404, detail="Proposal not found")
    # Create mapping
    m = BclTermMapping(
        tenant_id=auth.tenant_id,
        term_id=mp.term_id,
        target_kind=mp.target_kind,
        entity_name=mp.entity_name,
        field_name=mp.field_name,
        expression=mp.expression,
        filter=mp.filter,
        rationale=mp.rationale,
        confidence=mp.confidence,
        created_at=datetime.utcnow(),
    )
    db.add(m)
    # Delete proposal after accept
    db.delete(mp)
    db.commit()
    db.refresh(m)
    return AcceptRejectResponse(status="accepted", mapping=TermMappingRead(
        mapping_id=str(m.mapping_id),
        target_kind=m.target_kind,
        entity_name=m.entity_name,
        field_name=m.field_name,
        expression=m.expression,
        filter=m.filter,
        rationale=m.rationale,
        confidence=m.confidence,
    ))


@router.post("/proposals/{proposal_id}/reject", response_model=AcceptRejectResponse)
def reject_proposal(proposal_id: UUID, db: Session = Depends(get_db), auth: AuthContext = Depends(api_key_or_bearer)) -> AcceptRejectResponse:
    mp = db.query(BclMappingProposal).filter(
        BclMappingProposal.proposal_id == proposal_id,
        BclMappingProposal.tenant_id == auth.tenant_id,
    ).first()
    if not mp:
        raise HTTPException(status_code=404, detail="Proposal not found")
    db.delete(mp)
    db.commit()
    return AcceptRejectResponse(status="rejected", mapping=None)


