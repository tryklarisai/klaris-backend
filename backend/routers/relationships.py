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
import logging

from db import get_db
from models.connector import Connector
from models.schema import Schema
from models.schema_review import DatasetReview, GlobalCanonicalSchema, ReviewStatusEnum
from services.llm_client import get_llm_client_for_tenant
from pydantic import BaseModel, UUID4, Field
from sqlalchemy import text as sql_text, select, Table, Column, String as SAString, Text as SAText, DateTime as SADateTime, MetaData
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from pgvector.sqlalchemy import Vector
from services.indexer import upsert_cards


router = APIRouter(prefix="/tenants/{tenant_id}/relationships", tags=["Data Relationships"])

logger = logging.getLogger(__name__)

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

from collections import defaultdict
import copy
import re

def anchor_and_split_cross_entity_fields(result: dict) -> dict:
    """
    Ensure each source_entity's fields live in its anchored canonical entity.
    If a canonical field mixes mappings from multiple source entities, split it
    so that each source_entity's mappings move to that source's anchor entity.
    """
    entities = result.get("entities") or []
    if not entities:
        return result

    # Count mappings from each source_entity under each canonical entity
    src_counts = defaultdict(lambda: defaultdict(int))  # source_entity -> {canonical_entity_name: count}
    for e in entities:
        e_name = (e.get("name") or "").strip()
        for f in (e.get("fields") or []):
            for m in (f.get("mappings") or []):
                src_counts[m.get("source_entity", "")][e_name] += 1

    # Pick anchor entity for each source_entity (argmax count)
    src_anchor = {}
    for src, counts in src_counts.items():
        if counts:
            anchor_ent = max(counts.items(), key=lambda kv: kv[1])[0]
            src_anchor[src] = anchor_ent

    ent_by_name = {(e.get("name") or "").strip(): e for e in entities}

    def get_or_create_field(target_entity: dict, field_name: str, template_field: dict) -> dict:
        for f in (target_entity.get("fields") or []):
            if (f.get("name") or "").strip().lower() == (field_name or "").strip().lower():
                return f
        nf = {
            "name": field_name,
            "description": template_field.get("description", ""),
            "semantic_type": template_field.get("semantic_type", "identifier" if (field_name or "").lower().endswith("id") else "unknown"),
            "pii": template_field.get("pii", "none"),
            "primary_key": bool(template_field.get("primary_key", False)),
            "is_join_key": bool(template_field.get("is_join_key", False)),
            "nullable": bool(template_field.get("nullable", True)),
            "mappings": []
        }
        target_entity.setdefault("fields", []).append(nf)
        return nf

    for e in list(entities):
        e_name = (e.get("name") or "").strip()
        new_fields = []
        for f in (e.get("fields") or []):
            maps = f.get("mappings") or []
            by_src = defaultdict(list)
            for m in maps:
                by_src[m.get("source_entity", "")].append(m)

            stay = []
            for src, src_maps in by_src.items():
                anchor_name = src_anchor.get(src)
                if not anchor_name or anchor_name == e_name:
                    stay.extend(src_maps)
                else:
                    target_ent = ent_by_name.get(anchor_name)
                    if not target_ent:
                        target_ent = {"name": anchor_name, "description": "", "tags": [], "fields": []}
                        entities.append(target_ent)
                        ent_by_name[anchor_name] = target_ent
                    target_field = get_or_create_field(target_ent, f.get("name") or "", f)
                    target_field.setdefault("mappings", []).extend(copy.deepcopy(src_maps))
            if stay:
                f["mappings"] = stay
                new_fields.append(f)
        e["fields"] = new_fields

    result["entities"] = [e for e in entities if (e.get("fields") or [])]
    return result

