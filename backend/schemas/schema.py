"""
Schema Pydantic model (read-only, API surface).
Version: Pydantic v2, FastAPI 0.110+ compatible
"""
from pydantic import BaseModel, UUID4, Field
from typing import Any
from datetime import datetime

class SchemaRead(BaseModel):
    schema_id: UUID4 = Field(..., description="Schema UUID (primary key)")
    connector_id: UUID4 = Field(..., description="Connector UUID (FK)")
    tenant_id: UUID4 = Field(..., description="Tenant UUID (FK)")
    raw_schema: dict = Field(..., description="Canonical schema structure (opaque JSON)")
    fetched_at: datetime = Field(..., description="Schema fetch timestamp (UTC ISO8601)")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "schema_id": "c5b4ebcb-5959-41c0-8cc9-1e4b2bc3e0f4",
                "connector_id": "8c2be193-b8dd-4bbd-8d9a-1f8c7e47ce70",
                "tenant_id": "4d35dbe2-ff78-4e68-9797-70d484fcc394",
                "raw_schema": {
                    "entity": "Invoice",
                    "fields": [
                        {"name": "invoice_id", "type": "string", "sources": ["c-234.invoices.id"], "confidence": 0.98},
                        {"name": "amount", "type": "decimal", "sources": ["c-234.invoices.total"], "confidence": 0.96}
                    ],
                },
                "fetched_at": "2025-08-13T18:54:23.690Z"
            }
        }
