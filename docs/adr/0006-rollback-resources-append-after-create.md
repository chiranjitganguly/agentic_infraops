# ADR 0006: rollback_resources is Populated After Each Successful GCP Create, Not Pre-Planned

**Date**: 2026-05-10
**Status**: Accepted

## Context

The ProvisioningJob has a `rollback_resources` JSONB field used to track which GCP resources to delete if the job fails. A decision was needed on when and how this field is populated: pre-populated from dry-run output (the plan), or updated incrementally after each successful GCP create call (the actuals).

## Decision

`rollback_resources` starts empty (`[]`). The Airflow DAG appends each resource to the list immediately after its GCP `create_*` call succeeds, via `postgres-mcp` `update_job_status`. Rollback iterates the list and deletes exactly what was actually created.

The dry-run step validates parameters and confirms the operation would succeed — it does not populate `rollback_resources`.

## Consequences

**Benefits**:
- Rollback deletes exactly what exists — no 404 errors from attempting to delete resources that were never created
- The list is a faithful audit trail of what was created, not what was planned
- No divergence between dry-run plan and actual execution can cause incorrect cleanup

**Costs**:
- One extra `postgres-mcp` `update_job_status` write per successful provisioning step within the DAG
- Rollback cannot begin until at least one resource has been created (trivially acceptable — empty list means nothing to roll back)

**Alternative rejected**: Pre-populate from dry-run output and ignore 404s on rollback. Rejected because it silently masks plan/actuality divergence and produces misleading error signals during an already-failing workflow.
