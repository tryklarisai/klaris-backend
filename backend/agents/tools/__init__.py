# Package init for tools

"""
Tool adapters registry: maps Connector.type to a function that returns a LangChain Tool.
Keeps chat agent simple and lets new connectors plug-in by adding a single adapter.
"""
from __future__ import annotations
from typing import Any, Dict, List, Tuple, Callable, Optional
import json, logging, re
from langchain_core.tools import tool

try:
    # Local import; adapter lives alongside
    from .postgres_tool import make_postgres_tool
except Exception:
    make_postgres_tool = None  # type: ignore

try:
    from .gsheets_tool import make_gsheets_tool
except Exception:
    make_gsheets_tool = None  # type: ignore

# Runners for generic adapters
try:
    from .postgres_tool import make_postgres_tool_runner  # type: ignore
except Exception:
    make_postgres_tool_runner = None  # type: ignore
try:
    from .gsheets_tool import make_gsheets_tool_runner  # type: ignore
except Exception:
    make_gsheets_tool_runner = None  # type: ignore

# type -> adapter factory(connector) -> BaseTool
_ADAPTERS: Dict[str, Callable[[Any], Any]] = {}

if make_postgres_tool is not None:
    _ADAPTERS["postgres"] = make_postgres_tool
if make_gsheets_tool is not None:
    # Register canonical and aliases
    _ADAPTERS["google_drive"] = make_gsheets_tool
    _ADAPTERS["gdrive"] = make_gsheets_tool
    _ADAPTERS["gsheets"] = make_gsheets_tool


def build_tools_for_connectors(connectors: List[Any]) -> Tuple[List[Any], Dict[str, Dict[str, str]]]:
    tools: List[Any] = []
    route_meta: Dict[str, Dict[str, str]] = {}
    for c in connectors:
        # Normalize type and map aliases
        ctype = str(getattr(c, "type", "") or "").lower()
        if ctype in ("gdrive", "gsheets"):
            ctype = "google_drive"
        adapter = _ADAPTERS.get(ctype)
        if not adapter:
            continue
        tool = adapter(c)
        if not tool:
            continue
        tools.append(tool)
        route_meta[tool.name] = {
            "connector_id": str(getattr(c, "connector_id", "")),
            "connector_type": getattr(c, "type", ""),
        }
    return tools, route_meta


# ------------------------- Generic adapters -------------------------
logger = logging.getLogger("tools.adapters")


def _norm_type(t: str) -> str:
    t = (t or "").lower()
    if t in ("postgresql", "psql", "pg"):
        return "postgres"
    if t in ("google_drive", "gdrive", "gsheets"):
        return "google_drive"
    return t


def _normalize_identifier(s: str) -> str:
    try:
        return re.sub(r"[^a-z0-9]", "", str(s).lower())
    except Exception:
        return str(s) or ""


