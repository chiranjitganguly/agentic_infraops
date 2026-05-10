# ADR 0001: Skills as a Distinct Business Logic Layer Between Agents and MCP Servers

**Date**: 2026-05-10
**Status**: Accepted

## Context

The platform uses Google ADK agents for orchestration and MCP Servers as adapters for external systems (GCP APIs, PostgreSQL, Qdrant, PubSub). A question arose about where business logic lives: parameter validation, idempotency enforcement, dry-run logic, and rollback procedures.

Two simpler alternatives exist:
- **Collapse into agents**: agents contain all business logic and call MCP servers directly
- **Collapse into MCP servers**: MCP server tools contain both adapter logic and business rules

## Decision

Skills are a distinct, reusable Python package layer that sits between Agents and MCP Servers.

Call chain: `Agent → Skill → MCP Server → External System`

Skills own: parameter validation, idempotency checks, dry-run logic, rollback procedures.
MCP Servers own: external system calls only (thin adapters).
Agents own: routing, intent classification, confirmation flow, user interaction.

## Consequences

**Benefits**:
- Skills are independently testable without agents or MCP servers
- Multiple agents can share the same skill without duplicating logic
- MCP servers remain thin and swappable without affecting business rules
- Dry-run and rollback logic is co-located with the creation logic it mirrors

**Costs**:
- Three layers instead of two — more files, more interfaces to maintain
- Developers must know which layer to put new logic in (enforced by constitution and this ADR)
