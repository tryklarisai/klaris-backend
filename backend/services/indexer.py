from __future__ import annotations
from typing import Any, Dict, List, Tuple
import os
import hashlib
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.llm_client import get_llm_client


def _hash_key(parts: List[str]) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update((p or "").encode("utf-8"))
        h.update(b"|")
    return h.hexdigest()


def _truncate(text_value: str, max_len_env: str = "INDEX_MAX_TEXT_LEN") -> str:
    try:
        max_len = int(os.getenv(max_len_env, "1200"))
    except Exception:
        max_len = 1200
    if text_value is None:
        return ""
    if len(text_value) <= max_len:
        return text_value
    return text_value[: max_len - 3] + "..."


def _compute_entity_card(entity: dict, version: str, generated_at: str) -> Tuple[str, Dict[str, Any]]:
    name = entity.get("name") or ""
    tags = entity.get("tags") or []
    fields = entity.get("fields") or []
    pk_fields = [f.get("name") for f in fields if f.get("primary_key")]
    join_fields = [f.get("name") for f in fields if f.get("is_join_key")]
    pii_any = any((f.get("pii") or "none").lower() != "none" for f in fields)
    notable = []
    for f in fields[: min(len(fields), int(os.getenv("INDEX_MAX_FIELDS_PER_ENTITY", "200")) )]:
        if f.get("primary_key") or f.get("is_join_key") or (f.get("pii") or "none").lower() != "none":
            notable.append(f.get("name"))
    desc = entity.get("description") or ""
    tags_str = ", ".join(tags) if isinstance(tags, list) else str(tags)
    notable_str = ", ".join(notable) if notable else ""
    pk_str = ", ".join(pk_fields) if pk_fields else ""
    join_str = ", ".join(join_fields) if join_fields else ""
    card_text = f"{name} represents {desc}. Notable fields: {notable_str or 'n/a'}. Primary keys: {pk_str or 'n/a'}. Join keys: {join_str or 'n/a'}. Tags: {tags_str or 'n/a'}."
    metadata = {
        "card_kind": "entity",
        "entity_name": name,
        "entity_tags": tags,
        "version": version,
        "generated_at": generated_at,
        "pii_any": bool(pii_any),
        "primary_keys": pk_fields,
        "join_keys": join_fields,
        "field_count": len(fields),
    }
    return _truncate(card_text), metadata


def _compute_field_card(entity_name: str, field: dict) -> Tuple[str, Dict[str, Any]]:
    name = field.get("name") or ""
    data_type = field.get("data_type") or ""
    semantic_type = field.get("semantic_type") or ""
    pk = bool(field.get("primary_key"))
    jk = bool(field.get("is_join_key"))
    nullable = bool(field.get("nullable", True))
    pii = (field.get("pii") or "none")
    masking = field.get("masking") or "none"
    conf = float(field.get("confidence", 1.0) or 1.0)
    mappings = field.get("mappings") or []
    desc = field.get("description") or ""
    card_text = f"{name} is a {data_type} field ({semantic_type}). {'Primary key. ' if pk else ''}{'Join key. ' if jk else ''}PII: {pii}; masking: {masking}. {'Nullable.' if nullable else 'Not nullable.'} {desc}"
    metadata = {
        "card_kind": "field",
        "entity_name": entity_name,
        "field_name": name,
        "data_type": data_type,
        "semantic_type": semantic_type,
        "primary_key": pk,
        "is_join_key": jk,
        "nullable": nullable,
        "pii": pii,
        "masking": masking,
        "confidence": conf,
        "mappings": mappings,
    }
    return _truncate(card_text, "INDEX_MAX_TEXT_LEN"), metadata


def _compute_relationship_card(version: str, generated_at: str, rel: dict) -> Tuple[str, Dict[str, Any]]:
    rtype = rel.get("type") or ""
    fe = rel.get("from_entity") or ""
    te = rel.get("to_entity") or ""
    join_on = rel.get("join_on") or []
    conf = float(rel.get("confidence", 1.0) or 1.0)
    joins = ", ".join([f"{fe}.{p.get('from_field')} → {te}.{p.get('to_field')}" for p in join_on if p.get("from_field") and p.get("to_field")])
    card_text = f"{fe} to {te} is {rtype}. Join keys: {joins or 'n/a'}. Used to connect related records across sources. Confidence: {conf:.2f}."
    metadata = {
        "card_kind": "relationship",
        "type": rtype,
        "from_entity": fe,
        "to_entity": te,
        "join_on": join_on,
        "confidence": conf,
        "version": version,
        "generated_at": generated_at,
    }
    return _truncate(card_text), metadata


