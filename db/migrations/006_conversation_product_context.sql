ALTER TABLE conversations
ADD COLUMN IF NOT EXISTS context_mode TEXT NOT NULL DEFAULT 'general';

ALTER TABLE conversations
ADD COLUMN IF NOT EXISTS product_parent_asin TEXT REFERENCES products(parent_asin);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'conversations_context_mode_check'
    ) THEN
        ALTER TABLE conversations
        ADD CONSTRAINT conversations_context_mode_check
        CHECK (context_mode IN ('general', 'product'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'conversations_product_context_check'
    ) THEN
        ALTER TABLE conversations
        ADD CONSTRAINT conversations_product_context_check
        CHECK (
            (context_mode = 'general' AND product_parent_asin IS NULL)
            OR (context_mode = 'product' AND product_parent_asin IS NOT NULL)
        );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_conversations_product
ON conversations(product_parent_asin, updated_at DESC)
WHERE product_parent_asin IS NOT NULL;
