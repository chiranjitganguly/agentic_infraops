# Feature Specification: Agentic InfraOps Self-Service Platform (Phase 1)

**Feature Branch**: `001-agentic-infraops-platform`  
**Created**: 2026-05-10  
**Status**: Draft  
**Input**: Agentic InfraOps Self-Service Platform (Phase 1)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Self-Service VM Provisioning (Priority: P1)

A developer or platform engineer sends a natural language request — via chatbot or email — to provision a Compute Engine VM. The system interprets the request, fills in any missing defaults, confirms the intent, executes the provisioning workflow, and notifies the user when the VM is ready.

**Why this priority**: VM provisioning is the highest-value, most-requested infrastructure operation. Automating it reduces toil for platform engineers and unblocks developers waiting on infra.

**Independent Test**: Can be fully tested by submitting "Create a VM with 4 CPUs in us-central1" through the chatbot, verifying a VM is provisioned in GCP, and receiving a completion notification — end-to-end without any other flow being active.

**Acceptance Scenarios**:

1. **Given** a developer is authenticated and submits "Create a VM with 4 CPUs in us-central1" via chatbot, **When** the system processes the request, **Then** a VM is provisioned with the specified configuration and the user receives a success notification with the VM name and status.
2. **Given** a request is submitted with missing optional parameters (e.g., no machine type specified), **When** the system normalises the request, **Then** it applies documented defaults and notifies the user of the values used.
3. **Given** a provisioning request is submitted with invalid or conflicting parameters, **When** the system validates the request, **Then** it returns a clear error message indicating what is invalid and how to correct it — without creating any resources.
4. **Given** a provisioning workflow is triggered, **When** the underlying execution fails partway through, **Then** the system retries according to its retry policy and notifies the user of the outcome (success or persistent failure).

---

### User Story 2 - Self-Service Storage Bucket Provisioning (Priority: P1)

A developer or platform engineer requests creation of a Cloud Storage bucket through the self-service interface. The system classifies the intent, collects necessary parameters, provisions the bucket, and confirms completion.

**Why this priority**: Storage provisioning is equally foundational to VM provisioning as part of Phase 1 scope and shares the same provisioning pipeline.

**Independent Test**: Can be fully tested by submitting "Create a storage bucket named my-data-bucket in us-east1" and verifying bucket creation in GCP with a success notification.

**Acceptance Scenarios**:

1. **Given** a platform engineer requests a new storage bucket, **When** the system processes the request, **Then** the bucket is created with the specified name and region and the user receives confirmation.
2. **Given** a bucket name that already exists is requested, **When** the system attempts provisioning, **Then** it detects the conflict and returns an informative error without modifying the existing bucket.
3. **Given** a bucket provisioning request is submitted without a region, **When** the system normalises the request, **Then** it applies the default region and informs the user.

---

### User Story 3 - Infrastructure Status Enquiry (Priority: P2)

A user asks about the current state of an existing infrastructure resource (VM or storage bucket) via chatbot or email. The system retrieves live status from GCP and returns a clear, human-readable response.

**Why this priority**: Status enquiry provides immediate operational visibility without requiring direct GCP console access, reducing friction for developers and shortening feedback loops.

**Independent Test**: Can be fully tested by submitting "What is the status of vm-123?" and verifying the response reflects the live GCP resource state.

**Acceptance Scenarios**:

1. **Given** a user asks "What is the status of vm-123?" via chatbot, **When** the system processes the enquiry, **Then** it returns the VM's current state (e.g., running, stopped, terminated) and key metadata (zone, machine type).
2. **Given** a user asks for the status of a resource that does not exist, **When** the system queries GCP, **Then** it returns a clear "resource not found" message rather than an error.
3. **Given** a user asks for the status of a resource they are not authorised to view, **When** the system processes the request, **Then** it returns an access-denied message without exposing resource details.

---

### User Story 4 - Best-Practice FAQ Responses (Priority: P3)

A user asks a best-practice or guidance question (e.g., "What is the best practice for VPC design?") via the chatbot or email. The system retrieves relevant documentation and generates a concise, accurate answer.

**Why this priority**: FAQ capabilities reduce repeat questions to platform engineering teams and help developers self-serve knowledge, but they do not block core provisioning workflows.

