# Agentic InfraOps Platform — Frequently Asked Questions

## General

**Q: What can I provision through this platform?**
A: You can provision Compute Engine VMs, Cloud Storage buckets, and basic VPC networks. For other resource types (Cloud SQL, GKE clusters, Pub/Sub topics), contact the platform engineering team.

**Q: How do I check the status of a resource I provisioned?**
A: Submit a status enquiry through the chat interface or via the API: `GET /api/v1/jobs/<job_id>`. You can also ask the chatbot: "What is the status of vm-123?" or "Show me the status of bucket agentic-infraops-data-ml-prod."

**Q: How long does provisioning take?**
A: VM provisioning typically completes in 2–5 minutes. Bucket provisioning is usually under 1 minute. VPC provisioning takes 1–3 minutes. The end-to-end target including workflow scheduling is under 10 minutes.

**Q: What happens if I don't confirm my provisioning request?**
A: Requests that are not confirmed within 20 minutes are automatically cancelled. No GCP resources are created. You can resubmit the request at any time.

**Q: Can I submit multiple provisioning requests at once?**
A: Yes, but each request is processed independently. The platform enforces a limit of 10 provisioning operations per developer per day. Bulk operations are not supported — each resource must be requested individually.

**Q: How do I cancel a provisioning request?**
A: If the request has not been confirmed yet, simply let the 20-minute window expire. If the request is already in progress (status: `in_progress`), contact the platform engineering team to cancel it manually.

## Errors and Failures

**Q: My provisioning job failed. What should I do?**
A: Check the job status endpoint for the error message: `GET /api/v1/jobs/<job_id>`. The error will indicate whether the failure was a validation error (fix your request parameters), a GCP API error (retry or contact platform team), or a timeout (resubmit the request).

**Q: My job shows "rolled_back". Was my resource deleted?**
A: Yes. When a provisioning job fails after a resource is partially created, the platform automatically deletes the partial resource and sets the job status to `rolled_back`. Check the error message for the root cause before resubmitting.

**Q: I got a "daily limit exceeded" error. What can I do?**
A: Developer accounts are capped at 10 provisioning operations per day. Wait until midnight UTC for the limit to reset, or contact the platform team to request a temporary limit increase.

**Q: What does "circuit breaker open" mean?**
A: The platform's circuit breaker trips when it detects repeated GCP API failures (5 consecutive failures). This protects GCP from being overwhelmed and protects you from queuing requests that will fail. The circuit resets automatically after 60 seconds. If it persists, there may be a GCP service disruption — check https://status.cloud.google.com.

## Security

**Q: Who can see the resources I provision?**
A: All provisioned resources are registered in the Backstage service catalog and visible to all platform users. The GCP project IAM bindings are managed by the platform team — contact them if you need to restrict access to a specific resource.

**Q: Can I provision resources in any GCP project?**
A: No. All resources are provisioned in the configured GCP project (`agentic-infraops`). Cross-project provisioning is not supported.

**Q: How are API keys managed?**
A: API keys expire after 90 days. You will receive an email notification 7 days before expiry. Rotate your key using the `create_user.py` script or by contacting the platform team. Compromised keys should be reported immediately to the platform team for revocation.

## Email Channel

**Q: Can I submit requests via email?**
A: Yes. Send your request to the configured infraops email address. The platform polls for new emails every 30 seconds. Write your request in plain language, e.g.: "Please create a VM named backend-prod-api-01 with 4 CPUs in us-central1."

**Q: How do I confirm a provisioning request submitted via email?**
A: Reply to the confirmation email with "confirm" or "yes" in the body. Replies must be in the same email thread as the original confirmation message. Replies from a different thread or address will not be recognised.

**Q: What types of emails does the platform ignore?**
A: Auto-replies, out-of-office messages, and emails that do not contain a recognisable infrastructure intent are silently ignored. If you believe a valid request was ignored, resubmit it or contact the platform team.
