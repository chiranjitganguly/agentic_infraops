import pytest

from contracts.agents.provisioning import VMParameters
from contracts.schemas.user_role import DeveloperGuardrails, UserRoleType
from business_logic.gcp_compute.guardrails import validate_developer_guardrails


DEFAULT_GUARDRAILS = DeveloperGuardrails(
    allowed_regions=["us-central1", "us-east1", "europe-west1"],
    allowed_machine_types=["e2-standard-2", "e2-standard-4", "e2-standard-8"],
    allowed_storage_classes=["STANDARD", "NEARLINE"],
)


# B1: platform_engineer bypasses all guardrails

def test_platform_engineer_always_passes():
    params = VMParameters(machine_type="n2-standard-96")
    result = validate_developer_guardrails(
        params=params,
        region="asia-southeast1",
        user_role=UserRoleType.platform_engineer,
        guardrails=DEFAULT_GUARDRAILS,
    )
    assert result.passed is True
    assert result.violations == []


# B2: developer within allowed region and machine_type passes
def test_developer_within_guardrails_passes():
    params = VMParameters(machine_type="e2-standard-4")
    result = validate_developer_guardrails(
        params=params,
        region="us-central1",
        user_role=UserRoleType.developer,
        guardrails=DEFAULT_GUARDRAILS,
    )
    assert result.passed is True
    assert result.violations == []


# B3: developer + disallowed region → violation naming the field, provided value, and allowed values
def test_developer_disallowed_region_returns_violation():
    params = VMParameters(machine_type="e2-standard-4")
    result = validate_developer_guardrails(
        params=params,
        region="asia-southeast1",
        user_role=UserRoleType.developer,
        guardrails=DEFAULT_GUARDRAILS,
    )
    assert result.passed is False
    assert len(result.violations) == 1
    v = result.violations[0]
    assert v.field == "region"
    assert v.provided == "asia-southeast1"
    assert v.allowed == DEFAULT_GUARDRAILS.allowed_regions


# B4: developer + disallowed machine_type → violation naming machine_type
def test_developer_disallowed_machine_type_returns_violation():
    params = VMParameters(machine_type="n2-standard-96")
    result = validate_developer_guardrails(
        params=params,
        region="us-central1",
        user_role=UserRoleType.developer,
        guardrails=DEFAULT_GUARDRAILS,
    )
    assert result.passed is False
    assert len(result.violations) == 1
    v = result.violations[0]
    assert v.field == "machine_type"
    assert v.provided == "n2-standard-96"
    assert v.allowed == DEFAULT_GUARDRAILS.allowed_machine_types


# B5: both region and machine_type disallowed → two violations returned together
def test_developer_multiple_violations_returned_together():
    params = VMParameters(machine_type="n2-standard-96")
    result = validate_developer_guardrails(
        params=params,
        region="asia-southeast1",
        user_role=UserRoleType.developer,
        guardrails=DEFAULT_GUARDRAILS,
    )
    assert result.passed is False
    fields = {v.field for v in result.violations}
    assert fields == {"region", "machine_type"}


# B6: guardrails are configurable — a non-default allowed list is respected
def test_custom_guardrails_are_respected():
    restricted = DeveloperGuardrails(
        allowed_regions=["europe-west1"],
        allowed_machine_types=["e2-standard-2"],
        allowed_storage_classes=["STANDARD"],
    )
    # passes with the restricted set
    result_pass = validate_developer_guardrails(
        params=VMParameters(machine_type="e2-standard-2"),
        region="europe-west1",
        user_role=UserRoleType.developer,
        guardrails=restricted,
    )
    assert result_pass.passed is True

    # us-central1 is in DEFAULT_GUARDRAILS but not in the restricted set
    result_fail = validate_developer_guardrails(
        params=VMParameters(machine_type="e2-standard-2"),
        region="us-central1",
        user_role=UserRoleType.developer,
        guardrails=restricted,
    )
    assert result_fail.passed is False
    assert result_fail.violations[0].field == "region"
    assert result_fail.violations[0].allowed == ["europe-west1"]
