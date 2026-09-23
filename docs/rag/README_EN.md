# Policy Hybrid RAG

[한국어](README.md) · [Project home](../../README_EN.md)

This path retrieves internal refund, reshipment, compensation, promotion,
product-operation, and CS SOP documents. Product and review counts remain the
responsibility of deterministic SQL Tools; this path handles unstructured policy.

## Retrieval Contract

- Production retrieval uses only currently effective `APPROVED` versions.
- Product, collection, jurisdiction, department, and user access are enforced in SQL.
- Semantic similarity alone never authorizes a policy answer.
- Only Parent sections marked `sufficient` reach the final Agent context.
- Missing evidence returns `no_evidence`; equal-priority conflicts return `policy_conflict`.

## Parent and Child Units

| Unit | Default size | Responsibility |
|---|---:|---|
| Parent | 800–1,200 tokens | Complete policy section containing conditions, exceptions, and approvals |
| Child | 300–450 tokens | Precise retrieval unit for FTS and embeddings |
| Overlap | 50 tokens | Reduces context loss across Child boundaries |

Children store the FTS index and Dense Embedding. A retrieved Child points to a
Parent section, which is used for BGE-M3 reranking, evidence assessment, and final
citation.

Reranking Parents preserves deadlines, exceptions, and approval requirements
around the matched sentence. Child-only evidence could retrieve the relevant
sentence while omitting a limiting condition in the same section. ColBERT MaxSim
does not compress the Parent into one averaged vector; each query token can match
its closest Parent token.

## Runtime Flow

### 1. Scope filters

The retriever applies:

- Approval status and `valid_from / valid_to`
- Product-specific or global scope
- Collection, jurisdiction, and department
- Policy grants assigned to the authenticated user

An empty access-grant list returns `no_evidence` before an embedding or database
search is attempted.

### 2. Query embedding and two retrieval channels

The query Dense Embedding is generated at request time and compared with
precomputed Child embeddings. FTS and embedding retrieval are independent
channels, not a sequential filter where one channel limits the other.

| Channel | Unit | Default candidates | Ranking |
|---|---|---:|---|
| PostgreSQL FTS | Child | Up to 10 | `plainto_tsquery('simple')` + `ts_rank_cd` |
| pgvector | Child | Up to 10 | Cosine similarity with a default 0.33 threshold |

The FTS rank is not BM25. It uses PostgreSQL cover-density ranking through
`ts_rank_cd`. Explicit FTS matches are retained independently of the Vector
similarity threshold.

Embedding configuration depends on the runtime profile.

| Profile | Model | Dimensions |
|---|---|---:|
| Default `openai` | `text-embedding-3-small` | 1,536 |
| `local` | Remote `BAAI/bge-m3` Dense output | 1,024 |

Stored `model_key`, version, and dimensions must match the active settings.

### 3. Parent-level RRF

Children from both channels are grouped by `parent_chunk_id`. Multiple Children
from the same Parent in one channel do not add frequency credit; only that
Parent's best channel rank is used. All matched Child IDs remain available in
`matched_child_ids` for traceability.

When the Parent appears in both channels, both contributions are added.

```text
RRF(parent) = 1 / (60 + FTS rank) + 1 / (60 + Vector rank)
```

`60` is the RRF smoothing constant, not a candidate count. Ten Children per
channel can produce at most 20 unique Parent candidates and usually fewer after
deduplication.

### 4. BGE-M3 ColBERT reranking

RRF reliably fuses ranks from the FTS and embedding channels, but it does not
re-read candidate content against the question. The system therefore evaluates
every fused Parent with BGE-M3 Multi-vector scoring and promotes the policy
sections that best cover the question's detailed conditions.

#### Difference from dense retrieval

Dense retrieval compresses the question and an entire document into one vector
each. This is efficient for broad semantic matching, but a single vector may
dilute specific policy conditions, counts, or exceptions.

BGE-M3 Multi-vector representation retains one vector per token instead of
compressing the question and Parent into single vectors.

```text
Question: “How many free reshipments are allowed?”
Query vectors: [free] [reshipment] [how many] [allowed]

Parent: “One free reshipment is processed automatically for the same incident.”
Parent vectors: [one] [free] [reshipment] [automatically] [same] [incident]
```

#### MaxSim procedure

Late Interaction encodes the question and Parent independently, then compares
their token vectors at retrieval time. MaxSim proceeds as follows:

1. Encode the question as one vector per token.
2. Encode the Parent policy section in the same way.
3. Compare every query token with every Parent token.
4. Keep the highest similarity for each query token.
5. Average those maxima into the final query–Parent relevance score.
6. Sort all Parent candidates by that score in descending order.

The values below are illustrative rather than captured model outputs.

| Query token | Best matching Parent expression | Example MaxSim |
|---|---|---:|
| `free` | `free` | 0.96 |
| `reshipment` | `reshipment` | 0.98 |
| `how many` | `one` | 0.91 |
| `allowed` | `processed automatically` | 0.87 |

Exact wording is not required when the expressions are close in the embedding
space. BGE-M3 defines its Multi-vector score as:

$$
s_{mul}(q,p)=\frac{1}{N}\sum_{i=1}^{N}\max_{j}
\left(E_q[i]\cdot E_p[j]^T\right)
$$

