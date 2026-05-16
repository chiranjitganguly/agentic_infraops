-- Add clarification_question column to infra_requests for Phase 4 clarification flow.
ALTER TABLE infra_requests
  ADD COLUMN IF NOT EXISTS clarification_question TEXT;
