-- Migration: 003_immutable_audit
-- Enforces append-only semantics on audit_events: no UPDATE or DELETE permitted.
-- Any attempt is silently discarded (INSTEAD NOTHING).

CREATE OR REPLACE RULE no_update_audit_events
  AS ON UPDATE TO audit_events
  DO INSTEAD NOTHING;

CREATE OR REPLACE RULE no_delete_audit_events
  AS ON DELETE TO audit_events
  DO INSTEAD NOTHING;