def adapter_list_schema(connector: Any, schema_summary: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    return schema_summary or {"tables": []}


def adapter_read(
    connector: Any,
    connector_schemas: Dict[str, Any],
    args: Dict[str, Any],
    on_rows: Optional[Callable[[str, str, List[Any], List[List[Any]]], None]] = None,
) -> Dict[str, Any]:
    """Generic read adapter delegating to connector-specific runners.
    args: {"connector_id": str, "spec": dict|str}
    """
    connector_id = str(args.get("connector_id", ""))
    spec = args.get("spec")
    ctype = _norm_type(getattr(connector, "type", ""))

    # Postgres
    if ctype == "postgres":
        if make_postgres_tool_runner is None:
            return {"error": "postgres runner unavailable"}
        runner = make_postgres_tool_runner(getattr(connector, "config", {}))  # type: ignore[arg-type]
        if isinstance(spec, str):
            sql_query = spec
        elif isinstance(spec, dict):
            if spec.get("sql") or spec.get("query"):
                sql_query = spec.get("sql") or spec.get("query")
            else:
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

        try:
            spec_str = sql_query if isinstance(sql_query, str) else str(sql_query)
            if isinstance(spec_str, str) and len(spec_str) > 500:
                spec_str = spec_str[:500] + "..."
            logger.info("adapter_read start connector_id=%s type=%s sql=%s", connector_id, ctype, spec_str)
        except Exception:
            pass
        parsed = json.loads(runner(sql_query))
        if isinstance(parsed, dict):
            parsed.setdefault("connector_id", connector_id)
            parsed.setdefault("connector_type", ctype)
            cols, rows = parsed.get("columns"), parsed.get("rows")
            if on_rows and isinstance(cols, list) and isinstance(rows, list):
                try:
                    on_rows(connector_id, ctype, cols, rows)
                except Exception:
                    pass
        try:
            logger.info("adapter_read end connector_id=%s type=%s rows=%s cols=%s", connector_id, ctype, len(parsed.get("rows", []) if isinstance(parsed, dict) else []), len(parsed.get("columns", []) if isinstance(parsed, dict) else []))
        except Exception:
            pass
        return parsed if isinstance(parsed, dict) else {"result": parsed}

    # Google Sheets
    if ctype == "google_drive":
        if make_gsheets_tool_runner is None:
            return {"error": "gsheets runner unavailable"}
        runner = make_gsheets_tool_runner(getattr(connector, "config", {}))  # type: ignore[arg-type]
        schema_summary = connector_schemas.get(connector_id) or {}
        if isinstance(spec, dict) and "sheet" in spec and isinstance(spec["sheet"], dict):
            spec = dict(spec["sheet"])  # unwrap nesting
        if isinstance(spec, dict) and not spec.get("entity_id"):
            # Try to resolve from aliases using current schema
            entity_name = spec.get("entity") or spec.get("name") or spec.get("table")
            if isinstance(entity_name, str):
                tables = schema_summary.get("tables") or []
                norm_target = _normalize_identifier(entity_name)
                for t in tables:
                    tname = t.get("name")
                    tid = t.get("entity_id")
                    if not isinstance(tname, str):
                        continue
                    tparts = tname.split("/", 1)
                    sheet_part = tparts[-1].strip() if tparts else tname
                    if entity_name.strip() == tname or entity_name.strip() == sheet_part or _normalize_identifier(tname) == norm_target or _normalize_identifier(sheet_part) == norm_target:
                        if isinstance(tid, str):
                            spec = dict(spec)
                            spec["entity_id"] = tid
                            break
        if isinstance(spec, dict) and not spec.get("entity_id") and spec.get("file_id") and spec.get("sheet"):
            spec = dict(spec)
            spec["entity_id"] = f"{spec.get('file_id')}:{spec.get('sheet')}"
        if not isinstance(spec, (dict, str)):
            return {"error": "gsheets.read requires spec with entity_id"}

        try:
            spec_str = spec if isinstance(spec, str) else json.dumps(spec)
            if isinstance(spec_str, str) and len(spec_str) > 500:
                spec_str = spec_str[:500] + "..."
            logger.info("adapter_read start connector_id=%s type=%s spec=%s", connector_id, ctype, spec_str)
        except Exception:
            pass
        payload = spec if isinstance(spec, str) else json.dumps(spec)
        parsed = json.loads(runner(payload))
        if isinstance(parsed, dict):
            parsed.setdefault("connector_id", connector_id)
            parsed.setdefault("connector_type", ctype)
            cols, rows = parsed.get("columns"), parsed.get("rows")
            if on_rows and isinstance(cols, list) and isinstance(rows, list):
                try:
                    on_rows(connector_id, ctype, cols, rows)
                except Exception:
                    pass
        try:
            logger.info("adapter_read end connector_id=%s type=%s rows=%s cols=%s", connector_id, ctype, len(parsed.get("rows", []) if isinstance(parsed, dict) else []), len(parsed.get("columns", []) if isinstance(parsed, dict) else []))
        except Exception:
            pass
        return parsed if isinstance(parsed, dict) else {"result": parsed}

    return {"error": f"unsupported connector type: {ctype}"}


def make_generic_tools(
    connectors: List[Any],
    connector_schemas: Dict[str, Any],
    on_rows: Optional[Callable[[str, str, List[Any], List[List[Any]]], None]] = None,
) -> List[Any]:
    """Create generic list_schema and read tools backed by adapter_* functions."""
    # Map id->connector for quick lookup
    conn_map: Dict[str, Any] = {str(getattr(c, "connector_id", "")): c for c in connectors}

    @tool
    def list_schema(connector_id: str) -> Dict[str, Any]:
        """Return a compact schema summary for a connector to help decide what to read."""
        c = conn_map.get(str(connector_id))
        if not c:
            try:
                logger.info("tool[list_schema] error connector_not_found connector_id=%s", str(connector_id))
            except Exception:
                pass
            return {"error": "connector not found"}
        ctype = _norm_type(getattr(c, "type", ""))
        try:
            logger.info("tool[list_schema] start connector_id=%s type=%s", str(connector_id), ctype)
        except Exception:
            pass
        out = adapter_list_schema(c, connector_schemas.get(str(connector_id)))
        try:
            tcount = len(out.get("tables", [])) if isinstance(out, dict) else None
            logger.info("tool[list_schema] end connector_id=%s type=%s tables=%s", str(connector_id), ctype, tcount)
        except Exception:
            pass
        return out

    @tool
    def read(connector_id: str, spec: Optional[dict | str] = None) -> Dict[str, Any]:
        """Read data from a connector using a connector-specific spec. Include a LIMIT when applicable."""
        c = conn_map.get(str(connector_id))
        if not c or not isinstance(getattr(c, "config", None), dict):
            try:
                logger.info("tool[read] error connector_not_found connector_id=%s", str(connector_id))
            except Exception:
                pass
            return {"error": "connector not found"}
        try:
            spec_str = spec if isinstance(spec, str) else json.dumps(spec) if spec is not None else "null"
            if isinstance(spec_str, str) and len(spec_str) > 500:
                spec_str = spec_str[:500] + "..."
            logger.info("tool[read] start connector_id=%s type=%s spec=%s", str(connector_id), _norm_type(getattr(c, 'type', '')), spec_str)
        except Exception:
            pass
        res = adapter_read(c, connector_schemas, {"connector_id": str(connector_id), "spec": spec}, on_rows=on_rows)
        try:
            if isinstance(res, dict):
                err = res.get("error")
                rcount = len(res.get("rows", []) if isinstance(res.get("rows"), list) else [])
                ccount = len(res.get("columns", []) if isinstance(res.get("columns"), list) else [])
                sql_str = res.get("sql")
                if isinstance(sql_str, str) and len(sql_str) > 300:
                    sql_str = sql_str[:300] + "..."
                logger.info("tool[read] end connector_id=%s type=%s rows=%s cols=%s sql=%s error=%s", str(connector_id), _norm_type(getattr(c, 'type', '')), rcount, ccount, sql_str, err)
            else:
                logger.info("tool[read] end connector_id=%s type=%s non_dict_result", str(connector_id), _norm_type(getattr(c, 'type', '')))
        except Exception:
            pass
        return res if isinstance(res, dict) else {"result": res}

    return [list_schema, read]
