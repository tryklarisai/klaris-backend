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

from db import get_db
from agents.chat_graph import run_chat_agent, run_chat_agent_stream

router = APIRouter(prefix="/api/v1", tags=["Chat"])

JWT_SECRET = os.getenv("JWT_SECRET", "insecure-placeholder-change-in-env")
JWT_ALGORITHM = "HS256"


class ChatRequest(BaseModel):
    message: str


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
def chat_endpoint(
    body: ChatRequest,
    db: Session = Depends(get_db),
    credentials: HTTPAuthorizationCredentials = Depends(HTTPBearer()),
):
    tenant_id = _get_tenant_from_token(credentials)
    result = run_chat_agent(db, tenant_id, body.message)
    # Shape response
    route = result.get("route") or None
    if route and isinstance(route, dict):
        route = RouteMeta(**route)
    dp = result.get("data_preview") or None
    if dp and isinstance(dp, dict) and dp.get("columns") is not None:
        dp = DataPreview(**dp)
    return ChatResponse(
        answer=result.get("answer") or "",
        route=route,
        data_preview=dp,
        plans=result.get("plans") or [],
        clarifications=result.get("clarifications") or [],
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
    gen = run_chat_agent_stream(db, tenant_id, body.message)
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(gen, media_type="text/event-stream", headers=headers)