**Independent Test**: Can be fully tested by asking "What is the best practice for VPC design?" and verifying a relevant, documentation-grounded answer is returned.

**Acceptance Scenarios**:

1. **Given** a user asks a best-practice question in natural language, **When** the system processes the request, **Then** it returns a concise answer grounded in the organisation's documentation with source references.
2. **Given** a question that has no matching documentation, **When** the system searches the knowledge base, **Then** it informs the user that no specific guidance was found and suggests where to look.
3. **Given** a question that partially matches multiple documents, **When** the system retrieves content, **Then** it synthesises a response from the most relevant sources and cites them.

---

### Edge Cases

- What happens when a user submits an ambiguous request that could be interpreted as either a provisioning action or a status enquiry?
- What happens when an inbound email cannot be parsed into a recognisable intent (e.g., out-of-office replies, forwarded threads, malformed bodies)?
- How does the system handle a duplicate provisioning request for an already-existing resource (idempotency)?
- What happens when GCP APIs are temporarily unavailable during a status enquiry or provisioning attempt?
- How does the system respond when a user sends a message that does not match any recognised intent (provision, enquiry, faq)?
- What happens if a provisioning workflow partially succeeds (some resources created, others not)?
- How are concurrent provisioning requests from the same user handled?
- What happens when a developer attempts to provision a resource after hitting their daily limit?
- What happens when a developer submits a provisioning request that violates their guardrail (e.g., unsupported region or machine type)?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST accept natural language requests from authenticated users via chatbot interface.
- **FR-002**: The system MUST accept freeform natural language requests submitted via email — it MUST parse the email body (subject and body text) to extract intent and parameters, applying the same normalisation pipeline used for chatbot requests.
- **FR-003**: The system MUST classify each incoming request into one of three intents: provision, enquiry, or faq.
- **FR-004**: The system MUST normalise unstructured natural language requests into structured parameters before execution.
- **FR-005**: The system MUST apply documented default values for any unspecified provisioning parameters and communicate those defaults to the user.
- **FR-006**: The system MUST provision Compute Engine VMs on GCP based on structured provisioning requests.
- **FR-007**: The system MUST provision Cloud Storage buckets on GCP based on structured provisioning requests.
- **FR-008**: The system MUST support basic VPC configuration as part of provisioning workflows.
- **FR-009**: The system MUST execute provisioning workflows idempotently — submitting the same request twice MUST NOT create duplicate resources.
- **FR-010**: The system MUST retry failed provisioning steps according to a defined retry policy before reporting failure.
- **FR-011**: The system MUST query live GCP resource status in response to infrastructure enquiry requests.
- **FR-012**: The system MUST return resource status in human-readable format, not raw API responses.
- **FR-013**: The system MUST retrieve answers to best-practice questions from a curated knowledge base of infrastructure documentation.
- **FR-014**: The system MUST cite sources when returning FAQ answers.
- **FR-015**: The system MUST publish status events (provisioning pending, in_progress, retrying, succeeded, failed, cancelled) to notify users of workflow outcomes.
- **FR-016**: The system MUST enforce authentication for all user-facing interactions.
- **FR-017**: The system MUST enforce role-based access control with the following permission boundary: developers MAY provision resources only within pre-approved guardrails (fixed allowed regions, predefined machine types and bucket sizes); platform engineers MAY provision any resource configuration and perform VPC setup without guardrail restrictions.
- **FR-017a**: The system MUST reject a developer's provisioning request that falls outside the allowed guardrails and return a clear message stating which parameter violated the policy.
- **FR-018**: The system MUST maintain an audit log of all actions taken, including who requested what and when.
- **FR-019**: The system MUST return a clear, actionable error message for any request it cannot fulfil.
- **FR-020**: The system MUST allow new agent types and workflow definitions to be added without modifying existing agent code.
- **FR-021**: The system MUST enforce per-user daily provisioning limits: developers are limited to a maximum of 10 provisioned resources per day; platform engineers have no daily limit. When a developer's limit is reached, the system MUST reject further provisioning requests for that day with a clear explanation and the time at which the limit resets.

### Key Entities

