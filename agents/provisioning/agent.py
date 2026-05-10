import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Protocol
from uuid import UUID


@dataclass
class ProvisioningInput:
    correlation_id: UUID
    request_id: UUID
    infra_request_id: UUID
    resource_type: str
    resource_name: str
    region: str
    zone: str | None
    parameters: dict
    requesting_user: str
    user_role: str
    confirmed: bool


@dataclass
class ProvisioningPreConfirmOutput:
    correlation_id: UUID
    request_id: UUID
    job_id: UUID
    status: str
    confirmation_summary: str
    idempotency_key: str
    existing_job: dict | None
    expires_at: datetime


@dataclass
class ProvisioningPostConfirmOutput:
    correlation_id: UUID
    request_id: UUID
    job_id: UUID
    status: str
    message: str


class PostgresClient(Protocol):
    async def get_provisioning_job_by_idempotency_key(self, idempotency_key: str) -> dict | None: ...
    async def create_provisioning_job(self, **kwargs) -> dict: ...
    async def update_job_status(self, job_id: UUID, status: str) -> dict: ...
    async def update_request_status(self, infra_request_id: UUID, status: str, confirmed_at: datetime | None) -> dict: ...
    async def create_audit_event(self, **kwargs) -> dict: ...


class PubSubClient(Protocol):
    async def publish_provisioning_request(self, **kwargs) -> None: ...


def _make_idempotency_key(resource_type: str, resource_name: str, region: str) -> str:
    raw = f"{resource_type}:{resource_name}:{region}"
    return hashlib.sha256(raw.encode()).hexdigest()


async def handle_task(
    input: ProvisioningInput,
    postgres: PostgresClient,
    pubsub: PubSubClient,
) -> ProvisioningPreConfirmOutput | ProvisioningPostConfirmOutput:
    idempotency_key = _make_idempotency_key(
        input.resource_type, input.resource_name, input.region
    )

    if not input.confirmed:
        existing = await postgres.get_provisioning_job_by_idempotency_key(
            idempotency_key=idempotency_key
        )
        if existing:
            return ProvisioningPreConfirmOutput(
                correlation_id=input.correlation_id,
                request_id=input.request_id,
                job_id=UUID(existing["id"]),
                status="awaiting_confirmation",
                confirmation_summary=existing.get("confirmation_summary", ""),
                idempotency_key=idempotency_key,
                existing_job=existing,
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=20),
            )

        expires_at = datetime.now(timezone.utc) + timedelta(minutes=20)
        job = await postgres.create_provisioning_job(
            correlation_id=input.correlation_id,
            infra_request_id=input.infra_request_id,
            resource_type=input.resource_type,
            resource_name=input.resource_name,
            region=input.region,
            zone=input.zone,
            parameters=input.parameters,
            requesting_user=input.requesting_user,
            user_role=input.user_role,
            idempotency_key=idempotency_key,
            status="awaiting_confirmation",
        )

        summary = (
            f"Create {input.resource_type} '{input.resource_name}' "
            f"in {input.region}. Parameters: {input.parameters}. "
            f"Expires at {expires_at.isoformat()}."
        )

        return ProvisioningPreConfirmOutput(
            correlation_id=input.correlation_id,
            request_id=input.request_id,
            job_id=UUID(job["id"]),
            status="awaiting_confirmation",
            confirmation_summary=summary,
            idempotency_key=idempotency_key,
            existing_job=None,
            expires_at=expires_at,
        )

    # confirmed=True: look up the job, transition states, publish, audit
    existing = await postgres.get_provisioning_job_by_idempotency_key(
        idempotency_key=idempotency_key
    )
    job_id = UUID(existing["id"])
    confirmed_at = datetime.now(timezone.utc)

    await postgres.update_request_status(
        infra_request_id=input.infra_request_id,
        status="confirmed",
        confirmed_at=confirmed_at,
    )

    await postgres.update_job_status(
        job_id=job_id,
        status="queued",
    )

    await pubsub.publish_provisioning_request(
        job_id=job_id,
        correlation_id=input.correlation_id,
        request_id=input.request_id,
        resource_type=input.resource_type,
        resource_name=input.resource_name,
        region=input.region,
        zone=input.zone,
        parameters=input.parameters,
        requesting_user=input.requesting_user,
    )

    await postgres.create_audit_event(
        event_type="request_confirmed",
        actor=input.requesting_user,
        agent_name="provisioning-agent",
        resource_type=input.resource_type,
        resource_name=input.resource_name,
        correlation_id=input.correlation_id,
        request_id=input.request_id,
    )

    return ProvisioningPostConfirmOutput(
        correlation_id=input.correlation_id,
        request_id=input.request_id,
        job_id=job_id,
        status="queued",
        message=f"Provisioning job queued. Track progress at /api/v1/jobs/{job_id}/stream",
    )
