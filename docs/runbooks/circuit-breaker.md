# Runbook: Open Circuit Breaker

**Applies to:** PLR-002 — All GCP API calls wrapped with circuit breaker  
**Severity:** P1 (open circuit = all provisioning to that API fails)  
**Owner:** Platform Team

---

## Background

The circuit breaker opens after **5 consecutive failures** to a GCP API tool. In the open state, calls are immediately rejected without hitting the API. The circuit transitions to half-open after a cooldown, then back to closed if a probe succeeds.

States:
- `0` = closed (normal)
- `1` = half-open (probing)
- `2` = open (all calls rejected)

Metric: `circuit_breaker_state{tool="<tool_name>"}`

Alert: `CircuitBreakerFullyOpen` (critical, after 2 minutes open)

---

## Symptoms

- Prometheus alert `CircuitBreakerFullyOpen` firing for a specific `tool` label
- Provisioning jobs failing immediately with `CircuitBreakerOpenError`
- Airflow DAG task `provision` or `task_provision_vpc` failing in < 1 second
- No GCP API calls visible in Cloud Audit Logs for affected tool

---

## Immediate Triage (< 5 minutes)

### 1. Identify which tool is open

```bash
# Via Prometheus query (if running)
curl -s 'http://localhost:9090/api/v1/query?query=circuit_breaker_state==2' \
  | jq '.data.result[].metric.tool'

# Or grep application logs
docker compose -f docker/docker-compose.yml logs provisioning-agent \
  | grep "circuit_breaker_open" | tail -20
```

### 2. Check GCP API health

The circuit opened because GCP was returning errors. Check:

```bash
# Test the GCP Compute API directly
gcloud compute instances list --project=$GCP_PROJECT_ID --limit=1

# Test GCP Storage API
gcloud storage buckets list --project=$GCP_PROJECT_ID --limit=1

# Check GCP status page
open https://status.cloud.google.com/
```

### 3. Check recent error logs

```bash
docker compose -f docker/docker-compose.yml logs --since=15m mcp-gcp-resource \
  | grep -E "ERROR|CRITICAL|circuit_breaker"
```

### 4. Check PostgreSQL for failed jobs

```sql
SELECT resource_type, error_message, COUNT(*) as failures
FROM provisioning_jobs
WHERE status = 'failed'
  AND updated_at > NOW() - INTERVAL '30 minutes'
GROUP BY resource_type, error_message
ORDER BY failures DESC;
```

---

## Resolution

### If GCP API is down (transient outage)

Wait for GCP to recover. The circuit will probe automatically after the cooldown period (default: 60 seconds after entering open state).

Monitor recovery:
```bash
# Watch circuit state
watch -n 5 'curl -s "http://localhost:9090/api/v1/query?query=circuit_breaker_state" | jq .data.result'
```

### If GCP API is healthy but circuit is stuck open

The circuit auto-recovers via half-open probe. To force an immediate probe/reset:

```bash
# Restart the MCP server (forces circuit reset to closed state)
docker compose -f docker/docker-compose.yml restart mcp-gcp-resource
```

Verify reset:
```bash
curl -s 'http://localhost:9090/api/v1/query?query=circuit_breaker_state' \
  | jq '.data.result[] | select(.metric.tool=="<tool_name>")'
# Should show value "0" (closed)
```

### If GCP credentials have expired

```bash
# Check service account key validity
cat $GCP_SA_KEY_PATH | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('type'), d.get('client_email'))"

# Rotate credentials via GCP Console or:
gcloud iam service-accounts keys create new-key.json \
  --iam-account=<sa-email>@<project>.iam.gserviceaccount.com

# Update .env and restart
echo "GCP_SA_KEY_PATH=/path/to/new-key.json" >> .env
docker compose -f docker/docker-compose.yml restart mcp-gcp-resource provisioning-agent
```

---

## Manual Circuit Reset (Emergency Only)

If automated recovery is not happening and the GCP API is confirmed healthy:

```python
# Run in a Python shell inside the mcp-gcp-resource container
docker compose -f docker/docker-compose.yml exec mcp-gcp-resource python3 -c "
from mcp_servers.gcp_resource.server import _circuit_breaker
_circuit_breaker.reset()
print('Circuit breaker reset to CLOSED')
"
```

---

## After Recovery

1. **Verify provisioning works end-to-end**:

   ```bash
   # Submit a test VM request
   curl -X POST http://localhost:8000/api/v1/requests \
     -H 'Content-Type: application/json' \
     -H 'Authorization: Bearer <dev-token>' \
     -d '{"raw_input": "Create a VM named cb-test-01 in us-central1", "channel": "web"}'
   ```

2. **Check that queued jobs are retried**: Jobs that failed during the open window are in `failed` state. Users must resubmit, or an operator can re-trigger:

   ```sql
   -- Find jobs that failed with circuit breaker error
   SELECT id, infra_request_id, error_message
   FROM provisioning_jobs
   WHERE status = 'failed'
     AND error_message LIKE '%CircuitBreaker%'
     AND updated_at > NOW() - INTERVAL '1 hour';
   ```

3. **File incident report** with:
   - Root cause (GCP API issue, credential expiry, quota exhaustion)
   - Duration of open state
   - Number of requests affected
   - Resolution steps taken

---

## Escalation

| Condition | Action |
|-----------|--------|
| GCP API down > 30 min | Escalate to GCP Support |
| Credentials expired | Rotate via GCP Console, escalate to GCP admin |
| Circuit opens repeatedly | File P2 ticket for threshold tuning investigation |
| Unknown cause | Page platform on-call |

---

## Tuning Circuit Breaker Thresholds

Default settings (set via environment variables):

| Variable | Default | Description |
|----------|---------|-------------|
| `CB_FAILURE_THRESHOLD` | `5` | Consecutive failures before opening |
| `CB_RECOVERY_TIMEOUT` | `60` | Seconds before half-open probe |
| `CB_SUCCESS_THRESHOLD` | `1` | Probe successes before closing |

To tune:
```bash
# In .env
CB_FAILURE_THRESHOLD=3
CB_RECOVERY_TIMEOUT=30

# Restart affected services
docker compose -f docker/docker-compose.yml restart mcp-gcp-resource
```