- $E_q[i]$: vector for query token i
- $E_p[j]$: vector for Parent token j
- $\max_j$: select the Parent token that best matches each query token
- mean: measure how fully the Parent covers the query expressions

The definition follows the Multi-vector section of the
[official FlagEmbedding BGE-M3 documentation](https://github.com/FlagOpen/FlagEmbedding/blob/master/docs/source/bge/bge_m3.rst).

#### Why rerank Parents

Initial retrieval operates on short, focused Child chunks. A Child is effective
for finding a directly matching sentence, but it may omit an exception, scope,
deadline, or approval requirement from the surrounding policy. Once a Child is
found, the system restores its Parent section and applies MaxSim to that fuller
context.

```text
Child  → retrieval unit for finding a directly relevant sentence
Parent → reranking and evidence unit containing conditions and exceptions
```

#### Current settings and failure behavior

This stage uses only the **ColBERT score** among BGE-M3's Dense, Sparse, and
ColBERT outputs. FTS and embedding signals have already been fused by RRF, so the
reranker focuses on fine-grained token interaction.

| Setting | Default |
|---|---:|
| Maximum query length | 256 tokens |
| Maximum Parent length | 2,048 tokens |
| Batch size | 2 |
| Reranking input | All RRF-fused Parent candidates |
| Score | BGE-M3 ColBERT MaxSim |

Parents longer than 2,048 tokens may be truncated, and more candidates increase
token comparisons and GPU memory use. MaxSim is therefore a second-stage
reranker over the candidates narrowed by RRF, not a first-stage scanner over the
entire policy corpus.

A reranker timeout or runtime error does not fail policy retrieval. By default,
the system restores the existing RRF order and records the error type in
retrieval metadata.

```text
BGE-M3 succeeds       → rerank Parents by MaxSim score
Timeout/runtime error → preserve RRF order and record error metadata
```

### 5. Deterministic policy priority and conflict handling

This is not an LLM classification. Python compares metadata loaded from
PostgreSQL.

| Decision | Data |
|---|---|
| Same policy issue | `rag_chunks.rule_key` |
| Normalized effect | `rag_chunks.rule_effect` |
| Product specificity | `rag_document_products.parent_asin` |
| Authority | `rag_documents.authority_tier` |
| Effective date | `rag_document_versions.valid_from` |

Within one `rule_key`, product-specific policy wins, followed by the lower
Authority Tier number and the latest effective date. Different `rule_effect`
values at the same priority produce `policy_conflict` rather than an arbitrary
choice.

### 6. Final candidates and LLM evidence assessment

After priority resolution, the default top five Parents are sent to the evidence
validator. Tool callers may set `limit` from 1 to 20. The structured LLM returns:

- `sufficient`: policy directly supports the material conditions in the question
- `insufficient`: the topic is related but a material amount, deadline, eligibility rule, or exception is missing
- `conflict`: supplied evidence supports incompatible conclusions

Evidence-validator failure is fail-closed as `no_evidence`. Only supported
Parents are exposed to the final Agent.

## Policy Ingestion

See [policy_metadata_schema.md](policy_metadata_schema.md) for metadata rules.
Policy scope must be explicit in the manifest and is never inferred.

```powershell
psql -f db/migrations/004_policy_rag.sql
psql -f db/migrations/010_multi_model_embeddings.sql
python -m src.rag.ingestion <internal-policy-manifest.csv>
```

The example manifest is
[internal_policy_manifest.example.csv](internal_policy_manifest.example.csv).
Real policy content and secrets are not committed.

## Main Settings

| Variable | Default | Purpose |
|---|---|---|
| `RAG_CANDIDATE_LIMIT` | `10` | Child candidates per FTS and embedding channel |
| `RAG_RRF_K` | `60` | RRF smoothing constant |
| `RAG_MINIMUM_RELEVANCE_SIMILARITY` | `0.33` | Minimum Vector cosine similarity |
| `RAG_RERANKER_ENABLED` | `true` | Enable BGE-M3 reranking |
| `RAG_RERANKER_BASE_URL` | unset | Separate GPU reranker endpoint |
| `RAG_RERANKER_FALLBACK_TO_RRF` | `true` | Restore RRF order after reranker failure |
| `RAG_EVIDENCE_VALIDATION_ENABLED` | `true` | Enable the LLM evidence gate |
| `RAG_EVIDENCE_TIMEOUT_SECONDS` | `15` | Evidence-validator timeout |

## Code and Validation

- Retrieval, fusion, and priority: `src/rag/retriever.py`
- Embedding providers: `src/rag/embeddings.py`
- BGE-M3 reranking: `src/rag/rerankers.py`
- Evidence assessment: `src/rag/evidence.py`
- Database schema: `db/migrations/004_policy_rag.sql`
- Design decision: [ADR-001](../adr/001-review-analysis-and-policy-rag_EN.md)
- Evaluation commands: [Evaluation guide](../../eval/README_EN.md)

Quick regression tests:

```powershell
pytest tests/test_rag_chunking.py tests/test_rag_retrieval.py `
  tests/test_rag_embeddings.py tests/test_rag_routing.py -q
```
