"""T044 — GCP Compute developer guardrails skill.

validate_developer_guardrails(params, region, user_role, guardrails) → GuardrailResult

Platform engineers bypass all guardrails.
Developers are checked against allowed_regions and allowed_machine_types.
VPC provisioning is always blocked for developers (regardless of guardrails config).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from contracts.agents.provisioning import VMParameters
from contracts.schemas.user_role import DeveloperGuardrails, UserRoleType


@dataclass
class GuardrailViolation:
    field: str
    provided: str
    allowed: list[str]


@dataclass
class GuardrailResult:
    passed: bool
    violations: list[GuardrailViolation] = field(default_factory=list)


def validate_developer_guardrails(
    params: VMParameters,
    region: str,
    user_role: UserRoleType,
    guardrails: DeveloperGuardrails,
) -> GuardrailResult:
    """Validate a VM provisioning request against developer guardrails.

    Platform engineers always pass. Developers are checked against the
    allowed regions and machine types defined in DeveloperGuardrails.

    Args:
        params: VM parameters extracted by the intent classifier.
        region: Target GCP region.
        user_role: The requesting user's role.
        guardrails: Guardrail configuration (allowed lists, daily limit).

    Returns:
        GuardrailResult with passed=True or a list of violations.
    """
    if user_role == UserRoleType.platform_engineer:
        return GuardrailResult(passed=True)

    violations: list[GuardrailViolation] = []

    if region not in guardrails.allowed_regions:
        violations.append(GuardrailViolation(
            field="region",
            provided=region,
            allowed=guardrails.allowed_regions,
        ))

    if params.machine_type not in guardrails.allowed_machine_types:
        violations.append(GuardrailViolation(
            field="machine_type",
            provided=params.machine_type,
            allowed=guardrails.allowed_machine_types,
        ))

    if violations:
        return GuardrailResult(passed=False, violations=violations)
    return GuardrailResult(passed=True)


def validate_vpc_guardrail(user_role: UserRoleType) -> GuardrailResult:
    """Block VPC provisioning for developer role (platform engineer only).

    Args:
        user_role: The requesting user's role.
    """
    if user_role == UserRoleType.developer:
        return GuardrailResult(
            passed=False,
            violations=[
                GuardrailViolation(
                    field="resource_type",
                    provided="vpc_network",
                    allowed=["compute_instance", "storage_bucket"],
                )
            ],
        )
    return GuardrailResult(passed=True)


def validate_provisioning_guardrails(
    resource_type: str,
    region: str,
    user_role: UserRoleType,
    guardrails: DeveloperGuardrails,
    machine_type: str | None = None,
    storage_class: str | None = None,
) -> GuardrailResult:
    """Validate any provisioning request against developer guardrails.

    Platform engineers always pass. For developers:
    - VPC provisioning is unconditionally blocked.
    - Region must be in the allowed list.
    - machine_type (compute) or storage_class (bucket) must be in the allowed list.
    """
    if user_role == UserRoleType.platform_engineer:
        return GuardrailResult(passed=True)

    if resource_type == "vpc_network":
        return GuardrailResult(
            passed=False,
            violations=[
                GuardrailViolation(
                    field="resource_type",
                    provided="vpc_network",
                    allowed=["compute_instance", "storage_bucket"],
                )
            ],
        )

    violations: list[GuardrailViolation] = []

    if region not in guardrails.allowed_regions:
        violations.append(GuardrailViolation(
            field="region",
            provided=region,
            allowed=guardrails.allowed_regions,
        ))

    if resource_type == "compute_instance" and machine_type:
        if machine_type not in guardrails.allowed_machine_types:
            violations.append(GuardrailViolation(
                field="machine_type",
                provided=machine_type,
                allowed=guardrails.allowed_machine_types,
            ))

    if resource_type == "storage_bucket" and storage_class:
        if storage_class not in guardrails.allowed_storage_classes:
            violations.append(GuardrailViolation(
                field="storage_class",
                provided=storage_class,
                allowed=guardrails.allowed_storage_classes,
            ))

    return GuardrailResult(passed=not violations, violations=violations)
