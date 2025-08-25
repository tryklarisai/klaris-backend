"""
Connector API Pydantic Schemas
Production-grade: type-safe, linted, API versioned.
"""
from typing import Any, Dict, Optional
from uuid import UUID
from pydantic import BaseModel, Field, Json
from enum import Enum

class ConnectorType(str, Enum):
    POSTGRES = "postgres"
    GOOGLE_DRIVE = "google_drive"  # Use canonical name for clarity and extensibility
    # Add more types as needed

class ConnectorStatus(str, Enum):
    ACTIVE = "active"
    FAILED = "failed"

# Removed ConnectorConfig, use Dict[str, Any] for config

class ConnectorCreateRequest(BaseModel):
    type: ConnectorType
    config: Dict[str, Any]
    name: Optional[str] = None

class ConnectorCreateResponse(BaseModel):
    connector_id: UUID
    status: ConnectorStatus
    error: Optional[str] = None

class ConnectorSchemaInfo(BaseModel):
    schema_id: UUID
    fetched_at: str
    # Optionally add structure for preview

class ConnectorSummary(BaseModel):
    connector_id: UUID
    name: Optional[str] = None
    type: ConnectorType
    status: ConnectorStatus
    created_at: Optional[str] = None
    last_schema_fetch: Optional[str] = None
    error_message: Optional[str] = None
    schema: Optional[ConnectorSchemaInfo] = None
    config: Optional[Any] = None
    connector_metadata: Optional[Any] = None

class ConnectorListResponse(BaseModel):
    connectors: list[ConnectorSummary]
