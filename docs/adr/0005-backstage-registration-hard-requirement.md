# ADR 0005: Backstage Registration is a Hard Requirement for Job Success

**Date**: 2026-05-10
**Status**: Accepted

## Context

After a GCP resource is successfully provisioned, the Airflow DAG registers it in the Backstage catalog. A decision was needed on what happens if the Backstage `register_entity` call fails — whether to treat it as a hard failure (triggering rollback of the provisioned GCP resource) or as a best-effort side effect (job still succeeds, operator cleans up catalog gap later).

## Decision

Backstage registration is a hard requirement. If the `backstage-mcp` `register_entity` call fails after GCP provisioning succeeds, the DAG triggers the rollback task group — deleting the successfully provisioned GCP resources — and marks the job `failed`.

The DAG task ordering is:
```
provision_gcp_resource → register_backstage → update_job_succeeded
                                ↓ (on failure)
                         rollback_gcp_resource → update_job_failed
```

## Consequences

**Benefits**:
- The Backstage catalog is always consistent with what actually exists — no orphaned catalog entries, no missing entries
- Simplifies the operational model: succeeded job = GCP resource exists + Backstage entry exists, always
- No manual reconciliation process needed

**Costs**:
- **A Backstage API outage will cause successfully provisioned GCP resources to be destroyed.** This is the primary operational risk of this decision.
- Users experience a failure (and must resubmit) even though GCP accepted their provisioning request
- Backstage is now on the critical path for provisioning — it must be included in the platform's 99.5% uptime SLA

**Required mitigations**:
- Backstage must be deployed with the same reliability target as the rest of the platform
- Circuit breaker on all `backstage-mcp` calls with open-state alerting
- Runbook must document the Backstage outage recovery procedure (including how to manually register resources for jobs that were rolled back during an outage)

**Alternative rejected**: Best-effort registration (job succeeds regardless of Backstage) — rejected because it produces catalog drift that is operationally difficult to detect and reconcile at scale.