@router.post("/reviews")
def create_dataset_review(
    tenant_id: str,
    body: CreateDatasetReviewRequest,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
):
    """
    Canonical schema suggestion with 100% field coverage (ID-based) + relationship labeling (2nd pass),
    and cross-entity anchoring to keep source fields under their correct canonical entity.
    """
    from datetime import datetime as dt
    import json, os  # <-- added os

    ctx = check_auth_and_tenant(credentials, tenant_id)
    logger.info("[relationships] create_dataset_review start tenant_id=%s", tenant_id)

    # Validate connectors & fetch latest schemas
    if not body.connector_ids:
        raise HTTPException(status_code=400, detail="connector_ids required")
    id_set = {str(cid) for cid in body.connector_ids}
    connectors = db.query(Connector).filter(Connector.tenant_id == tenant_id).all()
    selected = [c for c in connectors if str(c.connector_id) in id_set and c.status.value == "active"]
    if not selected:
        raise HTTPException(status_code=400, detail="No active connectors selected")
    logger.info("[relationships] selected_connectors=%d", len(selected))

    latest_schemas: List[Schema] = []
    connector_by_id = {str(c.connector_id): c for c in selected}
    for c in selected:
        s = (db.query(Schema)
             .filter_by(connector_id=c.connector_id, tenant_id=tenant_id)
             .order_by(Schema.fetched_at.desc())
             .first())
        if s:
            latest_schemas.append(s)
    if not latest_schemas:
        raise HTTPException(status_code=400, detail="No schemas available for selected connectors")
    logger.info("[relationships] latest_schemas=%d", len(latest_schemas))

    provider, model, client = get_llm_client_for_tenant(db, str(tenant_id))
    # Inject usage logging context
    try:
        setattr(client, "_db", db)
        setattr(client, "_tenant_id", str(tenant_id))
        setattr(client, "_category", "relationships")
        setattr(client, "_module", "data_relationships")
    except Exception:
        pass
    options = body.options or CreateDatasetReviewOptions()
    rel_conf_threshold = float(options.confidence_threshold or 0.6)

    # Helpers
    def extract_entities(raw: dict) -> list:
        root = raw.get("schema", raw) if isinstance(raw, dict) else {}
        if isinstance(root, dict) and isinstance(root.get("entities"), list):
            return root["entities"]
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

    def norm(s: str) -> str:
        s = (s or "").strip()
        s = s.replace("-", "_")
        s = re.sub(r"[^A-Za-z0-9_]+", " ", s)
        s = re.sub(r"\s+", " ", s).lower()
        return s

    def toks(s: str) -> list[str]:
        return [t for t in norm(s).replace("_", " ").split() if t]

    def jaccard(a: set, b: set) -> float:
        if not a and not b:
            return 0.0
        return len(a & b) / max(1, len(a | b))

    # Build normalized input_entities (audit only)
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
    logger.info("[relationships] built input_entities count=%d", len(input_entities))

    # MANIFEST with mapping IDs (mids)
    manifest: List[dict] = []
    mid_lookup: dict[int, dict] = {}
    mid = 0
    for item in input_entities:
        cid = item["connector_id"]
        ename = item["entity_name"]
        for f in (item.get("fields") or []):
            entry = {
                "mid": mid,
                "connector_id": cid,
                "source_entity": ename,
                "source_field": f.get("name"),
                "type": f.get("type") or f.get("data_type") or None,
            }
            manifest.append(entry)
            mid_lookup[mid] = entry
            mid += 1

    total_manifest = len(manifest)
    if total_manifest == 0:
        raise HTTPException(status_code=400, detail="No fields found in selected connectors' schemas")
    logger.info("[relationships] manifest fields=%d", total_manifest)

    snapshot = {
        "connector_ids": [str(c.connector_id) for c in selected],
        "connectors": [{"connector_id": str(c.connector_id), "type": c.type} for c in selected],
        "schema_ids": [str(s.schema_id) for s in latest_schemas],
        "input_entities": input_entities[:200],
        "manifest": manifest,
        "params": options.model_dump(),
    }

    def manifest_lines(items: List[dict]) -> str:
        return "\n".join(
            f"{m['connector_id']}|{m['source_entity']}|{m['source_field']}|{(m.get('type') or '')}|{m['mid']}"
            for m in items
        )

    output_contract = {
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
                        "semantic_type": "string",
                        "pii": "none|low|medium|high",
                        "primary_key": False,
                        "is_join_key": False,
                        "nullable": True,
                        "mapping_ids": [0]
                    }
                ]
            }
        ],
        "relationships": []
    }

    system = (
        "You cluster source fields into canonical entities/fields.\n"
        "Return ONLY valid JSON matching the provided schema. Do not invent facts.\n"
        "Use mapping_ids to reference the MANIFEST lines; never omit an ID on purpose."
    )

    prompt = (
        "You will receive a MANIFEST of source fields.\n"
        "Group them into canonical ENTITIES and FIELDS.\n"
        "For each canonical field, provide: name, description, semantic_type, pii, key flags, nullable, "
        "and the list of mapping_ids that belong to it.\n\n"
        "OUTPUT JSON SCHEMA:\n" + json.dumps(output_contract) +
        "\n\nMANIFEST (one per line; format is connector_id|source_entity|source_field|type|mid):\n" +
        manifest_lines(manifest)
    )

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

    # LLM pass #1 (entities & fields)
    try:
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
                    if k not in dst:
                        dst[k] = v

        logger.info("[relationships] invoking LLM#1 provider=%s model=%s lines=%d", provider, model, total_manifest)
        parsed, usage = client.review_schema(
            prompt=prompt,
            system=system,
            temperature=0,
            max_tokens=8000
        )
        accumulate_usage(total_usage, usage or {})
        logger.info("[relationships] LLM#1 response received; usage=%s", usage)

        result = parsed if isinstance(parsed, dict) else {}
        if "version" not in result:
            result["version"] = "pilot-1"
        if not result.get("generated_at"):
            result["generated_at"] = dt.utcnow().isoformat() + "Z"
        result.setdefault("entities", [])
        result.setdefault("relationships", [])

        # Expand mapping_ids -> mappings
        covered_ids: set[int] = set()
        for e in result.get("entities", []):
            for f in (e.get("fields") or []):
                ids = f.pop("mapping_ids", []) or []
                maps = []
                for mid_val in ids:
                    try:
                        mid_int = int(mid_val)
                    except Exception:
                        continue
                    t = mid_lookup.get(mid_int)
                    if t:
                        covered_ids.add(mid_int)
                        maps.append({
                            "connector_id": t["connector_id"],
                            "source_entity": t["source_entity"],
                            "source_field": t["source_field"],
                            "confidence": 1.0
                        })
                f["mappings"] = maps

        # Auto-attach any missing IDs to an Unassigned entity
        missing_ids_initial = [m for m in mid_lookup.keys() if m not in covered_ids]
        if missing_ids_initial:
            by_src = defaultdict(list)
            for m in missing_ids_initial:
                by_src[mid_lookup[m]["source_entity"]].append(m)
            fallback_fields = []
            for src, mids in by_src.items():
                fallback_fields.append({
                    "name": f"{src} (raw)",
                    "description": f"Raw fields from {src} pending curation.",
                    "semantic_type": "unknown",
                    "pii": "none",
                    "primary_key": False,
                    "is_join_key": False,
                    "nullable": True,
                    "mappings": [
                        {
                            "connector_id": mid_lookup[m]["connector_id"],
                            "source_entity": mid_lookup[m]["source_entity"],
                            "source_field": mid_lookup[m]["source_field"],
                            "confidence": 0.5
                        }
                        for m in mids
                    ]
                })
            result["entities"].append({
                "name": "Unassigned",
                "description": "Source fields not confidently clustered yet.",
                "tags": ["unassigned"],
                "fields": fallback_fields
            })

        # Anchor & split cross-entity fields (fixes misplaced fields like 'Order ID')
        before_counts = sum(len(f.get("mappings") or []) for e in result.get("entities", []) for f in (e.get("fields") or []))
        result = anchor_and_split_cross_entity_fields(result)
        after_counts = sum(len(f.get("mappings") or []) for e in result.get("entities", []) for f in (e.get("fields") or []))
        logger.info("[relationships] anchoring split applied; mapping rows before=%d after=%d", before_counts, after_counts)

        # ------- Coverage log (robust) -------
        # Build reverse map: (connector_id, source_entity, source_field) -> mid
        def _k(cid, se, sf):
            return (str(cid).strip().lower(), (se or "").strip().lower(), (sf or "").strip().lower())
        reverse_mid = { _k(v["connector_id"], v["source_entity"], v["source_field"]): mid for mid, v in mid_lookup.items() }

        covered_ids_after: set[int] = set()
        for e in result.get("entities", []):
            for f in (e.get("fields") or []):
                for m in (f.get("mappings") or []):
                    mid_match = reverse_mid.get(_k(m.get("connector_id"), m.get("source_entity"), m.get("source_field")))
                    if mid_match is not None:
                        covered_ids_after.add(mid_match)

        total_manifest_count = len(manifest)
        covered_after = len(covered_ids_after)
        missing_after = total_manifest_count - covered_after
        if missing_after > 0:
            preview_ids = [mid for mid in mid_lookup.keys() if mid not in covered_ids_after][:10]
            preview = [mid_lookup[mid] for mid in preview_ids]
            logger.warning("[relationships] coverage total=%d covered=%d missing=%d (first_missing=%s)",
                           total_manifest_count, covered_after, missing_after, preview)
        else:
            logger.info("[relationships] coverage total=%d covered=%d missing=%d",
                        total_manifest_count, covered_after, missing_after)

        # -------- Relationships (second pass) --------
        # Build canonical field index
        canon_fields = []
        for e in result.get("entities", []):
            e_name = (e.get("name") or "").strip()
            for f in (e.get("fields") or []):
                canon_fields.append({
                    "entity": e_name,
                    "field": (f.get("name") or "").strip(),
                    "pk": bool(f.get("primary_key")),
                    "jk": bool(f.get("is_join_key")),
                    "sem": (f.get("semantic_type") or "").lower(),
                    "tokens": set(toks(f.get("name") or "")),
                })

        def is_id_like(cf):
            fname = cf["field"]
            return (cf["sem"] in ("identifier", "id", "key") or
                    bool(re.search(r"(?:^|[_\s])id$", norm(fname))) or
                    fname.lower().endswith("_id"))

        fields_for_join = [cf for cf in canon_fields if (cf["pk"] or cf["jk"] or is_id_like(cf))]
        logger.info("[relationships] candidate fields for join=%d / all=%d", len(fields_for_join), len(canon_fields))

        def score_pair(a, b):
            if a["entity"] == b["entity"]:
                return 0.0
            name_eq = 1.0 if norm(a["field"]) == norm(b["field"]) else 0.0
            j = jaccard(a["tokens"], b["tokens"])
            pkjk = 1.0 if (a["pk"] and b["jk"]) or (b["pk"] and a["jk"]) else 0.0
            both_id = 1.0 if (a["sem"] in ("identifier","id","key") and b["sem"] in ("identifier","id","key")) else 0.0
            score = 0.75 * max(name_eq, j) + 0.20 * pkjk + 0.05 * both_id
            return float(score)

        candidates = []
        pair_id = 0
        per_pair_bucket: dict[tuple, list] = defaultdict(list)
        for i in range(len(fields_for_join)):
            for j in range(i + 1, len(fields_for_join)):
                a = fields_for_join[i]; b = fields_for_join[j]
                sc = score_pair(a, b)
                if sc < 0.7:
                    continue
                pred_type = "unknown"
                f_entity, f_field = a["entity"], a["field"]
                t_entity, t_field = b["entity"], b["field"]
                if a["pk"] and b["jk"]:
                    pred_type = "one_to_many"
                    f_entity, f_field, t_entity, t_field = a["entity"], a["field"], b["entity"], b["field"]
                elif b["pk"] and a["jk"]:
                    pred_type = "one_to_many"
                    f_entity, f_field, t_entity, t_field = b["entity"], b["field"], a["entity"], a["field"]
                key = tuple(sorted([a["entity"], b["entity"]]))
                per_pair_bucket[key].append({
                    "pair_id": pair_id,
                    "from_entity": f_entity,
                    "from_field": f_field,
                    "to_entity": t_entity,
                    "to_field": t_field,
                    "score": sc,
                    "predicted_type": pred_type,
                    "hints": {
                        "a_pk": a["pk"], "a_jk": a["jk"], "b_pk": b["pk"], "b_jk": b["jk"],
                        "a_sem": a["sem"], "b_sem": b["sem"],
                    }
                })
                pair_id += 1

        MAX_PER_PAIR = int(os.getenv("REL_MAX_PER_ENTITY_PAIR", "5"))
        MAX_GLOBAL = int(os.getenv("REL_MAX_CANDIDATES", "300"))
        flat_candidates = []
        for key, lst in per_pair_bucket.items():
            lst_sorted = sorted(lst, key=lambda x: x["score"], reverse=True)[:MAX_PER_PAIR]
            flat_candidates.extend(lst_sorted)
        flat_candidates = sorted(flat_candidates, key=lambda x: x["score"], reverse=True)[:MAX_GLOBAL]
        logger.info("[relationships] candidate pairs=%d (after caps)", len(flat_candidates))

        relationships_out = []
        if flat_candidates:
            def candidate_lines(items: list[dict]) -> str:
                lines = []
                for c in items:
                    hints_str = json.dumps(c["hints"], separators=(",", ":"))
                    lines.append(f"{c['pair_id']}|{c['from_entity']}|{c['from_field']}|{c['to_entity']}|{c['to_field']}|{round(c['score'],3)}|{c['predicted_type']}|{hints_str}")
                return "\n".join(lines)

            rel_output_contract = {
                "relationships": [
                    {
                        "pair_id": 0,
                        "accept": True,
                        "type": "one_to_one|one_to_many|many_to_one|many_to_many|unknown",
                        "confidence": 0.0,
                        "note": "string"
                    }
                ]
            }
            rel_system = (
                "You are a precise data modeling assistant. "
                "Given candidate join key pairs across canonical entities, "
                "select only the pairs that are likely true relationships. "
                "Respond ONLY with JSON matching the schema. "
                "Use the pair_id to reference candidates; do not invent new pairs."
            )
            rel_prompt = (
                "CANDIDATE PAIRS (one per line; format is "
                "pair_id|from_entity|from_field|to_entity|to_field|score|predicted_type|hints_json):\n" +
                candidate_lines(flat_candidates) +
                "\n\nOUTPUT JSON SCHEMA:\n" + json.dumps(rel_output_contract)
            )

            logger.info("[relationships] invoking LLM#2 with %d candidates", len(flat_candidates))
            rel_parsed, rel_usage = client.review_schema(
                prompt=rel_prompt,
                system=rel_system,
                temperature=0,
                max_tokens=2000
            )
            accumulate_usage(total_usage, rel_usage or {})
            rel_items = (rel_parsed or {}).get("relationships") or []

            cand_by_id = {c["pair_id"]: c for c in flat_candidates}
            dedup = set()
            for it in rel_items:
                try:
                    if not it.get("accept", False):
                        continue
                    pid = int(it.get("pair_id"))
                    c = cand_by_id.get(pid)
                    if not c:
                        continue
                    rel_type = (it.get("type") or c.get("predicted_type") or "unknown").lower()
                    conf = float(it.get("confidence") or 0.0)
                    if conf < rel_conf_threshold:
                        continue
                    key = (c["from_entity"].lower(), c["from_field"].lower(),
                           c["to_entity"].lower(), c["to_field"].lower())
                    if key in dedup:
                        continue
                    dedup.add(key)
                    relationships_out.append({
                        "type": rel_type,
                        "from_entity": c["from_entity"],
                        "to_entity": c["to_entity"],
                        "join_on": [{"from_field": c["from_field"], "to_field": c["to_field"]}],
                        "confidence": conf
                    })
                except Exception:
                    continue

        result["relationships"] = relationships_out

        # Save review
        review.suggestions = result
        review.status = ReviewStatusEnum.succeeded.value
        review.token_usage = total_usage
        review.completed_at = dt.utcnow()
        db.commit()
        logger.info("[relationships] create_dataset_review completed review_id=%s rels=%d",
                    str(review.review_id), len(relationships_out))

    except Exception as e:
        review.status = ReviewStatusEnum.failed.value
        review.error_message = str(e)
        db.commit()
        logger.exception("[relationships] create_dataset_review failed: %s", e)
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


