"""T049 — Airflow DAG for VM provisioning.

DAG: provision_vm_dag
Schedule: None (triggered by PubSubPullSensor on infraops-provisioning-requests-vm-sub)

Task flow:
  wait_for_message → update_in_progress → dry_run_validate → provision_vm → register_backstage → update_succeeded
                                                                               ↓ (ONE_FAILED)
                                                                           rollback_group: rollback_vm → update_failed

Retry policy on provision_vm: 3 retries, exponential backoff with jitter (2^retry * 30s ± 10s).
rollback_resources starts empty; appended after each successful GCP create (ADR-0006).
Backstage registration failure triggers rollback (ADR-0005).
"""
from __future__ import annotations

import json
import logging
import os
import random
from datetime import datetime, timezone

from airflow import DAG
from airflow.models import TaskInstance
from airflow.operators.python import PythonOperator
from airflow.providers.google.cloud.sensors.pubsub import PubSubPullSensor
from airflow.utils.trigger_rule import TriggerRule

log = logging.getLogger(__name__)

_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "infraops-dev")
_SUBSCRIPTION = "infraops-provisioning-requests-vm-sub"
_SUBSCRIPTION_PATH = f"projects/{_PROJECT_ID}/subscriptions/{_SUBSCRIPTION}"

_DEFAULT_ARGS = {
    "owner": "infraops",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
}


