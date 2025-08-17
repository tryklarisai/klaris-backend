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
        "version": "pilot-1",
        "generated_at": "ISO-8601 UTC timestamp",
        "entities": [
            {
                "name": "string",
                "description": "string",
                "tags": ["string"],
                "fields": [
                    {
                        "name": "string",
                        "description": "string",
                        "data_type": "string",
                        "semantic_type": "string",
                        "nullable": True,
                        "primary_key": False,
                        "is_join_key": False,
                        "pii": "none|low|medium|high",
                        "masking": "string",
                        "confidence": 0.0,
                        "mappings": [
                            {"connector_id": "uuid", "source_entity": "string", "source_field": "string", "confidence": 0.0}
                        ]
                    }
                ]
            }
        ],
        "relationships": [
            {
                "type": "one_to_one|one_to_many|many_to_one|many_to_many|unknown",
                "from_entity": "string",
                "to_entity": "string",
                "join_on": [ { "from_field": "string", "to_field": "string" } ],
                "confidence": 0.0
            }
        ]
    }
    # Build prompt in parts to avoid accidental truncation/escaping issues
    prompt_intro = (
        "You are given multiple connector schemas (structure only). Build a simplified, connector-agnostic global canonical schema with: "
        "(a) entities (with fields, basic types, semantic types, nullability, primary keys, join keys, and PII), and "
        "(b) relationships (with type and join key pairs)."
    )
    prompt_instr = (
        "Return valid JSON ONLY matching this exact output format: " + json.dumps(output_hint) +
        "\nRequirements: (1) Include top-level 'version' with value 'pilot-1' and 'generated_at' as ISO-8601 UTC." \
        + " (2) Cover ALL input entities across ALL connectors." \
        + " (3) For each entity, include 'tags' as relevant keywords." \
        + " (4) For each field, include 'description' and 'confidence' (0..1), and per-source mappings (connector_id, source_entity, source_field, confidence)." \
        + " (5) Provide a confidence (0..1) for each relationship."
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
        merged = {"version": "pilot-1", "generated_at": None, "entities": [], "relationships": []}
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
            # Merge results (pilot format)
            ents = parsed.get("entities") or []
            rels = parsed.get("relationships") or []
            # Keep first generated_at if provided
            if not merged.get("generated_at"):
                ga = parsed.get("generated_at")
                if isinstance(ga, str) and ga:
                    merged["generated_at"] = ga
            # Deduplicate entities by name (case-insensitive)
            existing_names = { (e.get("name") or "").lower(): i for i, e in enumerate(merged["entities"]) }
            for e in ents:
                key = (e.get("name") or "").lower()
                if key in existing_names:
                    tgt = merged["entities"][existing_names[key]]
                    # Merge fields by name, and merge per-field mappings
                    def merge_fields(a, b):
                        index = { (f.get("name") or "").lower(): f for f in a }
                        for f in b:
                            fk = (f.get("name") or "").lower()
                            if fk in index:
                                tf = index[fk]
                                tmap = tf.get("mappings") or []
                                mmap = f.get("mappings") or []
                                seen_map = { (m.get("connector_id"), (m.get("source_entity") or "").lower(), (m.get("source_field") or "").lower()) for m in tmap }
                                for m in mmap:
                                    sig = (m.get("connector_id"), (m.get("source_entity") or "").lower(), (m.get("source_field") or "").lower())
                                    if sig not in seen_map:
                                        tmap.append(m)
                                if tmap:
                                    tf["mappings"] = tmap
                                # Merge field description and confidence
                                if not (str(tf.get("description") or "").strip()) and str(f.get("description") or "").strip():
                                    tf["description"] = f.get("description")
                                try:
                                    tfc = float(tf.get("confidence")) if tf.get("confidence") is not None else None
                                except Exception:
                                    tfc = None
                                try:
                                    fc = float(f.get("confidence")) if f.get("confidence") is not None else None
                                except Exception:
                                    fc = None
                                if fc is not None and (tfc is None or fc > tfc):
                                    tf["confidence"] = fc
                            else:
                                a.append(f)
                        return a
                    tgt["fields"] = merge_fields(tgt.get("fields", []), e.get("fields", []))
                    # Keep first non-empty description
                    tgt_desc = (tgt.get("description") or "").strip()
                    e_desc = (e.get("description") or "").strip()
                    if not tgt_desc and e_desc:
                        tgt["description"] = e.get("description")
                    # Union tags
                    tgt_tags = set((tgt.get("tags") or []))
                    new_tags = [t for t in (e.get("tags") or []) if isinstance(t, str) and t.strip()]
                    if new_tags:
                        tgt["tags"] = sorted(list(tgt_tags.union(new_tags)))
                else:
                    merged["entities"].append(e)
                    existing_names[key] = len(merged["entities"]) - 1
            # Merge relationships by composite key
            def rel_key(rel: dict):
                jt = tuple(sorted([ (p.get("from_field"), p.get("to_field")) for p in (rel.get("join_on") or []) ]))
                return (rel.get("from_entity"), rel.get("to_entity"), rel.get("type"), jt)
            seen_rel = { rel_key(r) for r in merged["relationships"] }
            for r in rels:
                k = rel_key(r)
                if k not in seen_rel:
                    merged["relationships"].append(r)
            # Accumulate usage
            accumulate_usage(total_usage, usage or {})

        # Ensure generated_at is set
        if not merged.get("generated_at"):
            from datetime import datetime as dt
            merged["generated_at"] = dt.utcnow().isoformat() + "Z"
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
    expected_version: Optional[int] = None


@router.post("/canonical")
def save_global_canonical(
    tenant_id: str,
    body: SaveGlobalCanonicalBody,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
):
    ctx = check_auth_and_tenant(credentials, tenant_id)
    # Determine next version and enforce optimistic concurrency
    latest = db.query(GlobalCanonicalSchema).filter_by(tenant_id=tenant_id).order_by(GlobalCanonicalSchema.version.desc()).first()
    if body.expected_version is not None:
        latest_version = latest.version if latest else 0
        if int(body.expected_version) != int(latest_version):
            # 409 Conflict with latest details for the client to refresh
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Version conflict: latest canonical has changed.",
                    "latest_version": latest_version,
                    "latest": {
                        "version": latest_version,
                        "canonical_graph": (latest.canonical_graph if latest else None),
                    },
                },
            )
    next_version = 1 if not latest else latest.version + 1
    from datetime import datetime as dt
    canon = GlobalCanonicalSchema(
        tenant_id=tenant_id,
        version=next_version,
        base_schema_ids=[str(x) for x in body.base_schema_ids],
        canonical_graph=body.user_edits or {},
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
        "base_schema_ids": canon.base_schema_ids,
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
        "base_schema_ids": latest.base_schema_ids,
    }


