from __future__ import annotations

from typing import Any, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class DocumentUploadResponse(BaseModel):
    document_id: str
    chunks: int
    status: str
    error: Optional[str] = None


class GroundRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k_terms: int = 5
    top_k_evidence: int = 5


class EvidenceSnippet(BaseModel):
    chunk_id: str
    text: str
    score: float
    document_id: str
    document_uri: str | None = None
    metadata: Any | None = None


class TermMappingRead(BaseModel):
    mapping_id: str
    target_kind: str
    entity_name: str | None = None
    field_name: str | None = None
    expression: Any | None = None
    filter: Any | None = None
    rationale: str | None = None
    confidence: int | None = None


class TermRead(BaseModel):
    term_id: str
    term: str
    normalized_term: str
    description: str | None = None
    aliases: List[str] = []
    mappings: List[TermMappingRead] = []
    score: float | None = None


class GroundResponse(BaseModel):
    terms: List[TermRead]
    evidence: List[EvidenceSnippet]


class ImportGlossaryResponse(BaseModel):
    terms_upserted: int
    aliases_created: int
    rows_processed: int


class GlossaryTermRead(BaseModel):
    term_id: str
    term: str
    description: str | None = None


class GlossaryUpdateRequest(BaseModel):
    term: Optional[str] = None
    description: Optional[str] = None


class CreateMappingRequest(BaseModel):
    target_kind: str
    entity_name: str | None = None
    field_name: str | None = None
    expression: Any | None = None
    filter: Any | None = None
    rationale: str | None = None
    confidence: int | None = None


class MappingUpdateRequest(BaseModel):
    target_kind: Optional[str] = None
    entity_name: Optional[str] = None
    field_name: Optional[str] = None
    expression: Any | None = None
    filter: Any | None = None
    rationale: Optional[str] = None
    confidence: Optional[int] = None


class ProposeMappingsResponse(BaseModel):
    proposals: int
    llm_usage: Any | None = None


class ProposalRead(BaseModel):
    proposal_id: str
    term_id: str
    term: str
    target_kind: str
    entity_name: str | None = None
    field_name: str | None = None
    expression: Any | None = None
    filter: Any | None = None
    rationale: str | None = None
    confidence: int | None = None
    evidence: Any | None = None
    created_at: str


class ListProposalsResponse(BaseModel):
    proposals: List[ProposalRead]


class AcceptRejectResponse(BaseModel):
    status: str
    mapping: TermMappingRead | None = None



