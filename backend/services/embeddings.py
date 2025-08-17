from __future__ import annotations
from typing import List
import os


class EmbeddingsClient:
    def embed(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError


class OpenAIEmbeddingsClient(EmbeddingsClient):
    def __init__(self) -> None:
        # Prefer EMBEDDING_API_KEY, fall back to LLM_API_KEY
        self.api_key = os.getenv("EMBEDDING_API_KEY", os.getenv("LLM_API_KEY"))
        if not self.api_key:
            raise RuntimeError("Missing EMBEDDING_API_KEY/LLM_API_KEY for embeddings")
        self.model = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")

    def embed(self, texts: List[str]) -> List[List[float]]:
        import requests
        url = f"{self.base_url}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # OpenAI supports batching; send in one request for simplicity
        payload = {"model": self.model, "input": texts}
        resp = requests.post(url, headers=headers, json=payload, timeout=int(os.getenv("INDEX_TIMEOUT_SECONDS", "60")))
        resp.raise_for_status()
        data = resp.json()
        vectors = [item["embedding"] for item in data.get("data", [])]
        if len(vectors) != len(texts):
            # Best-effort alignment
            raise RuntimeError("Embedding count mismatch")
        return vectors


def get_embeddings_client() -> EmbeddingsClient:
    provider = (os.getenv("EMBEDDING_PROVIDER") or os.getenv("LLM_PROVIDER") or "openai").lower()
    if provider == "openai":
        return OpenAIEmbeddingsClient()
    raise RuntimeError(f"Unsupported EMBEDDING_PROVIDER: {provider}")


