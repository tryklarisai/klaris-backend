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

        # List all files (limit 1000 for reasonable default)
        files_response = drive_service.files().list(
            q="trashed = false",
            fields="files(id, name, mimeType, parents, size)",
            pageSize=1000
        ).execute()
        files = files_response.get("files", [])

        # If metadata contains selected_drive_file_ids, filter files
        if metadata and isinstance(metadata.get("selected_drive_file_ids"), list) and metadata["selected_drive_file_ids"]:
            selected_ids = set(metadata["selected_drive_file_ids"])
            files = [f for f in files if f["id"] in selected_ids]

        result = []
        for f in files:
            entry = {
                "id": f["id"],
                "name": f["name"],
                "mimeType": f["mimeType"],
                "parents": f.get("parents", []),
                "sample_rows": None
            }
            # Google Sheets
            if f["mimeType"] == "application/vnd.google-apps.spreadsheet":
                try:
                    meta = sheets_service.spreadsheets().get(spreadsheetId=f["id"]).execute()
                    first_sheet = meta["sheets"][0]["properties"]["title"]
                    values = sheets_service.spreadsheets().values().get(
                        spreadsheetId=f["id"],
                        range=first_sheet
                    ).execute().get("values", [])
                    if values:
                        n = len(values)
                        sample_size = min(n-1, 10) if n > 1 else min(n, 10)
                        sample_rows = random.sample(values[1:], sample_size) if n > 1 else values[:sample_size]
                        entry["sample_rows"] = {
                            "header": values[0] if n > 1 else None,
                            "rows": sample_rows
                        }
                except Exception as e:
                    entry["sample_rows"] = {"error": str(e)}
            # Excel/xlsx
            elif f["mimeType"] in [
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/vnd.ms-excel"
            ]:
                try:
                    file_io = io.BytesIO()
                    data = drive_service.files().get_media(fileId=f["id"]).execute()
                    file_io.write(data)
                    file_io.seek(0)
                    df = pd.read_excel(file_io)
                    if not df.empty:
                        # Convert all columns to str to guarantee JSON serializable
                        df = df.astype(str)
                        sample_rows = df.sample(n=min(10, len(df))).to_dict(orient="records")
                        entry["sample_rows"] = {
                            "header": list(df.columns),
                            "rows": sample_rows
                        }
                except Exception as e:
                    entry["sample_rows"] = {"error": str(e)}
            result.append(entry)
        return {"files": result}
