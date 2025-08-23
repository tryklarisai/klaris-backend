from __future__ import annotations

from typing import Any, Dict, List
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import text

from services.llm_client import get_llm_client_for_tenant
from models.bcl import BclTerm, BclMappingProposal


def _fetch_latest_global_canonical(db: Session, tenant_id: str) -> Dict[str, Any] | None:
    q = text(
        """
        SELECT global_canonical_id, version, canonical_graph
        FROM global_canonical_schemas
        WHERE tenant_id::text = :tenant
        ORDER BY version DESC
        LIMIT 1
        """
    )
    row = db.execute(q, {"tenant": tenant_id}).mappings().first()
    if not row:
        return None
    return {
        "id": str(row["global_canonical_id"]),
        "version": int(row["version"]),
        "canonical_graph": row["canonical_graph"],
    }


def _collect_context_snippets(db: Session, tenant_id: str, max_snippets: int = 20) -> List[Dict[str, Any]]:
    q = text(
        """
        SELECT c.text, d.uri, c.metadata
        FROM bcl_chunks c
        JOIN bcl_documents d ON d.document_id = c.document_id
        WHERE c.tenant_id::text = :tenant
        ORDER BY c.created_at DESC
        LIMIT :k
        """
    )
    rows = db.execute(q, {"tenant": tenant_id, "k": max_snippets}).mappings().all()
    return [{"text": r["text"], "uri": r["uri"], "metadata": r.get("metadata") if isinstance(r, dict) else r["metadata"]} for r in rows]


def propose_mappings_for_all_terms(db: Session, tenant_id: str) -> Dict[str, Any]:
    canonical = _fetch_latest_global_canonical(db, tenant_id)
    if not canonical:
        return {"proposals": 0, "detail": "No global_canonical_schema for tenant"}

    # Gather inputs
    terms: List[BclTerm] = db.query(BclTerm).filter(BclTerm.tenant_id == tenant_id).all()
    if not terms:
        return {"proposals": 0, "detail": "No terms found"}
    context_snippets = _collect_context_snippets(db, tenant_id)

    # Build prompt (connector-agnostic) and call LLM
    provider, model, client = get_llm_client_for_tenant(db, tenant_id)
    try:
        setattr(client, "_db", db)
        setattr(client, "_tenant_id", tenant_id)
        setattr(client, "_category", "bcl_proposer")
    except Exception:
        pass
    import json
    system = (
        "You propose business-term mappings to a canonical data model."
        " Return ONLY valid JSON. Do NOT include SQL, do NOT mention connectors."
    )
    spec = {
        "type": "object",
        "properties": {
            "proposals": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "term": {"type": "string"},
                        "target_kind": {"type": "string"},
                        "entity_name": {"type": "string"},
                        "field_name": {"type": "string"},
                        "expression": {},
                        "filter": {},
                        "rationale": {"type": "string"},
                        "confidence": {"type": "number"},
                        "evidence_indices": {"type": "array", "items": {"type": "integer"}},
                    },
                    "required": ["term", "target_kind"],
                },
            }
        },
        "required": ["proposals"],
    }
    user = (
        "Business Terms (with aliases):\n" +
        json.dumps([{"term": t.term, "aliases": []} for t in terms], ensure_ascii=False) +
        "\n\nCanonical Schema (selected parts):\n" +
        json.dumps(canonical["canonical_graph"], ensure_ascii=False) +
        "\n\nBusiness Context Snippets (index-aligned):\n" +
        json.dumps([s.get("text") for s in context_snippets], ensure_ascii=False) +
        "\n\nTask: For each known term, propose zero or more mappings into the canonical model."
        " Use only existing entities/fields. Use evidence_indices to reference snippets that justify the mapping."
        " Respond strictly as JSON matching this schema: " + json.dumps(spec)
    )
    parsed, usage = client.review_schema(user, system=system, temperature=0.1)

    # Persist proposals
    now = datetime.utcnow()
    count = 0
    by_term = {t.term.lower().strip(): t for t in terms}
    for p in (parsed.get("proposals") or []):
        term_name = str(p.get("term") or "").lower().strip()
        term = by_term.get(term_name)
        if not term:
            continue
        mp = BclMappingProposal(
            tenant_id=term.tenant_id,
            term_id=term.term_id,
            target_kind=str(p.get("target_kind") or ""),
            entity_name=p.get("entity_name"),
            field_name=p.get("field_name"),
            expression=p.get("expression"),
            filter=p.get("filter"),
            rationale=p.get("rationale"),
            confidence=int(p.get("confidence") or 0),
            evidence={"indices": p.get("evidence_indices") or []},
            created_at=now,
        )
        db.add(mp)
        count += 1
    db.commit()
    return {"proposals": count, "llm_usage": usage}