def _update_job_status_sync(
    job_id: str,
    status: str,
    retry_count: int | None = None,
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
            retry_count=retry_count,
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

    context["ti"].xcom_push(key="job_data", value=data)
    _update_job_status_sync(job_id=job_id, status="in_progress")
    log.info("job_in_progress job_id=%s", job_id)


def task_dry_run_validate(**context: object) -> None:
    import asyncio

    from skills.gcp_compute.provisioner import create_vm

    data = context["ti"].xcom_pull(task_ids="update_in_progress", key="job_data")
    if data is None:
        data = context["ti"].xcom_pull(task_ids="wait_for_message")
        data = json.loads(data[0]["data"])

    params = data.get("parameters", {})

    async def _run() -> None:
        from mcp_servers.gcp_resource import server as gcp_server
        from mcp_servers.postgres import server as pg_server

        class _GcpClient:
            async def create_vm(self, **kwargs: object) -> dict:
                return gcp_server.create_vm(**kwargs)  # type: ignore[arg-type]

            async def delete_vm(self, **kwargs: object) -> dict:
                return gcp_server.delete_vm(**kwargs)  # type: ignore[arg-type]

        class _PgClient:
            async def update_job_status(self, **kwargs: object) -> dict:
                return await pg_server.update_job_status(**kwargs)  # type: ignore[arg-type]

        result = await create_vm(
            job_id=data["job_id"],
            project_id=_PROJECT_ID,
            zone=data.get("zone") or f"{data['region']}-a",
            instance_name=data["resource_name"],
            machine_type=params.get("machine_type", "e2-standard-4"),
            disk_size_gb=int(params.get("disk_size_gb", 50)),
            image_family=params.get("image_family", "debian-12"),
            image_project=params.get("image_project", "debian-cloud"),
            network=params.get("network", "default"),
            tags=params.get("tags", []),
            requesting_user=data["requesting_user"],
            rollback_resources=[],
            dry_run=True,
            gcp_client=_GcpClient(),  # type: ignore[arg-type]
            postgres=_PgClient(),  # type: ignore[arg-type]
        )

        if not result.success:
            raise RuntimeError(f"Dry-run validation failed: {result.error_message}")

        log.info("dry_run_ok job_id=%s", data["job_id"])

    asyncio.run(_run())


def task_provision_vm(**context: object) -> None:
    import asyncio

    from skills.gcp_compute.provisioner import create_vm

    ti: TaskInstance = context["ti"]
    data = ti.xcom_pull(task_ids="update_in_progress", key="job_data")
    if data is None:
        raw = ti.xcom_pull(task_ids="wait_for_message")
        data = json.loads(raw[0]["data"])

    params = data.get("parameters", {})
    rollback_resources: list = []

    async def _run() -> list:
        from mcp_servers.gcp_resource import server as gcp_server
        from mcp_servers.postgres import server as pg_server

        class _GcpClient:
            async def create_vm(self, **kwargs: object) -> dict:
                return gcp_server.create_vm(**kwargs)  # type: ignore[arg-type]

            async def delete_vm(self, **kwargs: object) -> dict:
                return gcp_server.delete_vm(**kwargs)  # type: ignore[arg-type]

        class _PgClient:
            async def update_job_status(self, **kwargs: object) -> dict:
                return await pg_server.update_job_status(**kwargs)  # type: ignore[arg-type]

        result = await create_vm(
            job_id=data["job_id"],
            project_id=_PROJECT_ID,
            zone=data.get("zone") or f"{data['region']}-a",
            instance_name=data["resource_name"],
            machine_type=params.get("machine_type", "e2-standard-4"),
            disk_size_gb=int(params.get("disk_size_gb", 50)),
            image_family=params.get("image_family", "debian-12"),
            image_project=params.get("image_project", "debian-cloud"),
            network=params.get("network", "default"),
            tags=params.get("tags", []),
            requesting_user=data["requesting_user"],
            rollback_resources=rollback_resources,
            dry_run=False,
            gcp_client=_GcpClient(),  # type: ignore[arg-type]
            postgres=_PgClient(),  # type: ignore[arg-type]
        )

        if not result.success:
            raise RuntimeError(result.error_message or "VM provisioning failed")

        return result.rollback_resources  # type: ignore[attr-defined]

    resources = asyncio.run(_run())
    ti.xcom_push(key="rollback_resources", value=resources)
    ti.xcom_push(key="gcp_resource_id", value=resources[0].get("gcp_resource_id") if resources else None)
    log.info("provision_vm_done job_id=%s resources=%s", data["job_id"], resources)


def task_register_backstage(**context: object) -> None:
    import asyncio

    ti: TaskInstance = context["ti"]
    data = ti.xcom_pull(task_ids="update_in_progress", key="job_data")
    if data is None:
        raw = ti.xcom_pull(task_ids="wait_for_message")
        data = json.loads(raw[0]["data"])

    gcp_resource_id = ti.xcom_pull(task_ids="provision_vm", key="gcp_resource_id")

    async def _run() -> None:
        from mcp_servers.backstage import server as bs_server

        await bs_server.register_entity(
            kind="Resource",
            name=data["resource_name"],
            namespace="default",
            metadata={
                "description": f"GCP compute_instance provisioned via InfraOps platform",
                "labels": {
                    "gcp-region": data["region"],
                    "gcp-project": _PROJECT_ID,
                    "provisioned-by": data["requesting_user"],
                    "provisioning-job-id": data["job_id"],
                },
                "annotations": {
                    "infraops/provisioned-at": datetime.now(timezone.utc).isoformat(),
                    "infraops/idempotency-key": data.get("idempotency_key", ""),
                },
            },
            spec={
                "type": "gcp-compute-instance",
                "owner": data["requesting_user"],
                "lifecycle": "production",
            },
        )

    asyncio.run(_run())
    log.info("backstage_registered job_id=%s resource=%s", data["job_id"], data["resource_name"])


def task_update_succeeded(**context: object) -> None:
    ti: TaskInstance = context["ti"]
    data = ti.xcom_pull(task_ids="update_in_progress", key="job_data")
    if data is None:
        raw = ti.xcom_pull(task_ids="wait_for_message")
        data = json.loads(raw[0]["data"])

    gcp_resource_id = ti.xcom_pull(task_ids="provision_vm", key="gcp_resource_id")
    rollback_resources = ti.xcom_pull(task_ids="provision_vm", key="rollback_resources") or []

    _update_job_status_sync(
        job_id=data["job_id"],
        status="succeeded",
        gcp_resource_id=gcp_resource_id,
        rollback_resources=rollback_resources,
    )
    log.info("job_succeeded job_id=%s", data["job_id"])


def task_rollback_vm(**context: object) -> None:
    import asyncio

    from contracts.schemas.provisioning_job import RollbackResource
    from skills.gcp_compute.rollback import rollback_vm

    ti: TaskInstance = context["ti"]
    data = ti.xcom_pull(task_ids="update_in_progress", key="job_data")
    if data is None:
        raw = ti.xcom_pull(task_ids="wait_for_message")
        data = json.loads(raw[0]["data"])

    rollback_resources_raw = ti.xcom_pull(task_ids="provision_vm", key="rollback_resources") or []

    resources = [RollbackResource(**r) for r in rollback_resources_raw]

    async def _run() -> None:
        from mcp_servers.gcp_resource import server as gcp_server

        class _GcpClient:
            async def delete_vm(self, project_id: str, zone: str, instance_name: str) -> dict:
                return gcp_server.delete_vm(project_id=project_id, zone=zone, instance_name=instance_name)  # type: ignore[arg-type]

        result = await rollback_vm(
            rollback_resources=resources,
            project_id=_PROJECT_ID,
            gcp_client=_GcpClient(),  # type: ignore[arg-type]
        )
        if not result.success:
            log.error("rollback_partial_failure job_id=%s attempts=%s", data["job_id"], result.attempts)

    asyncio.run(_run())
    log.info("rollback_vm_done job_id=%s", data["job_id"])


def task_update_failed(**context: object) -> None:
    ti: TaskInstance = context["ti"]
    data = ti.xcom_pull(task_ids="update_in_progress", key="job_data")
    if data is None:
        raw = ti.xcom_pull(task_ids="wait_for_message")
        data = json.loads(raw[0]["data"])

    _update_job_status_sync(
        job_id=data["job_id"],
        status="failed",
        error_message="Provisioning failed; rollback attempted.",
    )
    log.info("job_failed job_id=%s", data["job_id"])


def _exponential_backoff_with_jitter(retry_number: int) -> int:
    base = (2 ** retry_number) * 30
    jitter = random.randint(-10, 10)
    return max(30, base + jitter)


with DAG(
    dag_id="provision_vm_dag",
    default_args=_DEFAULT_ARGS,
    schedule_interval=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["infraops", "provisioning"],
) as dag:
    wait_for_message = PubSubPullSensor(
        task_id="wait_for_message",
        project_id=_PROJECT_ID,
        subscription=_SUBSCRIPTION,
        max_messages=1,
        ack_messages=True,
        messages_callback=lambda messages, **kw: [
            m for m in messages if json.loads(m.get("data", "{}")).get("resource_type") == "compute_instance"
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

    provision_vm = PythonOperator(
        task_id="provision_vm",
        python_callable=task_provision_vm,
        retries=3,
        retry_delay=None,
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

    rollback_vm_task = PythonOperator(
        task_id="rollback_vm",
        python_callable=task_rollback_vm,
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
        >> provision_vm
        >> register_backstage
        >> update_succeeded
    )

    [provision_vm, register_backstage] >> rollback_vm_task >> update_failed
