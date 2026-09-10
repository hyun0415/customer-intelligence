CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS rag_collections (
    collection_id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name                   TEXT NOT NULL UNIQUE,
    description            TEXT NOT NULL,
    embedding_model        TEXT NOT NULL,
    embedding_dimensions   INTEGER NOT NULL CHECK (embedding_dimensions > 0),
    distance_metric        TEXT NOT NULL DEFAULT 'cosine'
                           CHECK (distance_metric = 'cosine'),
    chunk_strategy         TEXT NOT NULL DEFAULT 'parent_child',
    is_active              BOOLEAN NOT NULL DEFAULT TRUE,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rag_documents (
    document_id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id          TEXT NOT NULL UNIQUE,
    collection_id      BIGINT NOT NULL REFERENCES rag_collections(collection_id),
    source_type        TEXT NOT NULL,
    authority_tier     SMALLINT NOT NULL CHECK (authority_tier BETWEEN 1 AND 4),
    publisher          TEXT NOT NULL,
    title              TEXT NOT NULL,
    source_url         TEXT,
    language           TEXT NOT NULL,
    jurisdiction       TEXT NOT NULL,
    department         TEXT NOT NULL,
    policy_key         TEXT NOT NULL,
    published_at       TIMESTAMPTZ,
    first_retrieved_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata           JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_rag_documents_filters
ON rag_documents(collection_id, jurisdiction, department, authority_tier);

CREATE TABLE IF NOT EXISTS rag_document_versions (
    document_version_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id         BIGINT NOT NULL REFERENCES rag_documents(document_id)
                        ON DELETE CASCADE,
    version_number      INTEGER NOT NULL CHECK (version_number > 0),
    content_hash        TEXT NOT NULL,
    raw_content         TEXT NOT NULL,
    cleaned_content     TEXT NOT NULL,
    retrieved_at        TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_from          TIMESTAMPTZ NOT NULL,
    valid_to            TIMESTAMPTZ,
    approval_status     TEXT NOT NULL,
    is_current          BOOLEAN NOT NULL DEFAULT FALSE,
    supersedes_version  INTEGER,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (document_id, version_number),
    UNIQUE (document_id, content_hash),
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    CHECK (supersedes_version IS NULL OR supersedes_version < version_number)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_rag_document_current_version
ON rag_document_versions(document_id)
WHERE is_current;

CREATE INDEX IF NOT EXISTS idx_rag_versions_effective
ON rag_document_versions(document_id, valid_from, valid_to);

CREATE TABLE IF NOT EXISTS rag_chunks (
    chunk_id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_version_id BIGINT NOT NULL
                        REFERENCES rag_document_versions(document_version_id)
                        ON DELETE CASCADE,
    parent_chunk_id     BIGINT REFERENCES rag_chunks(chunk_id) ON DELETE CASCADE,
    chunk_level         TEXT NOT NULL CHECK (chunk_level IN ('parent', 'child')),
    chunk_index         INTEGER NOT NULL CHECK (chunk_index >= 0),
    section_path        TEXT NOT NULL,
    section_title       TEXT NOT NULL,
    chunk_text          TEXT NOT NULL,
    embedding_text      TEXT NOT NULL,
    token_count         INTEGER NOT NULL CHECK (token_count > 0),
    embedding_model     TEXT,
    embedding_version   TEXT,
    embedding           vector(1536),
    search_vector       TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('simple', section_path || ' ' || section_title || ' ' || chunk_text)
    ) STORED,
    rule_key            TEXT,
    rule_effect         TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (document_version_id, chunk_level, chunk_index),
    CHECK (
        (chunk_level = 'parent' AND parent_chunk_id IS NULL AND embedding IS NULL)
        OR
        (chunk_level = 'child' AND parent_chunk_id IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_rag_chunks_search_vector
ON rag_chunks USING GIN(search_vector);

CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding_hnsw
ON rag_chunks USING hnsw (embedding vector_cosine_ops)
WHERE chunk_level = 'child' AND embedding IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_rag_chunks_parent
ON rag_chunks(parent_chunk_id)
WHERE chunk_level = 'child';

CREATE INDEX IF NOT EXISTS idx_rag_chunks_rule_key
ON rag_chunks(rule_key)
WHERE rule_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS rag_document_products (
    document_id  BIGINT NOT NULL REFERENCES rag_documents(document_id)
                 ON DELETE CASCADE,
    parent_asin  TEXT NOT NULL REFERENCES products(parent_asin) ON DELETE CASCADE,
    relation_type TEXT NOT NULL DEFAULT 'applies_to',
    PRIMARY KEY (document_id, parent_asin, relation_type)
);

CREATE INDEX IF NOT EXISTS idx_rag_document_products_asin
ON rag_document_products(parent_asin, document_id);

INSERT INTO rag_collections (
    name, description, embedding_model, embedding_dimensions
)
VALUES
    ('compensation_policy', '환불, 재배송, 쿠폰 등 보상 정책', 'text-embedding-3-small', 1536),
    ('promotion_policy', '프로모션과 쿠폰 중복 적용 정책', 'text-embedding-3-small', 1536),
    ('product_operation_guides', '제품별 운영 및 고객응대 가이드', 'text-embedding-3-small', 1536),
    ('cs_sop', '고객 불만 유형별 표준 운영 절차', 'text-embedding-3-small', 1536),
    ('exception_policy', '예외 승인과 escalation 정책', 'text-embedding-3-small', 1536)
ON CONFLICT (name) DO NOTHING;
