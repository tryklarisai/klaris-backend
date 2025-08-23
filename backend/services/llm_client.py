"""
LLM Client abstraction with Anthropic implementation.
Configuration via environment variables only; no hardcoding of provider/model.
"""
from __future__ import annotations
import os
import time
import math
from typing import Any, Dict, Optional, Tuple, List
import re


class LLMClient:
    def review_schema(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        timeout: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        raise NotImplementedError

    def write_cards(self, prompts: List[Dict[str, str]], timeout: Optional[int] = None) -> List[str]:
        """
        Optional convenience for batch prose generation. Each item: {"system": str, "user": str}.
        Returns card texts aligned with inputs. Default implementation calls review-like JSON mode is not required,
        concrete providers can override to use normal text responses.
        """
        raise NotImplementedError


class AnthropicClient(LLMClient):
    def __init__(self, *, api_key: str, model: str,
                 timeout: int = 30, max_tokens: int = 1500,
                 retry_max: int = 2, backoff_base: float = 0.5) -> None:
        from anthropic import Anthropic
        self.client = Anthropic(api_key=api_key)
        self.model = model
        self.timeout = int(timeout)
        self.max_tokens = int(max_tokens)
        self.retry_max = int(retry_max)
        self.backoff_base = float(backoff_base)

    def _best_effort_parse(self, text: str) -> Dict[str, Any]:
        import json
        # 1) direct parse
        try:
            return json.loads(text)
        except Exception:
            pass
        # 2) sanitize smart quotes and control chars
        cleaned = text
        cleaned = cleaned.replace("\u201c", '"').replace("\u201d", '"').replace("\u2019", "'")
        cleaned = ''.join(ch for ch in cleaned if ch >= ' ' or ch in ('\n', '\t'))
        try:
            return json.loads(cleaned)
        except Exception:
            pass
        # 3) longest balanced JSON object substring
        def balanced_substring(s: str) -> Optional[str]:
            depth = 0
            in_str = False
            esc = False
            start = None
            last_good = None
            for i, ch in enumerate(s):
                if in_str:
                    if esc:
                        esc = False
                    elif ch == '\\':
                        esc = True
                    elif ch == '"':
                        in_str = False
                else:
                    if ch == '"':
                        in_str = True
                    elif ch == '{':
                        if start is None:
                            start = i
                        depth += 1
                    elif ch == '}':
                        if depth > 0:
                            depth -= 1
                            if depth == 0 and start is not None:
                                last_good = s[start:i+1]
            return last_good
        sub = balanced_substring(cleaned)
        if sub:
            try:
                return json.loads(sub)
            except Exception:
                pass
        # 4) give up to empty structure to avoid 500
        return {"unified_entities": [], "cross_source_relationships": [], "entities": [], "relationships": []}

    def review_schema(self, prompt: str, system: Optional[str] = None, max_tokens: Optional[int] = None, timeout: Optional[int] = None, temperature: Optional[float] = None):
        attempt = 0
        last_err: Optional[Exception] = None
        while attempt <= self.retry_max:
            try:
                t0 = time.time()
                resp = self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens or self.max_tokens,
                    temperature=0 if temperature is None else float(temperature),
                    system=system or "You are a precise data modeling assistant. Return ONLY valid JSON matching the provided schema.",
                    messages=[{"role": "user", "content": prompt}],
                )
                text = resp.content[0].text if resp.content else "{}"
                parsed = self._best_effort_parse(text)
                usage = {
                    "input_tokens": getattr(resp.usage, "input_tokens", None),
                    "output_tokens": getattr(resp.usage, "output_tokens", None),
                    "total_tokens": None,
                }
                if usage["input_tokens"] is not None and usage["output_tokens"] is not None:
                    usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
                # Best-effort usage logging
                try:
                    from services.usage import log_usage_event  # local import to avoid cycles
                    db = getattr(self, "_db", None)
                    tenant_id = getattr(self, "_tenant_id", None)
                    if db is not None and tenant_id:
                        log_usage_event(
                            db,
                            tenant_id=str(tenant_id),
                            provider="anthropic",
                            model=self.model,
                            operation="chat",
                            category=getattr(self, "_category", None),
                            module=getattr(self, "_module", None),
                            input_tokens=usage.get("input_tokens"),
                            output_tokens=usage.get("output_tokens"),
                            total_tokens=usage.get("total_tokens"),
                            request_id=getattr(resp, "id", None),
                            latency_ms=int((time.time() - t0) * 1000),
                        )
                except Exception:
                    pass
                return parsed, usage
            except Exception as e:
                last_err = e
                if attempt == self.retry_max:
                    raise
                sleep_s = self.backoff_base * math.pow(2, attempt)
                time.sleep(sleep_s)
                attempt += 1