class BuildIndexBody(BaseModel):
    canonical_id: Optional[UUID4] = None


@router.post("/index/build")
def build_index(
    tenant_id: str,
    body: BuildIndexBody,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
):
    check_auth_and_tenant(credentials, tenant_id)
    # Fetch canonical: specific or latest
    if body.canonical_id:
        canon = db.query(GlobalCanonicalSchema).filter_by(tenant_id=tenant_id, global_canonical_id=str(body.canonical_id)).first()
        if not canon:
            raise HTTPException(status_code=404, detail="Canonical not found")
    else:
        canon = db.query(GlobalCanonicalSchema).filter_by(tenant_id=tenant_id).order_by(GlobalCanonicalSchema.version.desc()).first()
        if not canon:
            raise HTTPException(status_code=404, detail="No canonical available")
    # Validate required top-level keys
    cg = canon.canonical_graph or {}
    for key in ("version", "generated_at", "entities", "relationships"):
        if key not in cg:
            raise HTTPException(status_code=400, detail=f"Canonical missing required key: {key}")
    # Upsert into vector index
    res = upsert_cards(db, tenant_id, cg)
    return {"ok": True, "counts": res}


@router.get("/index/stats")
def index_stats(
    tenant_id: str,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
):
    check_auth_and_tenant(credentials, tenant_id)
    q = sql_text(
        "SELECT key_kind, COUNT(*) AS cnt FROM vector_cards WHERE tenant_id = :tenant_id GROUP BY key_kind"
    )
    rows = db.execute(q, {"tenant_id": tenant_id}).mappings().all()
    return {"counts": {r["key_kind"]: int(r["cnt"]) for r in rows}}


