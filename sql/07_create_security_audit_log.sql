CREATE TABLE IF NOT EXISTS security_audit_events (
    audit_event_id      UUID PRIMARY KEY,
    occurred_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    event_type          TEXT NOT NULL,
    outcome             TEXT NOT NULL CHECK (outcome IN ('success', 'failure', 'denied')),
    actor_user_id       BIGINT REFERENCES app_users(user_id) ON DELETE SET NULL,
    oidc_issuer         TEXT,
    oidc_subject        TEXT,
    session_fingerprint TEXT,
    request_id          UUID NOT NULL,
    ip_address          INET,
    user_agent          TEXT,
    resource_type       TEXT,
    resource_id         TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_security_audit_occurred
ON security_audit_events(occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_security_audit_actor
ON security_audit_events(actor_user_id, occurred_at DESC);
