CREATE TABLE IF NOT EXISTS rag_chunk_embeddings (
    chunk_embedding_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    chunk_id            BIGINT NOT NULL REFERENCES rag_chunks(chunk_id) ON DELETE CASCADE,
    model_key           TEXT NOT NULL,
    model_version       TEXT NOT NULL,
    dimensions          INTEGER NOT NULL CHECK (dimensions > 0),
    embedding           vector NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (chunk_id, model_key, model_version),
    CHECK (vector_dims(embedding) = dimensions)
);

CREATE INDEX IF NOT EXISTS idx_rag_chunk_embeddings_lookup
ON rag_chunk_embeddings(model_key, model_version, chunk_id);

CREATE INDEX IF NOT EXISTS idx_rag_chunk_embeddings_openai_hnsw
ON rag_chunk_embeddings USING hnsw ((embedding::vector(1536)) vector_cosine_ops)
WHERE model_key = 'text-embedding-3-small' AND dimensions = 1536;

CREATE INDEX IF NOT EXISTS idx_rag_chunk_embeddings_bge_m3_hnsw
ON rag_chunk_embeddings USING hnsw ((embedding::vector(1024)) vector_cosine_ops)
WHERE model_key = 'BAAI/bge-m3' AND dimensions = 1024;

INSERT INTO rag_chunk_embeddings (
    chunk_id, model_key, model_version, dimensions, embedding
)
SELECT
    chunk_id, embedding_model, COALESCE(embedding_version, '1'),
    vector_dims(embedding), embedding
FROM rag_chunks
WHERE chunk_level = 'child'
  AND embedding IS NOT NULL
  AND embedding_model IS NOT NULL
ON CONFLICT (chunk_id, model_key, model_version) DO NOTHING;
