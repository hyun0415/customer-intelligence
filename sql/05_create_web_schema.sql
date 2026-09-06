CREATE TABLE IF NOT EXISTS app_users (
    user_id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    oidc_issuer    TEXT NOT NULL,
    oidc_subject   TEXT NOT NULL,
    email          TEXT NOT NULL,
    display_name   TEXT NOT NULL,
    role           TEXT NOT NULL DEFAULT 'employee'
                   CHECK (role IN ('employee', 'manager', 'admin')),
    is_active      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (oidc_issuer, oidc_subject)
);

CREATE INDEX IF NOT EXISTS idx_app_users_email
ON app_users (LOWER(email));

CREATE TABLE IF NOT EXISTS user_policy_scopes (
    scope_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id        BIGINT NOT NULL REFERENCES app_users(user_id) ON DELETE CASCADE,
    collection     TEXT NOT NULL,
    jurisdiction   TEXT NOT NULL,
    department     TEXT NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, collection, jurisdiction, department)
);

CREATE INDEX IF NOT EXISTS idx_user_policy_scopes_user
ON user_policy_scopes(user_id);

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

CREATE TABLE IF NOT EXISTS conversations (
    conversation_id UUID PRIMARY KEY,
    user_id          BIGINT NOT NULL REFERENCES app_users(user_id) ON DELETE CASCADE,
    title            TEXT NOT NULL DEFAULT '새 대화',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_conversations_owner_updated
ON conversations(user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS conversation_messages (
    message_id       UUID PRIMARY KEY,
    conversation_id  UUID NOT NULL REFERENCES conversations(conversation_id)
                     ON DELETE CASCADE,
    role              TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content           TEXT NOT NULL,
    response_status   TEXT CHECK (
        response_status IS NULL
        OR response_status IN ('answer', 'no_evidence', 'conflict', 'escalation')
    ),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_conversation_messages_order
ON conversation_messages(conversation_id, created_at, message_id);

CREATE TABLE IF NOT EXISTS message_sources (
    message_id       UUID NOT NULL REFERENCES conversation_messages(message_id)
                     ON DELETE CASCADE,
    source_id        TEXT NOT NULL,
    title            TEXT NOT NULL,
    version_number   INTEGER,
    section_title    TEXT,
    metadata         JSONB NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (message_id, source_id)
);

CREATE TABLE IF NOT EXISTS escalations (
    escalation_id    UUID PRIMARY KEY,
    conversation_id  UUID NOT NULL REFERENCES conversations(conversation_id)
                     ON DELETE CASCADE,
    message_id       UUID NOT NULL REFERENCES conversation_messages(message_id)
                     ON DELETE CASCADE,
    user_id          BIGINT NOT NULL REFERENCES app_users(user_id) ON DELETE CASCADE,
    category         TEXT NOT NULL CHECK (
        category IN ('medical', 'safety', 'policy_conflict', 'other')
    ),
    reason           TEXT NOT NULL,
    occurrence_count INTEGER NOT NULL DEFAULT 1 CHECK (occurrence_count > 0),
    last_occurred_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status           TEXT NOT NULL DEFAULT 'open'
                     CHECK (status IN ('open', 'acknowledged', 'resolved')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_escalations_status_created
ON escalations(status, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_escalations_active_conversation
ON escalations(conversation_id)
WHERE status IN ('open', 'acknowledged');
