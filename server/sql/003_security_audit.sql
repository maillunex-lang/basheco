-- Server-side security audit, no credentials, bearer tokens, or raw IP addresses.
CREATE TABLE security_audit (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  event_type text NOT NULL CHECK (event_type IN (
    'account.registered','auth.login','auth.logout',
    'company.created','wallet.transfer'
  )),
  actor_account_id uuid,
  subject_id uuid,
  occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX security_audit_occurred_idx ON security_audit(occurred_at);
CREATE INDEX security_audit_actor_idx ON security_audit(actor_account_id, occurred_at DESC);
