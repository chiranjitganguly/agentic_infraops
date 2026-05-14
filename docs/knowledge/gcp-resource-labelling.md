# GCP Resource Labelling Standards

## Why Labels Matter

Labels are key-value pairs attached to GCP resources. The platform uses labels for:
- Cost attribution by team and environment
- Automated lifecycle management (e.g., delete dev resources older than 30 days)
- Audit queries ("show me all VMs owned by the data team")
- Backstage catalog registration

All resources provisioned through the platform are automatically labelled. Do not remove platform-managed labels.

## Mandatory Labels

Every provisioned resource must carry all of the following labels:

| Label Key | Description | Example Value |
|---|---|---|
| `managed-by` | Always set to `infraops-platform` | `infraops-platform` |
| `team` | Owning team slug | `data`, `backend`, `platform` |
| `environment` | Deployment environment | `prod`, `staging`, `dev` |
| `provisioned-by` | User ID that submitted the request | `dev@yourorg.com` |
| `job-id` | InfraOps job ID | `job-abc123` |

## Optional Labels

Include these in your provisioning request to improve discoverability:

| Label Key | Description | Example Value |
|---|---|---|
| `component` | Logical component name | `api-server`, `worker`, `cache` |
| `cost-center` | Finance cost centre code | `cc-1042` |
| `project` | Engineering project or initiative | `ml-pipeline-v2` |

## Label Constraints

GCP enforces the following constraints on labels:
- Maximum 64 labels per resource
- Key: 1–63 characters, lowercase letters, numbers, hyphens, underscores
- Value: 0–63 characters, lowercase letters, numbers, hyphens, underscores
- Keys and values are case-sensitive

## Changing Labels After Provisioning

Labels can be updated after provisioning without recreating the resource. Use the GCP Console, `gcloud` CLI, or submit an update request to the platform team. The `managed-by` and `job-id` labels are immutable — attempts to remove or change them will be rejected.
