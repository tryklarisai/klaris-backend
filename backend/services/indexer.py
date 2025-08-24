from __future__ import annotations
from typing import Any, Dict, List, Tuple
import json
import hashlib
from datetime import datetime
from sqlalchemy import text, Table, Column, String as SAString, Text as SAText, DateTime as SADateTime, MetaData, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from pgvector.sqlalchemy import Vector
from sqlalchemy.orm import Session

from services.settings import get_tenant_settings, get_setting
from constants import INDEX_MAX_TEXT_LEN as KEY_INDEX_MAX_TEXT_LEN
from constants import INDEX_MAX_FIELDS_PER_ENTITY as KEY_INDEX_MAX_FIELDS_PER_ENTITY


def _hash_key(parts: List[str]) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update((p or "").encode("utf-8"))
        h.update(b"|")
    return h.hexdigest()


def _truncate(text_value: str, max_len: int) -> str:
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
    for f in fields:
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
    return card_text, metadata


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
    return card_text, metadata


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
    return card_text, metadata


def _embed_texts(db: Session, tenant_id: str, texts: List[str]) -> List[List[float]]:
    from services.embeddings import embed_and_log
    return embed_and_log(db, tenant_id, texts, category="indexer_cards", module="data_relationships")


def upsert_cards(db: Session, tenant_id: str, canonical: Dict[str, Any]) -> Dict[str, Any]:
    settings = get_tenant_settings(db, tenant_id)
    max_text_len = int(get_setting(settings, KEY_INDEX_MAX_TEXT_LEN, 1200))
    max_fields_per_entity = int(get_setting(settings, KEY_INDEX_MAX_FIELDS_PER_ENTITY, 200))
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
        entity_cards.append((_truncate(text_value, max_text_len), meta, key_hash))
        for f in (ent.get("fields") or [])[:max_fields_per_entity]:
            f_text, f_meta = _compute_field_card(ent.get("name") or "", f)
            f_meta["tenant_id"] = tenant_id
            f_key_hash = _hash_key([tenant_id, "field", ent.get("name") or "", f.get("name") or ""])
            field_cards.append((_truncate(f_text, max_text_len), f_meta, f_key_hash))

    for rel in relationships:
        r_text, r_meta = _compute_relationship_card(version, generated_at, rel)
        r_meta["tenant_id"] = tenant_id
        r_key_hash = _hash_key([tenant_id, "relationship", rel.get("from_entity") or "", rel.get("to_entity") or "", rel.get("type") or ""])
        rel_cards.append((_truncate(r_text, max_text_len), r_meta, r_key_hash))

    # Embed texts
    texts = [t for (t, _, _) in entity_cards + field_cards + rel_cards]
    embeddings = _embed_texts(db, tenant_id, texts)

    # Upsert into pgvector-backed table (embedding stored as pgvector 'vector' type)
    now_dt = datetime.utcnow()
    rows = []
    for idx, (t, m, k) in enumerate(entity_cards + field_cards + rel_cards):
        rows.append({
            "tenant_id": tenant_id,
            "key_kind": m.get("card_kind"),
            "key_hash": k,
            "card_text": t,
            "metadata": m,
            "embedding": embeddings[idx],
            "created_at": now_dt,
            "updated_at": now_dt,
        })

    # Use SQLAlchemy Core with pgvector type for robust binding
    metadata = MetaData()
    vector_cards = Table(
        'vector_cards', metadata,
        Column('card_id', PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()),
        Column('tenant_id', PGUUID(as_uuid=True), nullable=False),
        Column('key_kind', SAString(length=32), nullable=False),
        Column('key_hash', SAString(length=128), nullable=False),
        Column('card_text', SAText(), nullable=False),
        Column('metadata', JSONB, nullable=False),
        Column('embedding', Vector(), nullable=False),
        Column('created_at', SADateTime(), nullable=False),
        Column('updated_at', SADateTime(), nullable=False),
    )

    for r in rows:
        ins = pg_insert(vector_cards).values(
            tenant_id=r['tenant_id'],
            key_kind=r['key_kind'],
            key_hash=r['key_hash'],
            card_text=r['card_text'],
            metadata=r['metadata'],
            embedding=r['embedding'],
            created_at=r['created_at'],
            updated_at=r['updated_at'],
        )
        upsert = ins.on_conflict_do_update(
            index_elements=[vector_cards.c.tenant_id, vector_cards.c.key_kind, vector_cards.c.key_hash],
            set_={
                'card_text': ins.excluded.card_text,
                'metadata': ins.excluded.metadata,
                'embedding': ins.excluded.embedding,
                'updated_at': ins.excluded.updated_at,
            }
        )
        db.execute(upsert)
    db.commit()

    return {
        "entities": len(entity_cards),
        "fields": len(field_cards),
        "relationships": len(rel_cards),
        "total": len(rows)
    }


