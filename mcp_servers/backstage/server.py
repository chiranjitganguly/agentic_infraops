"""T039 — backstage-mcp: MCP server wrapping the Backstage catalog API.

Tools: register_entity, update_entity, get_entity, list_entities_by_owner.
All tools wrapped with @gcp_circuit_breaker (reused for Backstage API calls).
"""
from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from contracts.shared.circuit_breaker import gcp_circuit_breaker
from contracts.shared.logging import configure_logging, get_logger

configure_logging(service_name="backstage-mcp")
logger = get_logger("backstage-mcp")

mcp = FastMCP("backstage-mcp")

_BACKSTAGE_API_URL = os.environ.get("BACKSTAGE_API_URL", "http://localhost:7007/api")
_BACKSTAGE_API_TOKEN = os.environ.get("BACKSTAGE_API_TOKEN", "")

_CATALOG_BASE = f"{_BACKSTAGE_API_URL}/catalog"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_BACKSTAGE_API_TOKEN}",
        "Content-Type": "application/json",
    }


def _entity_ref(kind: str, namespace: str, name: str) -> str:
    return f"{kind.lower()}:{namespace}/{name}"


@mcp.tool()
@gcp_circuit_breaker(tool="register_entity", resource_type="backstage_entity")
def register_entity(
    kind: str,
    name: str,
    namespace: str,
    metadata: dict[str, Any],
    spec: dict[str, Any],
) -> dict[str, str]:
    """Register a new entity in the Backstage catalog.

    Args:
        kind: Backstage entity kind (e.g. 'Resource', 'Component').
        name: Entity name (unique within namespace).
        namespace: Backstage namespace (default: 'default').
        metadata: Additional metadata dict (labels, annotations, description).
        spec: Entity spec dict (type, owner, lifecycle).
    """
    entity_body = {
        "apiVersion": "backstage.io/v1alpha1",
        "kind": kind,
        "metadata": {
            "name": name,
            "namespace": namespace,
            **metadata,
        },
        "spec": spec,
    }
    with httpx.Client(timeout=30) as client:
        response = client.post(
            f"{_CATALOG_BASE}/entities",
            json=entity_body,
            headers=_headers(),
        )
        response.raise_for_status()

    entity_ref = _entity_ref(kind, namespace, name)
    logger.info("backstage_entity_registered", entity_ref=entity_ref)
    return {"entity_ref": entity_ref}


@mcp.tool()
@gcp_circuit_breaker(tool="update_entity", resource_type="backstage_entity")
def update_entity(entity_ref: str, metadata_patch: dict[str, Any]) -> dict[str, str]:
    """Update metadata on an existing Backstage catalog entity.

    Args:
        entity_ref: Full entity reference (e.g. 'resource:default/my-vm').
        metadata_patch: Partial metadata dict to merge into the entity.
    """
    kind, rest = entity_ref.split(":", 1)
    namespace, name = rest.split("/", 1)

    with httpx.Client(timeout=30) as client:
        get_resp = client.get(
            f"{_CATALOG_BASE}/entities/by-name/{kind}/{namespace}/{name}",
            headers=_headers(),
        )
        get_resp.raise_for_status()
        entity = get_resp.json()

        entity["metadata"].update(metadata_patch)

        put_resp = client.put(
            f"{_CATALOG_BASE}/entities/by-name/{kind}/{namespace}/{name}",
            json=entity,
            headers=_headers(),
        )
        put_resp.raise_for_status()

    logger.info("backstage_entity_updated", entity_ref=entity_ref)
    return {"entity_ref": entity_ref}


@mcp.tool()
@gcp_circuit_breaker(tool="get_entity", resource_type="backstage_entity")
def get_entity(entity_ref: str) -> dict[str, Any]:
    """Fetch a Backstage catalog entity by ref.

    Returns empty dict if the entity does not exist.

    Args:
        entity_ref: Full entity reference (e.g. 'resource:default/my-vm').
    """
    kind, rest = entity_ref.split(":", 1)
    namespace, name = rest.split("/", 1)

    with httpx.Client(timeout=30) as client:
        response = client.get(
            f"{_CATALOG_BASE}/entities/by-name/{kind}/{namespace}/{name}",
            headers=_headers(),
        )
        if response.status_code == 404:
            return {}
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]


@mcp.tool()
@gcp_circuit_breaker(tool="list_entities_by_owner", resource_type="backstage_entity")
def list_entities_by_owner(owner: str, kind: str | None = None) -> list[dict[str, Any]]:
    """List all Backstage catalog entities owned by a user or team.

    Args:
        owner: Owner reference (e.g. 'user:default/dev@example.com').
        kind: Optional entity kind filter (e.g. 'Resource').
    """
    params: dict[str, str] = {"filter": f"spec.owner={owner}"}
    if kind:
        params["filter"] += f",kind={kind}"

    with httpx.Client(timeout=30) as client:
        response = client.get(
            f"{_CATALOG_BASE}/entities",
            params=params,
            headers=_headers(),
        )
        response.raise_for_status()
        return response.json()  # type: ignore[no-any-return]


if __name__ == "__main__":
    import os
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = int(os.environ.get("MCP_PORT", "8096"))
    mcp.run(transport="sse")
