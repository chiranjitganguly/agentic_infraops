# Runbook: Backstage API Outage

**Applies to:** ADR-0005 — Backstage registration is a hard requirement  
**Severity:** P1 when active — every failed registration causes a rollback  
**Owner:** Platform Team

---

## Symptoms

- Provisioning jobs reaching `register_backstage` DAG task then failing
- Airflow showing `BackstageRegistrationError` in task logs
- Jobs transitioning to `rolled_back` state in PostgreSQL
- Prometheus alert: `BackstageRegistrationFailureRate > 0` firing

---

## Immediate Triage (< 5 minutes)

1. **Confirm Backstage is down**

   ```bash
   curl -s -o /dev/null -w "%{http_code}" http://localhost:7007/api/catalog/entities
   # Expected: 200. If 5xx or connection refused → Backstage is down.
   ```

2. **Check how many jobs were rolled back**

   ```sql
   SELECT id, resource_name, resource_type, status, updated_at
   FROM infra_requests
   WHERE status = 'rolled_back'
     AND updated_at > NOW() - INTERVAL '1 hour'
   ORDER BY updated_at DESC;
   ```

3. **Identify which GCP resources were successfully created then rolled back**

   ```sql
   SELECT ir.id, ir.resource_name, ir.resource_type,
          rr.resource_type AS rollback_type, rr.gcp_resource_id
   FROM infra_requests ir
   JOIN provisioning_jobs pj ON pj.infra_request_id = ir.id
   CROSS JOIN LATERAL jsonb_array_elements(pj.rollback_resources) AS rr(value)
   WHERE ir.status = 'rolled_back'
     AND ir.updated_at > NOW() - INTERVAL '1 hour';
   ```

---

## During Outage: Pause New Provisioning

To prevent additional rollbacks while Backstage is unavailable, pause the provisioning DAGs:

```bash
# Pause all provisioning DAGs
docker compose -f docker/docker-compose.yml exec airflow-scheduler \
  airflow dags pause provision_vm_dag

docker compose -f docker/docker-compose.yml exec airflow-scheduler \
  airflow dags pause provision_bucket_dag

docker compose -f docker/docker-compose.yml exec airflow-scheduler \
  airflow dags pause provision_vpc_dag
```

---

## After Backstage Recovery

### Step 1: Verify Backstage is healthy

```bash
curl -s http://localhost:7007/api/catalog/entities | jq 'length'
# Should return a non-zero count
```

### Step 2: Manually register rolled-back resources that were actually deleted

Rolled-back resources are already deleted from GCP (rollback succeeded). No registration needed. Skip to Step 3.

### Step 3: Manually register any resources that survived rollback failure

If rollback itself also failed (check `pj.rollback_resources` where `success = false`), the GCP resource exists but is unregistered:

```bash
# For each unregistered resource, POST to Backstage catalog:
curl -X POST http://localhost:7007/api/catalog/locations \
  -H 'Content-Type: application/json' \
  -d '{
    "type": "url",
    "target": "https://github.com/your-org/infraops-catalog/blob/main/resources/<resource-name>.yaml"
  }'
```

Or use the registration script:

```bash
python infrastructure/scripts/register_backstage.py \
  --resource-type compute_instance \
  --resource-name <name> \
  --project-id <project> \
  --zone <zone>
```

### Step 4: Resubmit affected requests

For requests that were rolled back, users must resubmit. Notify them:

```sql
-- Get affected users and their rolled-back requests
SELECT requesting_user, resource_name, resource_type, updated_at
FROM infra_requests
WHERE status = 'rolled_back'
  AND updated_at > NOW() - INTERVAL '2 hours'
ORDER BY requesting_user;
```

### Step 5: Unpause DAGs and resume normal operations

```bash
docker compose -f docker/docker-compose.yml exec airflow-scheduler \
  airflow dags unpause provision_vm_dag

docker compose -f docker/docker-compose.yml exec airflow-scheduler \
  airflow dags unpause provision_bucket_dag

docker compose -f docker/docker-compose.yml exec airflow-scheduler \
  airflow dags unpause provision_vpc_dag
```

---

## Post-Incident

1. **Create incident report** documenting:
   - Time Backstage went down
   - Number of users affected
   - Number of resources rolled back
   - Time to recovery

2. **Review ADR-0005** — if Backstage outages are frequent, consider whether registration should be async with retry rather than a hard DAG dependency.

3. **Set up Backstage health monitoring** if not already in place:
   ```yaml
   # Add to observability/prometheus/rules.yml
   - alert: BackstageDown
     expr: up{job="backstage"} == 0
     for: 1m
     severity: critical
   ```

---

## Contact

| Role | Contact |
|------|---------|
| Platform on-call | See PagerDuty rotation |
| Backstage owner | platform-team@example.com |
| GCP admin | gcp-admin@example.com |
