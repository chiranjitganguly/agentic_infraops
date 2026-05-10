# ADR 0002: One InfraRequest Maps to Exactly One Resource Operation

**Date**: 2026-05-10
**Status**: Accepted

## Context

Users can submit natural language requests that reference multiple resources in a single message (e.g. "Create a VM and a storage bucket in us-central1"). A design decision was needed on whether the platform should support compound requests in Phase 1.

## Decision

Each InfraRequest maps to exactly one resource operation. Compound requests are rejected at normalisation time with a message instructing the user to submit them as separate requests.

The `InfraRequest → ProvisioningJob` relationship is 1:0..1 (one request produces at most one job). No fan-out from a single request to multiple jobs occurs in Phase 1.

## Consequences

**Benefits**:
- State machine remains simple and linear — no partial confirmation or partial failure semantics
- Idempotency key is unambiguous (one request, one resource)
- Confirmation UX is straightforward (one summary, one confirm/reject action)
- Data model stays clean: single FK from ProvisioningJob to InfraRequest with no ambiguity

**Costs**:
- Users must submit two requests to provision related resources (e.g. a VM and its associated bucket)
- No support for dependent resource creation (VM that requires a new VPC) in a single user interaction

**Revisit trigger**: Phase 2, if user feedback shows compound requests are a significant friction point.
