from __future__ import annotations
from typing import Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text


def log_usage_event(
    db: Session,
    *,
    tenant_id: str,
    provider: str,
    model: Optional[str],
    operation: str,  # 'chat' | 'embedding'
    category: Optional[str],
    input_tokens: Optional[int],
    output_tokens: Optional[int],
    total_tokens: Optional[int],
    request_id: Optional[str],
    thread_id: Optional[str] = None,
    route: Optional[str] = None,
    status: Optional[str] = None,
    latency_ms: Optional[int] = None,
    retry_attempt: Optional[int] = None,
    cache_hit: Optional[bool] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    try:
        db.execute(
            text(
                """
                INSERT INTO usage_events (
                    tenant_id, provider, model, operation, category,
                    input_tokens, output_tokens, total_tokens,
                    request_id, thread_id, route, status, latency_ms,
                    retry_attempt, cache_hit, metadata
                ) VALUES (
                    :tenant_id, :provider, :model, :operation, :category,
                    :input_tokens, :output_tokens, :total_tokens,
                    :request_id, :thread_id, :route, :status, :latency_ms,
                    :retry_attempt, :cache_hit, :metadata
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "provider": provider,
                "model": model,
                "operation": operation,
                "category": category,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "request_id": request_id,
                "thread_id": thread_id,
                "route": route,
                "status": status,
                "latency_ms": latency_ms,
                "retry_attempt": retry_attempt,
                "cache_hit": cache_hit,
                "metadata": metadata,
            },
        )
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass


