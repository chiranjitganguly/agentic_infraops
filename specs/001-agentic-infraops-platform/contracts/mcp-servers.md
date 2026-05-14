# MCP Server Contracts

**Protocol**: Anthropic MCP (stdio transport)
**Version**: 1.0.0 | **Date**: 2026-05-10

All MCP servers are Python services using the `mcp` library. Each wraps one external system and exposes its capabilities as typed tools. Agents invoke tools through the MCP protocol — no direct SDK calls to external systems are permitted in agent or skill code.

---

## 1. `gcp-resource-mcp`

Wraps GCP Compute Engine, Cloud Storage, and VPC Network APIs.

### Tools

| Tool | Description | Key Inputs | Returns |
|------|-------------|-----------|---------|
| `get_vm_status` | Get Compute Engine instance status | `project_id`, `zone`, `instance_name` | `ResourceStatus` |
| `get_bucket_status` | Get Cloud Storage bucket status | `project_id`, `bucket_name` | `ResourceStatus` |
| `get_vpc_status` | Get VPC network status | `project_id`, `network_name` | `ResourceStatus` |
| `create_vm` | Create a Compute Engine instance | `project_id`, `zone`, `instance_name`, `machine_type`, `disk_size_gb`, `image_family`, `image_project`, `network`, `tags`, `dry_run` | `{resource_id, status}` |
| `create_bucket` | Create a Cloud Storage bucket | `project_id`, `bucket_name`, `region`, `storage_class`, `uniform_bucket_level_access`, `versioning_enabled`, `labels`, `dry_run` | `{resource_id, status}` |
| `create_vpc_network` | Create a VPC network | `project_id`, `network_name`, `auto_create_subnetworks`, `dry_run` | `{resource_id, status}` |
| `create_subnetwork` | Create a subnet within a VPC | `project_id`, `region`, `subnet_name`, `network_name`, `ip_cidr_range`, `dry_run` | `{resource_id, status}` |
| `delete_vm` | Delete a Compute Engine instance (rollback) | `project_id`, `zone`, `instance_name` | `{status}` |
| `delete_bucket` | Delete a Cloud Storage bucket (rollback) | `project_id`, `bucket_name` | `{status}` |
| `delete_vpc_network` | Delete a VPC network (rollback) | `project_id`, `network_name` | `{status}` |
| `list_project_resources` | List all VMs and buckets in a project | `project_id`, `resource_type` | `[ResourceSummary]` |

### Return Type: `ResourceStatus`

Returned by `get_vm_status`, `get_bucket_status`, `get_vpc_status`.

```json
{
  "resource_type": "compute_instance | storage_bucket | vpc_network",
  "resource_name": "<string>",
  "project_id": "<string>",
  "gcp_status": "<GCP API status string, e.g. RUNNING | TERMINATED | ACTIVE>",
  "zone": "<string | null>",
  "region": "<string | null>",
  "metadata": "<typed metadata object — see Enquiry Agent contract for per-type schemas>",
  "queried_at": "<ISO 8601>"
}
```

### Return Type: `ResourceSummary`

Returned in the list from `list_project_resources`.

```json
{
  "resource_name": "<string>",
  "resource_type": "compute_instance | storage_bucket | vpc_network",
  "gcp_status": "<GCP API status string>",
  "zone_or_region": "<string | null>",
  "key_metadata": "<abbreviated single-field summary: machine_type or storage_class or routing_mode>",
  "creation_timestamp": "<ISO 8601 | null>"
}
```

### Circuit Breaker

All tools are wrapped with a circuit breaker (5 failures → open, 60s reset). Circuit state is exposed as a Prometheus gauge `gcp_resource_mcp_circuit_state{tool, resource_type}`.

---

## 2. `knowledge-base-mcp`

Wraps the Qdrant local vector database for hybrid FAQ retrieval.

### Tools

| Tool | Description | Key Inputs | Returns |
|------|-------------|-----------|---------|
| `search_documents` | Hybrid BM25 + vector search | `query`, `top_k` (default 5), `score_threshold` (default 0.5) | `[{chunk_text, source_doc, bm25_score, vector_score, final_score}]` |
| `get_document_by_id` | Retrieve a specific document chunk | `chunk_id` | `{chunk_text, source_doc, metadata}` |
| `index_document` | Add a new document to the knowledge base | `document_title`, `document_url`, `content`, `metadata` | `{chunk_ids: []}` |
| `get_collection_stats` | Return collection size and index health | — | `{num_documents, num_chunks, index_status}` |

### Embedding Model

- Dense embeddings: via LiteLLM gateway (`embedding` model alias)
- Sparse embeddings: Qdrant built-in FastEmbed BM25
- Fusion: Reciprocal Rank Fusion (RRF) with equal weight

---

## 3. `postgres-mcp`

Wraps PostgreSQL for all persistent state operations.

### Tools

| Tool | Description | Key Inputs | Returns |
|------|-------------|-----------|---------|
| `get_provisioning_job` | Fetch a job by ID | `job_id` | `ProvisioningJob` |
| `get_provisioning_job_by_idempotency_key` | Idempotency check | `idempotency_key` | `ProvisioningJob \| null` |
| `create_provisioning_job` | Insert new job row | `ProvisioningJobCreate` | `ProvisioningJob` |
| `update_job_status` | Update job status + emit NOTIFY | `job_id`, `status`, `retry_count?`, `gcp_resource_id?`, `error_message?` | `ProvisioningJob` |
| `cancel_job` | Set job status to `cancelled` | `job_id`, `requesting_user` | `ProvisioningJob` |
| `get_infra_request` | Fetch a request by ID | `infra_request_id` | `InfraRequest` |
| `create_infra_request` | Insert new request row | `InfraRequestCreate` | `InfraRequest` |
| `update_request_status` | Update request status | `infra_request_id`, `status`, `confirmed_at?` | `InfraRequest` |
| `get_user_role` | Fetch user role by user_id | `user_id` | `UserRole \| null` |
| `verify_api_key` | bcrypt verify + check expiry | `user_id`, `api_key_plaintext` | `{valid: bool, user_role: UserRole \| null}` |
| `get_daily_usage_count` | Count provisioning jobs today | `requesting_user` | `{count: int}` |
| `increment_daily_usage` | Increment and check limit | `requesting_user` | `{count: int, limit_reached: bool}` |
| `create_audit_event` | Insert audit event (append-only) | `AuditEventCreate` | `AuditEvent` |
| `create_faq_query` | Insert FAQ query record | `FAQQueryCreate` | `FAQQuery` |

---

## 4. `pubsub-mcp`

Wraps Cloud PubSub publish operations. Agents publish events — the PubSub sensor in Airflow handles consumption.

### Tools

| Tool | Description | Key Inputs | Returns |
|------|-------------|-----------|---------|
| `publish_provisioning_request` | Publish to `infraops.provisioning.requests` | `ProvisioningRequestEvent` | `{message_id: string}` |
| `publish_status_event` | Publish to `infraops.provisioning.status` | `ProvisioningStatusEvent` | `{message_id: string}` |
| `publish_audit_event` | Publish to `infraops.audit.events` | `AuditEventMessage` | `{message_id: string}` |

### Local Emulator

When `PUBSUB_EMULATOR_HOST` is set, all publish calls are routed to the local emulator automatically via the `google-cloud-pubsub` client library.

---

## 5. `airflow-mcp`

Wraps the Airflow REST API for operational queries. Note: DAGs are triggered by PubSub sensor, not by this MCP server. This server is used for status queries only.

### Tools

| Tool | Description | Key Inputs | Returns |
|------|-------------|-----------|---------|
| `get_dag_run_status` | Get status of a specific DAG run | `dag_id`, `dag_run_id` | `{state, start_date, end_date, task_instances}` |
| `list_dag_runs` | List recent runs of a DAG | `dag_id`, `limit` (default 10) | `[DagRunSummary]` |
| `get_task_instance` | Get status of a specific task | `dag_id`, `dag_run_id`, `task_id` | `TaskInstanceStatus` |

---

## 6. `backstage-mcp`

Wraps the Backstage catalog API for resource registration after successful provisioning.

### Tools

| Tool | Description | Key Inputs | Returns |
|------|-------------|-----------|---------|
| `register_entity` | Register a new catalog entity | `kind`, `name`, `namespace`, `metadata`, `spec` | `{entity_ref: string}` |
| `update_entity` | Update an existing catalog entity | `entity_ref`, `metadata_patch` | `{entity_ref: string}` |
| `get_entity` | Fetch an entity by ref | `entity_ref` | `BackstageEntity \| null` |
| `list_entities_by_owner` | List all entities owned by a user/team | `owner`, `kind?` | `[BackstageEntity]` |

### Catalog Entity Template (GCP Resource)

```yaml
apiVersion: backstage.io/v1alpha1
kind: Resource
metadata:
  name: <resource_name>
  description: "GCP <resource_type> provisioned via InfraOps platform"
  labels:
    gcp-region: <region>
    gcp-project: <project_id>
    provisioned-by: <requesting_user>
    provisioning-job-id: <job_id>
  annotations:
    infraops/provisioned-at: <ISO 8601 timestamp>
    infraops/idempotency-key: <idempotency_key>
spec:
  type: <gcp-compute-instance | gcp-storage-bucket | gcp-vpc-network>
  owner: <requesting_user>
  lifecycle: production
```

---

## 7. `gmail-mcp`

Wraps the Gmail API for inbound email processing and outbound notifications.

### Tools

| Tool | Description | Key Inputs | Returns |
|------|-------------|-----------|---------|
| `poll_unread_messages` | Get unread messages since last historyId | `history_id?` | `{messages: [GmailMessage], new_history_id: string}` |
| `get_message` | Fetch full message by ID | `message_id` | `GmailMessage` |
| `get_thread_messages` | Fetch all messages in a thread | `thread_id` | `[GmailMessage]` |
| `send_email` | Send an email (confirmation, notification) | `to`, `subject`, `body`, `thread_id?`, `in_reply_to?` | `{message_id, thread_id}` |
| `mark_as_read` | Mark a message as read | `message_id` | `{success: bool}` |
| `is_auto_reply` | Detect auto-reply headers | `message_id` | `{is_auto_reply: bool}` |

### Polling Behaviour

- Poll interval: 30 seconds
- Uses `history.list()` incremental sync after first poll
- Auto-reply detection: checks `X-Autoreply`, `Auto-Submitted`, `X-Auto-Response-Suppress` headers
- Confirmation reply detection: message must be in the same `thread_id` as a sent confirmation, and stripped body must contain "confirm", "yes", or "approve" (case-insensitive)
