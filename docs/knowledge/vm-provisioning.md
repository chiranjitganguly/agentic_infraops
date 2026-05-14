# VM Provisioning Best Practices

## Supported Machine Types

The platform supports the following Compute Engine machine types:

- `e2-standard-2` — 2 vCPUs, 8 GB RAM. Suitable for light workloads, CI runners, internal tooling.
- `e2-standard-4` — 4 vCPUs, 16 GB RAM. Suitable for most application workloads.
- `e2-standard-8` — 8 vCPUs, 32 GB RAM. Suitable for memory-intensive services or batch processing.

Request a machine type outside this list through the platform engineering team for approval.

## Supported Regions

Approved regions for VM provisioning:

- `us-central1` — Iowa, USA. Lowest latency for US-based teams.
- `us-east1` — South Carolina, USA. Use for US East Coast proximity.
- `europe-west1` — Belgium. Use for EU data residency requirements.

## Naming Conventions

VM names must follow the pattern: `<team>-<environment>-<purpose>-<sequence>`

Examples:
- `data-prod-worker-01`
- `platform-dev-bastion-01`
- `backend-staging-api-02`

Names must be lowercase, use hyphens only, and be 6–40 characters.

## Default Boot Disk

All VMs are provisioned with:
- **Image**: `debian-cloud/debian-12`
- **Boot disk size**: 50 GB SSD (`pd-ssd`)
- **Auto-delete**: enabled (disk is deleted when VM is deleted)

Request a custom image or larger disk in your provisioning request and it will be included in the confirmation summary.

## Network Configuration

By default, VMs are placed in the `default` VPC on the `default` subnet for the chosen region. To place a VM in a custom VPC or subnet, include the VPC name and subnet name in your request.

All VMs are provisioned **without a public IP** by default. If your workload requires external access, state this in the request and the provisioning agent will add an ephemeral external IP.

## Dry Run

Every provisioning request goes through a dry-run validation step before actual GCP API calls are made. The dry-run validates:
- Machine type is in the allowed list
- Region is in the allowed list
- Name follows the naming convention
- User has not exceeded the daily provisioning limit (10 resources per user per day)

If dry-run fails, the job is rejected with a clear error message and no GCP resources are created.

## Rollback

If provisioning fails after a VM is partially created, the platform automatically rolls back by deleting the VM. Rollback status is visible in the job status endpoint and the Airflow DAG.

## Confirmation Requirement

All provisioning requests require explicit confirmation within 20 minutes of submission. After submitting a request, you will receive a confirmation summary listing the resource to be created. Reply "confirm" via the same channel (chat or email) or use the confirm API endpoint.

Requests that are not confirmed within 20 minutes are automatically cancelled.

## Daily Limit

Each developer account is limited to 10 provisioning operations per day across all resource types. Platform engineers have a higher limit. Contact the platform team if you need a limit increase for a specific project.
