"""
Google Drive MCP Adapter
Implements: fetch_schema(config: dict) -> dict
Production: robust, typed, error handling, 10-sample rows for spreadsheets.
"""
from typing import Dict, Any
import random
import io
import os
from google.oauth2.credentials import Credentials as GoogleCredentials
from googleapiclient.discovery import build as google_build
import pandas as pd

class GoogleDriveMCPAdapter:
    @staticmethod
    def list_files(config: Dict[str, Any]) -> list:
        """
        Lists all files/folders in Google Drive for the authorized user.
        Returns a list of dicts with id, name, mimeType, sorted by modifiedTime descending, limit 1000.
        """
        access_token = config.get("oauth_access_token")
        refresh_token = config.get("oauth_refresh_token")
        token_uri = "https://oauth2.googleapis.com/token"
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        if not all([access_token, refresh_token, client_id, client_secret]):
            raise RuntimeError("Missing Google Drive credentials/config.")

        creds = GoogleCredentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri=token_uri,
            client_id=client_id,
            client_secret=client_secret
        )
        drive_service = google_build("drive", "v3", credentials=creds)

        # Get files, sorted by updated time, limited to 1000
        files_response = drive_service.files().list(
            q="trashed = false and not mimeType contains 'image/' and not mimeType contains 'video/'",
            orderBy="modifiedTime desc",
            fields="files(id, name, mimeType)",
            pageSize=1000
        ).execute()
        files = files_response.get("files", [])
        # Deterministic ordering: by name then id
        files.sort(key=lambda f: (f.get("name") or "", f.get("id") or ""))
        return files

    @staticmethod
    def fetch_schema(config: Dict[str, Any], metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Lists all files/folders, for each spreadsheet returns up to 10 sample rows (random if >10).
        Optionally, filters files by selected_drive_file_ids in metadata.
        """
        access_token = config.get("oauth_access_token")
        refresh_token = config.get("oauth_refresh_token")
        token_uri = "https://oauth2.googleapis.com/token"
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        if not all([access_token, refresh_token, client_id, client_secret]):
            raise RuntimeError("Missing Google Drive credentials/config.")

        creds = GoogleCredentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri=token_uri,
            client_id=client_id,
            client_secret=client_secret
        )
        drive_service = google_build("drive", "v3", credentials=creds)
        sheets_service = google_build("sheets", "v4", credentials=creds)

        # Build working set of files. If selection provided, fetch metadata per id (avoids listing entire Drive)
        selection_ids = set()
        if metadata and isinstance(metadata.get("selected_drive_file_ids"), list):
            selection_ids = set(metadata.get("selected_drive_file_ids") or [])
        files = []
        if selection_ids:
            for fid in selection_ids:
                try:
                    meta = drive_service.files().get(fileId=fid, fields="id,name,mimeType,parents,size").execute()
                    files.append(meta)
                except Exception:
                    # Skip files we cannot access
                    continue
        else:
            # Fallback: list (limited) – should rarely be used since we enforce selection upstream
            files_response = drive_service.files().list(
                q="trashed = false",
                fields="files(id, name, mimeType, parents, size)",
                pageSize=200
            ).execute()
            files = files_response.get("files", [])

        # If metadata contains selected_drive_file_ids, filter files
        if metadata and isinstance(metadata.get("selected_drive_file_ids"), list) and metadata["selected_drive_file_ids"]:
            selected_ids = set(metadata["selected_drive_file_ids"])
            files = [f for f in files if f["id"] in selected_ids]

        # Deterministic ordering of files for schema generation
        files.sort(key=lambda f: (f.get("name") or "", f.get("id") or ""))

        entities = []
        for f in files:
            file_id = f["id"]
            file_name = f["name"]
            mime = f["mimeType"]
            # Google Sheets
            if mime == "application/vnd.google-apps.spreadsheet":
                try:
                    # Configurable limits
                    import math
                    sample_rows_limit = int(os.getenv("GDRIVE_SHEET_SAMPLE_ROWS", "10"))
                    max_sheets = int(os.getenv("GDRIVE_MAX_SHEETS", "10"))

                    meta = sheets_service.spreadsheets().get(spreadsheetId=file_id).execute()
                    sheets_meta = meta.get("sheets", [])[:max_sheets]
                    # Deterministic ordering of sheets by title
                    sheets_meta.sort(key=lambda sh: (sh.get("properties", {}) or {}).get("title") or "")

                    # Column limit window for faster reads (A.. letter for max cols)
                    max_cols = int(os.getenv("GDRIVE_SHEET_MAX_COLS", "500"))
                    max_rows_window = int(os.getenv("GDRIVE_SHEET_SAMPLE_WINDOW_ROWS", "200"))

                    def col_letter(n: int) -> str:
                        # 1 -> A, 26 -> Z, 27 -> AA
                        s = ""
                        while n > 0:
                            n, r = divmod(n - 1, 26)
                            s = chr(65 + r) + s
                        return s

                    last_col = col_letter(max_cols)

                    for idx, sh in enumerate(sheets_meta):
                        title = sh.get("properties", {}).get("title")
                        if not title:
                            continue
                        # Pull only a window of cells for performance (header + up to window rows)
                        vals = sheets_service.spreadsheets().values().get(
                            spreadsheetId=file_id,
                            range=f"{title}!A1:{last_col}{max_rows_window}"
                        ).execute().get("values", [])
                        header = None
                        rows = []
                        fields = []
                        if vals:
                            total_rows = len(vals)
                            has_header = total_rows > 1
                            header = vals[0] if has_header else None
                            body_rows = vals[1:] if has_header else vals
                            if body_rows:
                                sample_size = min(sample_rows_limit, len(body_rows))
                                rows = random.sample(body_rows, sample_size) if len(body_rows) > sample_size else body_rows
                            if header:
                                fields = [{"name": str(h), "type": "string"} for h in header]
                        entity = {
                            "id": f"{file_id}:{title}",
                            "name": f"{file_name} / {title}",
                            "kind": "sheet",
                            "source": {"provider": "google_drive", "path": file_name},
                            "fields": fields,
                            "samples": [{"header": header, "rows": rows, "part": title}]
                        }
                        entities.append(entity)
                except Exception as e:
                    entities.append({
                        "id": file_id,
                        "name": file_name,
                        "kind": "sheet",
                        "source": {"provider": "google_drive", "path": file_name},
                        "fields": [],
                        "samples": [{"note": str(e), "rows": []}],
                    })
            # Excel/xlsx
            elif mime in [
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/vnd.ms-excel"
            ]:
                try:
                    file_io = io.BytesIO()
                    data = drive_service.files().get_media(fileId=file_id).execute()
                    file_io.write(data)
                    file_io.seek(0)
                    # Prefer engine based on mimeType for reliability
                    engine = None
                    if mime == "application/vnd.ms-excel":
                        engine = "xlrd"
                    # Read all sheets
                    try:
                        # Read only first N rows per sheet for performance
                        nrows = int(os.getenv("GDRIVE_SHEET_SAMPLE_WINDOW_ROWS", "200"))
                        sheets = pd.read_excel(file_io, sheet_name=None, engine=engine, nrows=nrows)
                    except Exception:
                        sheets = pd.read_excel(file_io, sheet_name=None, nrows=200)
                    sample_rows_limit = int(os.getenv("GDRIVE_SHEET_SAMPLE_ROWS", "10"))
                    for title, df in sorted(sheets.items(), key=lambda kv: kv[0]):
                        if isinstance(df, pd.DataFrame) and not df.empty:
                            df = df.astype(str)
                            rows_df = df.sample(n=min(sample_rows_limit, len(df))).to_dict(orient="records")
                            entities.append({
                                "id": f"{file_id}:{title}",
                                "name": f"{file_name} / {title}",
                                "kind": "sheet",
                                "source": {"provider": "google_drive", "path": file_name},
                                "fields": [{"name": str(c), "type": "string"} for c in list(df.columns)],
                                "samples": [{"header": list(df.columns), "rows": rows_df, "part": title}],
                            })
                        else:
                            entities.append({
                                "id": f"{file_id}:{title}",
                                "name": f"{file_name} / {title}",
                                "kind": "sheet",
                                "source": {"provider": "google_drive", "path": file_name},
                                "fields": [],
                                "samples": [{"rows": []}],
                            })
                except Exception as e:
                    entities.append({
                        "id": file_id,
                        "name": file_name,
                        "kind": "sheet",
                        "source": {"provider": "google_drive", "path": file_name},
                        "fields": [],
                        "samples": [{"note": str(e), "rows": []}],
                    })
            else:
                # Non-tabular files included as kind=file without samples
                entities.append({
                    "id": file_id,
                    "name": file_name,
                    "kind": "file",
                    "source": {"provider": "google_drive", "path": file_name},
                    "fields": [],
                    "samples": [],
                })
        # Deterministic ordering of entities
        entities.sort(key=lambda e: (e.get("name") or "", e.get("id") or ""))
        return {"entities": entities}
