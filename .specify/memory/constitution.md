<!--
SYNC IMPACT REPORT
==================
Version change: 1.2.0 → 1.3.0

Modified principles:
  X. Approved Technology Standards → expanded with LiteLLM, Python, pytest, Docker standards
  XI. Skills-First Development Standards → expanded with evaluation and testing expectations

Added sections:
  XII. LLM Access Standards
  XIII. Python Engineering Standards
  XIV. Testing & Agent Evaluation Standards
  XV. Local Development & Containerization Standards

Removed sections:
  None

Templates reviewed:
  ✅ .specify/templates/plan-template.md
  ✅ .specify/templates/spec-template.md
  ✅ .specify/templates/tasks-template.md

Deferred TODOs:
  Define formal skill registry structure
  Define reusable skill packaging/versioning model
  Define standardized agent evaluation datasets and benchmarks
-->

# Agentic Infra Ops Constitution

## Mission

Agentic Infra Ops exists to provide a scalable, secure, observable, and extensible
self-service infrastructure operations platform for cloud environments.

Phase 1 scope includes:
- Infrastructure provisioning
- Infrastructure status enquiry
- Documentation and best-practice guidance

Phase 1 explicitly excludes:
- Incident management
- Root Cause Analysis (RCA)
- Alerting
- Autonomous remediation
- Cost optimization
- Compliance enforcement

The platform MUST prioritize:
- automation
- safety
- auditability
- modularity
- contract-first development
- operational simplicity
- reusable skill-driven architecture

---

# Core Principles

## I. Agent-First Design

All infrastructure operations MUST be orchestrated through autonomous agents rather than
manual scripts or ad-hoc human actions.

Agents are the primary execution units. Humans define intent, review escalations,
and approve high-risk actions.

### Requirements

- Every operational capability MUST be exposed through agent-invocable tools, workflows, or reusable skills
- Agents MUST follow the plan → act → verify lifecycle
- Human approval points MUST be explicitly defined
- No infrastructure change may execute outside an agent-managed workflow
- Agents MUST remain independently deployable wherever practical
- Skills MUST be preferred over embedding repeated logic directly inside agents

### Constraints

Agents MUST NOT:
- directly mutate another agent’s internal state
- bypass orchestration contracts
- implement hidden side-channel integrations
- duplicate operational logic already available as reusable skills

### Rationale

Agent-first systems improve consistency, scalability, auditability,
and operational repeatability. Reusable skills reduce duplication,
improve maintainability, and accelerate agent composition.

---

## II. Infrastructure-as-Code

All infrastructure state MUST be represented as version-controlled code.

No infrastructure resource may exist outside declarative management.

### Requirements

- All resource definitions MUST exist in source control
- Infrastructure changes MUST flow through pull requests
- Drift detection MUST run continuously
- Secrets MUST NEVER exist in repositories, prompts, or static configs
- Infrastructure workflows MUST be reproducible

### Preferred Practices

- Immutable infrastructure over in-place mutation
- Declarative provisioning over imperative scripting
- Reconciliation loops over manual correction

### Rationale

Infrastructure-as-Code is foundational to safe and repeatable agentic operations.

---

## III. Observability-First (NON-NEGOTIABLE)

Every agent decision, workflow execution, infrastructure mutation,
and system event MUST be observable and attributable.

Unobservable production operations are prohibited.

### Requirements

All components MUST emit:
- structured logs
- metrics
- distributed traces
- audit events

Every operation MUST include:
- request_id
- correlation_id
- agent_name
- workflow_name
- timestamp

### Logging Rules

- Logs MUST be centralized
- Audit logs MUST be immutable
- Sensitive values MUST be redacted
- Traceability MUST span A2A and Pub/Sub boundaries

### Rationale

Observability is mandatory for debugging, governance,
security analysis, and operational trust.

---

## IV. Safety & Guardrails (NON-NEGOTIABLE)

Agents MUST operate within explicitly defined operational boundaries.

Destructive or irreversible operations MUST require approval unless pre-authorized.

### Requirements

- Blast-radius analysis MUST exist for destructive actions
- Rollback procedures MUST exist before execution
- Dry-run capability MUST exist for infrastructure mutations
- Circuit breakers MUST protect cloud APIs
- Rate limiting MUST exist for all infrastructure actions
- Least-privilege IAM MUST be enforced

### Orchestration Rules

The orchestrator agent MUST:
- coordinate workflows
- route intents
- manage correlations

The orchestrator MUST NOT:
- contain cloud-specific provisioning logic
- directly provision infrastructure
- become a monolithic execution engine

### Rationale

Agentic systems amplify operational power and therefore require
strict safety boundaries.

---

## V. Idempotency & Resilience

All operations MUST be idempotent and resilient to retries,
replays, partial failures, and eventual consistency.

### Requirements

