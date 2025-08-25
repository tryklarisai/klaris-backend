"""
chat_graph.py
Planning-only chat agent:
 - Loads connectors + truncated canonical schema for the tenant
 - Asks the LLM to propose connectors and read-only queries (no tool execution)
 - Returns plans + optional clarifications + a human-readable answer
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
import os, json, logging, re
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import text, bindparam
from datetime import datetime

from models.connector import Connector
from models.schema_review import GlobalCanonicalSchema
from models.schema import Schema
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain.callbacks.base import BaseCallbackHandler
from .tools import make_generic_tools
from services.chat_llm import stream_chat_with_tools
from pgvector.sqlalchemy import Vector
from services.embeddings import get_embeddings_client_for_tenant
from services.settings import get_tenant_settings, get_setting
from services.usage import log_usage_event

logger = logging.getLogger("chat_graph")

# In-memory store for chat histories keyed by session (tenant + thread)
_THREAD_HISTORIES: dict[str, InMemoryChatMessageHistory] = {}
# Per-session max turns configured from tenant settings
_SESSION_MAX_TURNS: dict[str, int] = {}

class MessageHistory:
    """Lightweight message history used in tests/back-compat.
    Stores (role, content) tuples and can convert to LangChain's InMemoryChatMessageHistory.
    """
    def __init__(self) -> None:
        self.messages: List[tuple[str, str]] = []

    def add_message(self, role: str, content: str) -> None:
        self.messages.append((str(role), str(content)))

    def to_langchain(self) -> InMemoryChatMessageHistory:
        h = InMemoryChatMessageHistory()
        try:
            for role, content in self.messages:
                r = (role or "").lower()
                if r in ("user", "human"):
                    h.add_user_message(content)
                elif r in ("assistant", "ai"):
                    h.add_ai_message(content)
                else:
                    # default to user message for unknown roles
                    h.add_user_message(content)
        except Exception:
            pass
        return h

def _session_key(tenant_id: UUID, thread_id: Optional[str]) -> str:
    return f"{tenant_id}:{thread_id or 'default'}"

def create_thread(tenant_id: UUID) -> str:
    import uuid as _uuid
    tid = _uuid.uuid4().hex
    _THREAD_HISTORIES[_session_key(tenant_id, tid)] = InMemoryChatMessageHistory()
    return tid

def list_threads(tenant_id: UUID) -> list[str]:
    prefix = f"{tenant_id}:"
    return [k.split(":", 1)[1] for k in _THREAD_HISTORIES.keys() if k.startswith(prefix)]

def delete_thread(tenant_id: UUID, thread_id: str) -> bool:
    key = _session_key(tenant_id, thread_id)
    return _THREAD_HISTORIES.pop(key, None) is not None

# _make_llm_for_tenant unused after ChatLLM wrapper adoption

def _build_connectors_summary(connectors: List[Connector]) -> List[Dict[str, Any]]:
    return [{"connector_id": str(c.connector_id), "connector_type": c.type} for c in connectors]

def _normalize_connector_type(t: str) -> str:
    t = (t or "").lower()
    if t in ("postgresql", "psql", "pg"): return "postgres"
    if t in ("google_drive", "gdrive", "gsheets"): return "google_drive"
    return t

def _build_connector_capabilities(connectors: List[Connector], connector_schemas: Dict[str, Any]) -> Dict[str, Any]:
    caps: Dict[str, Any] = {}
    for c in connectors:
        ctype = _normalize_connector_type(c.type)
        base = {
            "connector_type": c.type,
            "tools": {
                "list_schema": {"args": {"connector_id": "string"}},
                "read": {"args": {"connector_id": "string", "spec": "connector-specific"}},
            },
        }

        if ctype == "postgres":
            base["tools"]["read"]["spec_schema"] = {
                "oneOf": [
                    {"type": "string", "description": "Raw SQL SELECT (single statement, no comments/semicolon)"},
                    {
                        "type": "object",
                        "required": ["name", "columns"],
                        "properties": {
                            "name": {"type": "string", "description": "schema.table"},
                            "columns": {"type": "array", "items": {"type": "string"}},
                            "filters": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "required": ["column", "op", "value"],
                                    "properties": {
                                        "column": {"type": "string"},
                                        "op": {"type": "string", "enum": ["=", "!=", ">", ">=", "<", "<=", "in"]},
                                        "value": {"type": ["string", "number", "array"]},
                                    },
                                },
                            },
                            "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                        },
                    },
                ]
            }
            base["tools"]["read"]["examples"] = [
                {"spec": "SELECT order_id, sales_total FROM sales.fact_order LIMIT 50"},
                {"spec": {"name": "sales.fact_order", "columns": ["order_id","sales_total"], "limit": 50}},
            ]

        elif ctype in ("google_drive", "gdrive", "gsheets"):
            base["connector_type"] = "google_drive"
            base["tools"]["read"]["spec_schema"] = {
                "type": "object",
                "required": ["entity_id"],
                "properties": {
                    "entity_id": {"type": "string", "description": "<file_id>:<sheet_title>"},
                    "columns": {"type": "array", "items": {"type": "string"}},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                },
                "additionalProperties": True,
            }
            # Build dynamic examples from current connector schema when possible
            try:
                schema_summary = connector_schemas.get(str(c.connector_id)) or {}
                tables = schema_summary.get("tables") or []
                example = None
                if isinstance(tables, list) and tables:
                    t0 = tables[0]
                    eid = t0.get("entity_id") or "FILE_ID:Sheet1"
                    cols = t0.get("columns") or []
                    cols = cols[:2] if isinstance(cols, list) else []
                    if cols:
                        example = {"spec": {"entity_id": eid, "columns": cols, "limit": 50}}
                    else:
                        example = {"spec": {"entity_id": eid, "limit": 50}}
                base["tools"]["read"]["examples"] = [example] if example else [
                    {"spec": {"entity_id": "FILE_ID:Sheet1", "limit": 50}}
                ]
            except Exception:
                base["tools"]["read"]["examples"] = [
                    {"spec": {"entity_id": "FILE_ID:Sheet1", "limit": 50}}
                ]
        else:
            # generic fallback
            base["tools"]["read"]["spec_schema"] = {"type": "object", "description": "Connector-specific spec"}
            base["tools"]["read"]["examples"] = [{"spec": {"limit": 50}}]

        caps[str(c.connector_id)] = base
    return caps


def _summarize_connector_raw_schema(raw: Any) -> Dict[str, Any]:
    """Produce a compact table/column summary from a connector's raw schema JSON.
    Tries common shapes and truncates for prompt budget.
    """
    tables: List[Dict[str, Any]] = []
    try:
        # Common shape: { tables: [ { name, columns: [ { name }|str ] } ] }
        if isinstance(raw, dict) and isinstance(raw.get("tables"), list):
            for t in raw.get("tables", [])[:20]:
                tname = t.get("name") if isinstance(t, dict) else None
                cols: List[str] = []
                col_items = (t.get("columns") if isinstance(t, dict) else None) or []
                for c in col_items[:20]:
                    if isinstance(c, str):
                        cols.append(c)
                    elif isinstance(c, dict):
                        n = c.get("name") or c.get("column") or c.get("field")
                        if isinstance(n, str):
                            cols.append(n)
                if isinstance(tname, str):
                    tables.append({"name": tname, "columns": cols})
        # Alternative: { schemas: { schema: { tables: { name: [cols] } } } }
        elif isinstance(raw, dict) and isinstance(raw.get("schemas"), dict):
            for _, s in list(raw.get("schemas", {}).items())[:3]:
                if isinstance(s, dict):
                    tdict = s.get("tables") or s.get("relations") or {}
                    if isinstance(tdict, dict):
                        for tname, citems in list(tdict.items())[:20]:
                            cols: List[str] = []
                            if isinstance(citems, list):
                                for c in citems[:20]:
                                    if isinstance(c, str):
                                        cols.append(c)
                                    elif isinstance(c, dict):
                                        n = c.get("name") or c.get("column") or c.get("field")
                                        if isinstance(n, str):
                                            cols.append(n)
                            tables.append({"name": str(tname), "columns": cols})
        # Fallback: try relations list
        elif isinstance(raw, dict) and isinstance(raw.get("relations"), list):
            for r in raw.get("relations", [])[:20]:
                if isinstance(r, dict):
                    tname = r.get("name") or r.get("table") or r.get("relation")
                    cols: List[str] = []
                    col_items = r.get("columns") or []
                    if isinstance(col_items, list):
                        for c in col_items[:20]:
                            if isinstance(c, str):
                                cols.append(c)
                            elif isinstance(c, dict):
                                n = c.get("name") or c.get("column") or c.get("field")
                                if isinstance(n, str):
                                    cols.append(n)
                    if isinstance(tname, str):
                        # carry through optional entity_id if present
                        ent = {"name": tname, "columns": cols}
                        if isinstance(r, dict) and r.get("entity_id"):
                            ent["entity_id"] = r.get("entity_id")
                        tables.append(ent)
        # Google Drive MCP: raw shape { "entities": [ { id, name, fields: [...] } ] }
        elif isinstance(raw, dict) and isinstance(raw.get("entities"), list):
            for e in raw.get("entities", [])[:50]:
                if not isinstance(e, dict):
                    continue
                ename = e.get("name")
                eid = e.get("id") or e.get("entity_id")
                fields = e.get("fields") or []
                cols: List[str] = []
                if isinstance(fields, list):
                    for f in fields[:200]:
                        if isinstance(f, str):
                            cols.append(f)
                        elif isinstance(f, dict):
                            n = f.get("name") or f.get("column") or f.get("field")
                            if isinstance(n, str):
                                cols.append(n)
                if isinstance(ename, str):
                    ent = {"name": ename, "columns": cols}
                    if isinstance(eid, str):
                        ent["entity_id"] = eid
                    tables.append(ent)
    except Exception:
        pass
    summary: Dict[str, Any] = {"tables": tables[:20]}
    # Include tiny raw excerpt to help LLM if tables[] is empty
    if not summary["tables"] and isinstance(raw, dict):
        excerpt = {k: raw.get(k) for k in list(raw.keys())[:3]}
        summary["raw_excerpt"] = excerpt
    return summary

def _load_connector_schemas(db: Session, tenant_id: UUID, connectors: List[Connector]) -> Dict[str, Any]:
    """Load latest per-connector raw schemas and summarize for planning."""
    out: Dict[str, Any] = {}
    for c in connectors:
        try:
            latest = (
                db.query(Schema)
                .filter(Schema.tenant_id == tenant_id, Schema.connector_id == c.connector_id)
                .order_by(Schema.fetched_at.desc())
                .first()
            )
            if not latest:
                continue
            out[str(c.connector_id)] = _summarize_connector_raw_schema(latest.raw_schema)
        except Exception:
            continue
    return out

def _normalize_identifier(s: str) -> str:
    """Lowercase, remove non-alphanum, collapse to help match 'Order ID' vs 'order_id'."""
    try:
        return re.sub(r"[^a-z0-9]", "", s.lower())
    except Exception:
        return s or ""

def _attach_field_sources(canonical_summary: Dict[str, Any], connector_schemas: Dict[str, Any], connectors: List[Connector]) -> None:
    """Augment canonical_summary.unified_entities[*].fields[*] with candidate source mappings.
    Adds `sources: [{connector_id, connector_type, entity, column, kind}]` when names match.
    """
    if not canonical_summary or not isinstance(canonical_summary.get("unified_entities"), list):
        return
    # Map connector_id -> type
    ctype_map: Dict[str, str] = {str(c.connector_id): c.type for c in connectors}
    # Precompute per-connector column index
    column_index: Dict[str, List[Dict[str, str]]] = {}
    for cid, summary in connector_schemas.items():
        try:
            items: List[Dict[str, str]] = []
            for t in (summary.get("tables") or [])[:50]:
                tname = t.get("name") if isinstance(t, dict) else None
                if not isinstance(tname, str):
                    continue
                cols = t.get("columns") if isinstance(t, dict) else None
                if isinstance(cols, list):
                    for col in cols[:200]:
                        if isinstance(col, str) and col:
                            items.append({"entity": tname, "column": col, "norm": _normalize_identifier(col)})
                # fallback: if columns missing, still index table
            column_index[cid] = items
        except Exception:
            continue
    # Attach to fields
    for ent in canonical_summary.get("unified_entities", []):
        fields = ent.get("fields") if isinstance(ent, dict) else None
        if not isinstance(fields, list):
            continue
        for i, f in enumerate(fields):
            # field may be str or dict with name
            if isinstance(f, str):
                fname = f
                fobj = {"name": f}
                ent["fields"][i] = fobj
            elif isinstance(f, dict):
                fname = f.get("name") or f.get("field") or ""
                fobj = f
            else:
                continue
            norm_f = _normalize_identifier(str(fname))
            sources: List[Dict[str, str]] = []
            for cid, items in column_index.items():
                for it in items:
                    if it.get("norm") == norm_f:
                        connector_type = ctype_map.get(cid, "")
                        kind = "sheet" if connector_type in ("google_drive", "gdrive", "gsheets") else "sql"
                        sources.append({
                            "connector_id": cid,
                            "connector_type": connector_type,
                            "entity": it.get("entity", ""),
                            "column": it.get("column", ""),
                            "kind": kind,
                        })
                        if len(sources) >= 5:
                            break
                if len(sources) >= 5:
                    break
            if sources:
                fobj["sources"] = sources

def _load_canonical_summary(db: Session, tenant_id: UUID) -> Dict[str, Any]:
    """Fetch latest global canonical schema graph for the tenant.
    Returns a dict and guarantees `unified_entities` exists (empty list fallback).
    """
    try:
        latest = (
            db.query(GlobalCanonicalSchema)
            .filter(GlobalCanonicalSchema.tenant_id == tenant_id)
            .order_by(GlobalCanonicalSchema.version.desc())
            .first()
        )
        if latest:
            graph = latest.canonical_graph
            if isinstance(graph, dict):
                # Ensure expected key exists for downstream enrichment
                if not isinstance(graph.get("unified_entities"), list):
                    graph = dict(graph)
                    graph["unified_entities"] = []
                return graph
    except Exception:
        # Swallow and fallback to minimal summary to keep planner operational
        pass
    return {"unified_entities": []}


def _normalize_term_value(value: str) -> str:
    try:
        return " ".join((value or "").strip().lower().split())
    except Exception:
        return value or ""


def _glossary_context_for_query(db: Session, tenant_id: UUID, query_text: str, top_k_terms: int = 5) -> Dict[str, Any]:
    """Glossary-only matching for chat context.
    Order: exact normalized match → vector (if available) → FTS fallback.
    Returns { terms: [{term, normalized_term, description, score}] }.
    """
    term_rows: List[Dict[str, Any]] = []

    # 1) Exact normalized equality
    try:
        norm_q = _normalize_term_value(query_text)
        if norm_q:
            q_eq = text(
                """
                SELECT t.term_id::text, t.term, t.normalized_term, t.description,
                       1.0 AS score
                FROM bcl_terms t
                WHERE t.tenant_id::text = :tenant
                  AND t.normalized_term = :norm_q
                LIMIT :k
                """
            )
            for r in db.execute(q_eq, {"tenant": str(tenant_id), "norm_q": norm_q, "k": int(top_k_terms)}):
                term_rows.append(dict(r._mapping))
        if term_rows:
            logger.info("BCL: exact-normalized matched %d terms", len(term_rows))
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass

    # 2) Vector semantic match
    if len(term_rows) < int(top_k_terms):
        try:
            from services.embeddings import embed_and_log
            [qvec] = embed_and_log(db, str(tenant_id), [query_text], category="chat", module="chat_module")
            q_vec = text(
                """
                SELECT t.term_id::text, t.term, t.normalized_term, t.description,
                       1 - (t.embedding <=> :qvec) AS score
                FROM bcl_terms t
                WHERE t.tenant_id::text = :tenant AND t.embedding IS NOT NULL
                ORDER BY t.embedding <=> :qvec
                LIMIT :k
                """
            ).bindparams(bindparam("qvec", type_=Vector()))
            for r in db.execute(q_vec, {"qvec": qvec, "tenant": str(tenant_id), "k": int(top_k_terms - len(term_rows))}):
                term_rows.append(dict(r._mapping))
            logger.info("BCL: vector matched total %d terms", len(term_rows))
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass

    # 3) FTS fallback
    if len(term_rows) < int(top_k_terms) and isinstance(query_text, str) and query_text.strip():
        q_fts = text(
            """
            SELECT t.term_id::text, t.term, t.normalized_term, t.description,
                   0.5 AS score
            FROM bcl_terms t
            WHERE t.tenant_id::text = :tenant
              AND to_tsvector('english', coalesce(t.term,'') || ' ' || coalesce(t.description,'')) @@ plainto_tsquery('english', :q)
            LIMIT :k
            """
        )
        try:
            for r in db.execute(q_fts, {"tenant": str(tenant_id), "q": query_text, "k": int(top_k_terms - len(term_rows))}):
                term_rows.append(dict(r._mapping))
            logger.info("BCL: FTS matched total %d terms", len(term_rows))
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass

    # Build response
    terms: List[Dict[str, Any]] = []
    for tr in term_rows:
        terms.append({
            "term": tr.get("term"),
            "normalized_term": tr.get("normalized_term"),
            "description": tr.get("description"),
            "score": float(tr.get("score") or 0.0),
        })
    return {"terms": terms}


def _extract_chart_intent(message: str) -> Dict[str, Any]:
    """Detect if user asked for a chart and infer desired type/options.
    Returns { want_chart: bool, type_hint: Optional[str], stacked: bool, normalized: bool, grouped: bool }
    type_hint in {bar,line,area,scatter,heatmap,histogram,boxplot,bubble}.
    """
    try:
        m = (message or "").lower()
        want = any(k in m for k in ("chart", "plot", "graph", "visual", "visualize", "visualisation", "visualization", "heatmap", "histogram", "boxplot", "box plot"))
        type_hint = None
        for k in ("heatmap", "histogram", "boxplot", "box plot", "bubble", "bar", "line", "area", "scatter"):
            if k in m:
                type_hint = "boxplot" if k in ("boxplot", "box plot") else ("scatter" if k == "bubble" else k)
                break
        # Parse top-k like "top 5"
        import re as _re
        m_top = _re.search(r"top\s+(\d{1,3})", m)
        top_k = int(m_top.group(1)) if m_top else None
        # Rolling/smoothing like "7-day rolling" or "smooth"
        m_roll = _re.search(r"(\d{2}|\d{1})[- ]?(day|week|wk|hour|hr)?\s+(rolling|moving|window)", m)
        smooth_window = int(m_roll.group(1)) if m_roll else (7 if ("rolling" in m or "moving average" in m or "smooth" in m) else None)

        opts = {
            "stacked": any(w in m for w in ("stack", "stacked")),
            "normalized": any(w in m for w in ("100%", "percent", "percentage", "normalized", "normalize")),
            "grouped": any(w in m for w in ("grouped", "side-by-side", "side by side")),
            "top_k": top_k,
            "smooth_window": smooth_window,
        }
        return {"want_chart": want or (type_hint is not None), "type_hint": type_hint, **opts}
    except Exception:
        return {"want_chart": False, "type_hint": None, "stacked": False, "normalized": False, "grouped": False, "top_k": None, "smooth_window": None}


def _is_numeric(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        try:
            float(value)
            return True
        except Exception:
            return False
    return False


def _is_temporal(value: Any) -> bool:
    if isinstance(value, (int, float)):
        # Treat pure numbers as non-temporal (skip epoch heuristics for simplicity)
        return False
    if isinstance(value, str):
        s = value.strip()
        # Quick ISO-like patterns
        if re.match(r"^\d{4}-\d{2}-\d{2}", s):
            return True
        try:
            # Fallback to ISO parse
            datetime.fromisoformat(s.replace("Z", "+00:00"))
            return True
        except Exception:
            return False
    return False


MAX_ROWS = 100
MAX_SERIES = 8

def _build_charts_from_preview(message: str, preview: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build minimal Vega-Lite chart specs from data preview based on simple heuristics.
    Returns a list of { title?, type: 'vega-lite', spec }.
    """
    if not isinstance(preview, dict):
        return []
    columns = preview.get("columns") or []
    rows = preview.get("rows") or []
    if not isinstance(columns, list) or not isinstance(rows, list) or not columns or not rows:
        return []

    intent = _extract_chart_intent(message)
    if not intent.get("want_chart"):
        return []

    # Guard rows and sample size
    if len(rows) > MAX_ROWS:
        rows = rows[:MAX_ROWS]
    # Infer column types by sampling
    sample = rows[: min(50, MAX_ROWS)]
    num_cols: List[str] = []
    temporal_cols: List[str] = []
    cat_cols: List[str] = []
    import re as _re
    for idx, col in enumerate(columns):
        col_values = [r[idx] for r in sample if isinstance(r, list) and len(r) > idx]
        num_count = sum(1 for v in col_values if _is_numeric(v))
        temp_count = sum(1 for v in col_values if _is_temporal(v))
        name = str(col)
        if _re.search(r"(\b|_)(id|uuid|email)(\b|_)", name, _re.I):
            # skip id-like columns from x/series consideration
            continue
        if num_count >= max(1, len(col_values) // 2):
            num_cols.append(str(col))
        elif temp_count >= max(1, len(col_values) // 2) or str(col).lower() in ("date", "day", "month", "year", "timestamp", "created_at", "updated_at"):
            temporal_cols.append(str(col))
        else:
            cat_cols.append(str(col))

    # Build records for values
    values: List[Dict[str, Any]] = []
    for r in sample:
        if not isinstance(r, list):
            continue
        obj: Dict[str, Any] = {}
        for i, c in enumerate(columns):
            if i < len(r):
                obj[str(c)] = r[i]
        if obj:
            values.append(obj)

    charts: List[Dict[str, Any]] = []
    type_hint = intent.get("type_hint")

    def add_chart(spec: Dict[str, Any], title: Optional[str] = None):
        charts.append({"title": title, "type": "vega-lite", "spec": spec})

    # --- Simple template helpers (consistent defaults/styles) ---
    def _vl_base(values: List[Dict[str, Any]], mark: Dict[str, Any] | str, encoding: Dict[str, Any], transforms: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
        spec: Dict[str, Any] = {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "data": {"values": values},
            "mark": mark if isinstance(mark, dict) else {"type": str(mark), "tooltip": True},
            "encoding": encoding,
            "width": "container",
            "height": 280,
        }
        if transforms:
            spec["transform"] = transforms
        return spec

    def build_line(values: List[Dict[str, Any]], x: str, y: str, series: Optional[str] = None, transforms: List[Dict[str, Any]] | None = None, area: bool = False, y_title: Optional[str] = None) -> Dict[str, Any]:
        enc: Dict[str, Any] = {
            "x": {"field": x, "type": "temporal"},
            "y": {"field": y, "type": "quantitative"},
        }
        if y_title:
            enc["y"]["title"] = y_title
        if series:
            enc["color"] = {"field": series, "type": "nominal"}
        return _vl_base(values, {"type": ("area" if area else "line"), "tooltip": True}, enc, transforms)

    def build_bar(values: List[Dict[str, Any]], x: str, y: str, series: Optional[str] = None, transforms: List[Dict[str, Any]] | None = None, stacked: Optional[str | bool] = None, column_facet: Optional[str] = None, y_title: Optional[str] = None) -> Dict[str, Any]:
        enc: Dict[str, Any] = {
            "x": {"field": x, "type": "nominal"},
            "y": {"field": y, "type": "quantitative"},
        }
        if y_title:
            enc["y"]["title"] = y_title
        if stacked is not None:
            enc["y"]["stack"] = stacked
        if series:
            enc["color"] = {"field": series, "type": "nominal"}
        spec = _vl_base(values, {"type": "bar", "tooltip": True}, enc, transforms)
        if column_facet:
            spec["column"] = {"field": column_facet, "type": "nominal"}
        return spec

    def build_scatter(values: List[Dict[str, Any]], x: str, y: str, size: Optional[str] = None, transforms: List[Dict[str, Any]] | None = None, y_title: Optional[str] = None) -> Dict[str, Any]:
        enc: Dict[str, Any] = {
            "x": {"field": x, "type": "quantitative"},
            "y": {"field": y, "type": "quantitative"},
        }
        if y_title:
            enc["y"]["title"] = y_title
        if size:
            enc["size"] = {"field": size, "type": "quantitative"}
        return _vl_base(values, {"type": "point", "tooltip": True}, enc, transforms)

    def build_hist(values: List[Dict[str, Any]], x: str) -> Dict[str, Any]:
        enc = {
            "x": {"field": x, "bin": True, "type": "quantitative"},
            "y": {"aggregate": "count", "type": "quantitative", "title": "Count"},
        }
        return _vl_base(values, {"type": "bar", "tooltip": True}, enc)

    def build_heatmap(values: List[Dict[str, Any]], x: str, y: str, transforms: List[Dict[str, Any]]) -> Dict[str, Any]:
        enc = {
            "x": {"field": x, "type": "nominal"},
            "y": {"field": y, "type": "nominal"},
            "color": {"field": "value", "type": "quantitative"},
        }
        return _vl_base(values, {"type": "rect", "tooltip": True}, enc, transforms)

    # Prefer temporal line/area when available
    if temporal_cols and num_cols:
        x = temporal_cols[0]
        nums = num_cols[:MAX_SERIES]
        transforms: List[Dict[str, Any]] = []
        enc_y_field = None
        if len(nums) > 1:
            # Fold to long for multi-series
            transforms.append({"fold": nums, "as": ["series", "value"]})
            # Coerce numeric strings before aggregating
            transforms.append({"calculate": "toNumber(datum['value'])", "as": "value_num"})
            # Aggregate per period/series (sum)
            transforms.append({"aggregate": [{"op": "sum", "field": "value_num", "as": "metric"}], "groupby": [x, "series"]})
            # Rolling smoothing if asked
            if intent.get("smooth_window"):
                transforms.append({
                    "window": [{"op": "mean", "field": "metric", "as": "metric_smooth"}],
                    "frame": [-(int(intent.get("smooth_window")) - 1), 0],
                    "groupby": ["series"],
                    "sort": [{"field": x}]
                })
                enc_y_field = "metric_smooth"
            else:
                enc_y_field = "metric"
        else:
            # Coerce numeric strings then aggregate per period
            transforms.append({"calculate": f"toNumber(datum['{nums[0]}'])", "as": "metric_src"})
            transforms.append({"aggregate": [{"op": "sum", "field": "metric_src", "as": "metric"}], "groupby": [x]})
            if intent.get("smooth_window"):
                transforms.append({
                    "window": [{"op": "mean", "field": "metric", "as": "metric_smooth"}],
                    "frame": [-(int(intent.get("smooth_window")) - 1), 0],
                    "sort": [{"field": x}]
                })
                enc_y_field = "metric_smooth"
            else:
                enc_y_field = "metric"
        # Y-axis title
        y_title = None
        if len(nums) == 1:
            y_title = str(nums[0])
        elif len(nums) > 1:
            y_title = "Sum"
        spec = build_line(values, x=x, y=enc_y_field or "metric", series=("series" if len(nums) > 1 else None), transforms=transforms, area=(type_hint == "area"), y_title=y_title)
        add_chart(spec, title=None)
        return charts

    # Temporal count (no numeric present) → line/area of counts by period
    if temporal_cols and not num_cols:
        x = temporal_cols[0]
        spec = _vl_base(values, {"type": ("area" if type_hint == "area" else "line"), "tooltip": True}, {
            "x": {"field": x, "type": "temporal", "timeUnit": "yearmonthdate"},
            "y": {"aggregate": "count", "type": "quantitative", "title": "Count"}
        })
        add_chart(spec, title=None)
        return charts

    # Histogram of a single numeric column
    if intent.get("type_hint") in ("histogram", "density") and num_cols:
        x = num_cols[0]
        spec = build_hist(values, x)
        add_chart(spec, title=None)
        return charts

    # Heatmap for two categorical (or binned) axes
    if intent.get("type_hint") == "heatmap" and (len(cat_cols) + len(temporal_cols)) >= 2:
        ax = (cat_cols + temporal_cols)
        x = ax[0]
        y = ax[1]
        spec = build_heatmap(values, x, y, transforms=[{"aggregate": [{"op": "count", "as": "value"}], "groupby": [x, y]}])
        add_chart(spec, title=None)
        return charts

    # Scatter if user asked and we have 2 numeric columns
    if type_hint == "scatter" and len(num_cols) >= 2:
        x, y = num_cols[0], num_cols[1]
        spec = build_scatter(values, x, y, size=(num_cols[2] if (len(num_cols) >= 3 and intent.get("type_hint") == "bubble") else None), y_title=str(y))
        add_chart(spec, title=None)
        return charts

    # Bar for categorical + numeric (supports grouped/stacked/normalized)
    if cat_cols and num_cols:
        x = cat_cols[0]
        # If multiple numeric measures and no natural series, emit separate charts per measure (instead of folding)
        if len(num_cols) >= 2 and not (len(cat_cols) >= 2):
            for measure in num_cols[:MAX_SERIES]:
                transforms: List[Dict[str, Any]] = []
                transforms.append({"calculate": f"toNumber(datum['{measure}'])", "as": "metric_src"})
                transforms.append({"aggregate": [{"op": "sum", "field": "metric_src", "as": "metric"}], "groupby": [x]})
                # Top-K
                if intent.get("top_k"):
                    transforms.append({
                        "window": [{"op": "rank", "as": "rank"}],
                        "sort": [{"field": "metric", "order": "descending"}],
                    })
                    transforms.append({"filter": f"datum.rank <= {int(intent['top_k'])}"})
                stacked = "normalize" if intent.get("normalized") else (True if intent.get("stacked") else None)
                spec = build_bar(values, x=x, y="metric", series=None, transforms=transforms, stacked=stacked, y_title=str(measure))
                add_chart(spec, title=str(measure))
            return charts
        # Otherwise, single measure or natural series present
        series: Optional[str] = None
        transforms: List[Dict[str, Any]] = []
        if len(cat_cols) >= 2:
            series = cat_cols[1]
        y = num_cols[0]
        transforms.append({"calculate": f"toNumber(datum['{y}'])", "as": "metric_src"})
        transforms.append({
            "aggregate": [{"op": "sum", "field": "metric_src", "as": "metric"}],
            "groupby": [x] + ([series] if series else []),
        })
        # Top-K
        if intent.get("top_k"):
            transforms.append({
                "window": [{"op": "rank", "as": "rank"}],
                "sort": [{"field": "metric", "order": "descending"}],
                **({"groupby": [series]} if series else {})
            })
            transforms.append({"filter": f"datum.rank <= {int(intent['top_k'])}"})
        enc: Dict[str, Any] = {
            "x": {"field": x, "type": "nominal"},
            "y": {"field": "metric", "type": "quantitative", "title": str(y)},
        }
        if series and intent.get("grouped"):
            spec = build_bar(values, x=x, y="metric", series=series, transforms=transforms, column_facet=series, y_title=str(y))
            add_chart(spec, title=None)
            return charts
        stacked = "normalize" if intent.get("normalized") else (True if intent.get("stacked") else None)
        spec = build_bar(values, x=x, y="metric", series=series, transforms=transforms, stacked=stacked, y_title=str(y))
        add_chart(spec, title=None)
        return charts

    # Pure categorical → count per category bar
    if cat_cols and not num_cols:
        x = cat_cols[0]
        spec = build_bar(values, x=x, y="count", transforms=[{"aggregate": [{"op": "count", "as": "count"}], "groupby": [x]}], y_title="Count")
        add_chart(spec, title=None)
        return charts

    # Fallback: if at least 2 numeric columns, scatter
    if len(num_cols) >= 2:
        x, y = num_cols[0], num_cols[1]
        spec = {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "data": {"values": values},
            "mark": {"type": "point", "tooltip": True},
            "encoding": {
                "x": {"field": x, "type": "quantitative"},
                "y": {"field": y, "type": "quantitative", "title": str(y)}
            }
        }
        add_chart(spec, title=None)
        return charts

    return []

def run_chat_agent(db: Session, tenant_id: UUID, message: str) -> Dict[str, Any]:
    raise RuntimeError(
        "run_chat_agent() has been removed. Use run_chat_agent_stream() and aggregate its events for a final response."
    )

def _history_for_session(session_id: str) -> InMemoryChatMessageHistory:
    """Get or create an in-memory history for a session, trimming to a window size.
    
    Max turns are set per-session from tenant settings in run_chat_agent_stream.
    """
    hist = _THREAD_HISTORIES.setdefault(session_id, InMemoryChatMessageHistory())
    try:
        max_turns = int(_SESSION_MAX_TURNS.get(session_id, 20))
        msgs = getattr(hist, "messages", None)
        if isinstance(msgs, list) and max_turns > 0:
            # Keep last 2*max_turns messages (approx pairs)
            limit = 2 * max_turns
            if len(msgs) > limit:
                hist.messages = msgs[-limit:]
    except Exception:
        pass
    return hist

async def run_chat_agent_stream(db: Session, tenant_id: UUID, message: str, thread_id: Optional[str] = None):
    """Yield Server-Sent Events using LangChain's astream_events for minimal maintenance.
    Events: token, thought (agent logs), tool_start, tool_end, final, done
    """
    connectors: List[Connector] = db.query(Connector).filter(Connector.tenant_id == tenant_id).all()
    canonical_summary = _load_canonical_summary(db, tenant_id)
    conn_summaries = _build_connectors_summary(connectors)
    connector_schemas = _load_connector_schemas(db, tenant_id, connectors)
    _attach_field_sources(canonical_summary, connector_schemas, connectors)
    connector_capabilities = _build_connector_capabilities(connectors, connector_schemas)

    # Streaming agent instructions (same content as non-streaming path)
    agent_instructions = (
        "You are an analytics assistant. Use the available tools to plan and gather data. "
        "Use ONLY tables/columns derivable from the provided schema context (canonical_summary and connector_schemas). Do NOT guess or invent. "
        "Fields in canonical_summary include candidate source mappings in field.sources; prefer those to choose connector/resource. "
        "When uncertain, ask a brief clarification before proceeding. Keep tool calls minimal (use LIMITs). "
        "Use list_schema to explore only when needed, then use read with a precise spec per connector_capabilities. "
        "Before calling any tools, first restate the user's goal in a friendly, clear, and concise way. "
        "Then outline a short, structured plan of the logical steps you will follow. "
        "As you execute tool calls, narrate progress succinctly and sequentially. "
        "Finish by summarizing the completed work distinctly from your upfront plan. "
        "If the user asks for a chart/graph/plot, you MUST run read tool(s) to produce a compact aggregated table suitable for plotting, with small LIMITs. "
        "Charts Result Contract: ONLY return aggregated tables in one of these shapes: [x, y] or [x, series, value]. x is categorical or temporal; y/value is numeric. Use GROUP BY x[, series]. "
        "Never return entity-level rows (ids, emails, uuids) for chart requests. Prefer top-k and short time buckets to keep results small (≤ 100 rows, ≤ 8 series). "
        "Do NOT say that you cannot create charts; the application will render charts from your tabular result. "
        "For time ranges like 'last 3 quarters', compute those periods and aggregate accordingly. "
        "After gathering, produce a concise final answer to the user. Do not output JSON; respond with natural language."
    )

    previews: List[Dict[str, Any]] = []
    data_preview: Optional[Dict[str, Any]] = None
    route_meta: Optional[Dict[str, str]] = None

    def _on_rows(connector_id: str, connector_type: str, columns: List[Any], rows: List[List[Any]]) -> None:
        nonlocal data_preview, route_meta
        # Prefer the preview with more numeric columns (better chance to chart multiple series)
        try:
            def count_numeric(cols: List[Any], rs: List[List[Any]]) -> int:
                sample = rs[:50]
                cnt = 0
                for idx, _c in enumerate(cols or []):
                    col_values = [r[idx] for r in sample if isinstance(r, list) and len(r) > idx]
                    num_count = sum(1 for v in col_values if _is_numeric(v))
                    if num_count >= max(1, len(col_values) // 2):
                        cnt += 1
                return cnt
            incoming_numeric = count_numeric(columns or [], rows or [])
            current_numeric = count_numeric((data_preview or {}).get("columns") or [], (data_preview or {}).get("rows") or []) if data_preview else -1
        except Exception:
            incoming_numeric, current_numeric = 0, -1
        if data_preview is None or incoming_numeric > current_numeric or (incoming_numeric == current_numeric and len(columns or []) > len((data_preview or {}).get("columns") or [])):
            data_preview = {"columns": columns, "rows": rows[:50]}
        if route_meta is None:
            route_meta = {"tool": "read", "connector_id": str(connector_id), "connector_type": connector_type}
        previews.append({
            "connector_id": str(connector_id),
            "connector_type": connector_type,
            "columns": columns,
            "rows": rows[:50],
        })

    tools = make_generic_tools(connectors, connector_schemas, on_rows=_on_rows)

    glossary_ctx = _glossary_context_for_query(db, tenant_id, message)
    chart_intent = _extract_chart_intent(message)

    payload = {
        "tenant_id": str(tenant_id),
        "connectors": conn_summaries,
        "canonical_summary": canonical_summary,
        "connector_schemas": connector_schemas,
        "connector_capabilities": connector_capabilities,
        "glossary_context": glossary_ctx,
        "chart_intent": chart_intent,
    }

    context_json = json.dumps(payload)
    prompt = ChatPromptTemplate.from_messages([
        ("system", agent_instructions),
        ("system", "Context for tools and planning (JSON): {context}"),
        ("system", "Charting rules (Result Contract): If chart_intent.want_chart is true, your **final tool call** MUST return a small, aggregated table in one of these shapes:\n"
                    "A) [x, y] where x is temporal OR categorical, and y is a single numeric aggregate (COUNT/SUM/AVG). 5–100 rows.\n"
                    "B) [x, series, value] where x is temporal OR categorical, series is a short label, and value is numeric. 5–100 rows.\n"
                    "Do NOT return entity-level rows (ids/emails/order lines). Use GROUP BY and aggregations. If you cannot determine the aggregation, ask one brief clarification before calling tools.\n"
                    "SQL examples:\n"
                    " - Temporal: SELECT date_trunc('month', created_at) AS period, COUNT(*) AS orders FROM sales.orders GROUP BY 1 ORDER BY 1 LIMIT 100\n"
                    " - Categorical: SELECT status AS x, COUNT(*) AS y FROM tickets GROUP BY 1 ORDER BY 2 DESC LIMIT 50\n"
                    " - Multi-series: SELECT date_trunc('week', created_at) AS period, channel AS series, COUNT(*) AS value FROM events GROUP BY 1,2 ORDER BY 1 LIMIT 100\n"),
        ("system", "If glossary_context.terms contains any term mentioned or implied by the user, you MUST use the provided mappings exactly (expressions/filters) and MUST NOT substitute alternative definitions. "
                   "Prefer mappings with higher confidence. When you explain your answer, concisely reflect the provided rationale where helpful. "
                   "If no mappings are given for a relevant term, ask a brief clarification rather than assuming a definition."),
        MessagesPlaceholder("chat_history"),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])

    # Configure per-session chat history window from tenant settings
    try:
        settings = get_tenant_settings(db, tenant_id)
        max_turns_cfg = int(get_setting(settings, "CHAT_HISTORY_MAX_TURNS", 20))
    except Exception:
        max_turns_cfg = 20

    # Back-compat: allow passing a MessageHistory object instead of thread_id
    provided_history = None
    if isinstance(thread_id, MessageHistory):
        provided_history = thread_id
        thread_id = "__inline__"
    session_id = _session_key(tenant_id, thread_id)
    _SESSION_MAX_TURNS[session_id] = max_turns_cfg
    if provided_history is not None:
        _THREAD_HISTORIES[session_id] = provided_history.to_langchain()

    # Usage capture (best-effort)
    import time
    t0 = time.time()
    usage_input = 0
    usage_output = 0
    usage_total = 0

    class _UsageCapture(BaseCallbackHandler):
        def __init__(self) -> None:
            self.input_tokens = 0
            self.output_tokens = 0
            self.total_tokens = 0

        def on_chat_model_end(self, response, **kwargs):  # type: ignore[override]
            try:
                usage = None
                
                # OpenAI via LangChain often exposes token counts here
                usage = getattr(response, "usage_metadata", None)
                if not usage:
                    gens = getattr(response, "generations", None)
                    if gens and len(gens) > 0 and len(gens[0]) > 0:
                        gi = getattr(gens[0][0], "generation_info", None) or {}
                        usage = gi.get("usage") or gi.get("token_usage") or gi
                if not usage:
                    lo = getattr(response, "llm_output", None) or {}
                    if isinstance(lo, dict):
                        usage = lo.get("token_usage") or lo.get("usage")
                if isinstance(usage, dict):
                    pi = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
                    co = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
                    tt = int(usage.get("total_tokens") or (pi + co))
                    self.input_tokens += pi
                    self.output_tokens += co
                    self.total_tokens += tt
            except Exception:
                pass

        def on_llm_end(self, response, **kwargs):  # type: ignore[override]
            # Fallback for non-chat models
            try:
                usage = getattr(response, "usage_metadata", None)
                if not usage:
                    lo = getattr(response, "llm_output", None) or {}
                    if isinstance(lo, dict):
                        usage = lo.get("token_usage") or lo.get("usage")
                if isinstance(usage, dict):
                    pi = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
                    co = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
                    tt = int(usage.get("total_tokens") or (pi + co))
                    self.input_tokens += pi
                    self.output_tokens += co
                    self.total_tokens += tt
            except Exception:
                pass

    usage_cb = _UsageCapture()
    # Retry removed per pilot: keep streaming simple and responsive

    charts_payload: Optional[List[Dict[str, Any]]] = None
    try:
        # Send an initial event to prompt clients to render immediately
        yield "event: ready\ndata: {}\n\n"
        async for ev in stream_chat_with_tools(
            db,
            str(tenant_id),
            prompt=prompt,
            tools=tools,
            session_id=session_id,
            history_provider=_history_for_session,
            input_payload={"input": message, "context": context_json},
            callbacks=[usage_cb],
        ):
            etype = ev.get("event")
            data = ev.get("data", {}) or {}
            # Stream tokens
            if etype in ("on_llm_stream", "on_chat_model_stream"):
                chunk = data.get("chunk")
                token = getattr(chunk, "content", None)
                if token is None:
                    token = chunk if isinstance(chunk, str) else str(chunk)
                token_s = str(token)
                if token_s:
                    yield f"event: token\ndata: {json.dumps({'token': token_s})}\n\n"
            # Tool lifecycle
            elif etype == "on_tool_start":
                name = ev.get("name") or data.get("name") or "tool"
                inp = data.get("input")
                yield f"event: tool_start\ndata: {json.dumps({'tool': name, 'input': str(inp)})}\n\n"
            elif etype == "on_tool_end":
                out_full = data.get("output")
                # Capture preview from tool output if on_rows callback hasn't set it yet
                try:
                    if (
                        data_preview is None
                        and isinstance(out_full, dict)
                        and isinstance(out_full.get("columns"), list)
                        and isinstance(out_full.get("rows"), list)
                    ):
                        data_preview = {
                            "columns": out_full.get("columns"),
                            "rows": (out_full.get("rows") or [])[:50],
                        }
                except Exception:
                    pass
                # Populate route metadata from tool output if available
                try:
                    if route_meta is None and isinstance(out_full, dict):
                        cid = out_full.get("connector_id")
                        ctype = out_full.get("connector_type")
                        if isinstance(cid, str) and cid:
                            route_meta = {"tool": "read", "connector_id": str(cid), "connector_type": str(ctype or "")}
                except Exception:
                    pass
                # truncate rows in outputs to keep SSE light
                outp = out_full
                if isinstance(outp, dict) and isinstance(outp.get("rows"), list):
                    outp = dict(outp)
                    outp["rows"] = outp["rows"][:5]
                yield f"event: tool_end\ndata: {json.dumps(outp)}\n\n"
            # Usage accumulation if provided by backend
            elif etype in ("on_llm_end", "on_chat_model_end"):
                try:
                    usage = None
                    if isinstance(data, dict):
                        # Prefer direct usage fields present in OpenAI stream end
                        usage = (
                            data.get("usage")
                            or data.get("usage_metadata")
                            or data.get("generation_info", {}).get("usage")
                        )
                        if not usage:
                            resp = data.get("response") or {}
                            if isinstance(resp, dict):
                                usage = resp.get("usage") or resp.get("usage_metadata")
                        # Fallback: parse from stringified output if present
                        if not usage:
                            try:
                                out_s = str(data.get("output") or "")
                                idx = out_s.find("usage_metadata=")
                                if idx != -1:
                                    start = idx + len("usage_metadata=")
                                    # capture balanced braces
                                    depth = 0
                                    j = start
                                    started = False
                                    while j < len(out_s):
                                        ch = out_s[j]
                                        if ch == '{':
                                            depth += 1
                                            started = True
                                        elif ch == '}':
                                            depth -= 1
                                            if started and depth == 0:
                                                j += 1
                                                break
                                        j += 1
                                    blob = out_s[start:j]
                                    # Safely evaluate python-literal dict
                                    import ast
                                    parsed = ast.literal_eval(blob)
                                    if isinstance(parsed, dict):
                                        usage = parsed
                            except Exception:
                                pass
                    if isinstance(usage, dict):
                        pi = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
                        co = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
                        tt = int(usage.get("total_tokens") or (pi + co))
                        usage_input += pi
                        usage_output += co
                        usage_total += tt
                except Exception:
                    pass
            # Agent thoughts (optional: use action logs from events)
            elif etype == "on_agent_action" or etype == "on_chain_start":
                log = data.get("action") or data.get("name") or ""
                yield f"event: thought\ndata: {json.dumps({'log': str(log)})}\n\n"
            elif etype == "on_chain_end":
                final = data.get("output", "")
                # Sanitize common disclaimers about charting since the app renders charts
                try:
                    fs = str(final)
                    lower = fs.lower()
                    bad_phrases = [
                        "can't create visual",
                        "cannot create visual",
                        "can't create charts",
                        "cannot create charts",
                        "can't create a chart",
                        "cannot create a chart",
                    ]
                    if any(p in lower for p in bad_phrases):
                        fs = re.sub(r"(?i)\b(can('|’)t|cannot)\s+create\s+(visual|chart|charts)[^\.]*\.?\s*", "", fs).strip()
                        if not fs:
                            fs = "Here is a concise summary based on your request."
                        final = fs
                except Exception:
                    pass
                payload = {"answer": str(final)}
                if route_meta:
                    payload["route"] = route_meta
                if data_preview and isinstance(data_preview, dict) and data_preview.get("columns") is not None:
                    payload["data_preview"] = data_preview
                # Server-driven chart generation (based on user message and preview)
                try:
                    charts_payload = _build_charts_from_preview(message, data_preview)
                    if charts_payload:
                        # Sanitize specs before sending
                        sanitized: List[Dict[str, Any]] = []
                        for c in charts_payload:
                            spec = c.get("spec") if isinstance(c, dict) else None
                            try:
                                # local sanitizer
                                allowed_top = {"$schema","data","mark","encoding","width","height","transform","layer","vconcat","hconcat","title","resolve","facet","autosize"}
                                if not (isinstance(spec, dict)):
                                    continue
                                if len(json.dumps(spec)) > 120_000:
                                    continue
                                spec = {k:v for k,v in spec.items() if isinstance(k,str) and k in allowed_top}
                                if spec.get("width") is None:
                                    spec["width"] = "container"
                                if spec.get("height") is None:
                                    spec["height"] = 280
                                sanitized.append({"title": c.get("title"), "type": "vega-lite", "spec": spec})
                            except Exception:
                                continue
                        if sanitized:
                            payload["charts"] = sanitized
                except Exception:
                    charts_payload = None
                yield f"event: final\ndata: {json.dumps(payload)}\n\n"
    except Exception as e:
        logger.exception("astream_events failed: %s", e)
        yield f"event: error\ndata: {json.dumps(str(e))}\n\n"
    finally:
        # Log usage best-effort
        try:
            settings = get_tenant_settings(db, tenant_id)
            provider = str(get_setting(settings, "LLM_PROVIDER", "openai")).lower()
            model = str(get_setting(settings, "LLM_MODEL", "gpt-4o"))
            route_str = None
            if route_meta:
                try:
                    route_str = json.dumps(route_meta)
                except Exception:
                    route_str = str(route_meta)
            log_usage_event(
                db,
                tenant_id=str(tenant_id),
                provider=provider,
                model=model,
                operation="chat",
                category="chat",
                module="chat_module",
                input_tokens=int(usage_cb.input_tokens or usage_input) if (usage_cb.input_tokens or usage_input) else None,
                output_tokens=int(usage_cb.output_tokens or usage_output) if (usage_cb.output_tokens or usage_output) else None,
                total_tokens=int(usage_cb.total_tokens or usage_total) if (usage_cb.total_tokens or usage_total) else None,
                request_id=None,
                thread_id=str(thread_id) if isinstance(thread_id, str) else None,
                route=route_str,
                latency_ms=int((time.time() - t0) * 1000),
            )
        except Exception:
            pass
        yield "event: done\ndata: {}\n\n"
