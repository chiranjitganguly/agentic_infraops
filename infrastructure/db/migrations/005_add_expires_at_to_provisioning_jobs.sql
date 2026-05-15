-- Add expires_at to provisioning_jobs to track confirmation window expiry.
ALTER TABLE provisioning_jobs
    ADD COLUMN expires_at TIMESTAMPTZ;
