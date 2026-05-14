# Storage Bucket Provisioning Best Practices

## Supported Storage Classes

- `STANDARD` — Low latency, frequently accessed data. Suitable for active datasets, application assets, and logs.
- `NEARLINE` — Data accessed less than once a month. Suitable for backups and archival with occasional reads.

For `COLDLINE` or `ARCHIVE` storage, contact the platform engineering team.

## Supported Regions

Buckets can be provisioned in any approved region:

- `us-central1`
- `us-east1`
- `europe-west1`

Multi-region or dual-region buckets are not supported through self-service. Submit a request to the platform team.

## Naming Conventions

Bucket names must be globally unique across all GCP projects. The platform enforces the pattern:

`<gcp-project-id>-<team>-<purpose>-<environment>`

Examples:
- `agentic-infraops-data-ml-prod`
- `agentic-infraops-backend-assets-staging`

Names must be 3–63 characters, lowercase, and use only hyphens (no dots or underscores).

## Default Configuration

All buckets are provisioned with:
- **Versioning**: disabled by default. Request versioning in your provisioning request if required.
- **Uniform bucket-level access**: enabled. Object ACLs are not supported.
- **Public access**: blocked. No bucket or object is ever publicly readable by default.
- **Lifecycle rules**: none by default. Request a lifecycle rule (e.g., delete objects older than 90 days) in your provisioning request.

## Encryption

All buckets use Google-managed encryption keys (GMEK) by default. Customer-managed encryption keys (CMEK) require a separate approval process through the security team.

## Data Residency

To comply with data residency requirements, always specify the region explicitly. The platform will not infer a region from team location. Choosing `europe-west1` is required for any data subject to EU data protection regulations.

## Rollback

If bucket provisioning fails after the bucket is created (e.g., IAM binding fails), the platform rolls back by deleting the bucket. Any objects uploaded between creation and rollback will be permanently deleted. Do not upload objects to a bucket until the job status shows `completed`.

## Dry Run

The dry-run step validates:
- Storage class is in the allowed list
- Region is in the allowed list
- Name follows the naming convention and is not already taken in your GCP project
- User has not exceeded the daily provisioning limit
