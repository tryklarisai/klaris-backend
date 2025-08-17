"""
Connectors API endpoints
Production-grade: FastAPI router, error handling, type hints, MCP connection logic (pilot version)
"""
from fastapi import APIRouter, HTTPException, Depends, status, Request, Query
from sqlalchemy.orm import Session
from uuid import UUID
from typing import Optional
from datetime import datetime

from models.connector import Connector, ConnectorStatus
from models.tenant import Tenant
from models.schema import Schema
from db import get_db
from schemas.connector import (
    ConnectorCreateRequest, ConnectorCreateResponse, ConnectorListResponse, ConnectorSummary,
    ConnectorType
)

import os
import time
from urllib.parse import urlencode
from fastapi.responses import RedirectResponse

import requests
from uuid import UUID

def make_json_safe(obj):
    """
    Recursively convert any UUID or datetime in dict/list to string, so that the structure becomes fully JSON serializable.
    """
    from datetime import datetime
    if isinstance(obj, dict):
        return {k: make_json_safe(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [make_json_safe(x) for x in obj]
    elif isinstance(obj, UUID):
        return str(obj)
    elif isinstance(obj, datetime):
        return obj.isoformat()
    else:
        return obj

def test_mcp_connection_and_fetch_schema(conn_type: str, config: dict) -> tuple[bool, Optional[dict], Optional[str]]:
    """
    Tries to connect to the MCP server and fetch /schema endpoint.
    Returns (success, schema_json, error_message).
    """
    try:
        # MCP test (ping or GET version or similar, depending on spec)
        url = config["mcp_url"].rstrip("/") + "/schema"
        resp = requests.get(url, auth=(config.get("username"), config.get("password")), timeout=8)
        if resp.status_code != 200:
            return False, None, f"Bad status {resp.status_code} from MCP /schema"
        data = resp.json()
        return True, data, None
    except Exception as e:
        return False, None, str(e)

# ----------------- Root-level OAuth endpoints ----------------
oauth_router = APIRouter()

@oauth_router.get("/connectors/google-drive/authorize")
def google_drive_authorize(request: Request):
    """
    Begins the Google OAuth flow for Google Drive. Redirects to Google's OAuth2.0 consent screen.
    Expects tenant_id as query param; builds state param with nonce+tenant_id for CSRF protection.
    """
    import secrets
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    redirect_uri = os.getenv("GOOGLE_OAUTH_REDIRECT_URI")
    tenant_id = request.query_params.get("tenant_id")
    if not client_id or not redirect_uri:
        raise HTTPException(status_code=500, detail="OAuth env not configured")
    if tenant_id is None:
        raise HTTPException(status_code=400, detail="Missing tenant_id query parameter")
    scope = "https://www.googleapis.com/auth/drive.readonly https://www.googleapis.com/auth/spreadsheets.readonly"
    # Secure random CSRF token (nonce)
    csrf_token = secrets.token_urlsafe(16)
    state = f"{csrf_token}:{tenant_id}"
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "access_type": "offline",
        "scope": scope,
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return RedirectResponse(url)

@oauth_router.get("/connectors/google-drive/callback")
def google_drive_callback(request: Request, db: Session = Depends(get_db)):
    """
    Handles the OAuth2 callback after Google user authorizes this app.
    Parses tenant_id from state, verifies token, handles code exchange and connector DB save.
    """
    import requests as pyrequests
    import os
    from datetime import datetime, timedelta
    from models.connector import ConnectorStatus, Connector
    from schemas.connector import ConnectorType
    from uuid import uuid4

    code = request.query_params.get("code")
    error = request.query_params.get("error")
    state = request.query_params.get("state")
    if error:
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code (OAuth callback)")
    if not state or ":" not in state:
        raise HTTPException(status_code=400, detail="Invalid state param (missing tenant id)")
    csrf_token, tenant_id = state.split(":", 1)
    # TODO: validate CSRF/nonce if tracking sessions
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    redirect_uri = os.getenv("GOOGLE_OAUTH_REDIRECT_URI")
    if not all([client_id, client_secret, redirect_uri]):
        raise HTTPException(status_code=500, detail="Google OAuth env not configured")
    # Exchange code for tokens
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    }
    # Retry token exchange with exponential backoff to handle transient network issues
    attempts = 3
    backoff = 1.0
    token_resp = None
    last_err = None
    for i in range(attempts):
        try:
            # Use a (connect, read) timeout tuple
            token_resp = pyrequests.post(token_url, data=data, timeout=(5, 30))
            break
        except pyrequests.exceptions.RequestException as e:
            last_err = e
            if i < attempts - 1:
                time.sleep(backoff)
                backoff *= 2
            else:
                raise HTTPException(status_code=503, detail=f"Google token endpoint unreachable: {str(e)}")
    if token_resp is None or token_resp.status_code != 200:
        detail = token_resp.text if token_resp is not None else str(last_err)
        raise HTTPException(status_code=400, detail=f"Token exchange failed: {detail}")
    token_json = token_resp.json()
    # tokens
    access_token = token_json.get("access_token")
    refresh_token = token_json.get("refresh_token")
    expires_in = token_json.get("expires_in")
    expiry = datetime.utcnow() + timedelta(seconds=expires_in) if expires_in else None
    if not access_token or not refresh_token:
        raise HTTPException(status_code=400, detail="Did not receive access/refresh token from Google.")
    # Store a new Connector in DB (status=ACTIVE)
    now = datetime.utcnow()
    connector = Connector(
        connector_id=uuid4(),
        tenant_id=tenant_id,
        type=ConnectorType.GOOGLE_DRIVE.value,
        config={
            # Don't persist access_token beyond expiry; refresh_token is for renewals
            "oauth_access_token": access_token,
            "oauth_refresh_token": refresh_token,
            "token_expiry": expiry.isoformat() if expiry else None
        },
        status=ConnectorStatus.ACTIVE,
        created_at=now,
        updated_at=now,
        last_schema_fetch=None # will be fetched in MCP step
    )
    db.add(connector)
    db.commit()
    # Redirect back to the Connectors list page on the frontend.
    # FRONTEND_URL is expected to be just the host (e.g., https://demo.tryklaris.ai)
    base = os.getenv("FRONTEND_URL", "http://localhost:3000")
    redirect_url = f"{base.rstrip('/')}/connectors?gdrive=success"
    return RedirectResponse(redirect_url)

# Original connectors CRUD API
router = APIRouter(prefix="/tenants/{tenant_id}/connectors", tags=["Connectors"])

import google.auth.transport.requests
from google.oauth2.credentials import Credentials as GoogleCredentials
from googleapiclient.discovery import build as google_build
import pandas as pd
import random
import io
import requests as pyrequests

from mcp.google_drive import GoogleDriveMCPAdapter
from mcp.postgres import PostgresMCPAdapter

@router.get("/{connector_id}/google-drive-files", summary="List Google Drive files for a connector", response_model=list)
def list_google_drive_files(
    tenant_id: str,
    connector_id: str,
    db: Session = Depends(get_db)
):
    from models.connector import Connector
    # Find connector for this tenant
    connector = db.query(Connector).filter_by(connector_id=connector_id, tenant_id=tenant_id).first()
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    # Only allow for Google Drive connectors
    if connector.type not in ("gdrive", "google_drive", "GOOGLE_DRIVE"):
        raise HTTPException(status_code=400, detail="Connector is not Google Drive type")
    try:
        files = GoogleDriveMCPAdapter.list_files(connector.config)
        return files
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Google Drive API error: {str(e)}")


@router.get("/{connector_id}/postgres-tables", summary="List Postgres tables for a connector", response_model=list)
def list_postgres_tables(
    tenant_id: str,
    connector_id: str,
    db: Session = Depends(get_db)
):
    from models.connector import Connector
    conn = db.query(Connector).filter_by(connector_id=connector_id, tenant_id=tenant_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connector not found")
    if conn.type not in ("postgres", "POSTGRES"):
        raise HTTPException(status_code=400, detail="Connector is not Postgres type")
    try:
        tables = PostgresMCPAdapter.list_tables(conn.config)
        return tables
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Postgres list tables error: {str(e)}")


@router.get("/{connector_id}/select-files", summary="Unified selectable items for a connector", response_model=list)
def list_selectable_items(
    tenant_id: str,
    connector_id: str,
    db: Session = Depends(get_db)
):
    from models.connector import Connector
    conn = db.query(Connector).filter_by(connector_id=connector_id, tenant_id=tenant_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connector not found")
    ctype = (conn.type or "").lower()
    try:
        if ctype in ("google_drive", "gdrive"):
            return GoogleDriveMCPAdapter.list_files(conn.config)
        if ctype == "postgres":
            tables = PostgresMCPAdapter.list_tables(conn.config)
            # Normalize to the same shape the UI expects: {id, name, mimeType}
            items = [
                {"id": t["name"], "name": t["name"], "mimeType": t["schema"]}
                for t in tables
            ]
            items.sort(key=lambda x: x.get("name") or "")
            return items
        raise HTTPException(status_code=400, detail=f"Unsupported connector type: {conn.type}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Selection listing failed: {str(e)}")

@router.post("/{connector_id}/fetch-schema")
def fetch_connector_schema(
    tenant_id: str,
    connector_id: str,
    db: Session = Depends(get_db),
    full: bool = Query(False, description="When true, ignores saved selection filters and returns full schema")
):
    """
    Fetches schema for connector via MCP adapter. Stores as canonical schema for this connector.
    """
    from models.connector import Connector
    from models.schema import Schema
    from datetime import datetime
    from schemas.connector import ConnectorType
    from mcp import get_adapter

    conn = db.query(Connector).filter_by(connector_id=connector_id, tenant_id=tenant_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="Connector not found")

    try:
        mcp_adapter = get_adapter(conn.type)
        # For refresh endpoint: by default apply saved selection filters so the
        # schema reflects the user's selected entities. If `full=true`, ignore filters and
        # return the complete schema (used by UI for editing).
        if not full:
            meta = conn.connector_metadata or {}
            ctype = (conn.type or "").lower()
            if ctype in ("google_drive", "gdrive"):
                selected = meta.get("selected_drive_file_ids") or []
                if not isinstance(selected, list) or len(selected) == 0:
                    raise HTTPException(status_code=400, detail="No files selected. Please select Google Drive files first.")
            elif ctype == "postgres":
                selected = meta.get("selected_table_names") or []
                if not isinstance(selected, list) or len(selected) == 0:
                    raise HTTPException(status_code=400, detail="No tables selected. Please select Postgres tables first.")
            metadata = meta
        else:
            metadata = None
        mcp_schema = mcp_adapter.fetch_schema(conn.config, metadata)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"MCP fetch_schema failed: {e}")

    # Save to DB
    now = datetime.utcnow()
    schema = Schema(
        connector_id=str(conn.connector_id),
        tenant_id=str(tenant_id),
        raw_schema=make_json_safe({"schema": mcp_schema, "fetched_at": now.isoformat()}),
        fetched_at=now
    )
    db.add(schema)
    conn.last_schema_fetch = now
    db.commit()
    return {"schema": mcp_schema, "fetched_at": now.isoformat()}

@router.post("", response_model=ConnectorCreateResponse, status_code=status.HTTP_201_CREATED)
def create_connector(
    tenant_id: UUID,
    request: ConnectorCreateRequest,
    db: Session = Depends(get_db)
):
    # Make sure tenant exists
    tenant = db.query(Tenant).filter_by(tenant_id=tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    now = datetime.utcnow()
    connector = Connector(
        tenant_id=str(tenant_id),
        type=request.type.value,
        config=request.config,
        status=ConnectorStatus.FAILED,  # pessimistic by default
        created_at=now,
        updated_at=now,
    )
    db.add(connector)
    db.flush()  # get generated connector_id (UUID)

    # Skip MCP connection and schema fetch
    db.commit()
    return ConnectorCreateResponse(
        connector_id=connector.connector_id,
        status=connector.status.value,
        error=connector.error_message,
    )

@router.get("", response_model=ConnectorListResponse)
def list_connectors(
    tenant_id: UUID,
    db: Session = Depends(get_db)
):
    connectors = db.query(Connector).filter_by(tenant_id=tenant_id).all()
    # Deterministic ordering: by type then connector_id
    connectors.sort(key=lambda c: ((c.type or "").lower(), str(getattr(c, "connector_id", ""))))
    result = []
    for conn in connectors:
        last_schema = db.query(Schema).filter_by(
            connector_id=conn.connector_id
        ).order_by(Schema.fetched_at.desc()).first()
        schema_info = None
        if last_schema:
            schema_info = {
                "schema_id": last_schema.schema_id,
                "fetched_at": last_schema.fetched_at.isoformat(),
                "raw_schema": last_schema.raw_schema,
            }
        result.append(ConnectorSummary(
            connector_id=conn.connector_id,
            type=conn.type,
            status=conn.status.value,
            created_at=conn.created_at.isoformat() if getattr(conn, 'created_at', None) else None,
            last_schema_fetch=conn.last_schema_fetch.isoformat() if conn.last_schema_fetch else None,
            error_message=conn.error_message,
            schema=schema_info,
            config=conn.config,
            connector_metadata=conn.connector_metadata
        ))
    return ConnectorListResponse(connectors=result)

# --- Re-test connector endpoint ---
from fastapi.responses import JSONResponse

@router.post("/{connector_id}/retest")
def retest_connector(
    tenant_id: UUID,
    connector_id: UUID,
    db: Session = Depends(get_db),
):
    connector = db.query(Connector).filter_by(tenant_id=tenant_id, connector_id=connector_id).first()
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    now = datetime.utcnow()
    # Connection test/fetch schema logic:
    ok, schema_json, error = test_mcp_connection_and_fetch_schema(connector.type, connector.config)
    if ok and schema_json:
        connector.status = ConnectorStatus.ACTIVE
        connector.last_schema_fetch = now
        connector.error_message = None
        schema = Schema(
            connector_id=str(connector.connector_id),
            tenant_id=str(tenant_id),
            raw_schema=make_json_safe(schema_json),
            fetched_at=now,
        )
        db.add(schema)
        db.commit()
        return JSONResponse({
            "status": "active",
            "error": None,
            "schema": schema_json,
        })
    else:
        connector.status = ConnectorStatus.FAILED
        connector.error_message = error or "Unknown failure"
        connector.last_schema_fetch = None
        db.commit()
        return JSONResponse({
            "status": "failed",
            "error": connector.error_message,
            "schema": None,
        })


# --- Canonical Schema fetch for a connector (NESTED ROUTE, replaces top-level) ---
from schemas.schema import SchemaRead
import jwt
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from schemas.connector import ConnectorSummary

JWT_SECRET = os.getenv("JWT_SECRET", "insecure-placeholder-change-in-env")
JWT_ALGORITHM = "HS256"

import logging

def check_auth_and_tenant(credentials: HTTPAuthorizationCredentials, tenant_id: str) -> dict:
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception as e:
        logging.error(f"JWT decode failed: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
    if "tenant" not in payload or "tenant_id" not in payload["tenant"] or str(payload["tenant"]["tenant_id"]) != str(tenant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant context missing or mismatch in token")
    return {"tenant_id": payload["tenant"]["tenant_id"], "user": payload.get("user")}

# Removed per-connector schema review feature

@router.put(
    "/{connector_id}",
    summary="Update connector (partial or full, including config/metadata)",
    tags=["Connectors"],
    response_model=ConnectorSummary,
    response_description="The updated connector.",
    responses={
        200: {
            "description": "The updated connector.",
            "content": {
                "application/json": {
                    "example": {
                        "connector_id": "e8ab50c8-52dd-4872-a9e5-7effa1802164",
                        "type": "gdrive",
                        "status": "active",
                        "last_schema_fetch": "2025-08-13T22:32:12.123Z",
                        "error_message": None,
                        "schema": {
                          "schema_id": "c5b4ebcb-5959-41c0-8cc9-1e4b2bc3e0f4",
                          "fetched_at": "2025-08-13T18:54:23.690Z",
                          "raw_schema": {"entity":"Invoice","fields":[{"name":"id","type":"string"}]}
                        },
                        "config": {
                          "oauth_access_token": "...",
                          "selected_drive_file_ids": ["1abCDe...", "1FghIjkl..."]
                        }
                    }
                }
            }
        },
        404: {"description": "Connector not found."},
        403: {"description": "Forbidden tenant."}
    },
)
def update_connector(
    tenant_id: str,
    connector_id: str,
    request: ConnectorCreateRequest,  # Accepts full config object
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
):
    """
    Updates a connector (full or partial update, including metadata/config JSON).
    - For Google Drive connectors, this allows updating 'selected_drive_file_ids' inside config.
    - For future connectors, use connector-specific keys inside config/metadata.
    - No backend validation for those subfields at this time (frontend responsibility).
    - Existing keys in config are preserved if not overwritten.
    - Returns the updated connector (with config).

    Example config for updating Drive file selection:
    {
        "type": "gdrive",
        "config": {
            ...,
            "selected_drive_file_ids": ["id1", "id2", ...]
        }
    }
    """
    check_auth_and_tenant(credentials, tenant_id)
    connector = db.query(Connector).filter_by(tenant_id=tenant_id, connector_id=connector_id).first()
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    connector.type = request.type.value
    # Merge old config with new keys (for partial update flexibility)
    old_config = dict(connector.config or {})
    next_config = dict(request.config or {})
    old_config.update(next_config)  # Partial update: merge new keys/values into existing
    connector.config = old_config
    connector.updated_at = datetime.utcnow()
    db.commit()
    last_schema = db.query(Schema).filter_by(
        connector_id=connector.connector_id
    ).order_by(Schema.fetched_at.desc()).first()
    schema_info = None
    if last_schema:
        schema_info = {
            "schema_id": last_schema.schema_id,
            "fetched_at": last_schema.fetched_at.isoformat(),
            "raw_schema": last_schema.raw_schema,
        }
    return ConnectorSummary(
        connector_id=connector.connector_id,
        type=connector.type,
        status=connector.status.value,
        created_at=connector.created_at.isoformat() if getattr(connector, 'created_at', None) else None,
        last_schema_fetch=connector.last_schema_fetch.isoformat() if connector.last_schema_fetch else None,
        error_message=connector.error_message,
        schema=schema_info,
        config=connector.config,
        connector_metadata=connector.connector_metadata,
    )


@router.patch(
    "/{connector_id}",
    summary="Partially update connector fields.",
    tags=["Connectors"],
    response_model=ConnectorSummary,
    response_description="The updated connector.",
    responses={
        200: {"description": "The updated connector.", "content": {"application/json": {"example": {}}}},
        404: {"description": "Connector not found."},
        403: {"description": "Forbidden tenant."}
    },
)
def patch_connector(
    tenant_id: str,
    connector_id: str,
    patch_data: dict,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
):
    """
    PATCH endpoint: partial update to any mutable field (connector_metadata, config, status, type, etc).
    Only included fields are updated. Missing fields are left as is.
    """
    check_auth_and_tenant(credentials, tenant_id)
    connector = db.query(Connector).filter_by(tenant_id=tenant_id, connector_id=connector_id).first()
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    allowed_fields = ["connector_metadata", "config", "status", "type"]
    made_update = False
    for key in allowed_fields:
        if key in patch_data and patch_data[key] is not None:
            setattr(connector, key, patch_data[key])
            made_update = True
    if not made_update:
        raise HTTPException(status_code=400, detail="No updatable fields present in patch body.")
    connector.updated_at = datetime.utcnow()
    db.commit()
    last_schema = db.query(Schema).filter_by(
        connector_id=connector.connector_id
    ).order_by(Schema.fetched_at.desc()).first()
    schema_info = None
    if last_schema:
        schema_info = {
            "schema_id": last_schema.schema_id,
            "fetched_at": last_schema.fetched_at.isoformat(),
            "raw_schema": last_schema.raw_schema,
        }
    return ConnectorSummary(
        connector_id=connector.connector_id,
        type=connector.type,
        status=connector.status.value,
        created_at=connector.created_at.isoformat() if getattr(connector, 'created_at', None) else None,
        last_schema_fetch=connector.last_schema_fetch.isoformat() if connector.last_schema_fetch else None,
        error_message=connector.error_message,
        schema=schema_info,
        config=connector.config,
        connector_metadata=connector.connector_metadata,
    )

## Removed per-connector schema review/canonical endpoints

@router.get(
    "/{connector_id}/schemas/{schema_id}",
    response_model=SchemaRead,
    summary="Fetch canonical schema for a connector (tenant- and connector-scoped)",
    tags=["Connectors"],
    response_description="Canonical schema with connector, tenant, fetched time, and canonical fields.",
    responses={
        200: {
            "description": "The canonical schema object identified by connector and schema_id, if authorized.",
            "content": {
                "application/json": {
                    "example": {
                        "schema_id": "c5b4ebcb-5959-41c0-8cc9-1e4b2bc3e0f4",
                        "connector_id": "8c2be193-b8dd-4bbd-8d9a-1f8c7e47ce70",
                        "tenant_id": "4d35dbe2-ff78-4e68-9797-70d484fcc394",
                        "raw_schema": {
                          "entity": "Invoice",
                          "fields": [
                            {"name": "invoice_id", "type": "string", "sources": ["c-234.invoices.id"], "confidence": 0.98},
                            {"name": "amount", "type": "decimal", "sources": ["c-234.invoices.total"], "confidence": 0.96}
                          ]
                        },
                        "fetched_at": "2025-08-13T18:54:23.690Z"
                    }
                }
            }
        },
        404: {"description": "Not found - No schema with this ID exists for this connector."},
        403: {"description": "Forbidden - This schema exists, but you do not have access (wrong tenant)."}
    },
)
def get_schema_for_connector(
    tenant_id: str,
    connector_id: str,
    schema_id: str,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
):
    """
    Fetch and return canonical schema for a given connector.
    - Enforces tenant isolation and connector-scoping.
    - Returns 200 when both connector_id and schema_id belong to this tenant and match.
    - 404 if schema_id does not exist for this connector.
    - 403 if tenant mismatch.
    """
    check_auth_and_tenant(credentials, tenant_id)
    schema = db.query(Schema).filter(
        Schema.schema_id == schema_id,
        Schema.connector_id == connector_id,
        Schema.tenant_id == tenant_id,
    ).first()
    if not schema:
        raise HTTPException(status_code=404, detail="Schema not found for this connector")
    return SchemaRead.model_validate(schema)