class ValidationErrorItem(BaseModel):
    path: str
    message: str


class ValidateCanonicalBody(BaseModel):
    canonical_graph: dict


@router.post("/canonical/validate")
def validate_canonical(
    tenant_id: str,
    body: ValidateCanonicalBody,
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
):
    check_auth_and_tenant(credentials, tenant_id)
    graph = body.canonical_graph or {}
    errors: list[dict] = []

    def add_err(path: str, msg: str):
        errors.append({"path": path, "message": msg})

    # Limits from env
    import os
    max_entities = int(os.getenv("REL_MAX_ENTITIES", "2000"))
    max_fields = int(os.getenv("REL_MAX_FIELDS_PER_ENTITY", "500"))
    max_rels = int(os.getenv("REL_MAX_RELATIONSHIPS", "5000"))

    # Pilot-only shape
    ents = graph.get("entities") or []
    rels = graph.get("relationships") or []

    if not isinstance(ents, list):
        add_err("/unified_entities", "must be a list")
    else:
        if len(ents) > max_entities:
            add_err("/unified_entities", f"too many entities (>{max_entities})")
        seen_names = set()
        for i, e in enumerate(ents):
            name = (e.get("name") or "").strip()
            if not name:
                add_err(f"/unified_entities[{i}]/name", "required")
            key = name.lower()
            if key in seen_names:
                add_err(f"/unified_entities[{i}]/name", "duplicate entity name")
            seen_names.add(key)
            # Fields
            fields = e.get("fields") or []
            if not isinstance(fields, list):
                add_err(f"/unified_entities[{i}]/fields", "must be a list")
            else:
                if len(fields) > max_fields:
                    add_err(f"/unified_entities[{i}]/fields", f"too many fields (>{max_fields})")
                seen_f = set()
                for j, f in enumerate(fields):
                    fname = (f.get("name") or "").strip()
                    if not fname:
                        add_err(f"/unified_entities[{i}]/fields[{j}]/name", "required")
                    fk = fname.lower()
                    if fk in seen_f:
                        add_err(f"/unified_entities[{i}]/fields[{j}]/name", "duplicate field name")
                    seen_f.add(fk)
                    pii = (f.get("pii_sensitivity") or f.get("pii") or "none").lower()
                    if pii not in ("none", "low", "medium", "high"):
                        add_err(f"/unified_entities[{i}]/fields[{j}]/pii_sensitivity", "invalid enum")

    if not isinstance(rels, list):
        add_err("/cross_source_relationships", "must be a list")
    else:
        if len(rels) > max_rels:
            add_err("/relationships", f"too many relationships (>{max_rels})")
        # Reference validation
        ent_index = { (e.get("name") or "").lower(): e for e in ents if isinstance(e, dict) }
        for k, r in enumerate(rels):
            t = (r.get("type") or "unknown").lower()
            if t not in ("one_to_one", "one_to_many", "many_to_one", "many_to_many", "unknown"):
                add_err(f"/relationships[{k}]/type", "invalid enum")
            fe = (r.get("from_entity") or "").lower()
            te = (r.get("to_entity") or "").lower()
            if fe not in ent_index:
                add_err(f"/relationships[{k}]/from_entity", "unknown entity")
            if te not in ent_index:
                add_err(f"/relationships[{k}]/to_entity", "unknown entity")
            # Support legacy single from_field/to_field and pilot join_on list
            ff = r.get("from_field")
            tf = r.get("to_field")
            join_on = r.get("join_on") or []
            if ff or tf:
                if ff:
                    fields = ent_index.get(fe, {}).get("fields", [])
                    if (ff.lower() if isinstance(ff, str) else "") not in { (f.get("name") or "").lower() for f in fields }:
                        add_err(f"/relationships[{k}]/from_field", "unknown field for from_entity")
                if tf:
                    fields = ent_index.get(te, {}).get("fields", [])
                    if (tf.lower() if isinstance(tf, str) else "") not in { (f.get("name") or "").lower() for f in fields }:
                        add_err(f"/relationships[{k}]/to_field", "unknown field for to_entity")
            elif isinstance(join_on, list) and len(join_on) > 0:
                for idxp, p in enumerate(join_on):
                    pf = (p.get("from_field") or "").lower()
                    pt = (p.get("to_field") or "").lower()
                    if not pf or not pt:
                        add_err(f"/relationships[{k}]/join_on[{idxp}]", "from_field and to_field required")
                        continue
                    ffields = ent_index.get(fe, {}).get("fields", [])
                    tfields = ent_index.get(te, {}).get("fields", [])
                    if pf not in { (f.get("name") or "").lower() for f in ffields }:
                        add_err(f"/relationships[{k}]/join_on[{idxp}]/from_field", "unknown field for from_entity")
                    if pt not in { (f.get("name") or "").lower() for f in tfields }:
                        add_err(f"/relationships[{k}]/join_on[{idxp}]/to_field", "unknown field for to_entity")

    if errors:
        return {"ok": False, "errors": errors}
    return {"ok": True}