class OpenAIClient(LLMClient):
    def __init__(self, *, api_key: str, base_url: str, model: str,
                 timeout: int = 90, max_tokens: int = 4000,
                 retry_max: int = 2, backoff_base: float = 0.5) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = int(timeout)
        self.max_tokens = int(max_tokens)
        self.retry_max = int(retry_max)
        self.backoff_base = float(backoff_base)

    def _best_effort_parse(self, text: str) -> Dict[str, Any]:
        import json
        # 1) direct parse
        try:
            return json.loads(text)
        except Exception:
            pass
        # 2) sanitize quotes/control chars
        cleaned = text
        cleaned = cleaned.replace("\u201c", '"').replace("\u201d", '"').replace("\u2019", "'")
        cleaned = ''.join(ch for ch in cleaned if ch >= ' ' or ch in ('\n', '\t'))
        try:
            return json.loads(cleaned)
        except Exception:
            pass
        # 3) longest balanced JSON object substring
        def balanced_substring(s: str) -> Optional[str]:
            depth = 0
            in_str = False
            esc = False
            start = None
            last_good = None
            for i, ch in enumerate(s):
                if in_str:
                    if esc:
                        esc = False
                    elif ch == '\\':
                        esc = True
                    elif ch == '"':
                        in_str = False
                else:
                    if ch == '"':
                        in_str = True
                    elif ch == '{':
                        if start is None:
                            start = i
                        depth += 1
                    elif ch == '}':
                        if depth > 0:
                            depth -= 1
                            if depth == 0 and start is not None:
                                last_good = s[start:i+1]
            return last_good
        sub = balanced_substring(cleaned)
        if sub:
            try:
                return json.loads(sub)
            except Exception:
                pass
        return {"unified_entities": [], "cross_source_relationships": [], "entities": [], "relationships": []}

    def review_schema(self, prompt: str, system: Optional[str] = None, max_tokens: Optional[int] = None, timeout: Optional[int] = None, temperature: Optional[float] = None):
        import json
        import requests
        attempt = 0
        last_err: Optional[Exception] = None
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "temperature": 0 if temperature is None else float(temperature),
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system or "You are a precise data modeling assistant. Return ONLY valid JSON matching the provided schema."},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens or self.max_tokens,
        }
        while attempt <= self.retry_max:
            try:
                t0 = time.time()
                resp = requests.post(url, headers=headers, json=payload, timeout=timeout or self.timeout)
                resp.raise_for_status()
                data = resp.json()
                text = data.get("choices", [{}])[0].get("message", {}).get("content") or "{}"
                # Try best-effort local parse first
                parsed = self._best_effort_parse(text)
                # If empty fallback, try a JSON repair round-trip
                if not parsed or (not parsed.get("unified_entities") and not parsed.get("entities")):
                    repair_payload = {
                        "model": self.model,
                        "temperature": 0,
                        "response_format": {"type": "json_object"},
                        "messages": [
                            {"role": "system", "content": "You repair malformed JSON. Return only valid JSON, no prose."},
                            {"role": "user", "content": f"Repair this into valid strict JSON only (no prose):\n{text}"},
                        ],
                        "max_tokens": self.max_tokens,
                    }
                    resp2 = requests.post(url, headers=headers, json=repair_payload, timeout=timeout or self.timeout)
                    resp2.raise_for_status()
                    data2 = resp2.json()
                    text2 = data2.get("choices", [{}])[0].get("message", {}).get("content") or "{}"
                    parsed = self._best_effort_parse(text2)
                usage = data.get("usage", {})
                # Best-effort usage logging
                try:
                    from services.usage import log_usage_event  # local import to avoid cycles
                    db = getattr(self, "_db", None)
                    tenant_id = getattr(self, "_tenant_id", None)
                    if db is not None and tenant_id:
                        log_usage_event(
                            db,
                            tenant_id=str(tenant_id),
                            provider="openai",
                            model=self.model,
                            operation="chat",
                            category=getattr(self, "_category", None),
                            module=getattr(self, "_module", None),
                            input_tokens=usage.get("prompt_tokens"),
                            output_tokens=usage.get("completion_tokens"),
                            total_tokens=usage.get("total_tokens"),
                            request_id=resp.headers.get("x-request-id") or data.get("id"),
                            latency_ms=int((time.time() - t0) * 1000),
                        )
                except Exception:
                    pass
                return parsed, usage
            except Exception as e:
                last_err = e
                if attempt == self.retry_max:
                    raise
                sleep_s = self.backoff_base * math.pow(2, attempt)
                time.sleep(sleep_s)
                attempt += 1

    def write_cards(self, prompts: List[Dict[str, str]], timeout: Optional[int] = None) -> List[str]:
        import requests
        results: List[str] = []
        url = f"{self.base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        for p in prompts:
            payload = {
                "model": self.model,
                "temperature": 0.3,
                "messages": [
                    {"role": "system", "content": p.get("system") or "You write concise, fact-based summaries."},
                    {"role": "user", "content": p.get("user") or ""},
                ],
                "max_tokens": self.max_tokens,
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout or self.timeout)
            resp.raise_for_status()
            data = resp.json()
            text = data.get("choices", [{}])[0].get("message", {}).get("content") or ""
            results.append(text)
        return results


