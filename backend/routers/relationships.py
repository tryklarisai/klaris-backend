"""
Global Data Relationships router (tenant-scoped)
Builds a unified global ontology across selected connectors' latest schemas.
"""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
import os
import jwt

from db import get_db
from models.connector import Connector
from models.schema import Schema
from models.schema_review import DatasetReview, GlobalCanonicalSchema, ReviewStatusEnum
from services.llm_client import get_llm_client
from pydantic import BaseModel, UUID4, Field


router = APIRouter(prefix="/tenants/{tenant_id}/relationships", tags=["Data Relationships"])

JWT_SECRET = os.getenv("JWT_SECRET", "insecure-placeholder-change-in-env")
JWT_ALGORITHM = "HS256"


def check_auth_and_tenant(credentials: HTTPAuthorizationCredentials, tenant_id: str) -> dict:
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
    if "tenant" not in payload or "tenant_id" not in payload["tenant"] or str(payload["tenant"]["tenant_id"]) != str(tenant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant context missing or mismatch in token")
    return {"tenant_id": payload["tenant"]["tenant_id"], "user": payload.get("user")}


class CreateDatasetReviewOptions(BaseModel):
    domain: Optional[str] = None
    confidence_threshold: Optional[float] = Field(default=0.6, ge=0.0, le=1.0)
    max_entities: Optional[int] = Field(default=1000, ge=1)


class CreateDatasetReviewRequest(BaseModel):
    connector_ids: List[UUID4]
    options: Optional[CreateDatasetReviewOptions] = None


@router.post("/reviews")
def create_dataset_review(
    tenant_id: str,
    body: CreateDatasetReviewRequest,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
):
    ctx = check_auth_and_tenant(credentials, tenant_id)
    # Validate connectors and fetch latest schemas per connector
    if not body.connector_ids:
        raise HTTPException(status_code=400, detail="connector_ids required")
    id_set = {str(cid) for cid in body.connector_ids}
    connectors = db.query(Connector).filter(Connector.tenant_id == tenant_id).all()
    selected = [c for c in connectors if str(c.connector_id) in id_set and c.status.value == "active"]
    if not selected:
        raise HTTPException(status_code=400, detail="No active connectors selected")
    latest_schemas: List[Schema] = []
    connector_by_id = {str(c.connector_id): c for c in selected}
    for c in selected:
        s = db.query(Schema).filter_by(connector_id=c.connector_id, tenant_id=tenant_id).order_by(Schema.fetched_at.desc()).first()
        if s:
            latest_schemas.append(s)
    if not latest_schemas:
        raise HTTPException(status_code=400, detail="No schemas available for selected connectors")

    provider, model, client = get_llm_client()
    options = body.options or CreateDatasetReviewOptions()
    # Prepare normalized input snapshot (structure-only, entities extracted)
    import json
    def extract_entities(raw: dict) -> list:
        # raw is typically {"schema": mcp_schema, "fetched_at": ...} or just mcp_schema
        root = raw.get("schema", raw) if isinstance(raw, dict) else {}
        if isinstance(root, dict) and isinstance(root.get("entities"), list):
            return root["entities"]
        # Fallbacks for legacy shapes
        entities = []
        if isinstance(root.get("tables"), list):
            for t in root["tables"]:
                entities.append({
                    "id": f"{t.get('schema')}.{t.get('table')}",
                    "name": f"{t.get('schema')}.{t.get('table')}",
                    "kind": "table",
                    "fields": [{"name": c.get("name"), "type": c.get("type")} for c in (t.get("columns") or [])]
                })
        if isinstance(root.get("files"), list):
            for f in root["files"]:
                entities.append({
                    "id": f.get("id"),
                    "name": f.get("name"),
                    "kind": "file",
                    "fields": []
                })
        return entities

    input_entities = []
    for s in latest_schemas:
        cid = str(s.connector_id)
        conn = connector_by_id.get(cid)
        conn_type = (conn.type if conn else "").lower()
        ents = extract_entities(s.raw_schema or {})
        for e in ents:
            input_entities.append({
                "connector_id": cid,
                "connector_type": conn_type,
                "entity_id": e.get("id") or e.get("name"),
                "entity_name": e.get("name"),
                "kind": e.get("kind"),
                "fields": e.get("fields", []),
            })

    snapshot = {
        "connector_ids": [str(c.connector_id) for c in selected],
        "connectors": [{"connector_id": str(c.connector_id), "type": c.type} for c in selected],
        "schema_ids": [str(s.schema_id) for s in latest_schemas],
        "input_entities": input_entities,
        "params": options.model_dump(),
    }
    system = "You are a precise data modeling assistant. Return ONLY valid JSON matching the provided output schema."
    output_hint = {
        "unified_entities": [
            {
                "name": "string",
                "description": "string",
                "tags": ["string"],
                "confidence": 0.0,
                "fields": [
                    {
                        "name": "string",
                        "description": "string",
                        "semantic_type": "string",
                        "pii_sensitivity": "none|low|medium|high",
                        "nullable": True,
                        "data_type": "string",
                        "confidence": 0.0
                    }
                ],
                "source_mappings": [
                    {"connector_id": "uuid", "table": "string", "field": "string", "confidence": 0.0}
                ],
            }
        ],
        "cross_source_relationships": [
            {
                "from_entity": "string",
                "from_field": "string",
                "to_entity": "string",
                "to_field": "string",
                "type": "one_to_one|one_to_many|many_to_one|many_to_many|unknown",
                "description": "string",
                "confidence": 0.0
            }
        ]
    }
    # Build prompt in parts to avoid accidental truncation/escaping issues
    prompt_intro = (
        "You are given multiple connector schemas (structure only). Build a unified global ontology with entities and fields mapped across sources,"
        " including PII classification and semantic types, and infer cross-source relationships."
    )
    prompt_instr = (
        "Return valid JSON only matching this output format: " + json.dumps(output_hint) +
        "\nRequirements: (1) Cover ALL input entities across ALL connectors. "
        "(2) For each unified entity, include source_mappings for every contributing input entity with connector_id and entity/table/field names."
    )
    prompt_data = "Input entities JSON array:\n" + json.dumps(snapshot["input_entities"])  # compact to reduce length
    prompt = prompt_intro + "\n" + prompt_instr + "\n\n" + prompt_data

    review = DatasetReview(
        tenant_id=tenant_id,
        provider=provider,
        model=model,
        status=ReviewStatusEnum.pending.value,
        input_snapshot=snapshot,
        suggestions=None,
    )
    db.add(review)
    db.flush()
    try:
        # Chunking to avoid timeouts and token overflows
        max_per_call = int(os.getenv("DATASET_REVIEW_MAX_ENTITIES_PER_CALL", "150"))
        chunks = [input_entities[i:i+max_per_call] for i in range(0, len(input_entities), max_per_call)]
        merged = {"unified_entities": [], "cross_source_relationships": []}
        total_usage: dict = {}

        def accumulate_usage(dst: dict, src: dict):
            if not isinstance(src, dict):
                return
            for k, v in src.items():
                if isinstance(v, (int, float)):
                    dst[k] = (dst.get(k) or 0) + v
                elif isinstance(v, dict):
                    if k not in dst or not isinstance(dst.get(k), dict):
                        dst[k] = {}
                    accumulate_usage(dst[k], v)
                else:
                    # For non-numeric scalars or lists, keep the first value if not present
                    if k not in dst:
                        dst[k] = v
        for idx, chunk in enumerate(chunks):
            chunk_snapshot = {**snapshot, "input_entities": chunk}
            chunk_prompt = prompt_intro + "\n" + prompt_instr + "\n\n" + ("Input entities JSON array:\n" + json.dumps(chunk))
            parsed, usage = client.review_schema(prompt=chunk_prompt, system=system)
            # Merge results
            ue = parsed.get("unified_entities") or []
            csr = parsed.get("cross_source_relationships") or []
            # Deduplicate unified entities by name (case-insensitive)
            existing_names = { (e.get("name") or "").lower(): i for i, e in enumerate(merged["unified_entities"]) }
            for e in ue:
                key = (e.get("name") or "").lower()
                if key in existing_names:
                    tgt = merged["unified_entities"][existing_names[key]]
                    # Merge fields by name
                    def merge_fields(a, b):
                        seen = { (f.get("name") or "").lower() for f in a }
                        for f in b:
                            if (f.get("name") or "").lower() not in seen:
                                a.append(f)
                        return a
                    tgt["fields"] = merge_fields(tgt.get("fields", []), e.get("fields", []))
                    # Merge source_mappings
                    tgt_sm = tgt.get("source_mappings", [])
                    seen_sm = { (m.get("connector_id"), m.get("table"), m.get("field")) for m in tgt_sm }
                    for m in e.get("source_mappings", []):
                        keym = (m.get("connector_id"), m.get("table"), m.get("field"))
                        if keym not in seen_sm:
                            tgt_sm.append(m)
                    tgt["source_mappings"] = tgt_sm
                else:
                    merged["unified_entities"].append(e)
                    existing_names[key] = len(merged["unified_entities"]) - 1
            # Merge relationships by tuple key
            seen_rel = { (r.get("from_entity"), r.get("from_field"), r.get("to_entity"), r.get("to_field"), r.get("type")) for r in merged["cross_source_relationships"] }
            for r in csr:
                keyr = (r.get("from_entity"), r.get("from_field"), r.get("to_entity"), r.get("to_field"), r.get("type"))
                if keyr not in seen_rel:
                    merged["cross_source_relationships"].append(r)
            # Accumulate usage
            accumulate_usage(total_usage, usage or {})

        review.suggestions = merged
        review.status = ReviewStatusEnum.succeeded.value
        review.token_usage = total_usage
        from datetime import datetime as dt
        review.completed_at = dt.utcnow()
        db.commit()
    except Exception as e:
        review.status = ReviewStatusEnum.failed.value
        review.error_message = str(e)
        db.commit()
        raise HTTPException(status_code=500, detail=f"LLM enrichment failed: {e}")
    return {
        "review_id": str(review.review_id),
        "input_snapshot": snapshot,
        "suggestions": review.suggestions,
        "status": review.status,
        "provider": review.provider,
        "model": review.model,
        "token_usage": review.token_usage,
        "created_at": review.created_at.isoformat(),
        "completed_at": review.completed_at.isoformat() if review.completed_at else None,
    }


class SaveGlobalCanonicalBody(BaseModel):
    base_schema_ids: List[UUID4]
    review_id: Optional[UUID4] = None
    user_edits: dict
    note: Optional[str] = None


@router.post("/canonical")
def save_global_canonical(
    tenant_id: str,
    body: SaveGlobalCanonicalBody,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
):
    ctx = check_auth_and_tenant(credentials, tenant_id)
    # Determine next version
    latest = db.query(GlobalCanonicalSchema).filter_by(tenant_id=tenant_id).order_by(GlobalCanonicalSchema.version.desc()).first()
    next_version = 1 if not latest else latest.version + 1
    from datetime import datetime as dt
    canon = GlobalCanonicalSchema(
        tenant_id=tenant_id,
        version=next_version,
        base_schema_ids=[str(x) for x in body.base_schema_ids],
        canonical_graph=body.user_edits,
        note=body.note,
        approved_by_user_id=(ctx.get("user") or {}).get("user_id"),
        approved_at=dt.utcnow(),
        created_at=dt.utcnow(),
    )
    db.add(canon)
    db.commit()
    return {
        "global_canonical_id": str(canon.global_canonical_id),
        "version": canon.version,
        "canonical_graph": canon.canonical_graph,
        "created_at": canon.created_at.isoformat(),
    }


@router.get("/canonical/latest")
def get_latest_global_canonical(
    tenant_id: str,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
):
    check_auth_and_tenant(credentials, tenant_id)
    latest = db.query(GlobalCanonicalSchema).filter_by(tenant_id=tenant_id).order_by(GlobalCanonicalSchema.version.desc()).first()
    if not latest:
        raise HTTPException(status_code=404, detail="No global canonical found")
    return {
        "global_canonical_id": str(latest.global_canonical_id),
        "version": latest.version,
        "canonical_graph": latest.canonical_graph,
        "created_at": latest.created_at.isoformat(),
    }


