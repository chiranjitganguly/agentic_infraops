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