def get_llm_client() -> Tuple[str, str, LLMClient]:
    raise RuntimeError("Use tenant-scoped LLM client factory: get_llm_client_for_tenant")


# Tenant settings aware factories
from typing import Tuple
from services.settings import get_tenant_settings, get_setting
from constants import (
    LLM_PROVIDER as KEY_LLM_PROVIDER,
    LLM_MODEL as KEY_LLM_MODEL,
    LLM_API_KEY as KEY_LLM_API_KEY,
    OPENAI_BASE_URL as KEY_OPENAI_BASE_URL,
    LLM_TIMEOUT_SECONDS as KEY_LLM_TIMEOUT_SECONDS,
    LLM_MAX_TOKENS as KEY_LLM_MAX_TOKENS,
    LLM_RETRY_MAX as KEY_LLM_RETRY_MAX,
    LLM_BACKOFF_BASE as KEY_LLM_BACKOFF_BASE,
)
from sqlalchemy.orm import Session


def get_llm_client_for_settings(settings: dict) -> Tuple[str, str, LLMClient]:
    provider = str(get_setting(settings, KEY_LLM_PROVIDER, "anthropic")).lower()
    model = str(get_setting(settings, KEY_LLM_MODEL, "gpt-4o"))
    if provider == "openai":
        client = OpenAIClient(
            api_key=str(get_setting(settings, KEY_LLM_API_KEY, "")),
            base_url=str(get_setting(settings, KEY_OPENAI_BASE_URL, "https://api.openai.com/v1")),
            model=model,
            timeout=int(get_setting(settings, KEY_LLM_TIMEOUT_SECONDS, 90)),
            max_tokens=int(get_setting(settings, KEY_LLM_MAX_TOKENS, 4000)),
            retry_max=int(get_setting(settings, KEY_LLM_RETRY_MAX, 2)),
            backoff_base=float(get_setting(settings, KEY_LLM_BACKOFF_BASE, 0.5)),
        )
        # allow usage logger context injection by callers
        setattr(client, "_provider", "openai")
        return provider, model, client
    elif provider == "anthropic":
        client = AnthropicClient(
            api_key=str(get_setting(settings, KEY_LLM_API_KEY, "")),
            model=model,
            timeout=int(get_setting(settings, KEY_LLM_TIMEOUT_SECONDS, 30)),
            max_tokens=int(get_setting(settings, KEY_LLM_MAX_TOKENS, 1500)),
            retry_max=int(get_setting(settings, KEY_LLM_RETRY_MAX, 2)),
            backoff_base=float(get_setting(settings, KEY_LLM_BACKOFF_BASE, 0.5)),
        )
        setattr(client, "_provider", "anthropic")
        return provider, model, client
    else:
        raise RuntimeError(f"Unsupported LLM provider: {provider}")


def get_llm_client_for_tenant(db: Session, tenant_id: str) -> Tuple[str, str, LLMClient]:
    settings = get_tenant_settings(db, tenant_id)
    return get_llm_client_for_settings(settings)


