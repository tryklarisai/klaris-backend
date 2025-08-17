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

from models.connector import Connector
from models.schema_review import GlobalCanonicalSchema
from models.schema import Schema
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import tool
from langchain.agents import AgentExecutor, create_openai_tools_agent
try:
    # Reuse validated, read-only runner from Postgres tool
    from .tools.postgres_tool import make_postgres_tool_runner  # type: ignore
except Exception as e:  # pragma: no cover
    logging.getLogger("chat_graph").warning("Failed to import Postgres tool runner: %s", e)
    make_postgres_tool_runner = None  # type: ignore
try:
    # Sheets read runner (expects JSON spec)
    from .tools.gsheets_tool import make_gsheets_tool_runner  # type: ignore
except Exception as e:  # pragma: no cover
    logging.getLogger("chat_graph").warning("Failed to import GSheets tool runner: %s", e)
    make_gsheets_tool_runner = None  # type: ignore

logger = logging.getLogger("chat_graph")

def _make_llm():
    provider = os.getenv("LLM_PROVIDER", "openai").lower()
    model = os.getenv("LLM_MODEL", "gpt-4o")
    temperature = float(os.getenv("LLM_TEMPERATURE", "0"))
    try:
        logger.info("llm_init provider=%s model=%s temperature=%s", provider, model, temperature)
    except Exception:
        pass
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model, temperature=temperature, streaming=True)
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model, temperature=temperature, streaming=True)
    else:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=model, temperature=temperature, streaming=True)

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


