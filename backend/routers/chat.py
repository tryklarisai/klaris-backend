"""
chat.py
Chat API router powered by LangGraph agent.
Single endpoint that returns the assistant's answer with optional tool route and data preview.
"""
from __future__ import annotations
from typing import Any, List, Optional, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.orm import Session
from uuid import UUID
import os
import jwt
import json

from db import get_db
from models.tenant import ChatThread
from agents.chat_graph import run_chat_agent_stream, create_thread, list_threads, delete_thread

router = APIRouter(prefix="/api/v1", tags=["Chat"])

JWT_SECRET = os.getenv("JWT_SECRET", "insecure-placeholder-change-in-env")
JWT_ALGORITHM = "HS256"


class ChatRequest(BaseModel):
    message: str
    thread_id: Optional[str] = None


class RouteMeta(BaseModel):
    tool: Optional[str] = None
    connector_id: Optional[str] = None
    connector_type: Optional[str] = None


class DataPreview(BaseModel):
    columns: List[str]
    rows: List[list[Any]]


class ChatResponse(BaseModel):
    answer: str
    route: Optional[RouteMeta] = None
    data_preview: Optional[DataPreview] = None
    plans: Optional[List[Dict[str, Any]]] = None
    clarifications: Optional[List[str]] = None


class CreateThreadBody(BaseModel):
    title: Optional[str] = None


def _get_tenant_from_token(credentials: HTTPAuthorizationCredentials) -> UUID:
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")
    tenant = payload.get("tenant") or {}
    tenant_id = tenant.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant context missing from token")
    try:
        return UUID(str(tenant_id))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid tenant id in token")


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    body: ChatRequest,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
):
    tenant_id = _get_tenant_from_token(credentials)
    # Best-effort: ensure thread exists in DB and set auto-title if missing
    if body.thread_id:
        try:
            th = (
                db.query(ChatThread)
                .filter(ChatThread.tenant_id == tenant_id, ChatThread.thread_id == body.thread_id)
                .first()
            )
            if th is None:
                th = ChatThread(thread_id=str(body.thread_id), tenant_id=tenant_id, title=None)
                db.add(th)
                db.commit()
            if (th.title is None or str(th.title).strip() == "") and (body.message or "").strip():
                # Use first 5 words as a friendly title
                words = (body.message or "").strip().split()
                snippet = " ".join(words[:5])
                th.title = f"Q: {snippet}" if snippet else f"Thread - {str(body.thread_id)[:8]}"
                db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
    gen = run_chat_agent_stream(db, tenant_id, body.message, thread_id=body.thread_id)
    answer: str = ""
    route: Optional[Dict[str, Any]] = None
    data_preview: Optional[Dict[str, Any]] = None
    try:
        async for sse in gen:
            lines = [ln for ln in sse.strip().split("\n") if ln]
            if not lines or not lines[0].startswith("event:"):
                continue
            ev = lines[0].split(":", 1)[1].strip()
            if ev == "final":
                data_line = next((ln for ln in lines if ln.startswith("data:")), None)
                if data_line:
                    try:
                        payload = json.loads(data_line.split(":", 1)[1].strip())
                    except Exception:
                        payload = {}
                    answer = str(payload.get("answer") or "")
                    route = payload.get("route") if isinstance(payload, dict) else None
                    dp = payload.get("data_preview") if isinstance(payload, dict) else None
                    if isinstance(dp, dict):
                        data_preview = dp
            elif ev == "error":
                data_line = next((ln for ln in lines if ln.startswith("data:")), None)
                detail = None
                if data_line:
                    detail = data_line.split(":", 1)[1].strip()
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail or "Agent error")
    finally:
        try:
            await gen.aclose()
        except Exception:
            pass

    route_model = RouteMeta(**route) if isinstance(route, dict) else None
    dp_model = DataPreview(**data_preview) if isinstance(data_preview, dict) and data_preview.get("columns") is not None else None
    return ChatResponse(
        answer=answer,
        route=route_model,
        data_preview=dp_model,
        plans=[],
        clarifications=[],
    )


@router.post("/chat/stream")
async def chat_stream_endpoint(
    body: ChatRequest,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
):
    """Return Server-Sent Events streaming the agent's thinking and tool progress.
    Events:
      - token: incremental model tokens
      - thought: agent action log lines
      - tool_start/tool_end: tool execution lifecycle with truncated outputs
      - final: final natural language answer
      - done: stream termination sentinel
    """
    tenant_id = _get_tenant_from_token(credentials)
    # Best-effort: ensure thread exists in DB and set auto-title if missing
    if body.thread_id:
        try:
            th = (
                db.query(ChatThread)
                .filter(ChatThread.tenant_id == tenant_id, ChatThread.thread_id == body.thread_id)
                .first()
            )
            if th is None:
                th = ChatThread(thread_id=str(body.thread_id), tenant_id=tenant_id, title=None)
                db.add(th)
                db.commit()
            if (th.title is None or str(th.title).strip() == "") and (body.message or "").strip():
                words = (body.message or "").strip().split()
                snippet = " ".join(words[:5])
                th.title = f"Q: {snippet}" if snippet else f"Thread - {str(body.thread_id)[:8]}"
                db.commit()
        except Exception:
            try:
                db.rollback()
            except Exception:
                pass
    gen = run_chat_agent_stream(db, tenant_id, body.message, thread_id=body.thread_id)
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(gen, media_type="text/event-stream", headers=headers)


@router.post("/chat/threads")
async def create_thread_endpoint(
    body: Optional[CreateThreadBody] = None,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
):
    tenant_id = _get_tenant_from_token(credentials)
    tid = create_thread(tenant_id)
    # Persist thread metadata with optional title
    try:
        title = None
        if body and isinstance(body, CreateThreadBody) and body.title:
            t = str(body.title).strip()
            title = t if t else None
        th = ChatThread(thread_id=str(tid), tenant_id=tenant_id, title=title)
        db.add(th)
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    return {"thread_id": tid}


@router.get("/chat/threads")
async def list_threads_endpoint(
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
):
    tenant_id = _get_tenant_from_token(credentials)
    try:
        rows = (
            db.query(ChatThread)
            .filter(ChatThread.tenant_id == tenant_id)
            .order_by(ChatThread.updated_at.desc())
            .all()
        )
        if rows:
            return {"threads": [{"thread_id": r.thread_id, "title": r.title} for r in rows]}
    except Exception:
        pass
    # Fallback to in-memory thread ids if DB is empty or unavailable
    try:
        ids = list_threads(tenant_id)
    except Exception:
        ids = []
    return {"threads": [{"thread_id": i, "title": None} for i in ids]}


@router.delete("/chat/threads/{thread_id}")
async def delete_thread_endpoint(
    thread_id: str,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
):
    tenant_id = _get_tenant_from_token(credentials)
    deleted = False
    # Remove from DB first
    try:
        th = (
            db.query(ChatThread)
            .filter(ChatThread.tenant_id == tenant_id, ChatThread.thread_id == thread_id)
            .first()
        )
        if th is not None:
            db.delete(th)
            db.commit()
            deleted = True
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    # Remove from in-memory histories
    try:
        if delete_thread(tenant_id, thread_id):
            deleted = True
    except Exception:
        pass
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    return {"deleted": True}