@router.get("/index/search")
def index_search(
    tenant_id: str,
    q: str,
    top_k: int = 10,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
):
    check_auth_and_tenant(credentials, tenant_id)
    # Embed query
    from services.indexer import _embed_texts  # reuse internal helper
    vec = _embed_texts([q])[0]
    # Cosine distance search using SQLAlchemy Core with pgvector Vector type
    md = MetaData()
    vector_cards = Table(
        'vector_cards', md,
        Column('card_id', PGUUID(as_uuid=True), primary_key=True),
        Column('tenant_id', PGUUID(as_uuid=True), nullable=False),
        Column('key_kind', SAString(length=32), nullable=False),
        Column('key_hash', SAString(length=128), nullable=False),
        Column('card_text', SAText(), nullable=False),
        Column('metadata', JSONB, nullable=False),
        Column('embedding', Vector(), nullable=False),
        Column('created_at', SADateTime(), nullable=False),
        Column('updated_at', SADateTime(), nullable=False),
    )
    # distance expression
    dist = vector_cards.c.embedding.cosine_distance(vec)
    stmt = (
        select(
            vector_cards.c.key_kind,
            vector_cards.c.key_hash,
            vector_cards.c.card_text,
            vector_cards.c.metadata,
            (1 - dist).label('score')
        )
        .where(vector_cards.c.tenant_id == tenant_id)
        .order_by(dist)
        .limit(int(max(1, min(100, top_k))))
    )
    rows = db.execute(stmt).mappings().all()
    return {"results": [
        {"key_kind": r["key_kind"], "card_text": r["card_text"], "metadata": r["metadata"], "score": float(r["score"]) }
        for r in rows
    ]}


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


