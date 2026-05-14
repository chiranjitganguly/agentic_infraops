"""T — airflow-mcp: MCP server wrapping the Airflow REST API for DAG run status queries.

Tools: get_dag_run_status, list_dag_runs, get_task_instance

Note: DAGs are triggered by PubSub sensor, not by this server.
"""
from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from contracts.shared.logging import configure_logging, get_logger

configure_logging(service_name="airflow-mcp")
logger = get_logger("airflow-mcp")

mcp = FastMCP("airflow-mcp")

_AIRFLOW_API_URL = os.environ.get("AIRFLOW_API_URL", "http://localhost:8080/api/v1")
_AIRFLOW_USERNAME = os.environ.get("AIRFLOW_USERNAME", "admin")
_AIRFLOW_PASSWORD = os.environ.get("AIRFLOW_PASSWORD", "admin")


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=_AIRFLOW_API_URL,
        auth=(_AIRFLOW_USERNAME, _AIRFLOW_PASSWORD),
        timeout=30.0,
    )


@mcp.tool()
def get_dag_run_status(dag_id: str, dag_run_id: str) -> dict[str, Any]:
    """Get the status of a specific Airflow DAG run including task instance states.

    Args:
        dag_id: The DAG identifier (e.g. provision_gcp_resource).
        dag_run_id: The specific DAG run ID.
    """
    with _client() as client:
        run_resp = client.get(f"/dags/{dag_id}/dagRuns/{dag_run_id}")
        run_resp.raise_for_status()
        run = run_resp.json()

        tasks_resp = client.get(f"/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances")
        tasks_resp.raise_for_status()
        task_instances = tasks_resp.json().get("task_instances", [])

    logger.info("get_dag_run_status", dag_id=dag_id, dag_run_id=dag_run_id, state=run.get("state"))
    return {
        "dag_id": run.get("dag_id"),
        "dag_run_id": run.get("dag_run_id"),
        "state": run.get("state"),
        "start_date": run.get("start_date"),
        "end_date": run.get("end_date"),
        "task_instances": [
            {
                "task_id": t.get("task_id"),
                "state": t.get("state"),
                "start_date": t.get("start_date"),
                "end_date": t.get("end_date"),
                "try_number": t.get("try_number"),
            }
            for t in task_instances
        ],
    }


@mcp.tool()
def list_dag_runs(dag_id: str, limit: int = 10) -> list[dict[str, Any]]:
    """List recent runs of a DAG, newest first.

    Args:
        dag_id: The DAG identifier.
        limit: Maximum number of runs to return (default 10).
    """
    with _client() as client:
        resp = client.get(
            f"/dags/{dag_id}/dagRuns",
            params={"limit": limit, "order_by": "-execution_date"},
        )
        resp.raise_for_status()
        runs = resp.json().get("dag_runs", [])

    logger.info("list_dag_runs", dag_id=dag_id, count=len(runs))
    return [
        {
            "dag_run_id": r.get("dag_run_id"),
            "state": r.get("state"),
            "execution_date": r.get("execution_date"),
            "start_date": r.get("start_date"),
            "end_date": r.get("end_date"),
        }
        for r in runs
    ]


@mcp.tool()
def get_task_instance(dag_id: str, dag_run_id: str, task_id: str) -> dict[str, Any]:
    """Get the status of a specific task instance within a DAG run.

    Args:
        dag_id: The DAG identifier.
        dag_run_id: The specific DAG run ID.
        task_id: The task identifier within the DAG.
    """
    with _client() as client:
        resp = client.get(f"/dags/{dag_id}/dagRuns/{dag_run_id}/taskInstances/{task_id}")
        resp.raise_for_status()
        t = resp.json()

    logger.info("get_task_instance", dag_id=dag_id, task_id=task_id, state=t.get("state"))
    return {
        "task_id": t.get("task_id"),
        "dag_id": t.get("dag_id"),
        "dag_run_id": t.get("dag_run_id"),
        "state": t.get("state"),
        "start_date": t.get("start_date"),
        "end_date": t.get("end_date"),
        "duration": t.get("duration"),
        "try_number": t.get("try_number"),
        "operator": t.get("operator"),
    }


if __name__ == "__main__":
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = int(os.environ.get("MCP_PORT", "8094"))
    mcp.run(transport="sse")
