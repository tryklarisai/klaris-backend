"""
gsheets_tool.py
Unified Google Sheets and Excel tool for LangGraph agent (via Google Drive OAuth tokens)
- Exposes a safe, read-only reader for both Google Sheets and Excel files.
- Validates input as JSON: {"entity_id": "<file_id>:<sheet_title>", "columns": [..], "limit": 200}
- Returns JSON with keys: columns, rows, row_count.
- Excel files are downloaded and processed with pandas DataFrames (in-memory caching)
"""
from __future__ import annotations
from typing import Dict, Any, Optional
import json
import os
import time
import io
import pandas as pd

from google.oauth2.credentials import Credentials as GoogleCredentials
from googleapiclient.discovery import build as google_build
from langchain_core.tools import StructuredTool
from googleapiclient.errors import HttpError
from utils.oauth_utils import get_valid_google_credentials


# In-memory cache for DataFrames (simple dict for pilot phase)
_dataframe_cache: Dict[str, Dict[str, Any]] = {}

def _build_creds_from_config(conn_cfg: Dict[str, Any]) -> GoogleCredentials:
    creds, updated_config = get_valid_google_credentials(conn_cfg)
    if not creds:
        raise RuntimeError("Missing Google Drive credentials/config for Sheets tool or failed to refresh token")
    return creds

def _query_dataframe(df: pd.DataFrame, spec: dict) -> dict:
    """Execute query on pandas DataFrame - load ALL data for accuracy in pilot phase"""
    try:
        # Get query parameters
        columns = spec.get("columns") or df.columns.tolist()
        limit = int(spec.get("limit", 200))
        
        # TODO: Add filtering support for complex queries later
        # TODO: Add aggregation support (sum, count, avg, etc.)
        # TODO: Add sorting support
        # For now: simple column selection and limit
        
        # Select requested columns
        available_columns = [col for col in columns if col in df.columns]
        if available_columns:
            result_df = df[available_columns]
        else:
            result_df = df
        
        # Apply limit for response (but keep all data in memory)
        limited_df = result_df.head(limit)
        
        return {
            "columns": limited_df.columns.tolist(),
            "rows": limited_df.values.tolist(),
            "row_count": len(limited_df),
            "total_rows": len(result_df),
            "file_info": {
                "type": "excel_dataframe",
                "total_available": len(df)
            }
        }
        
    except Exception as e:
        return {
            "columns": [],
            "rows": [],
            "row_count": 0,
            "error": f"DataFrame query error: {str(e)}"
        }


