"""
Pydantic models for Schema Review requests/responses and Canonical Schema payloads.
"""
from __future__ import annotations
from typing import Any, List, Optional, Literal
from pydantic import BaseModel, Field, UUID4
from datetime import datetime


class RelationshipSuggestion(BaseModel):
    from_table: str
    from_field: str
    to_table: str
    to_field: str
    type: Literal["one_to_one", "one_to_many", "many_to_one", "many_to_many", "unknown"] = "unknown"
    description: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)


class FieldSuggestion(BaseModel):
    original_name: str
    recommended_name: str
    description: Optional[str] = None
    semantic_type: Optional[str] = None
    pii_sensitivity: Literal["none", "low", "medium", "high"] = "none"
    nullable: Optional[bool] = None
    data_type: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: Optional[str] = None


class TableSuggestion(BaseModel):
    original_name: str
    recommended_name: str
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    fields: List[FieldSuggestion] = Field(default_factory=list)
    relationships: List[RelationshipSuggestion] = Field(default_factory=list)


class SchemaReviewSuggestions(BaseModel):
    tables: List[TableSuggestion] = Field(default_factory=list)


# Global ontology suggestions for cross-source enrichment
class SourceMapping(BaseModel):
    connector_id: UUID4
    table: str
    field: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class UnifiedField(BaseModel):
    name: str
    description: Optional[str] = None
    semantic_type: Optional[str] = None
    pii_sensitivity: Literal["none", "low", "medium", "high"] = "none"
    nullable: Optional[bool] = None
    data_type: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)


class UnifiedEntity(BaseModel):
    name: str
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    fields: List[UnifiedField] = Field(default_factory=list)
    source_mappings: List[SourceMapping] = Field(default_factory=list)


class CrossSourceRel(BaseModel):
    from_entity: str
    from_field: Optional[str] = None
    to_entity: str
    to_field: Optional[str] = None
    type: Literal["one_to_one", "one_to_many", "many_to_one", "many_to_many", "unknown"] = "unknown"
    description: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)


class GlobalOntology(BaseModel):
    unified_entities: List[UnifiedEntity] = Field(default_factory=list)
    cross_source_relationships: List[CrossSourceRel] = Field(default_factory=list)


class CreateSchemaReviewOptions(BaseModel):
    domain: Optional[str] = None
    confidence_threshold: Optional[float] = Field(default=0.6, ge=0.0, le=1.0)
    max_entities: Optional[int] = Field(default=500, ge=1)


class CreateSchemaReviewRequest(BaseModel):
    source_schema_id: Optional[UUID4] = None
    options: Optional[CreateSchemaReviewOptions] = None


class SchemaReviewRead(BaseModel):
    review_id: UUID4
    tenant_id: UUID4
    connector_id: UUID4
    source_schema_id: Optional[UUID4] = None
    provider: str
    model: str
    status: str
    error_message: Optional[str] = None
    input_snapshot: dict
    suggestions: Optional[SchemaReviewSuggestions] = None
    token_usage: Optional[dict] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SaveCanonicalRequest(BaseModel):
    base_schema_id: UUID4
    review_id: Optional[UUID4] = None
    user_edits: SchemaReviewSuggestions
    note: Optional[str] = None


class CanonicalSchemaRead(BaseModel):
    canonical_schema_id: UUID4
    tenant_id: UUID4
    connector_id: UUID4
    base_schema_id: Optional[UUID4]
    version: int
    canonical_schema: SchemaReviewSuggestions
    note: Optional[str] = None
    approved_by_user_id: Optional[UUID4] = None
    approved_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


