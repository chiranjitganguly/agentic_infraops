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
import uuid
from datetime import datetime, timedelta, timezone

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
    import json as _json
    import os

    import psycopg2

    db_url = os.environ["DATABASE_URL"]
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE provisioning_jobs SET
                    status = %s,
                    retry_count = COALESCE(%s, retry_count),
                    gcp_resource_id = COALESCE(%s, gcp_resource_id),
                    error_message = COALESCE(%s, error_message),
                    rollback_resources = COALESCE(%s::jsonb, rollback_resources),
                    updated_at = NOW()
                WHERE id = %s::uuid
                """,
                (
                    status,
                    retry_count,
                    gcp_resource_id,
                    error_message,
                    _json.dumps(rollback_resources) if rollback_resources is not None else None,
                    job_id,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _get_compute():
    from googleapiclient import discovery
    return discovery.build("compute", "v1")


def _wait_for_zone_operation(compute, project_id: str, zone: str, operation_name: str) -> None:
    import time
    while True:
        result = compute.zoneOperations().get(project=project_id, zone=zone, operation=operation_name).execute()
        if result["status"] == "DONE":
            if "error" in result:
                raise RuntimeError(f"GCP operation failed: {result['error']}")
            return
        time.sleep(2)


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

    from contracts.agents.provisioning import VMParameters
    from skills.gcp_compute.provisioner import create_vm

    data = context["ti"].xcom_pull(task_ids="update_in_progress", key="job_data")
    if data is None:
        data = context["ti"].xcom_pull(task_ids="wait_for_message")
        data = json.loads(data[0]["data"])

    params = data.get("parameters", {})

    async def _run() -> None:
        vm_params = VMParameters(
            machine_type=params.get("machine_type", "e2-standard-4"),
            disk_size_gb=int(params.get("disk_size_gb", 50)),
            image_family=params.get("image_family", "debian-12"),
            image_project=params.get("image_project", "debian-cloud"),
            network=params.get("network", "default"),
            tags=params.get("tags", []),
        )

        # dry_run=True returns immediately without calling gcp_client or postgres_client
        result = await create_vm(
            params=vm_params,
            region=data["region"],
            resource_name=data["resource_name"],
            zone=data.get("zone") or f"{data['region']}-a",
            project_id=_PROJECT_ID,
            job_id=uuid.UUID(data["job_id"]),
            dry_run=True,
            gcp_client=None,  # type: ignore[arg-type]
            postgres_client=None,  # type: ignore[arg-type]
        )

        if not result.success:
            raise RuntimeError(f"Dry-run validation failed: {result.error_message}")

        log.info("dry_run_ok job_id=%s", data["job_id"])

    asyncio.run(_run())


def task_provision_vm(**context: object) -> None:
    import asyncio

    from contracts.agents.provisioning import VMParameters
    from skills.gcp_compute.provisioner import create_vm

    ti: TaskInstance = context["ti"]
    data = ti.xcom_pull(task_ids="update_in_progress", key="job_data")
    if data is None:
        raw = ti.xcom_pull(task_ids="wait_for_message")
        data = json.loads(raw[0]["data"])

    params = data.get("parameters", {})

    async def _run() -> str | None:
        import json as _json

        import psycopg2

        class _GcpClient:
            async def create_vm(self, **kwargs) -> dict:
                import time
                compute = _get_compute()
                project_id = kwargs["project_id"]
                zone = kwargs["zone"]
                instance_name = kwargs["instance_name"]
                machine_type = kwargs.get("machine_type", "e2-standard-4")
                disk_size_gb = kwargs.get("disk_size_gb", 50)
                image_family = kwargs.get("image_family", "debian-12")
                image_project = kwargs.get("image_project", "debian-cloud")
                network = kwargs.get("network", "default")
                tags = kwargs.get("tags") or []

                instance_body = {
                    "name": instance_name,
                    "machineType": f"zones/{zone}/machineTypes/{machine_type}",
                    "disks": [{
                        "boot": True,
                        "autoDelete": True,
                        "initializeParams": {
                            "sourceImage": f"projects/{image_project}/global/images/family/{image_family}",
                            "diskSizeGb": str(disk_size_gb),
                        },
                    }],
                    "networkInterfaces": [{"network": f"global/networks/{network}"}],
                    "tags": {"items": tags},
                }

                operation = compute.instances().insert(project=project_id, zone=zone, body=instance_body).execute()
                _wait_for_zone_operation(compute, project_id, zone, operation["name"])
                instance = compute.instances().get(project=project_id, zone=zone, instance=instance_name).execute()
                resource_id = str(instance.get("id", ""))
                log.info("create_vm_succeeded instance_name=%s resource_id=%s", instance_name, resource_id)
                return {"resource_id": resource_id, "status": "RUNNING"}

            async def delete_vm(self, **kwargs) -> dict:
                return {"status": "SKIPPED"}

        class _PgClient:
            async def update_job_status(self, job_id: uuid.UUID, rollback_resources: list) -> None:
                db_url = os.environ["DATABASE_URL"]
                conn = psycopg2.connect(db_url)
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE provisioning_jobs SET rollback_resources = %s::jsonb, updated_at = NOW() WHERE id = %s::uuid",
                            (_json.dumps(rollback_resources), str(job_id)),
                        )
                    conn.commit()
                finally:
                    conn.close()

        vm_params = VMParameters(
            machine_type=params.get("machine_type", "e2-standard-4"),
            disk_size_gb=int(params.get("disk_size_gb", 50)),
            image_family=params.get("image_family", "debian-12"),
            image_project=params.get("image_project", "debian-cloud"),
            network=params.get("network", "default"),
            tags=params.get("tags", []),
        )

        result = await create_vm(
            params=vm_params,
            region=data["region"],
            resource_name=data["resource_name"],
            zone=data.get("zone") or f"{data['region']}-a",
            project_id=_PROJECT_ID,
            job_id=uuid.UUID(data["job_id"]),
            dry_run=False,
            gcp_client=_GcpClient(),  # type: ignore[arg-type]
            postgres_client=_PgClient(),  # type: ignore[arg-type]
        )

        if not result.success:
            raise RuntimeError(result.error_message or "VM provisioning failed")

        return result.gcp_resource_id

    gcp_resource_id = asyncio.run(_run())
    ti.xcom_push(key="gcp_resource_id", value=gcp_resource_id)
    log.info("provision_vm_done job_id=%s gcp_resource_id=%s", data["job_id"], gcp_resource_id)


def task_register_backstage(**context: object) -> None:
    import httpx

    ti: TaskInstance = context["ti"]
    data = ti.xcom_pull(task_ids="update_in_progress", key="job_data")
    if data is None:
        raw = ti.xcom_pull(task_ids="wait_for_message")
        data = json.loads(raw[0]["data"])

    gcp_resource_id = ti.xcom_pull(task_ids="provision_vm", key="gcp_resource_id")

    backstage_url = os.environ.get("BACKSTAGE_API_URL", "http://backstage:7007/api")
    backstage_token = os.environ.get("BACKSTAGE_API_TOKEN", "")

    entity_body = {
        "apiVersion": "backstage.io/v1alpha1",
        "kind": "Resource",
        "metadata": {
            "name": data["resource_name"],
            "namespace": "default",
            "description": "GCP compute_instance provisioned via InfraOps platform",
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
        "spec": {
            "type": "gcp-compute-instance",
            "owner": data["requesting_user"],
            "lifecycle": "production",
        },
    }

    headers = {"Content-Type": "application/json"}
    if backstage_token:
        headers["Authorization"] = f"Bearer {backstage_token}"

    try:
        with httpx.Client(timeout=30) as client:
            response = client.post(
                f"{backstage_url}/catalog/entities",
                json=entity_body,
                headers=headers,
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("backstage_registration_failed job_id=%s error=%s", data["job_id"], exc)
        raise RuntimeError(f"Backstage registration failed: {exc}") from exc

    log.info("backstage_registered job_id=%s resource=%s", data["job_id"], data["resource_name"])


def task_update_succeeded(**context: object) -> None:
    ti: TaskInstance = context["ti"]
    data = ti.xcom_pull(task_ids="update_in_progress", key="job_data")
    if data is None:
        raw = ti.xcom_pull(task_ids="wait_for_message")
        data = json.loads(raw[0]["data"])

    gcp_resource_id = ti.xcom_pull(task_ids="provision_vm", key="gcp_resource_id")

    _update_job_status_sync(
        job_id=data["job_id"],
        status="succeeded",
        gcp_resource_id=gcp_resource_id,
    )
    log.info("job_succeeded job_id=%s", data["job_id"])


def task_rollback_vm(**context: object) -> None:
    import asyncio
    import json as _json

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
        class _GcpClient:
            async def delete_vm(self, project_id: str, zone: str, instance_name: str) -> dict:
                from googleapiclient.errors import HttpError
                compute = _get_compute()
                try:
                    operation = compute.instances().delete(project=project_id, zone=zone, instance=instance_name).execute()
                    _wait_for_zone_operation(compute, project_id, zone, operation["name"])
                    log.info("delete_vm_succeeded instance_name=%s", instance_name)
                    return {"status": "DELETED"}
                except HttpError as exc:
                    if exc.resp.status == 404:
                        log.info("delete_vm_not_found_ignored instance_name=%s", instance_name)
                        return {"status": "NOT_FOUND"}
                    raise

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
        messages_callback=lambda messages, context, **kw: [
            {"data": m.message.data.decode("utf-8")}
            for m in messages
            if json.loads(m.message.data.decode("utf-8")).get("resource_type") == "compute_instance"
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
        retry_delay=timedelta(seconds=30),
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
        trigger_rule=TriggerRule.ALL_DONE,
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