def make_gsheets_tool_runner(conn_cfg: Dict[str, Any]):
    """Unified tool runner for both Google Sheets and Excel files"""
    creds = _build_creds_from_config(conn_cfg)
    sheets_service = google_build("sheets", "v4", credentials=creds)
    drive_service = google_build("drive", "v3", credentials=creds)

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

    def _process_excel_file(file_id: str, sheet_title: str, spec: dict, drive_service, file_name: str, file_size: str) -> str:
        """Process Excel file by downloading and loading into pandas DataFrame"""
        try:
            cache_key = f"{file_id}:{sheet_title}"
            
            # Check if we have this sheet cached in memory
            if cache_key in _dataframe_cache:
                cached_data = _dataframe_cache[cache_key]
                df = cached_data["dataframe"]
                print(f"Using cached DataFrame for {file_name}/{sheet_title} ({len(df)} rows)")
                return json.dumps(_query_dataframe(df, spec))
            
            print(f"Loading Excel file: {file_name} (size: {file_size} bytes)")
            
            # Download Excel file content
            file_content = drive_service.files().get_media(fileId=file_id).execute()
            file_io = io.BytesIO(file_content)
            
            # TODO: Add file size warnings for large files (>50MB)
            # TODO: Add progress indicators for slow downloads
            # For pilot: load ALL data for accuracy
            
            # Read Excel file - load ALL sheets initially  
            try:
                # Try to read all sheets first to get sheet names
                all_sheets = pd.read_excel(file_io, sheet_name=None, engine='openpyxl')
                
                # Find the requested sheet (exact match or case-insensitive)
                target_sheet = None
                for sheet_name in all_sheets.keys():
                    if sheet_name == sheet_title or sheet_name.lower() == sheet_title.lower():
                        target_sheet = sheet_name
                        break
                
                if target_sheet is None:
                    available_sheets = list(all_sheets.keys())
                    return json.dumps({
                        "error": f"Sheet '{sheet_title}' not found in {file_name}. "
                                f"Available sheets: {available_sheets}"
                    })
                
                # Get the target DataFrame
                df = all_sheets[target_sheet]
                
                # Clean up DataFrame - remove empty rows/columns
                df = df.dropna(how='all').dropna(axis=1, how='all')
                
                # Ensure column names are strings
                df.columns = [str(col) for col in df.columns]
                
                # Convert all data to strings to avoid JSON serialization issues
                # TODO: Add proper type detection and handling for production
                # TODO: Preserve numeric types for calculations and aggregations
                # For pilot: convert everything to strings for JSON compatibility
                df = df.astype(str)
                
                # Handle NaN values that become 'nan' strings
                df = df.replace('nan', '')
                
                print(f"Loaded Excel sheet '{target_sheet}' with {len(df)} rows and {len(df.columns)} columns")
                
            except Exception as read_err:
                return json.dumps({
                    "error": f"Failed to read Excel file {file_name}: {str(read_err)}. "
                            f"Make sure the file is not corrupted and the sheet name is correct."
                })
            
            # Cache the DataFrame in memory (simple cache for pilot)
            # TODO: Add TTL and memory management for production
            # TODO: Add cache size limits and LRU eviction
            _dataframe_cache[cache_key] = {
                "dataframe": df,
                "timestamp": time.time(),
                "file_name": file_name,
                "file_size": file_size
            }
            
            print(f"Cached DataFrame for {file_name}/{sheet_title} in memory")
            
            # Execute query on the DataFrame
            return json.dumps(_query_dataframe(df, spec))
            
        except Exception as e:
            return json.dumps({
                "error": f"Excel processing error for {file_name}: {str(e)}"
            })

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
            
        # First, check file type to determine processing method
        try:
            file_meta = drive_service.files().get(
                fileId=file_id, 
                fields="mimeType,name,size"
            ).execute()
            mime_type = file_meta.get("mimeType", "")
            file_name = file_meta.get("name", "unknown")
            file_size = file_meta.get("size", "0")
            
            # Handle Excel files with DataFrame processing
            if mime_type in [
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",  # .xlsx
                "application/vnd.ms-excel"  # .xls
            ]:
                return _process_excel_file(file_id, sheet_title, spec, drive_service, file_name, file_size)
                
            # Handle Google Sheets with existing API logic
            elif mime_type == "application/vnd.google-apps.spreadsheet":
                # Continue to existing Google Sheets processing below
                pass
            else:
                return json.dumps({
                    "error": f"Unsupported file type: {mime_type}. "
                            f"Supported types: Google Sheets, Excel (.xlsx/.xls)"
                })
                
        except Exception as meta_err:
            return json.dumps({"error": f"Unable to access file metadata: {str(meta_err)}"})
        
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
            # First, verify this is actually a Google Sheets document
            try:
                file_meta = drive_service.files().get(
                    fileId=file_id, 
                    fields="mimeType,name"
                ).execute()
                mime_type = file_meta.get("mimeType", "")
                file_name = file_meta.get("name", "unknown")
                
                if mime_type != "application/vnd.google-apps.spreadsheet":
                    return json.dumps({
                        "error": f"File '{file_name}' is not a Google Sheets document (type: {mime_type}). "
                                f"Only native Google Sheets are supported. Please convert Excel files to Google Sheets format."
                    })
            except Exception as meta_err:
                return json.dumps({"error": f"Unable to access file metadata: {str(meta_err)}"})
            
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
