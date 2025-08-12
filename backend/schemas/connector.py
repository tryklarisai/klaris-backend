"""
Connector API Pydantic Schemas
Production-grade: type-safe, linted, API versioned.
"""
from typing import Any, Optional
from uuid import UUID
from pydantic import BaseModel, Field, Json
from enum import Enum

class ConnectorType(str, Enum):
    POSTGRES = "postgres"
    GDRIVE = "gdrive"
    # Add more types as needed

class ConnectorStatus(str, Enum):
    ACTIVE = "active"
    FAILED = "failed"

class ConnectorConfig(BaseModel):
    # Minimum MCP config
    mcp_url: str = Field(..., example="http://my-mcp-server:8000")
    username: Optional[str] = Field(None)
    password: Optional[str] = Field(None)
    client_id: Optional[str] = Field(None)
    client_secret: Optional[str] = Field(None)
    extra: Optional[Any] = Field(None)

class ConnectorCreateRequest(BaseModel):
    type: ConnectorType
    config: ConnectorConfig

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
    type: ConnectorType
    status: ConnectorStatus
    last_schema_fetch: Optional[str] = None
    error_message: Optional[str] = None
    schema: Optional[ConnectorSchemaInfo] = None

class ConnectorListResponse(BaseModel):
    connectors: list[ConnectorSummary]
