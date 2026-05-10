-- Migration: 002_notify_trigger
-- Creates the notify_job_status_change() trigger that drives SSE via LISTEN/NOTIFY.
-- Fires AFTER any UPDATE to provisioning_jobs.status.

CREATE OR REPLACE FUNCTION notify_job_status_change()
RETURNS TRIGGER AS $$
BEGIN
  PERFORM pg_notify(
    'infraops_job_status',
    json_build_object(
      'job_id',      NEW.id,
      'status',      NEW.status,
      'updated_at',  NEW.updated_at,
      'correlation_id', NEW.correlation_id
    )::text
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER job_status_notify
  AFTER UPDATE OF status ON provisioning_jobs
  FOR EACH ROW
  EXECUTE FUNCTION notify_job_status_change();
