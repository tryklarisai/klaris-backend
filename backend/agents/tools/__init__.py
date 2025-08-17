# Package init for tools

"""
Tool adapters registry: maps Connector.type to a function that returns a LangChain Tool.
Keeps chat agent simple and lets new connectors plug-in by adding a single adapter.
"""
from __future__ import annotations
from typing import Any, Dict, List, Tuple, Callable

try:
    # Local import; adapter lives alongside
    from .postgres_tool import make_postgres_tool
except Exception:
    make_postgres_tool = None  # type: ignore

try:
    from .gsheets_tool import make_gsheets_tool
except Exception:
    make_gsheets_tool = None  # type: ignore


# type -> adapter factory(connector) -> BaseTool
_ADAPTERS: Dict[str, Callable[[Any], Any]] = {}

if make_postgres_tool is not None:
    _ADAPTERS["postgres"] = make_postgres_tool
if make_gsheets_tool is not None:
    # Register canonical and aliases
    _ADAPTERS["google_drive"] = make_gsheets_tool
    _ADAPTERS["gdrive"] = make_gsheets_tool
    _ADAPTERS["gsheets"] = make_gsheets_tool


def build_tools_for_connectors(connectors: List[Any]) -> Tuple[List[Any], Dict[str, Dict[str, str]]]:
    tools: List[Any] = []
    route_meta: Dict[str, Dict[str, str]] = {}
    for c in connectors:
        # Normalize type and map aliases
        ctype = str(getattr(c, "type", "") or "").lower()
        if ctype in ("gdrive", "gsheets"):
            ctype = "google_drive"
        adapter = _ADAPTERS.get(ctype)
        if not adapter:
            continue
        tool = adapter(c)
        if not tool:
            continue
        tools.append(tool)
        route_meta[tool.name] = {
            "connector_id": str(getattr(c, "connector_id", "")),
            "connector_type": getattr(c, "type", ""),
        }
    return tools, route_meta
