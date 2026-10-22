ALTER TABLE message_sources
ADD COLUMN IF NOT EXISTS citation_key TEXT,
ADD COLUMN IF NOT EXISTS parent_chunk_id BIGINT,
ADD COLUMN IF NOT EXISTS rule_keys JSONB NOT NULL DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS excerpt TEXT;

UPDATE message_sources
SET citation_key = source_id
WHERE citation_key IS NULL;

ALTER TABLE message_sources
ALTER COLUMN citation_key SET NOT NULL;

ALTER TABLE message_sources
DROP CONSTRAINT IF EXISTS message_sources_pkey;

ALTER TABLE message_sources
ADD CONSTRAINT message_sources_pkey PRIMARY KEY (message_id, citation_key);
