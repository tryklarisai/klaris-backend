from __future__ import annotations
from typing import List
from services.settings import get_tenant_settings, get_setting
from constants import (
    EMBEDDING_PROVIDER as KEY_EMBEDDING_PROVIDER,
    EMBEDDING_MODEL as KEY_EMBEDDING_MODEL,
    EMBEDDING_API_KEY as KEY_EMBEDDING_API_KEY,
    OPENAI_BASE_URL as KEY_OPENAI_BASE_URL,
)
from sqlalchemy.orm import Session
from services.usage import log_usage_event


class EmbeddingsClient:
    def embed(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError


class OpenAIEmbeddingsClient(EmbeddingsClient):
    def __init__(self, *, api_key: str, model: str, base_url: str, timeout: int = 60) -> None:
        if not api_key:
            raise RuntimeError("Missing embeddings API key")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = int(timeout)

    def embed(self, texts: List[str]) -> List[List[float]]:
        import requests, time
        url = f"{self.base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": self.model, "input": texts}
        t0 = time.time()
        resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        # Preserve provider usage for caller
        try:
            self.last_usage = data.get("usage") or None
            self.last_request_id = resp.headers.get("x-request-id") or data.get("id")
        except Exception:
            self.last_usage = None
            self.last_request_id = None
        vectors = [item["embedding"] for item in data.get("data", [])]
        if len(vectors) != len(texts):
            raise RuntimeError("Embedding count mismatch")
        return vectors


def get_embeddings_client_for_settings(settings: dict) -> EmbeddingsClient:
    provider = str(get_setting(settings, KEY_EMBEDDING_PROVIDER, "openai")).lower()
    if provider == "openai":
        return OpenAIEmbeddingsClient(
            api_key=str(get_setting(settings, KEY_EMBEDDING_API_KEY, "")),
            model=str(get_setting(settings, KEY_EMBEDDING_MODEL, "text-embedding-3-small")),
            base_url=str(get_setting(settings, KEY_OPENAI_BASE_URL, "https://api.openai.com/v1")),
            timeout=60,
        )
    raise RuntimeError(f"Unsupported EMBEDDING_PROVIDER: {provider}")


def get_embeddings_client_for_tenant(db: Session, tenant_id: str) -> EmbeddingsClient:
    settings = get_tenant_settings(db, tenant_id)
    return get_embeddings_client_for_settings(settings)


def embed_and_log(db: Session, tenant_id: str, texts: List[str], category: str | None = None) -> List[List[float]]:
    client = get_embeddings_client_for_tenant(db, tenant_id)
    settings = get_tenant_settings(db, tenant_id)
    provider = str(get_setting(settings, KEY_EMBEDDING_PROVIDER, "openai")).lower()
    model = str(get_setting(settings, KEY_EMBEDDING_MODEL, "text-embedding-3-small"))
    import time, requests
    t0 = time.time()
    try:
        vectors = client.embed(texts)
    finally:
        # Best-effort logging with minimal fields
        try:
            usage = getattr(client, "last_usage", None) or {}
            input_tokens = None
            total_tokens = None
            if isinstance(usage, dict):
                input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens") or None
                total_tokens = usage.get("total_tokens") or None
            log_usage_event(
                db,
                tenant_id=tenant_id,
                provider=provider,
                model=model,
                operation="embedding",
                category=category,
                input_tokens=int(input_tokens) if input_tokens is not None else None,
                output_tokens=None,
                total_tokens=int(total_tokens) if total_tokens is not None else None,
                request_id=getattr(client, "last_request_id", None),
                latency_ms=int((time.time() - t0) * 1000),
            )
        except Exception:
            pass
    return vectors

