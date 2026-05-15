-- Add user_role column to provisioning_jobs for auditing which role submitted the job.
ALTER TABLE provisioning_jobs
    ADD COLUMN user_role user_role_type;
