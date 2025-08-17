"""
Postgres tool for LangGraph agent
- Exposes a safe, read-only SQL execution tool per connector.
- Validates input SQL (SELECT-only), enforces LIMIT and statement timeout.
"""
from __future__ import annotations
from typing import Callable, Dict, Any, Tuple
import re
import json
from sqlalchemy import create_engine, text
from sqlalchemy.engine.url import make_url
from langchain_core.tools import StructuredTool

# Basic SQL validator/sanitizer for SELECT-only queries
_FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|create|truncate|grant|revoke|comment|copy|vacuum|analyze)\b", re.IGNORECASE)
_MULTISTMT = re.compile(r";|--|/\*|\*/")


def _ensure_limit(sql: str, max_rows: int) -> str:
    s = sql.strip().rstrip(";")
    # Append LIMIT if none present (naive check)
    if re.search(r"\blimit\b", s, re.IGNORECASE) is None:
        s = f"{s} LIMIT {max_rows}"
    return s


def _validate_sql(sql: str) -> Tuple[bool, str | None]:
    s = sql.strip()
    if not s:
        return False, "empty SQL"
    # Allow a single trailing semicolon; remove it for validation
    import re as _re
    s_no_term = _re.sub(r";\s*$", "", s)
    if not re.match(r"^\s*select\b", s_no_term, re.IGNORECASE):
        return False, "only SELECT queries are allowed"
    if _FORBIDDEN.search(s_no_term):
        return False, "forbidden keyword detected"
    # Disallow additional semicolons/comments inside the statement
    if _MULTISTMT.search(s_no_term):
        return False, "multiple statements or comments are not allowed"
    return True, None


def _build_pg_url(conn_cfg: Dict[str, Any]) -> str:
    """
    Build SQLAlchemy Postgres URL from config. Accepts either discrete keys
    (user, password, host, port, database) or a DSN/URL under one of:
    url, dsn, database_url, DATABASE_URL.
    """
    url = (
        conn_cfg.get("url")
        or conn_cfg.get("dsn")
        or conn_cfg.get("database_url")
        or conn_cfg.get("DATABASE_URL")
    )
    if url:
        try:
            return str(make_url(url))
        except Exception as e:
            raise RuntimeError(f"Invalid Postgres URL/DSN in config: {e}")

    user = conn_cfg.get("user")
    password = conn_cfg.get("password")
    host = conn_cfg.get("host")
    port = conn_cfg.get("port") or 5432
    database = conn_cfg.get("database")
    if not all([user, password, host, database]):
        raise RuntimeError("Invalid Postgres connector config")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


def make_postgres_tool_runner(conn_cfg: Dict[str, Any]) -> Callable[[str], str]:
    """
    Returns a callable that executes read-only SELECT SQL against the given Postgres config.
    The callable takes a single argument `sql` and returns a JSON string with {columns, rows}.
    """
    url = _build_pg_url(conn_cfg)

    def _run(sql: str) -> str:
        ok, err = _validate_sql(sql)
        if not ok:
            return json.dumps({"error": err})
        # Enforce row cap
        MAX_ROWS = 200
        sql2 = _ensure_limit(sql, MAX_ROWS)
        engine = create_engine(
            url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 5},
        )
        try:
            with engine.connect() as conn:
                # Statement timeout in ms (e.g., 10s)
                conn.execute(text("SET LOCAL statement_timeout = 10000"))
                # Transaction read-only
                conn.execute(text("SET TRANSACTION READ ONLY"))
                result = conn.execute(text(sql2))
                cols = list(result.keys())
                rows = [list(r) for r in result.fetchall()]
                out = {
                    "columns": cols,
                    "rows": rows,
                    "row_count": len(rows),
                    "sql": sql2,
                }
                return json.dumps(out)
        except Exception as e:
            return json.dumps({"error": str(e)})
        finally:
            engine.dispose()

    return _run


def make_postgres_tool(connector: Any):
    """
    Adapter: given a Connector row, return a LangChain Tool for read-only SQL.
    Expects connector.config with Postgres connection fields.
    """
    cfg = getattr(connector, "config", None) or {}
    runner = make_postgres_tool_runner(cfg)

    def _run(sql: str) -> str:
        return runner(sql)

    name = f"postgres_run_sql_{getattr(connector, 'connector_id', 'unknown')}"
    return StructuredTool.from_function(
        name=name,
        description=(
            "Execute a safe SELECT-only SQL query against this Postgres connector. "
            "Return JSON with keys: columns, rows, row_count, sql."
        ),
        func=_run,
    )
