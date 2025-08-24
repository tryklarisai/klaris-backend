from __future__ import annotations

from typing import Any, Dict, Optional
from sqlalchemy.orm import Session
from constants import TENANT_SETTINGS_DEFAULT
from models.tenant import Tenant


def get_tenant_settings(db: Session, tenant_id: str) -> Dict[str, Any]:
    t = db.query(Tenant).filter(Tenant.tenant_id == tenant_id).first()
    if not t:
        return dict(TENANT_SETTINGS_DEFAULT)
    base = dict(TENANT_SETTINGS_DEFAULT)
    try:
        custom = t.settings or {}
        base.update(custom)
    except Exception:
        pass
    return base


def get_setting(settings: Dict[str, Any], key: str, default: Any = None) -> Any:
    return settings.get(key, default)