- Repeated execution MUST produce consistent outcomes
- Operations MUST tolerate retries safely
- Partial failures MUST converge to valid system state
- Distributed workflows MUST avoid synchronous transactional assumptions
- Pub/Sub consumers MUST support replay safety

### Preferred Practices

- Eventual consistency over distributed locking
- State reconciliation over imperative repair
- Async workflows over blocking orchestration

### Rationale

Distributed agent systems are failure-prone by nature.
Resilience and idempotency are mandatory design properties.

---

## VI. Contract-First & Event-Driven Architecture

All integrations MUST be schema-driven and event-oriented.

### Requirements

Before implementation, the following MUST exist:
- request schemas
- response schemas
- event contracts
- workflow payload definitions

### Event Standards

All events MUST:
- be immutable
- be versioned
- include timestamps
- include correlation identifiers

### Compatibility Rules

Allowed:
- additive schema evolution
- optional metadata extensions

Forbidden:
- breaking field removals
- incompatible type changes
- enum breaking changes

### Communication Model

Preferred communication hierarchy:
1. Pub/Sub asynchronous events
2. Workflow orchestration
3. Direct A2A calls (only when necessary)

### Rationale

Schema-first design prevents integration drift and enables safe scaling.

---

## VII. Agent Governance & Orchestration

All agents MUST expose explicit operational contracts.

### Every agent MUST define:
- responsibilities
- supported intents
- input schemas
- output schemas
- retry behavior
- failure behavior
- observability metadata
- reusable skills consumed
- reusable skills exposed

### Agent Isolation Rules

Agents MUST NOT:
- access another agent’s datastore directly
- share mutable runtime state
- bypass approved communication channels

### Workflow Ownership

- Apache Airflow orchestrates workflows
- Agents execute business logic
- Backstage provides discoverability and cataloging

Business logic MUST NOT live inside workflow DAGs.

### Skill Usage Standards

- Shared operational logic MUST be implemented as reusable skills
- Skills SHOULD remain domain-focused and composable
- Skills MUST expose versioned interfaces/contracts
- Skills SHOULD be independently testable
- Agents SHOULD orchestrate skills rather than embed duplicated logic

### Rationale

Strong boundaries and reusable skills prevent agent sprawl,
logic duplication, and architectural coupling.

---

## VIII. Knowledge & FAQ Standards

The FAQ/Knowledge agent MUST provide answers grounded in approved documentation sources.

### Requirements

- Semantic retrieval MUST be used over static prompt stuffing
- Knowledge sources MUST be versioned
- Source attribution SHOULD be preserved where practical
- Hallucinated operational guidance is prohibited

### Approved Knowledge Sources

- Internal operational documentation
- Google Cloud best practices
- Approved architecture standards

### Rationale

Operational guidance must remain trustworthy and explainable.

---

## IX. Cloud Provider Extensibility

Phase 1 targets Google Cloud Platform (GCP).

However:
- schemas
- workflows
- contracts
- orchestration models

SHOULD remain extensible for future multi-cloud support.

### Requirements

Cloud-provider-specific logic SHOULD be isolated behind adapters.

### Rationale

Avoiding provider lock-in improves long-term flexibility.

---

## X. Approved Technology Standards

| Capability | Standard |
|---|---|
| Programming Language | Python |
| Agent Framework | Google ADK |
| Workflow Engine | Apache Airflow |
| Service Catalog | Backstage |
| Messaging | Pub/Sub |
| Cloud Platform | GCP |
| LLM Access Layer | LiteLLM |
| Integration Protocol | MCP |
| Infrastructure Model | Infrastructure-as-Code |
| Testing Framework | pytest |
| Container Runtime | Docker |
| Preferred Ecosystem | Open Source |

Alternative technologies require architectural review approval.

---

## XI. Skills-First Development Standards

Reusable skills are a foundational architectural construct of this platform.

Skills encapsulate reusable operational capabilities that can be shared
across agents, workflows, and orchestration patterns.

### Requirements

- Skills MUST be preferred over duplicated logic
- Skills MUST remain modular and composable
- Skills MUST expose clear contracts/interfaces
- Skills SHOULD support independent lifecycle management
- Skills MUST support observability and tracing
- Skills SHOULD remain cloud-provider abstract where practical

### Preferred Skill Categories

- GCP provisioning skills
- IAM management skills
- Resource validation skills
- Approval workflow skills
- Status retrieval skills
- Documentation retrieval skills
- Policy evaluation skills

### Governance

- Skills MUST be versioned
- Breaking changes require semantic version upgrades
- Skills SHOULD be cataloged and discoverable through Backstage
- Skills MUST include automated tests
- Skills SHOULD include evaluation coverage where AI reasoning is involved

### Rationale

Skills reduce duplication, accelerate development,
improve consistency, and simplify long-term extensibility.

---

## XII. LLM Access Standards

All LLM access MUST be routed exclusively through LiteLLM.

