-- Migration: 001_initial_schema
-- Creates all enums, tables, indexes, and updated_at trigger.
-- Domain: channel_type uses 'web' (not 'chatbot')
-- Domain: job_status uses 'awaiting_confirmation' + 'queued' (not 'pending')

-- ─── Trigger function ─────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION trigger_set_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ─── Enums ────────────────────────────────────────────────────────────────────
CREATE TYPE channel_type AS ENUM ('web', 'email');

CREATE TYPE intent_type AS ENUM ('provision', 'enquiry', 'faq');

CREATE TYPE request_status AS ENUM (
  'received',
  'classifying',
  'clarifying',
  'awaiting_confirmation',
  'confirmed',
  'rejected',
  'expired',
  'fulfilled',
  'failed'
);

CREATE TYPE job_status AS ENUM (
  'awaiting_confirmation',
  'queued',
  'in_progress',
  'retrying',
  'rollback',
  'succeeded',
  'failed',
  'cancelled'
);

CREATE TYPE resource_type_enum AS ENUM (
  'compute_instance',
  'storage_bucket',
  'vpc_network'
);

CREATE TYPE user_role_type AS ENUM ('developer', 'platform_engineer');

-- ─── user_roles ───────────────────────────────────────────────────────────────
CREATE TABLE user_roles (
  user_id                   TEXT          PRIMARY KEY,
  role                      user_role_type NOT NULL,
  api_key_hash              TEXT          NOT NULL,
  api_key_expires_at        TIMESTAMPTZ   NOT NULL,
  api_key_last_used         TIMESTAMPTZ,
  daily_provisioning_count  INTEGER       NOT NULL DEFAULT 0,
  daily_count_reset_at      TIMESTAMPTZ   NOT NULL,
  created_at                TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  updated_at                TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE TRIGGER set_updated_at_user_roles
  BEFORE UPDATE ON user_roles
  FOR EACH ROW EXECUTE FUNCTION trigger_set_timestamp();

-- ─── infra_requests ───────────────────────────────────────────────────────────
CREATE TABLE infra_requests (
  id                  UUID          PRIMARY KEY DEFAULT gen_random_uuid(),
  correlation_id      UUID          NOT NULL,
  raw_input           TEXT          NOT NULL,
  channel             channel_type  NOT NULL,
  intent              intent_type,
  confidence          FLOAT         CHECK (confidence >= 0.0 AND confidence <= 1.0),
  normalized_params   JSONB         NOT NULL DEFAULT '{}',
  requesting_user     TEXT          NOT NULL,
  user_role           user_role_type NOT NULL,
  status              request_status NOT NULL DEFAULT 'received',
  confirmation_summary TEXT,
  created_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  confirmed_at        TIMESTAMPTZ,
  expires_at          TIMESTAMPTZ   NOT NULL,
  email_thread_id     TEXT,
  email_message_id    TEXT,
  updated_at          TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
  CONSTRAINT email_fields_required CHECK (
    channel != 'email' OR (email_thread_id IS NOT NULL AND email_message_id IS NOT NULL)
  ),
  CONSTRAINT expires_at_valid CHECK (
    expires_at = created_at + INTERVAL '20 minutes'
  )
);

CREATE INDEX idx_infra_requests_correlation_id ON infra_requests (correlation_id);
CREATE INDEX idx_infra_requests_requesting_user ON infra_requests (requesting_user);
CREATE INDEX idx_infra_requests_status ON infra_requests (status, created_at);

CREATE TRIGGER set_updated_at_infra_requests
  BEFORE UPDATE ON infra_requests
  FOR EACH ROW EXECUTE FUNCTION trigger_set_timestamp();

-- ─── provisioning_jobs ────────────────────────────────────────────────────────
CREATE TABLE provisioning_jobs (
  id                  UUID              PRIMARY KEY DEFAULT gen_random_uuid(),
  infra_request_id    UUID              NOT NULL REFERENCES infra_requests(id),
  correlation_id      UUID              NOT NULL,
  idempotency_key     TEXT              NOT NULL UNIQUE,
  resource_type       resource_type_enum NOT NULL,
  resource_name       TEXT              NOT NULL,
  region              TEXT              NOT NULL,
  zone                TEXT,
  parameters          JSONB             NOT NULL DEFAULT '{}',
  status              job_status        NOT NULL DEFAULT 'awaiting_confirmation',
  retry_count         INTEGER           NOT NULL DEFAULT 0 CHECK (retry_count >= 0 AND retry_count <= 3),
  gcp_resource_id     TEXT,
  rollback_resources  JSONB             NOT NULL DEFAULT '[]',
  error_message       TEXT,
  requesting_user     TEXT              NOT NULL,
  dry_run             BOOLEAN           NOT NULL DEFAULT FALSE,
  created_at          TIMESTAMPTZ       NOT NULL DEFAULT NOW(),
  updated_at          TIMESTAMPTZ       NOT NULL DEFAULT NOW(),
  completed_at        TIMESTAMPTZ
);

CREATE UNIQUE INDEX idx_provisioning_jobs_idempotency_key ON provisioning_jobs (idempotency_key);
CREATE INDEX idx_provisioning_jobs_requesting_user ON provisioning_jobs (requesting_user, created_at DESC);
CREATE INDEX idx_provisioning_jobs_status ON provisioning_jobs (status, created_at);
CREATE INDEX idx_provisioning_jobs_correlation_id ON provisioning_jobs (correlation_id);

CREATE TRIGGER set_updated_at_provisioning_jobs
  BEFORE UPDATE ON provisioning_jobs
  FOR EACH ROW EXECUTE FUNCTION trigger_set_timestamp();

-- ─── faq_queries ─────────────────────────────────────────────────────────────
CREATE TABLE faq_queries (
  id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  correlation_id      UUID        NOT NULL,
  raw_question        TEXT        NOT NULL,
  requesting_user     TEXT        NOT NULL,
  retrieved_chunks    JSONB       NOT NULL DEFAULT '[]',
  generated_answer    TEXT        NOT NULL DEFAULT '',
  sources_cited       JSONB       NOT NULL DEFAULT '[]',
  answer_confidence   FLOAT       CHECK (answer_confidence >= 0.0 AND answer_confidence <= 1.0),
  no_results_found    BOOLEAN     NOT NULL DEFAULT FALSE,
  created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_faq_queries_correlation_id ON faq_queries (correlation_id);
CREATE INDEX idx_faq_queries_requesting_user ON faq_queries (requesting_user);

-- ─── audit_events ─────────────────────────────────────────────────────────────
CREATE TABLE audit_events (
  id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type      TEXT        NOT NULL,
  actor           TEXT        NOT NULL,
  agent_name      TEXT        NOT NULL,
  workflow_name   TEXT,
  resource_type   TEXT,
  resource_name   TEXT,
  intent          TEXT,
  payload         JSONB       NOT NULL DEFAULT '{}',
  timestamp       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  correlation_id  UUID        NOT NULL,
  request_id      UUID        NOT NULL
);

CREATE INDEX idx_audit_events_correlation_id ON audit_events (correlation_id);
CREATE INDEX idx_audit_events_request_id ON audit_events (request_id);
CREATE INDEX idx_audit_events_event_type ON audit_events (event_type, timestamp);
CREATE INDEX idx_audit_events_actor ON audit_events (actor, timestamp);
