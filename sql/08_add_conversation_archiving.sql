ALTER TABLE conversations
ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_conversations_owner_active
ON conversations(user_id, updated_at DESC)
WHERE archived_at IS NULL;
