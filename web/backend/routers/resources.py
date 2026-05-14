"""T074a/T074b — Direct GCP resource status endpoints (bypass NL classification).

GET /resources/{resource_type}/{resource_name}  — single resource status
GET /resources                                  — list resources by type
"""
from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from contracts.agents.enquiry import ResourceType
from contracts.shared.logging import get_logger
from skills.status_query.formatter import format_list_response, format_status_response
from skills.status_query.querier import list_resources, query_resource_status

logger = get_logger("resources-router")
router = APIRouter(tags=["resources"])

_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")


@router.get("/resources/{resource_type}/{resource_name}")
async def get_resource_status(
    resource_type: str,
    resource_name: str,
    request: Request,
    project_id: str = Query(default=""),
    zone: str = Query(default=""),
    region: str = Query(default=""),
) -> JSONResponse:
    """Get live GCP status for a single named resource."""
    try:
        rt = ResourceType(resource_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid resource_type '{resource_type}'. Must be one of: {[e.value for e in ResourceType]}",
        )

    effective_project = project_id or _PROJECT_ID
    effective_zone = zone or None
    effective_region = region or None

    try:
        result = query_resource_status(
            resource_type=rt,
            resource_name=resource_name,
            project_id=effective_project,
            zone=effective_zone,
            region=effective_region,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("resource_status_failed", resource_name=resource_name, error=str(exc))
        raise HTTPException(status_code=502, detail="GCP API error. Try again later.")

    if result.get("not_found"):
        raise HTTPException(
            status_code=404,
            detail=f"No {resource_type} named '{resource_name}' found in project '{effective_project}'.",
        )

    metadata = result["metadata"]
    summary = format_status_response(
        metadata=metadata,
        gcp_status=result["gcp_status"],
        resource_name=result["resource_name"],
        resource_type=rt,
    )

    return JSONResponse(
        status_code=200,
        content={
            "resource_type": rt.value,
            "resource_name": result["resource_name"],
            "gcp_status": result["gcp_status"],
            "metadata": metadata.model_dump(mode="json"),
            "human_readable_summary": summary,
            "queried_at": result["queried_at"].isoformat(),
        },
    )


@router.get("/resources")
async def list_project_resources(
    request: Request,
    resource_type: Annotated[str, Query(description="compute_instance | storage_bucket | vpc_network")],
    project_id: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> JSONResponse:
    """List all GCP resources of the given type in the project."""
    try:
        rt = ResourceType(resource_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid resource_type '{resource_type}'. Must be one of: {[e.value for e in ResourceType]}",
        )

    effective_project = project_id or _PROJECT_ID

    try:
        resources = list_resources(rt, effective_project)
    except Exception as exc:
        logger.error("list_resources_failed", resource_type=resource_type, error=str(exc))
        raise HTTPException(status_code=502, detail="GCP API error. Try again later.")

    page = resources[offset: offset + limit]

    return JSONResponse(
        status_code=200,
        content={
            "resource_type": rt.value,
            "project_id": effective_project,
            "resources": [r.model_dump(mode="json") for r in page],
            "total_count": len(resources),
            "queried_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        },
    )
