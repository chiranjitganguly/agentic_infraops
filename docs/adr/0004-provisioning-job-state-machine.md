# ADR 0004: ProvisioningJob State Machine — `awaiting_confirmation` and `queued` as Distinct States

**Date**: 2026-05-10
**Status**: Accepted

## Context

The ProvisioningJob state machine initially used a single `pending` state for two different waiting conditions: (1) waiting for user confirmation, and (2) waiting for Airflow to pick up the PubSub message after confirmation. These have different semantics — different user-facing messages, different cancellability, and different timeout enforcement.

## Decision

`pending` is retired. Two distinct states replace it:

- **`awaiting_confirmation`** — job exists, confirmation summary shown to user, 20-minute timeout running, cancellable by user
- **`queued`** — user confirmed, PubSub message published, Airflow PubSubPullSensor not yet fired, no longer cancellable

Full state machine:
```
awaiting_confirmation → queued → in_progress → retrying → succeeded
                                                         → rollback → failed
awaiting_confirmation → cancelled  (user action or 20-min timeout)
queued → cancelled  (user action before Airflow picks up)
```

## Consequences

**Benefits**:
- Each state has a single unambiguous meaning and a single blocker (human vs infrastructure)
- User-facing messages are unambiguous: "Waiting for your confirmation" vs "Queued — starting soon"
- Cancellation logic is state-gated: only `awaiting_confirmation` and `queued` are cancellable
- Timeout enforcement targets `awaiting_confirmation` only — no risk of timing out a legitimately queued job

**Costs**:
- One additional enum value and state transition to test and document
- All contracts referencing job status (PostgreSQL enum, PubSub events, web API) must use the new values — `pending` must not appear in any code

**Migration note**: The old `pending` value is invalid. Any code or schema using `pending` for ProvisioningJob status is a bug.