def _adapter_postgres_list_schema(connector: Connector, schema_summary: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return schema_summary or {"tables": []}

def _adapter_postgres_read(connector: Connector, args: Dict[str, Any]) -> Dict[str, Any]:
    runner = make_postgres_tool_runner(connector.config)  # type: ignore[arg-type]
    # `args` looks like {"connector_id": "...", "spec": <dict|str>}
    outer_spec = args if isinstance(args, dict) else {}
    spec = outer_spec.get("spec")

    # Mode 1: explicit SQL (string or dict with sql/query)
    if isinstance(spec, str):
        sql_query = spec
    elif isinstance(spec, dict):
        if spec.get("sql") or spec.get("query"):
            sql_query = spec.get("sql") or spec.get("query")
        else:
            # Mode 2: relation — accept either flat or nested under "relation"
            relation = spec.get("relation") if isinstance(spec.get("relation"), dict) else spec
            name = relation.get("name") if isinstance(relation, dict) else None
            columns = relation.get("columns") if isinstance(relation, dict) else None
            filters = relation.get("filters") if isinstance(relation, dict) else None
            limit = relation.get("limit") if isinstance(relation, dict) else None
            if not isinstance(name, str) or not isinstance(columns, list):
                return {"error": "postgres.read requires spec.sql or spec.relation{name,columns}"}

            def _quote_ident(s: str) -> str:
                s = str(s)
                return '"' + s.replace('"', '""') + '"'

            sel_cols = ", ".join(_quote_ident(c) for c in columns)
            where_parts: List[str] = []
            for f in (filters or []):
                col = f.get("column")
                op = (f.get("op") or "=").lower()
                val = f.get("value")
                if col is None:
                    continue
                if op == "in" and isinstance(val, list):
                    def _lit(v):
                        if isinstance(v, (int, float)):
                            return str(v)
                        return "'" + str(v).replace("'", "''") + "'"
                    where_parts.append(f"{_quote_ident(col)} IN (" + ", ".join(_lit(v) for v in val) + ")")
                else:
                    if isinstance(val, (int, float)):
                        lit = str(val)
                    else:
                        lit = "'" + str(val).replace("'", "''") + "'"
                    if op not in ("=", "!=", ">", ">=", "<", "<="):
                        op = "="
                    where_parts.append(f"{_quote_ident(col)} {op} {lit}")
            where_sql = (" WHERE " + " AND ".join(where_parts)) if where_parts else ""
            lim_sql = f" LIMIT {int(limit)}" if isinstance(limit, int) else " LIMIT 200"
            sql_query = f"SELECT {sel_cols} FROM {name}{where_sql}{lim_sql}"
    else:
        return {"error": "postgres.read requires spec (string SQL or relation dict)"}

    parsed_r = json.loads(runner(sql_query))
    return parsed_r

def _adapter_gsheets_list_schema(connector: Connector, schema_summary: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return schema_summary or {"tables": []}

def _adapter_gsheets_read(connector: Connector, args: Dict[str, Any]) -> Dict[str, Any]:
    runner = make_gsheets_tool_runner(connector.config)  # type: ignore[arg-type]
    spec = args.get("spec") if isinstance(args, dict) else None
    if not isinstance(spec, (dict, str)):
        return {"error": "gsheets.read requires args.spec"}

    # If spec is dict and nested under "sheet", unwrap it
    if isinstance(spec, dict) and "sheet" in spec and isinstance(spec["sheet"], dict):
        spec = dict(spec["sheet"])

    # If dict, allow file_id+sheet OR direct entity_id
    if isinstance(spec, dict) and not spec.get("entity_id"):
        if spec.get("file_id") and spec.get("sheet"):
            spec = dict(spec)
            spec["entity_id"] = f"{spec.get('file_id')}:{spec.get('sheet')}"
        else:
            return {"error": "missing entity_id or file_id+sheet"}

    parsed = json.loads(runner(spec if isinstance(spec, str) else json.dumps(spec)))
    return parsed


# Central adapter registry (single place for connector-specific logic)
ADAPTERS: Dict[str, Dict[str, Any]] = {
    "postgres": {"list_schema": _adapter_postgres_list_schema, "read": _adapter_postgres_read},
    "google_drive": {"list_schema": _adapter_gsheets_list_schema, "read": _adapter_gsheets_read},
}

def _load_canonical_summary(db: Session, tenant_id: UUID) -> Dict[str, Any]:
    latest = (
        db.query(GlobalCanonicalSchema)
        .filter(GlobalCanonicalSchema.tenant_id == tenant_id)
        .order_by(GlobalCanonicalSchema.version.desc())
        .first()
    )
    if not latest:
        return {}
    cg = latest.canonical_graph or {}
    ents = cg.get("unified_entities", [])[:20]  # keep prompt small
    for e in ents:
        if isinstance(e.get("fields"), list):
            e["fields"] = e["fields"][:20]
    return {"unified_entities": ents}

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

def run_chat_agent(db: Session, tenant_id: UUID, message: str) -> Dict[str, Any]:
    connectors: List[Connector] = db.query(Connector).filter(Connector.tenant_id == tenant_id).all()
    canonical_summary = _load_canonical_summary(db, tenant_id)
    conn_summaries = _build_connectors_summary(connectors)
    connector_schemas = _load_connector_schemas(db, tenant_id, connectors)

    agent_instructions = (
    "You are an analytics assistant. Use the available tools to plan and gather data.\n"
    "- Use ONLY tables/columns derivable from the provided schema context (canonical_summary, connector_schemas). Do NOT guess.\n"
    "- For tool calls, consult `connector_capabilities` to see what tools exist and the required spec shapes (schemas & examples are provided there).\n"
    "- Prefer field.sources in canonical_summary to pick connector/entity.\n"
    "- Keep reads minimal and include LIMITs when applicable.\n"
    "- Before calling any tools, briefly restate the user's goal and outline a short plan.\n"
    "- As you execute tool calls, narrate progress succinctly.\n"
    "- Finish with a concise final answer in natural language (no JSON)."
    )


    # Enrich canonical schema fields with candidate data sources for the planner
    _attach_field_sources(canonical_summary, connector_schemas, connectors)
    connector_capabilities = _build_connector_capabilities(connectors, connector_schemas)

    # Build tools that delegate to the adapter registry, allowing the LLM to call them directly
    previews: List[Dict[str, Any]] = []
    data_preview: Optional[Dict[str, Any]] = None
    route_meta: Optional[Dict[str, str]] = None

    # Streaming agent instructions (same content as non-streaming path)
    agent_instructions = (
    "You are an analytics assistant. Use the available tools to plan and gather data.\n"
    "- Use ONLY tables/columns derivable from the provided schema context (canonical_summary, connector_schemas). Do NOT guess.\n"
    "- For tool calls, consult `connector_capabilities` to see what tools exist and the required spec shapes (schemas & examples are provided there).\n"
    "- Prefer field.sources in canonical_summary to pick connector/entity.\n"
    "- Keep reads minimal and include LIMITs when applicable.\n"
    "- Before calling any tools, briefly restate the user's goal and outline a short plan.\n"
    "- As you execute tool calls, narrate progress succinctly.\n"
    "- Finish with a concise final answer in natural language (no JSON)."
    )


    

    @tool
    def list_schema(connector_id: str) -> Dict[str, Any]:
        """Return a compact schema summary for a connector to help decide what to read."""
        conn_for_plan = None
        for c in connectors:
            if str(c.connector_id) == str(connector_id):
                conn_for_plan = c
                break
        if not conn_for_plan:
            try:
                logger.info("tool_call list_schema error connector_not_found connector_id=%s", str(connector_id))
            except Exception:
                pass
            return {"error": "connector not found"}
        ctype = _normalize_connector_type(conn_for_plan.type)
        adapter = ADAPTERS.get(ctype)
        if not adapter or not adapter.get("list_schema"):
            try:
                logger.info("tool_call list_schema error unsupported_type connector_id=%s type=%s", str(connector_id), ctype)
            except Exception:
                pass
            return {"error": f"unsupported connector type: {ctype}"}
        try:
            logger.info("tool_call list_schema start connector_id=%s type=%s", str(connector_id), ctype)
        except Exception:
            pass
        out = adapter["list_schema"](conn_for_plan, connector_schemas.get(str(connector_id)))
        try:
            tables = (out or {}).get("tables") if isinstance(out, dict) else None
            tcount = len(tables) if isinstance(tables, list) else None
            logger.info("tool_call list_schema end connector_id=%s type=%s tables=%s", str(connector_id), ctype, tcount)
        except Exception:
            pass
        return out

    @tool
    def read(connector_id: str, spec: Optional[dict | str] = None) -> Dict[str, Any]:
        """Read data from a connector using a connector-specific spec. Include a LIMIT when applicable."""
        nonlocal data_preview, route_meta
        conn_for_plan = None
        for c in connectors:
            if str(c.connector_id) == str(connector_id):
                conn_for_plan = c
                break
        if not conn_for_plan or not isinstance(getattr(conn_for_plan, "config", None), dict):
            try:
                logger.info("tool_call read error connector_not_found connector_id=%s", str(connector_id))
            except Exception:
                pass
            return {"error": "connector not found"}
        ctype = _normalize_connector_type(conn_for_plan.type)
        adapter = ADAPTERS.get(ctype)
        if not adapter or not adapter.get("read"):
            try:
                logger.info("tool_call read error unsupported_type connector_id=%s type=%s", str(connector_id), ctype)
            except Exception:
                pass
            return {"error": f"unsupported connector type: {ctype}"}
        # For Google Sheets, allow resolving entity_id from entity/name using current schema
        if ctype == "google_drive" and isinstance(spec, dict):
            try:
                es = spec.get("entity_id")
                if not es:
                    # Accept alias keys
                    entity_name = spec.get("entity") or spec.get("name") or spec.get("table")
                    if isinstance(entity_name, str):
                        schema_summary = connector_schemas.get(str(connector_id)) or {}
                        tables = schema_summary.get("tables") or []
                        # match full name or just the sheet title after ' / '
                        norm_target = _normalize_identifier(entity_name)
                        found_eid = None
                        for t in tables:
                            tname = t.get("name")
                            tid = t.get("entity_id")
                            if not isinstance(tname, str):
                                continue
                            # exact or normalized match
                            tparts = tname.split("/", 1)
                            sheet_part = tparts[-1].strip() if tparts else tname
                            if entity_name.strip() == tname or entity_name.strip() == sheet_part or _normalize_identifier(tname) == norm_target or _normalize_identifier(sheet_part) == norm_target:
                                if isinstance(tid, str):
                                    found_eid = tid
                                    break
                        if found_eid:
                            spec = dict(spec)
                            spec["entity_id"] = found_eid
            except Exception:
                pass

        # Log start with a safely truncated spec
        try:
            spec_str = spec if isinstance(spec, str) else json.dumps(spec) if spec is not None else "null"
            if isinstance(spec_str, str) and len(spec_str) > 500:
                spec_str = spec_str[:500] + "..."
            logger.info("tool_call read start connector_id=%s type=%s spec=%s", str(connector_id), ctype, spec_str)
        except Exception:
            pass
        parsed_r = adapter["read"](conn_for_plan, {"connector_id": str(connector_id), "spec": spec})
        if isinstance(parsed_r, dict):
            parsed_r.setdefault("connector_id", str(connector_id))
            parsed_r.setdefault("connector_type", ctype)
            cols, rows = parsed_r.get("columns"), parsed_r.get("rows")
            if isinstance(cols, list) and isinstance(rows, list):
                if data_preview is None:
                    data_preview = {"columns": cols, "rows": rows[:50]}
                    route_meta = {"tool": "read", "connector_id": str(connector_id), "connector_type": ctype}
                previews.append({"connector_id": str(connector_id), "connector_type": ctype, "columns": cols, "rows": rows[:50]})
        try:
            if isinstance(parsed_r, dict):
                err = parsed_r.get("error")
                rcount = len(parsed_r.get("rows")) if isinstance(parsed_r.get("rows"), list) else None
                ccount = len(parsed_r.get("columns")) if isinstance(parsed_r.get("columns"), list) else None
                sql_str = parsed_r.get("sql")
                if isinstance(sql_str, str) and len(sql_str) > 300:
                    sql_str = sql_str[:300] + "..."
                logger.info("tool_call read end connector_id=%s type=%s rows=%s cols=%s sql=%s error=%s", str(connector_id), ctype, rcount, ccount, sql_str, err)
            else:
                logger.info("tool_call read end connector_id=%s type=%s non_dict_result", str(connector_id), ctype)
        except Exception:
            pass
        return parsed_r if isinstance(parsed_r, dict) else {"result": parsed_r}

    tools = [list_schema, read]

    # Prepare agent prompt with context
    payload = {
        "tenant_id": str(tenant_id),
        "connectors": conn_summaries,
        "canonical_summary": canonical_summary,
        "connector_schemas": connector_schemas,
        "connector_capabilities": connector_capabilities,
    }
    context_json = json.dumps(payload)
    prompt = ChatPromptTemplate.from_messages([
        ("system", agent_instructions),
        ("system", "Context for tools and planning (JSON): {context}"),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])

    llm = _make_llm()
    agent = create_openai_tools_agent(llm, tools, prompt)
    executor = AgentExecutor(agent=agent, tools=tools, verbose=False, max_iterations=6, return_intermediate_steps=True)

    try:
        result = executor.invoke({"input": message, "context": context_json})
    except Exception as e:
        logger.exception("Agent execution failed: %s", e)
        result = {"output": "I could not execute the tools due to an internal error.", "intermediate_steps": []}

    # Extract any tabular observations from intermediate steps if not already captured
    try:
        inter = result.get("intermediate_steps", []) or []
        for step in inter:
            # step is typically a tuple (AgentAction, observation)
            if isinstance(step, (list, tuple)) and len(step) == 2:
                ob = step[1]
                if isinstance(ob, dict) and isinstance(ob.get("columns"), list) and isinstance(ob.get("rows"), list):
                    if data_preview is None:
                        data_preview = {"columns": ob.get("columns"), "rows": ob.get("rows")[:50]}
                        route_meta = {
                            "tool": "read",
                            "connector_id": str(ob.get("connector_id", "")),
                            "connector_type": str(ob.get("connector_type", "")),
                        }
                    previews.append({
                        "connector_id": str(ob.get("connector_id", "")),
                        "connector_type": str(ob.get("connector_type", "")),
                        "columns": ob.get("columns"),
                        "rows": (ob.get("rows") or [])[:50],
                    })
    except Exception:
        pass

    answer_text = str(result.get("output", "")).strip() or ""
    plans: List[Dict[str, Any]] = []
    clarifications: List[str] = []

    return {
        "answer": answer_text,
        "plans": plans,
        "clarifications": clarifications,
        "route": route_meta,
        "data_preview": data_preview,
    }


async def run_chat_agent_stream(db: Session, tenant_id: UUID, message: str):
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
        "After gathering, produce a concise final answer to the user. Do not output JSON; respond with natural language."
    )

    previews: List[Dict[str, Any]] = []
    data_preview: Optional[Dict[str, Any]] = None
    route_meta: Optional[Dict[str, str]] = None

    @tool
    def list_schema(connector_id: str) -> Dict[str, Any]:
        """Return a compact schema summary for a connector to help decide what to read."""
        conn_for_plan = next((c for c in connectors if str(c.connector_id) == str(connector_id)), None)
        if not conn_for_plan:
            try:
                logger.info("tool_call[list_schema] error connector_not_found connector_id=%s", str(connector_id))
            except Exception:
                pass
            return {"error": "connector not found"}
        ctype = _normalize_connector_type(conn_for_plan.type)
        adapter = ADAPTERS.get(ctype)
        if not adapter or not adapter.get("list_schema"):
            try:
                logger.info("tool_call[list_schema] error unsupported_type connector_id=%s type=%s", str(connector_id), ctype)
            except Exception:
                pass
            return {"error": f"unsupported connector type: {ctype}"}
        try:
            logger.info("tool_call[list_schema] start connector_id=%s type=%s", str(connector_id), ctype)
        except Exception:
            pass
        out = adapter["list_schema"](conn_for_plan, connector_schemas.get(str(connector_id)))
        try:
            tables = (out or {}).get("tables") if isinstance(out, dict) else None
            tcount = len(tables) if isinstance(tables, list) else None
            logger.info("tool_call[list_schema] end connector_id=%s type=%s tables=%s", str(connector_id), ctype, tcount)
        except Exception:
            pass
        return out

    @tool
    def read(connector_id: str, spec: Optional[dict | str] = None) -> Dict[str, Any]:
        """Read data from a connector using a connector-specific spec. Include a LIMIT when applicable."""
        nonlocal data_preview, route_meta
        conn_for_plan = next((c for c in connectors if str(c.connector_id) == str(connector_id)), None)
        if not conn_for_plan or not isinstance(getattr(conn_for_plan, "config", None), dict):
            try:
                logger.info("tool_call[read] error connector_not_found connector_id=%s", str(connector_id))
            except Exception:
                pass
            return {"error": "connector not found"}
        ctype = _normalize_connector_type(conn_for_plan.type)
        adapter = ADAPTERS.get(ctype)
        if not adapter or not adapter.get("read"):
            try:
                logger.info("tool_call[read] error unsupported_type connector_id=%s type=%s", str(connector_id), ctype)
            except Exception:
                pass
            return {"error": f"unsupported connector type: {ctype}"}
        # For Google Sheets, allow resolving entity_id from entity/name using current schema
        if ctype == "google_drive" and isinstance(spec, dict):
            try:
                es = spec.get("entity_id")
                if not es:
                    entity_name = spec.get("entity") or spec.get("name") or spec.get("table")
                    if isinstance(entity_name, str):
                        schema_summary = connector_schemas.get(str(connector_id)) or {}
                        tables = schema_summary.get("tables") or []
                        norm_target = _normalize_identifier(entity_name)
                        found_eid = None
                        for t in tables:
                            tname = t.get("name")
                            tid = t.get("entity_id")
                            if not isinstance(tname, str):
                                continue
                            tparts = tname.split("/", 1)
                            sheet_part = tparts[-1].strip() if tparts else tname
                            if entity_name.strip() == tname or entity_name.strip() == sheet_part or _normalize_identifier(tname) == norm_target or _normalize_identifier(sheet_part) == norm_target:
                                if isinstance(tid, str):
                                    found_eid = tid
                                    break
                        if found_eid:
                            spec = dict(spec)
                            spec["entity_id"] = found_eid
            except Exception:
                pass

        try:
            spec_str = spec if isinstance(spec, str) else json.dumps(spec) if spec is not None else "null"
            if isinstance(spec_str, str) and len(spec_str) > 500:
                spec_str = spec_str[:500] + "..."
            logger.info("tool_call[read] start connector_id=%s type=%s spec=%s", str(connector_id), ctype, spec_str)
        except Exception:
            pass
        parsed_r = adapter["read"](conn_for_plan, {"connector_id": str(connector_id), "spec": spec})
        if isinstance(parsed_r, dict):
            parsed_r.setdefault("connector_id", str(connector_id))
            parsed_r.setdefault("connector_type", ctype)
            cols, rows = parsed_r.get("columns"), parsed_r.get("rows")
            if isinstance(cols, list) and isinstance(rows, list):
                if data_preview is None:
                    data_preview = {"columns": cols, "rows": rows[:50]}
                    route_meta = {"tool": "read", "connector_id": str(connector_id), "connector_type": ctype}
                previews.append({"connector_id": str(connector_id), "connector_type": ctype, "columns": cols, "rows": rows[:50]})
        try:
            if isinstance(parsed_r, dict):
                err = parsed_r.get("error")
                rcount = len(parsed_r.get("rows")) if isinstance(parsed_r.get("rows"), list) else None
                ccount = len(parsed_r.get("columns")) if isinstance(parsed_r.get("columns"), list) else None
                sql_str = parsed_r.get("sql")
                if isinstance(sql_str, str) and len(sql_str) > 300:
                    sql_str = sql_str[:300] + "..."
                logger.info("tool_call[read] end connector_id=%s type=%s rows=%s cols=%s sql=%s error=%s", str(connector_id), ctype, rcount, ccount, sql_str, err)
            else:
                logger.info("tool_call[read] end connector_id=%s type=%s non_dict_result", str(connector_id), ctype)
        except Exception:
            pass
        return parsed_r if isinstance(parsed_r, dict) else {"result": parsed_r}

    tools = [list_schema, read]

    payload = {
        "tenant_id": str(tenant_id),
        "connectors": conn_summaries,
        "canonical_summary": canonical_summary,
        "connector_schemas": connector_schemas,
        "connector_capabilities": connector_capabilities,
    }
    context_json = json.dumps(payload)
    prompt = ChatPromptTemplate.from_messages([
        ("system", agent_instructions),
        ("system", "Context for tools and planning (JSON): {context}"),
        ("human", "{input}"),
        MessagesPlaceholder("agent_scratchpad"),
    ])

    llm = _make_llm()
    agent = create_openai_tools_agent(llm, tools, prompt)
    executor = AgentExecutor(agent=agent, tools=tools, verbose=False, max_iterations=6, return_intermediate_steps=False)

    try:
        # Send an initial event to prompt clients to render immediately
        yield "event: ready\ndata: {}\n\n"
        async for ev in executor.astream_events({"input": message, "context": context_json}, version="v2"):
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
                outp = data.get("output")
                # truncate rows in outputs to keep SSE light
                if isinstance(outp, dict) and isinstance(outp.get("rows"), list):
                    outp = dict(outp)
                    outp["rows"] = outp["rows"][:5]
                yield f"event: tool_end\ndata: {json.dumps(outp)}\n\n"
            # Agent thoughts (optional: use action logs from events)
            elif etype == "on_agent_action" or etype == "on_chain_start":
                log = data.get("action") or data.get("name") or ""
                yield f"event: thought\ndata: {json.dumps({'log': str(log)})}\n\n"
            elif etype == "on_chain_end":
                final = data.get("output", "")
                payload = {"answer": str(final)}
                if route_meta:
                    payload["route"] = route_meta
                if data_preview and isinstance(data_preview, dict) and data_preview.get("columns") is not None:
                    payload["data_preview"] = data_preview
                yield f"event: final\ndata: {json.dumps(payload)}\n\n"
    except Exception as e:
        logger.exception("astream_events failed: %s", e)
        yield f"event: error\ndata: {json.dumps(str(e))}\n\n"
    finally:
        yield "event: done\ndata: {}\n\n"