- **InfraRequest**: A normalised, structured representation of a user's natural language request — includes intent, resource type, parameters, requesting user, and timestamp.
- **ProvisioningJob**: A tracked unit of work that represents a single provisioning operation — includes status, retry count, GCP resource ID, and outcome event. Valid lifecycle states: `pending → in_progress → retrying → succeeded / failed / cancelled`. A job may transition from `in_progress` to `retrying` on transient failure; it reaches `failed` only after exhausting the retry policy. A job may be `cancelled` by an authorised user before it reaches `in_progress`.
- **ResourceStatus**: A snapshot of a GCP resource's current state — includes resource type, name, zone/region, status, and key metadata.
- **FAQQuery**: A user question submitted for knowledge retrieval — includes the raw question, matched document references, and generated answer.
- **AuditEvent**: An immutable record of a system action — includes actor, action type, resource affected, intent, and timestamp.
- **UserRole**: The access level assigned to an authenticated user. Two roles exist in Phase 1: `developer` (provisioning within guardrails — fixed regions, predefined machine types and bucket sizes; enquiry and FAQ unrestricted) and `platform_engineer` (unrestricted provisioning including VPC setup; enquiry and FAQ unrestricted).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can submit a provisioning request and receive a fully operational resource within 10 minutes for standard configurations.
- **SC-002**: At least 90% of valid natural language requests are correctly classified into the right intent (provision, enquiry, faq) without human intervention.
- **SC-003**: Users receive a response to an infrastructure status enquiry within 30 seconds of submitting the request.
- **SC-004**: Users receive a relevant, documentation-grounded FAQ answer within 60 seconds of asking a best-practice question.
- **SC-005**: Duplicate provisioning requests for the same resource are handled safely — no duplicate resources are created in 100% of cases.
- **SC-006**: Platform engineers spend at least 50% less time manually handling routine VM and bucket provisioning requests compared to the pre-platform baseline.
- **SC-007**: All provisioning operations are traceable end-to-end in the audit log with zero gaps for authorised actions.
- **SC-008**: The system correctly refuses unauthorised actions in 100% of tested cases.
- **SC-009**: The platform supports at least 50 concurrent self-service requests without degradation.
- **SC-010**: The platform achieves 99.5% monthly uptime (no more than 3.6 hours of unplanned downtime per month).

## Assumptions

- Users accessing the chatbot are pre-authenticated via the organisation's existing identity provider; the platform enforces authorisation but does not manage identity issuance.
- Email is used as both an input channel and a notification channel. For input, users send freeform natural language emails; the system parses the subject and body to extract intent and parameters using the same normalisation pipeline as the chatbot. For notification, the system sends status updates to the requesting user's email address.
- Platform engineers have broader provisioning permissions than developers; the exact permission matrix will be defined during planning.
- Default values for provisioning parameters (e.g., default region, machine type, storage class) will be defined and documented during implementation, not in this spec.
- The knowledge base for FAQ responses is pre-populated with existing GCP infrastructure documentation; curation and update processes are out of scope for Phase 1.
- VPC setup in scope is limited to basic configurations (e.g., creating a VPC network and subnet); advanced networking (firewall rules, VPN, shared VPC) is deferred.
- The system is not responsible for deprovisioning or modifying existing resources in Phase 1 — only creation and status enquiry are in scope.
- Cost approval or budget guardrails for provisioning requests are out of scope for Phase 1.

## Clarifications

### Session 2026-05-10

- Q: What are the valid lifecycle states and transitions for a ProvisioningJob? → A: Extended state machine: `pending → in_progress → retrying → succeeded / failed / cancelled`
- Q: What is the system availability target? → A: 99.5% monthly uptime (~3.6 hrs downtime/month)
- Q: What is the permission boundary between developer and platform engineer roles? → A: Developers provision within guardrails (fixed regions, predefined sizes); platform engineers have unrestricted provisioning including VPC setup.
- Q: How does the email input channel work — freeform or structured template? → A: Freeform email body; system parses subject and body using the same NLP normalisation pipeline as the chatbot.
- Q: Should provisioning requests be rate-limited per user? → A: Yes — developers capped at 10 provisioned resources per day; platform engineers unlimited. Requests beyond the cap are rejected with a clear message and reset time.
