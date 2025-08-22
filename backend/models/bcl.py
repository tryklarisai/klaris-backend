"""
Business Context Layer (BCL) ORM models

Tables: bcl_documents, bcl_chunks, bcl_terms, bcl_term_aliases, bcl_term_mappings, bcl_term_evidence
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, Integer, Float
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from .base import Base


class BclDocument(Base):
    __tablename__ = "bcl_documents"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False
    )
    uri: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_meta: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    chunks: Mapped[list[BclChunk]] = relationship(
        "BclChunk", back_populates="document", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<BclDocument id={self.document_id} tenant={self.tenant_id} uri={self.uri!r}>"


class BclChunk(Base):
    __tablename__ = "bcl_chunks"

    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bcl_documents.document_id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(), nullable=False)
    # 'metadata' is reserved by SQLAlchemy declarative; map attribute to column name 'metadata'
    chunk_metadata: Mapped[Any | None] = mapped_column('metadata', JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    document: Mapped[BclDocument] = relationship("BclDocument", back_populates="chunks")

    evidences: Mapped[list[BclTermEvidence]] = relationship(
        "BclTermEvidence", back_populates="chunk", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<BclChunk id={self.chunk_id} doc={self.document_id}>"


class BclTerm(Base):
    __tablename__ = "bcl_terms"

    term_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False
    )
    term: Mapped[str] = mapped_column(String(256), nullable=False)
    normalized_term: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(), nullable=True)
    examples: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    source_meta: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    aliases: Mapped[list[BclTermAlias]] = relationship(
        "BclTermAlias", back_populates="term", cascade="all, delete-orphan"
    )
    mappings: Mapped[list[BclTermMapping]] = relationship(
        "BclTermMapping", back_populates="term", cascade="all, delete-orphan"
    )
    evidences: Mapped[list[BclTermEvidence]] = relationship(
        "BclTermEvidence", back_populates="term", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<BclTerm id={self.term_id} tenant={self.tenant_id} term={self.term!r}>"


class BclTermAlias(Base):
    __tablename__ = "bcl_term_aliases"

    alias_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False
    )
    term_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bcl_terms.term_id", ondelete="CASCADE"), nullable=False
    )
    alias: Mapped[str] = mapped_column(String(256), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    term: Mapped[BclTerm] = relationship("BclTerm", back_populates="aliases")

    def __repr__(self) -> str:
        return f"<BclTermAlias id={self.alias_id} term_id={self.term_id} alias={self.alias!r}>"


class BclTermMapping(Base):
    __tablename__ = "bcl_term_mappings"

    mapping_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False
    )
    term_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bcl_terms.term_id", ondelete="CASCADE"), nullable=False
    )
    target_kind: Mapped[str] = mapped_column(String(16), nullable=False)  # table | column | expression | filter
    entity_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    field_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    expression: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    filter: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    term: Mapped[BclTerm] = relationship("BclTerm", back_populates="mappings")

    def __repr__(self) -> str:
        return f"<BclTermMapping id={self.mapping_id} term_id={self.term_id} kind={self.target_kind}>"


class BclTermEvidence(Base):
    __tablename__ = "bcl_term_evidence"

    evidence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False
    )
    term_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bcl_terms.term_id", ondelete="CASCADE"), nullable=False
    )
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bcl_chunks.chunk_id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    term: Mapped[BclTerm] = relationship("BclTerm", back_populates="evidences")
    chunk: Mapped[BclChunk] = relationship("BclChunk", back_populates="evidences")

    def __repr__(self) -> str:
        return f"<BclTermEvidence id={self.evidence_id} term_id={self.term_id} chunk_id={self.chunk_id}>"


class BclMappingProposal(Base):
    __tablename__ = "bcl_mapping_proposals"

    proposal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.tenant_id", ondelete="CASCADE"), nullable=False
    )
    term_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bcl_terms.term_id", ondelete="CASCADE"), nullable=False
    )
    target_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    entity_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    field_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    expression: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    filter: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)