Direct provider SDK usage inside agents or skills is prohibited unless explicitly approved.

### Requirements

- LiteLLM MUST act as the unified LLM abstraction layer
- Model configuration MUST be centralized
- Provider credentials MUST remain externalized from application logic
- Retry, fallback, timeout, and rate-limiting policies MUST be centrally managed
- Token usage and model invocation metrics MUST be observable

### Preferred Practices

- Use provider-agnostic model abstractions
- Use centralized prompt management where practical
- Implement model fallback policies for resilience

### Rationale

Centralized LLM access simplifies governance, observability,
cost management, provider portability, and operational consistency.

---

## XIII. Python Engineering Standards

Python is the official programming language of the platform.

All Python code MUST follow modern Python engineering best practices.

### Requirements

- Python type hints MUST be used
- Code MUST follow PEP8 standards
- Ruff or equivalent linting MUST be enforced
- Black or equivalent formatting MUST be enforced
- Dependency management MUST be reproducible
- Async-first patterns SHOULD be preferred where appropriate

### Project Standards

- Business logic MUST remain modular
- Shared utilities MUST be extracted into reusable packages/modules
- Circular dependencies are prohibited
- Configuration MUST be environment-driven

### Preferred Practices

- Pydantic for schema validation
- Structured logging libraries
- Typed interfaces/contracts
- Explicit exception handling

### Rationale

Strong engineering standards improve maintainability,
testability, and operational reliability.

---

## XIV. Testing & Agent Evaluation Standards

Testing and evaluation are mandatory for all components.

### Testing Requirements

- pytest is the mandatory testing framework
- Unit tests MUST exist for all critical logic
- Integration tests MUST validate agent interactions
- Contract tests MUST validate schemas and event payloads
- Workflow tests MUST validate Airflow DAG behavior

### Agent Evaluation Requirements

AI-powered agents and skills MUST include evaluation coverage.

### Evaluation Areas

- Intent classification accuracy
- Tool selection accuracy
- Response grounding quality
- Hallucination prevention
- Workflow correctness
- Safety policy adherence

### Evaluation Standards

- Evaluation datasets SHOULD be versioned
- Regression evaluations MUST run in CI/CD
- Evaluation metrics MUST be observable
- Failing evaluation thresholds MUST block promotion

### Rationale

Agent systems cannot be trusted without continuous validation,
testing, and behavioral evaluation.

---

## XV. Local Development & Containerization Standards

The entire application stack MUST be runnable locally using Docker containers.

### Requirements

- Every service MUST provide a Dockerfile
- Local orchestration MUST support docker-compose or equivalent
- Local development MUST not require cloud deployment
- Mocked or emulated infrastructure SHOULD be supported where practical
- Local environments MUST support end-to-end workflow testing

### Preferred Local Components

- Local Airflow containers
- Local Pub/Sub emulators
- Local vector databases
- Local LiteLLM gateway
- Local observability stack

### Rationale

Local reproducibility accelerates development,
testing, onboarding, and operational debugging.

---

# Security & Compliance Standards

## Credential Management

- Secrets MUST NOT exist in source code, prompts, or logs
- Runtime secret injection MUST be used
- Secret rotation MUST be supported

## Access Control

- RBAC is mandatory
- Least privilege is mandatory
- Agent permissions MUST be scoped per operation

## Network Security

- Control-plane components MUST NOT be publicly exposed
- Approved ingress/egress boundaries MUST be enforced

## Vulnerability Management

- Container scanning is mandatory
- Dependency scanning is mandatory
- Critical vulnerabilities block deployment

## Compliance Logging

Privileged operations MUST be audit logged and retained
per compliance policy.

---

# Development & Deployment Workflow

## Mandatory Workflow

All work MUST follow:

Spec → Plan → Tasks → Implement

Skipping phases requires documented justification.

## Branching Strategy

- Feature branches only
- Direct commits to main/master prohibited

## Merge Requirements

Every pull request MUST pass:
- linting
- automated tests
- schema validation
- security scanning
- constitution compliance checks
- evaluation checks

Human approval is mandatory.

## Environment Promotion

Changes affecting:
- agent behavior
- schemas
- workflows
- infrastructure

MUST be validated in staging before production.

## Rollback Readiness

Every deployment MUST include:
- rollback documentation
- tested rollback procedure

---

# Governance

This Constitution supersedes all informal conventions and undocumented practices.

## Amendment Process

1. Propose amendment via pull request
2. Document rationale and impact
3. Update Sync Impact Report
4. Update affected templates/specifications
5. Obtain architectural approval

## Versioning

- MAJOR → breaking governance changes
- MINOR → new principles or major expansions
- PATCH → clarifications and wording fixes

All pull requests MUST validate compliance with this Constitution.

---

**Version**: 1.3.0  
**Ratified**: 2026-05-10  
**Last Amended**: 2026-05-10