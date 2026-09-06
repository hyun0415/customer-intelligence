ALTER TABLE escalations
ADD COLUMN IF NOT EXISTS occurrence_count INTEGER NOT NULL DEFAULT 1
CHECK (occurrence_count > 0);

ALTER TABLE escalations
ADD COLUMN IF NOT EXISTS last_occurred_at TIMESTAMPTZ NOT NULL
DEFAULT CURRENT_TIMESTAMP;

WITH grouped AS (
    SELECT conversation_id,
           (ARRAY_AGG(escalation_id ORDER BY created_at, escalation_id))[1] AS keep_id,
           COUNT(*)::INTEGER AS occurrence_count,
           MAX(created_at) AS last_occurred_at
    FROM escalations
    WHERE status IN ('open', 'acknowledged')
    GROUP BY conversation_id
    HAVING COUNT(*) > 1
)
UPDATE escalations e
SET occurrence_count = grouped.occurrence_count,
    last_occurred_at = grouped.last_occurred_at
FROM grouped
WHERE e.escalation_id = grouped.keep_id;

WITH ranked AS (
    SELECT escalation_id,
           ROW_NUMBER() OVER (
               PARTITION BY conversation_id
               ORDER BY created_at, escalation_id
           ) AS row_number
    FROM escalations
    WHERE status IN ('open', 'acknowledged')
)
DELETE FROM escalations e
USING ranked
WHERE e.escalation_id = ranked.escalation_id
  AND ranked.row_number > 1;

CREATE UNIQUE INDEX IF NOT EXISTS uq_escalations_active_conversation
ON escalations(conversation_id)
WHERE status IN ('open', 'acknowledged');
