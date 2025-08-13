from typing import Dict, Callable, Any

# MCP registry of adapters by connector type
MCP_REGISTRY: Dict[str, Any] = {}

def register_adapter(connector_type: str, adapter_class: Any):
    MCP_REGISTRY[connector_type] = adapter_class

def get_adapter(connector_type: str):
    adapter = MCP_REGISTRY.get(connector_type)
    if not adapter:
        raise ValueError(f"No MCP adapter registered for connector type: {connector_type}")
    return adapter

# Register known adapters here
from .google_drive import GoogleDriveMCPAdapter
register_adapter("google_drive", GoogleDriveMCPAdapter)