def _embed_texts(texts: List[str]) -> List[List[float]]:
    # Provider/model/API key are read inside LLM client config
    # IMPORTANT: Use a true embedding endpoint, not chat. Here we use OpenAI via langchain-openai if available
    from langchain_openai import OpenAIEmbeddings
    model = os.getenv("EMBEDDING_MODEL", os.getenv("LLM_EMBEDDING_MODEL", "text-embedding-3-small"))
    api_key = os.getenv("EMBEDDING_API_KEY", os.getenv("LLM_API_KEY"))
    if not api_key:
        raise RuntimeError("Missing EMBEDDING_API_KEY/LLM_API_KEY for embeddings")
    embedder = OpenAIEmbeddings(model=model, api_key=api_key)
    return embedder.embed_documents(texts)


def upsert_cards(db: Session, tenant_id: str, canonical: Dict[str, Any]) -> Dict[str, Any]:
    version = canonical.get("version") or ""
    generated_at = canonical.get("generated_at") or datetime.utcnow().isoformat() + "Z"
    entities = canonical.get("entities") or []
    relationships = canonical.get("relationships") or []

    # Prepare cards
    entity_cards: List[Tuple[str, Dict[str, Any], str]] = []  # (text, meta, key_hash)
    field_cards: List[Tuple[str, Dict[str, Any], str]] = []
    rel_cards: List[Tuple[str, Dict[str, Any], str]] = []

    for ent in entities:
        text_value, meta = _compute_entity_card(ent, version, generated_at)
        meta["tenant_id"] = tenant_id
        key_hash = _hash_key([tenant_id, "entity", ent.get("name") or ""])
        entity_cards.append((text_value, meta, key_hash))
        for f in ent.get("fields") or []:
            f_text, f_meta = _compute_field_card(ent.get("name") or "", f)
            f_meta["tenant_id"] = tenant_id
            f_key_hash = _hash_key([tenant_id, "field", ent.get("name") or "", f.get("name") or ""])
            field_cards.append((f_text, f_meta, f_key_hash))

    for rel in relationships:
        r_text, r_meta = _compute_relationship_card(version, generated_at, rel)
        r_meta["tenant_id"] = tenant_id
        r_key_hash = _hash_key([tenant_id, "relationship", rel.get("from_entity") or "", rel.get("to_entity") or "", rel.get("type") or ""])
        rel_cards.append((r_text, r_meta, r_key_hash))

    # Embed texts
    texts = [t for (t, _, _) in entity_cards + field_cards + rel_cards]
    embeddings = _embed_texts(texts)

    # Upsert into pgvector-backed table (embedding stored as pgvector 'vector' type)
    now_iso = datetime.utcnow().isoformat()
    rows = []
    for idx, (t, m, k) in enumerate(entity_cards + field_cards + rel_cards):
        rows.append({
            "tenant_id": tenant_id,
            "key_kind": m.get("card_kind"),
            "key_hash": k,
            "card_text": t,
            "metadata": m,
            "embedding": embeddings[idx],
            "created_at": now_iso,
            "updated_at": now_iso,
        })

    # Use INSERT ... ON CONFLICT for idempotent upsert by unique key
    # We store embedding as float[] for portability; if you switch to pgvector type, adjust migration and casting
    for r in rows:
        stmt = text(
            """
            INSERT INTO vector_cards (card_id, tenant_id, key_kind, key_hash, card_text, metadata, embedding, created_at, updated_at)
            VALUES (gen_random_uuid(), :tenant_id, :key_kind, :key_hash, :card_text, CAST(:metadata AS JSONB), :embedding, :created_at, :updated_at)
            ON CONFLICT (tenant_id, key_kind, key_hash)
            DO UPDATE SET card_text = EXCLUDED.card_text, metadata = EXCLUDED.metadata, embedding = EXCLUDED.embedding, updated_at = EXCLUDED.updated_at
            """
        )
        # psycopg2/pgvector expects a python list for vector; many drivers cast it implicitly
        db.execute(stmt, r)
    db.commit()

    return {
        "entities": len(entity_cards),
        "fields": len(field_cards),
        "relationships": len(rel_cards),
        "total": len(rows)
    }


