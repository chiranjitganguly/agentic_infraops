"""T089 — Airflow DAG for VPC network provisioning.

DAG: provision_vpc_dag
Schedule: None (triggered by PubSubPullSensor on infraops-provisioning-requests-vpc-sub)

Task flow:
  wait_for_message → update_in_progress → dry_run_validate → provision_vpc → register_backstage → update_succeeded
                                                                               ↓ (ONE_FAILED)
                                                                           rollback_group: rollback_vpc → update_failed

VPC provisioning is restricted to platform_engineer role (developer blocked in update_in_progress).
rollback_resources appended after each successful GCP create (ADR-0006).
Backstage registration failure triggers rollback (ADR-0005).
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone

from airflow import DAG
from airflow.models import TaskInstance
from airflow.operators.python import PythonOperator
from airflow.providers.google.cloud.sensors.pubsub import PubSubPullSensor
from airflow.utils.trigger_rule import TriggerRule

log = logging.getLogger(__name__)

_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "infraops-dev")
_SUBSCRIPTION = "infraops-provisioning-requests-vpc-sub"

_DEFAULT_ARGS = {
    "owner": "infraops",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
}


def _update_job_status_sync(
    job_id: str,
    status: str,
    gcp_resource_id: str | None = None,
    error_message: str | None = None,
    rollback_resources: list | None = None,
) -> None:
    import asyncio

    from mcp_servers.postgres import server as pg

    async def _run() -> None:
        await pg.update_job_status(
            job_id=job_id,
            status=status,
            gcp_resource_id=gcp_resource_id,
            error_message=error_message,
            rollback_resources=rollback_resources,
        )

    asyncio.run(_run())


def task_update_in_progress(**context: object) -> None:
    messages = context["ti"].xcom_pull(task_ids="wait_for_message")
    if not messages:
        raise ValueError("No messages received from PubSubPullSensor")

    message = messages[0]
    data = json.loads(message["data"])
    job_id = data["job_id"]

    # VPC provisioning requires platform_engineer role
    if data.get("user_role") == "developer":
        raise RuntimeError(
            f"VPC provisioning requires platform_engineer role. "
            f"User {data.get('requesting_user', 'unknown')} has role 'developer'."
        )

    context["ti"].xcom_push(key="job_data", value=data)
    _update_job_status_sync(job_id=job_id, status="in_progress")
    log.info("vpc_job_in_progress job_id=%s", job_id)


def task_dry_run_validate(**context: object) -> None:
    import asyncio

    from contracts.agents.provisioning import VPCParameters
    from skills.gcp_network.provisioner import create_vpc

    ti: TaskInstance = context["ti"]
    data = ti.xcom_pull(task_ids="update_in_progress", key="job_data")
    if data is None:
        raw = ti.xcom_pull(task_ids="wait_for_message")
        data = json.loads(raw[0]["data"])

    params = data.get("parameters", {})

    async def _run() -> None:
        from mcp_servers.gcp_resource import server as gcp_server
        from mcp_servers.postgres import server as pg_server

        class _GcpClient:
            async def create_vpc_network(self, **kwargs: object) -> dict:
                return gcp_server.create_vpc_network(**kwargs)  # type: ignore[arg-type]

            async def create_subnetwork(self, **kwargs: object) -> dict:
                return gcp_server.create_subnetwork(**kwargs)  # type: ignore[arg-type]

        class _PgClient:
            async def update_job_status(self, job_id: uuid.UUID, rollback_resources: list) -> None:
                await pg_server.update_job_status(job_id=str(job_id), rollback_resources=rollback_resources)  # type: ignore[arg-type]

        vpc_params = VPCParameters(
            auto_create_subnetworks=params.get("auto_create_subnetworks", False),
            subnet_name=params.get("subnet_name", ""),
            subnet_region=params.get("subnet_region", data["region"]),
            subnet_cidr=params.get("subnet_cidr", "10.0.0.0/24"),
        )

        result = await create_vpc(
            params=vpc_params,
            region=data["region"],
            resource_name=data["resource_name"],
            project_id=_PROJECT_ID,
            job_id=uuid.UUID(data["job_id"]),
            dry_run=True,
            gcp_client=_GcpClient(),  # type: ignore[arg-type]
            postgres_client=_PgClient(),  # type: ignore[arg-type]
        )

        if not result.success:
            raise RuntimeError(f"VPC dry-run validation failed: {result.error_message}")

        log.info("vpc_dry_run_ok job_id=%s", data["job_id"])

    asyncio.run(_run())


def task_provision_vpc(**context: object) -> None:
    import asyncio

    from contracts.agents.provisioning import VPCParameters
    from skills.gcp_network.provisioner import create_vpc

    ti: TaskInstance = context["ti"]
    data = ti.xcom_pull(task_ids="update_in_progress", key="job_data")
    if data is None:
        raw = ti.xcom_pull(task_ids="wait_for_message")
        data = json.loads(raw[0]["data"])

    params = data.get("parameters", {})

    async def _run() -> str | None:
        from mcp_servers.gcp_resource import server as gcp_server
        from mcp_servers.postgres import server as pg_server

        class _GcpClient:
            async def create_vpc_network(self, **kwargs: object) -> dict:
                return gcp_server.create_vpc_network(**kwargs)  # type: ignore[arg-type]

            async def create_subnetwork(self, **kwargs: object) -> dict:
                return gcp_server.create_subnetwork(**kwargs)  # type: ignore[arg-type]

        class _PgClient:
            async def update_job_status(self, job_id: uuid.UUID, rollback_resources: list) -> None:
                await pg_server.update_job_status(job_id=str(job_id), rollback_resources=rollback_resources)  # type: ignore[arg-type]

        vpc_params = VPCParameters(
            auto_create_subnetworks=params.get("auto_create_subnetworks", False),
            subnet_name=params.get("subnet_name", ""),
            subnet_region=params.get("subnet_region", data["region"]),
            subnet_cidr=params.get("subnet_cidr", "10.0.0.0/24"),
        )

        result = await create_vpc(
            params=vpc_params,
            region=data["region"],
            resource_name=data["resource_name"],
            project_id=_PROJECT_ID,
            job_id=uuid.UUID(data["job_id"]),
            dry_run=False,
            gcp_client=_GcpClient(),  # type: ignore[arg-type]
            postgres_client=_PgClient(),  # type: ignore[arg-type]
        )

        if not result.success:
            raise RuntimeError(result.error_message or "VPC provisioning failed")

        return result.gcp_resource_id

    gcp_resource_id = asyncio.run(_run())
    ti.xcom_push(key="gcp_resource_id", value=gcp_resource_id)
    log.info("provision_vpc_done job_id=%s gcp_resource_id=%s", data["job_id"], gcp_resource_id)


def task_register_backstage(**context: object) -> None:
    import asyncio

    ti: TaskInstance = context["ti"]
    data = ti.xcom_pull(task_ids="update_in_progress", key="job_data")
    if data is None:
        raw = ti.xcom_pull(task_ids="wait_for_message")
        data = json.loads(raw[0]["data"])

    gcp_resource_id = ti.xcom_pull(task_ids="provision_vpc", key="gcp_resource_id")

    async def _run() -> None:
        from mcp_servers.backstage import server as bs_server

        params = data.get("parameters", {})
        await bs_server.register_entity(
            kind="Resource",
            name=data["resource_name"],
            namespace="default",
            metadata={
                "description": "GCP VPC network provisioned via InfraOps platform",
                "labels": {
                    "gcp-region": data["region"],
                    "gcp-project": _PROJECT_ID,
                    "provisioned-by": data["requesting_user"],
                    "provisioning-job-id": data["job_id"],
                },
                "annotations": {
                    "infraops/provisioned-at": datetime.now(timezone.utc).isoformat(),
                    "infraops/subnet-cidr": params.get("subnet_cidr", ""),
                },
            },
            spec={
                "type": "gcp-vpc-network",
                "owner": data["requesting_user"],
                "lifecycle": "production",
            },
        )

    asyncio.run(_run())
    log.info("backstage_registered job_id=%s vpc=%s", data["job_id"], data["resource_name"])


def task_update_succeeded(**context: object) -> None:
    ti: TaskInstance = context["ti"]
    data = ti.xcom_pull(task_ids="update_in_progress", key="job_data")
    if data is None:
        raw = ti.xcom_pull(task_ids="wait_for_message")
        data = json.loads(raw[0]["data"])

    gcp_resource_id = ti.xcom_pull(task_ids="provision_vpc", key="gcp_resource_id")

    _update_job_status_sync(
        job_id=data["job_id"],
        status="succeeded",
        gcp_resource_id=gcp_resource_id,
    )
    log.info("vpc_job_succeeded job_id=%s", data["job_id"])


def task_rollback_vpc(**context: object) -> None:
    import asyncio

    from contracts.schemas.provisioning_job import RollbackResource
    from skills.gcp_network.rollback import rollback_vpc

    ti: TaskInstance = context["ti"]
    data = ti.xcom_pull(task_ids="update_in_progress", key="job_data")
    if data is None:
        raw = ti.xcom_pull(task_ids="wait_for_message")
        data = json.loads(raw[0]["data"])

    rollback_resources_raw = ti.xcom_pull(task_ids="provision_vpc", key="rollback_resources") or []
    resources = [RollbackResource(**r) for r in rollback_resources_raw]

    async def _run() -> None:
        from mcp_servers.gcp_resource import server as gcp_server

        class _GcpClient:
            async def delete_vpc_network(self, project_id: str, network_name: str) -> dict:
                return gcp_server.delete_vpc_network(project_id=project_id, network_name=network_name)  # type: ignore[arg-type]

        result = await rollback_vpc(
            rollback_resources=resources,
            project_id=_PROJECT_ID,
            gcp_client=_GcpClient(),  # type: ignore[arg-type]
        )
        if not result.success:
            log.error("rollback_vpc_partial_failure job_id=%s errors=%s", data["job_id"], result.errors)

    asyncio.run(_run())
    log.info("rollback_vpc_done job_id=%s", data["job_id"])


def task_update_failed(**context: object) -> None:
    ti: TaskInstance = context["ti"]
    data = ti.xcom_pull(task_ids="update_in_progress", key="job_data")
    if data is None:
        raw = ti.xcom_pull(task_ids="wait_for_message")
        data = json.loads(raw[0]["data"])

    _update_job_status_sync(
        job_id=data["job_id"],
        status="failed",
        error_message="VPC provisioning failed; rollback attempted.",
    )
    log.info("vpc_job_failed job_id=%s", data["job_id"])


with DAG(
    dag_id="provision_vpc_dag",
    default_args=_DEFAULT_ARGS,
    schedule_interval=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["infraops", "provisioning", "vpc"],
) as dag:
    wait_for_message = PubSubPullSensor(
        task_id="wait_for_message",
        project_id=_PROJECT_ID,
        subscription=_SUBSCRIPTION,
        max_messages=1,
        ack_messages=True,
        messages_callback=lambda messages, **kw: [
            m for m in messages
            if json.loads(m.get("data", "{}")).get("resource_type") == "vpc_network"
        ],
        poke_interval=10,
        timeout=3600,
        mode="reschedule",
    )

    update_in_progress = PythonOperator(
        task_id="update_in_progress",
        python_callable=task_update_in_progress,
    )

    dry_run_validate = PythonOperator(
        task_id="dry_run_validate",
        python_callable=task_dry_run_validate,
    )

    provision_vpc = PythonOperator(
        task_id="provision_vpc",
        python_callable=task_provision_vpc,
        retries=3,
        retry_exponential_backoff=True,
        max_retry_delay=300,
    )

    register_backstage = PythonOperator(
        task_id="register_backstage",
        python_callable=task_register_backstage,
    )

    update_succeeded = PythonOperator(
        task_id="update_succeeded",
        python_callable=task_update_succeeded,
    )

    rollback_vpc_task = PythonOperator(
        task_id="rollback_vpc",
        python_callable=task_rollback_vpc,
        trigger_rule=TriggerRule.ONE_FAILED,
    )

    update_failed = PythonOperator(
        task_id="update_failed",
        python_callable=task_update_failed,
        trigger_rule=TriggerRule.ONE_FAILED,
    )

    (
        wait_for_message
        >> update_in_progress
        >> dry_run_validate
        >> provision_vpc
        >> register_backstage
        >> update_succeeded
    )

    [provision_vpc, register_backstage] >> rollback_vpc_task >> update_failed
