from __future__ import annotations

from typing import Any, List, Tuple
from datetime import datetime
import io
import os

from sqlalchemy.orm import Session

from models.bcl import BclDocument, BclChunk
from services.embeddings import get_embeddings_client


def _normalize_kind(mime_type: str | None, filename: str | None) -> str:
    if mime_type:
        if "excel" in mime_type:
            return "excel"
        if "csv" in mime_type:
            return "csv"
        if "pdf" in mime_type:
            return "pdf"
        if "word" in mime_type or "msword" in mime_type or "officedocument.wordprocessingml" in mime_type:
            return "docx"
        if "text" in mime_type:
            return "text"
    if filename and filename.lower().endswith(".xlsx"):
        return "excel"
    if filename and filename.lower().endswith(".csv"):
        return "csv"
    if filename and filename.lower().endswith(".pdf"):
        return "pdf"
    if filename and filename.lower().endswith(".docx"):
        return "docx"
    if filename and filename.lower().endswith(".txt"):
        return "text"
    return "unknown"


def _chunk_text(text: str, max_chars_env: str = "BCL_CHUNK_CHARS") -> List[str]:
    try:
        max_chars = int(os.getenv(max_chars_env, "1400"))
    except Exception:
        max_chars = 1400
    if not text:
        return []
    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        chunks.append(text[start:end])
        start = end
    return chunks


def _extract_text_from_csv(bytes_data: bytes, encoding: str | None = None) -> Tuple[str, List[dict]]:
    import pandas as pd
    buf = io.BytesIO(bytes_data)
    df = pd.read_csv(buf, encoding=encoding or "utf-8", dtype=str)
    df = df.fillna("")
    text_lines = []
    provenance: List[dict] = []
    for idx, row in df.iterrows():
        line = ", ".join([f"{col}: {row[col]}" for col in df.columns])
        text_lines.append(line)
        provenance.append({"row_index": int(idx)})
    return "\n".join(text_lines), provenance


def _extract_text_from_excel(bytes_data: bytes) -> Tuple[str, List[dict]]:
    import pandas as pd
    buf = io.BytesIO(bytes_data)
    xl = pd.ExcelFile(buf)
    all_text: List[str] = []
    provenance: List[dict] = []
    for sheet in xl.sheet_names:
        df = xl.parse(sheet, dtype=str).fillna("")
        for idx, row in df.iterrows():
            line = ", ".join([f"{col}: {row[col]}" for col in df.columns])
            all_text.append(f"[{sheet}] {line}")
            provenance.append({"sheet": sheet, "row_index": int(idx)})
    return "\n".join(all_text), provenance


def _extract_text_fallback(bytes_data: bytes) -> Tuple[str, List[dict]]:
    try:
        text = bytes_data.decode("utf-8", errors="ignore")
    except Exception:
        text = ""
    return text, []


def _extract_text_from_pdf(bytes_data: bytes) -> Tuple[str, List[dict]]:
    try:
        from pypdf import PdfReader
    except Exception as e:
        # Library not available
        raise RuntimeError("PDF support not installed. Please add 'pypdf' to requirements.") from e
    reader = PdfReader(io.BytesIO(bytes_data))
    texts: List[str] = []
    provenance: List[dict] = []
    for idx, page in enumerate(reader.pages):
        try:
            content = page.extract_text() or ""
        except Exception:
            content = ""
        texts.append(content)
        provenance.append({"page": idx + 1})
    return "\n\n".join(texts), provenance


def _normalize_extracted_text(text: str) -> str:
    """Clean up OCR/PDF artifacts so UI doesn't render one word per line.
    - Replace bullets with dashes
    - Collapse CRs
    - Convert single newlines to spaces (keep blank lines as paragraph breaks)
    - Collapse multiple spaces
    """
    import re
    if not text:
        return ""
    text = text.replace("\r", "")
    text = text.replace("•", "- ")
    lines = text.split("\n")
    parts: List[str] = []
    empty_streak = 0
    for line in lines:
        s = line.strip()
        if not s:
            empty_streak += 1
            continue
        if empty_streak >= 1 and parts:
            parts.append("\n\n")  # paragraph break
        empty_streak = 0
        parts.append(s + " ")
    cleaned = "".join(parts).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = cleaned.replace("\n \n", "\n\n")
    return cleaned


def ingest_document(
    db: Session,
    tenant_id: str,
    *,
    uri: str,
    filename: str | None,
    mime_type: str | None,
    content: bytes,
) -> dict:
    kind = _normalize_kind(mime_type, filename)
    status = "processed"
    error_message = None

    # Create document row
    doc = BclDocument(
        tenant_id=tenant_id,
        uri=uri,
        title=filename,
        mime_type=mime_type,
        kind=kind,
        status=status,
        error_message=None,
        source_meta={"filename": filename, "mime_type": mime_type},
        created_at=datetime.utcnow(),
    )
    db.add(doc)
    db.flush()

    # Extract and chunk
    text = ""
    provenance_rows: List[dict] = []
    try:
        if kind == "csv":
            text, provenance_rows = _extract_text_from_csv(content)
        elif kind == "excel":
            text, provenance_rows = _extract_text_from_excel(content)
        elif kind == "pdf":
            text, provenance_rows = _extract_text_from_pdf(content)
            text = _normalize_extracted_text(text)
        elif kind == "text":
            text, provenance_rows = _extract_text_fallback(content)
            text = _normalize_extracted_text(text)
        else:
            # Unsupported for now; mark and return
            doc.status = "unsupported"
            doc.error_message = "Unsupported file type for extraction"
            db.commit()
            return {"document_id": str(doc.document_id), "chunks": 0, "status": doc.status}
    except Exception as e:
        doc.status = "failed"
        doc.error_message = str(e)
        db.commit()
        return {"document_id": str(doc.document_id), "chunks": 0, "status": doc.status, "error": str(e)}

    chunks = _chunk_text(text)
    if not chunks:
        db.commit()
        return {"document_id": str(doc.document_id), "chunks": 0, "status": doc.status}

    # Embed and insert
    embed_client = get_embeddings_client()
    vectors = embed_client.embed(chunks)
    now = datetime.utcnow()
    created = 0
    for i, chunk_text in enumerate(chunks):
        meta: dict[str, Any] = {"position": i}
        if i < len(provenance_rows):
            meta.update(provenance_rows[i])
        bcl_chunk = BclChunk(
            tenant_id=tenant_id,
            document_id=doc.document_id,
            text=chunk_text,
            embedding=vectors[i],
            chunk_metadata=meta,
            created_at=now,
        )
        db.add(bcl_chunk)
        created += 1

    db.commit()
    return {"document_id": str(doc.document_id), "chunks": created, "status": doc.status}


