"""
Global and domain-specific constants for Tenant and platform settings.
"""
from typing import Final, Set

TENANT_NAME_MAX_LENGTH: Final[int] = 100
TENANT_PLAN_MAX_LENGTH: Final[int] = 32
TENANT_ALLOWED_PLANS: Final[Set[str]] = {"pilot", "pro", "enterprise"}
TENANT_DEFAULT_CREDIT: Final[int] = 0
TENANT_LIST_LIMIT: Final[int] = 20
TENANT_SETTINGS_DEFAULT: Final[dict] = {
    # Chat / LLM defaults (tenant-overridable)
    "LLM_PROVIDER": "openai",
    "LLM_MODEL": "gpt-4o",
    "LLM_TEMPERATURE": 0.0,
    "LLM_API_KEY": "",  # set per tenant
    "OPENAI_BASE_URL": "https://api.openai.com/v1",
    "CHAT_HISTORY_MAX_TURNS": 20,

    # Embeddings
    "EMBEDDING_PROVIDER": "openai",
    "EMBEDDING_MODEL": "text-embedding-3-small",
    "EMBEDDING_API_KEY": "",  # set per tenant or reuse LLM_API_KEY

    # Indexing / Cards
    "INDEX_MAX_TEXT_LEN": 1200,
    "INDEX_MAX_FIELDS_PER_ENTITY": 200,
}

# Settings keys (avoid string literals elsewhere)
LLM_PROVIDER: Final[str] = "LLM_PROVIDER"
LLM_MODEL: Final[str] = "LLM_MODEL"
LLM_TEMPERATURE: Final[str] = "LLM_TEMPERATURE"
LLM_API_KEY: Final[str] = "LLM_API_KEY"
OPENAI_BASE_URL: Final[str] = "OPENAI_BASE_URL"
CHAT_HISTORY_MAX_TURNS: Final[str] = "CHAT_HISTORY_MAX_TURNS"
EMBEDDING_PROVIDER: Final[str] = "EMBEDDING_PROVIDER"
EMBEDDING_MODEL: Final[str] = "EMBEDDING_MODEL"
EMBEDDING_API_KEY: Final[str] = "EMBEDDING_API_KEY"
LLM_TIMEOUT_SECONDS: Final[str] = "LLM_TIMEOUT_SECONDS"
LLM_MAX_TOKENS: Final[str] = "LLM_MAX_TOKENS"
LLM_RETRY_MAX: Final[str] = "LLM_RETRY_MAX"
LLM_BACKOFF_BASE: Final[str] = "LLM_BACKOFF_BASE"
INDEX_MAX_TEXT_LEN: Final[str] = "INDEX_MAX_TEXT_LEN"
INDEX_MAX_FIELDS_PER_ENTITY: Final[str] = "INDEX_MAX_FIELDS_PER_ENTITY"
