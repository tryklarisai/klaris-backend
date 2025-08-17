"""
gsheets_tool.py
Google Sheets tool for LangGraph agent (via Google Drive OAuth tokens)
- Exposes a safe, read-only Sheets reader per connector.
- Validates input as JSON: {"entity_id": "<file_id>:<sheet_title>", "columns": [..], "limit": 200}
- Returns JSON with keys: columns, rows, row_count.
"""
from __future__ import annotations
from typing import Dict, Any
import json
import os
import time

from google.oauth2.credentials import Credentials as GoogleCredentials
from googleapiclient.discovery import build as google_build
from langchain_core.tools import StructuredTool
from googleapiclient.errors import HttpError


def _build_creds_from_config(conn_cfg: Dict[str, Any]) -> GoogleCredentials:
    access_token = conn_cfg.get("oauth_access_token")
    refresh_token = conn_cfg.get("oauth_refresh_token")
    token_uri = "https://oauth2.googleapis.com/token"
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    if not all([access_token, refresh_token, client_id, client_secret]):
        raise RuntimeError("Missing Google Drive credentials/config for Sheets tool")
    return GoogleCredentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri=token_uri,
        client_id=client_id,
        client_secret=client_secret,
    )


def make_gsheets_tool_runner(conn_cfg: Dict[str, Any]):
    creds = _build_creds_from_config(conn_cfg)
    sheets_service = google_build("sheets", "v4", credentials=creds)

    # Column/window caps to prevent large reads
    max_cols = int(os.getenv("GDRIVE_SHEET_MAX_COLS", "500"))
    max_window_rows = int(os.getenv("GDRIVE_SHEET_SAMPLE_WINDOW_ROWS", "2000"))

    def col_letter(n: int) -> str:
        s = ""
        while n > 0:
            n, r = divmod(n - 1, 26)
            s = chr(65 + r) + s
        return s

    last_col = col_letter(max_cols)

    def _run(spec_json: str) -> str:
        try:
            spec = json.loads(spec_json) if isinstance(spec_json, str) else (spec_json or {})
        except Exception:
            return json.dumps({"error": "input must be JSON"})
        entity_id = (spec or {}).get("entity_id")  # "<file_id>:<sheet_title>" or "<file_id>::<sheet_title>"
        columns = (spec or {}).get("columns") or None
        limit = int((spec or {}).get("limit") or 200)
        if not entity_id:
            return json.dumps({"error": "entity_id required as '<file_id>:<sheet_title>'"})
        # Support both ':' and '::' separators
        if "::" in entity_id:
            file_id, sheet_title = entity_id.split("::", 1)
        elif ":" in entity_id:
            file_id, sheet_title = entity_id.split(":", 1)
        else:
            return json.dumps({"error": "entity_id must be '<file_id>:<sheet_title>' or '<file_id>::<sheet_title>'"})
        # Ensure A1-notation sheet name is quoted if needed (handles spaces/special chars)
        def _quote_sheet_name(name: str) -> str:
            n = str(name)
            if n.startswith("'") and n.endswith("'"):
                return n
            # Escape single quotes per A1 notation rules
            return "'" + n.replace("'", "''") + "'"

        # Retry/backoff helper for transient Sheets API errors
        def _fetch_values(rng: str):
            attempts = 0
            while attempts < 3:
                try:
                    resp = sheets_service.spreadsheets().values().get(
                        spreadsheetId=file_id,
                        range=rng,
                    ).execute()
                    return resp.get("values", [])
                except HttpError as he:
                    status = getattr(getattr(he, "resp", None), "status", None)
                    if status in (429, 500, 502, 503, 504):
                        time.sleep(0.5 * (attempts + 1))
                        attempts += 1
                        continue
                    raise
                except Exception:
                    if attempts < 1:
                        time.sleep(0.2)
                        attempts += 1
                        continue
                    raise
            return []

        try:
            rng_sheet = _quote_sheet_name(sheet_title)
            rng = f"{rng_sheet}!A1:{last_col}{min(max_window_rows, max(1, limit) + 1)}"
            values = _fetch_values(rng)
            if not values:
                return json.dumps({"columns": [], "rows": [], "row_count": 0})
            header = values[0]
            rows = values[1:]
            # Apply column projection
            if columns:
                col_idx = [header.index(c) for c in columns if c in header]
                new_header = [header[i] for i in col_idx]
                proj_rows = [[(r[i] if i < len(r) else "") for i in col_idx] for r in rows]
                header = new_header
                rows = proj_rows
            # Enforce limit and return
            rows = rows[:limit]
            return json.dumps({
                "columns": [str(c) for c in header],
                "rows": [[str(x) for x in r] for r in rows],
                "row_count": len(rows),
            })
        except HttpError as e:
            msg = str(e)
            # Fallback: resolve sheet title by listing sheets and retry with exact title match (case/space normalized)
            if ("Unable to parse range" in msg) or ("Requested entity was not found" in msg):
                try:
                    meta = sheets_service.spreadsheets().get(
                        spreadsheetId=file_id,
                        fields="sheets.properties.title",
                    ).execute()
                    titles = [
                        (s.get("properties", {}) or {}).get("title")
                        for s in (meta.get("sheets", []) or [])
                    ]
                    def _norm(s: str) -> str:
                        return " ".join((s or "").strip().lower().split())
                    target = _norm(sheet_title)
                    match = next((t for t in titles if _norm(t or "") == target), None)
                    if not match:
                        return json.dumps({"error": "sheet title not found"})
                    rng_sheet = _quote_sheet_name(match)
                    rng = f"{rng_sheet}!A1:{last_col}{min(max_window_rows, max(1, limit) + 1)}"
                    values = _fetch_values(rng)
                    if not values:
                        return json.dumps({"columns": [], "rows": [], "row_count": 0})
                    header = values[0]
                    rows = values[1:]
                    # Apply column projection if requested
                    if columns:
                        col_idx = [header.index(c) for c in columns if c in header]
                        new_header = [header[i] for i in col_idx]
                        proj_rows = [[(r[i] if i < len(r) else "") for i in col_idx] for r in rows]
                        header = new_header
                        rows = proj_rows
                    rows = rows[:limit]
                    return json.dumps({
                        "columns": [str(c) for c in header],
                        "rows": [[str(x) for x in r] for r in rows],
                        "row_count": len(rows),
                    })
                except Exception as e2:
                    return json.dumps({"error": str(e2)})
            else:
                return json.dumps({"error": msg})
        except Exception as e:
            return json.dumps({"error": str(e)})

    return _run


def make_gsheets_tool(connector: Any):  # type: ignore[name-defined]
    cfg = getattr(connector, "config", None) or {}
    runner = make_gsheets_tool_runner(cfg)

    def _run(spec_json: str) -> str:
        return runner(spec_json)

    name = f"gsheets_read_{getattr(connector, 'connector_id', 'unknown')}"
    description = (
        "Read Google Sheets data by entity_id '<file_id>:<sheet_title>'. "
        "Input must be JSON with keys: entity_id, optional columns[], optional limit. "
        "Returns JSON with keys: columns, rows, row_count."
    )
    return StructuredTool.from_function(
        name=name,
        description=description,
        func=_run,
    )
