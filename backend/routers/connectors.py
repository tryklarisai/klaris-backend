"""
Connectors API endpoints
Production-grade: FastAPI router, error handling, type hints, MCP connection logic (pilot version)
"""
from fastapi import APIRouter, HTTPException, Depends, status
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

import requests

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

router = APIRouter(prefix="/tenants/{tenant_id}/connectors", tags=["Connectors"])

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
        tenant_id=tenant_id,
        type=request.type.value,
        config=request.config.dict(),
        status=ConnectorStatus.FAILED,  # pessimistic by default
        created_at=now,
        updated_at=now,
    )
    db.add(connector)
    db.flush()  # get generated connector_id (UUID)

    # Test connection and try to fetch schema based on connector type
    ok, schema_json, error = test_mcp_connection_and_fetch_schema(request.type.value, request.config.dict())
    if ok and schema_json:
        connector.status = ConnectorStatus.ACTIVE
        connector.last_schema_fetch = now
        connector.error_message = None
        # Save current schema
        schema = Schema(
            connector_id=connector.connector_id,
            tenant_id=tenant_id,
            raw_schema=schema_json,
            fetched_at=now,
        )
        db.add(schema)
    else:
        connector.status = ConnectorStatus.FAILED
        connector.error_message = error or "Unknown failure during connection/schema fetch"
        connector.last_schema_fetch = None
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
            last_schema_fetch=conn.last_schema_fetch.isoformat() if conn.last_schema_fetch else None,
            error_message=conn.error_message,
            schema=schema_info,
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
            connector_id=connector.connector_id,
            tenant_id=tenant_id,
            raw_schema=schema_json,
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
