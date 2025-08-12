"""
Global and domain-specific constants for Tenant and platform settings.
"""
from typing import Final, Set

TENANT_NAME_MAX_LENGTH: Final[int] = 100
TENANT_PLAN_MAX_LENGTH: Final[int] = 32
TENANT_ALLOWED_PLANS: Final[Set[str]] = {"pilot", "pro", "enterprise"}
TENANT_DEFAULT_CREDIT: Final[int] = 0
TENANT_LIST_LIMIT: Final[int] = 20
TENANT_SETTINGS_DEFAULT: Final[dict] = {}
