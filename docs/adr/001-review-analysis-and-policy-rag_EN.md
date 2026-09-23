# ADR-001: Separating Tested SQL Tools from Policy Hybrid RAG

[한국어](001-review-analysis-and-policy-rag.md) · [Main documentation](../../README_EN.md)

## Status

Accepted

## Decision at a Glance

The Customer Intelligence Agent uses evidence with different properties, so the
system does not force every question through one retrieval method.

| Question and data | Execution path | Intended guarantee |
|---|---|---|
| Products, ratings, review counts, dates, and recurring complaints | Tested PostgreSQL Tools | Exact filtering, sorting, aggregation, and traceable review text |
| Refunds, reshipments, compensation, exceptions, and CS procedures | Access-filtered policy Hybrid RAG | Current policy evidence applicable to the signed-in user |
| Questions combining complaints and handling rules | Retrieve SQL and RAG evidence separately, then combine through the Agent | Preserve the distinction between customer experience and operating rules |

The governing principle is:

> **Deterministic code controls numbers and data selection; models are used within
> bounded roles for semantic retrieval and explanation.**

## Problem

Review analytics and internal policy may both be required for one natural-language
question, but they have different correctness requirements.

- Review counts, rating ratios, and date filters require exact computation.
- Equivalent policies may use different wording, making keyword-only retrieval insufficient.
- Reviews provide evidence of customer experience, not policy, medical, or safety proof.
- Policies define permitted actions but do not show complaint frequency for a product.

Putting all data in Vector search or one LLM prompt would mix numerical
reproducibility, policy scope, and evidence provenance. The two paths therefore
remain separate.

## Chosen Architecture

```text
User question
  ↓
Agent determines intent and required evidence
  ├─ Review-analysis path
  │    → Tested SQL Tool
  │    → PostgreSQL sample and statistics
  │    → Optional Aspect Extractor and Python validation/aggregation
  │
  ├─ Policy-RAG path
  │    → Access, validity, and scope filters
  │    → Child FTS + embedding retrieval
  │    → Parent-level RRF
  │    → BGE-M3 MaxSim reranking
  │    → Policy priority and LLM evidence assessment
  │
  └─ Combined questions merge both results while preserving provenance
       ↓
Answer separating quantitative metrics, review text, and policy evidence
```

The Agent never writes executable SQL. It selects a Tool; tested code owns the
query conditions and aggregation.

## Path 1: Customer Review Analysis

| Stage | Responsibility |
|---|---|
| Tool selection | Agent chooses product, rating, negative-review, or recurring-pattern Tool |
| SQL retrieval | PostgreSQL returns a sample and metrics under code-defined rules |
| Semantic extraction | For pattern questions, the Extractor structures per-review Aspect, sentiment, and evidence |
| Code validation | Python checks source containment and the allowed taxonomy |
| Aggregation | Python computes unique-review counts, sample ratios, and average confidence |
| Answer | Agent explains only the validated Tool result |

This path reduces the risk of invented tables, filters, and numbers. See the
[customer review analysis guide](../review-analysis/README_EN.md) for schemas,
Redis caching, and the limitations of per-review calls.

## Path 2: Internal Policy Hybrid RAG

| Stage | Responsibility |
|---|---|
| Pre-filter | Apply approval, validity, product, collection, jurisdiction, department, and user access |
| Child retrieval | Run PostgreSQL FTS `ts_rank_cd` and embedding cosine search independently |
| Parent fusion | Restore Parent sections for matched Children and combine ranks with RRF |
| Fine reranking | Compare query and Parent tokens with BGE-M3 ColBERT MaxSim |
| Policy priority | Resolve product specificity, Authority Tier, and effective date in Python |
| Evidence assessment | Structured LLM returns only `sufficient / insufficient / conflict` |
| Answer boundary | Cite supported Parents only; return `no_evidence` after insufficient or failed validation |

FTS preserves exact policy terminology, while embeddings recover semantic
paraphrases. RRF combines ranks without assuming comparable raw scores. BGE-M3
is a second-stage token-level reranker, not a first-stage scanner over the entire
corpus. See the [Policy RAG guide](../rag/README_EN.md) for candidate counts and
MaxSim details.

## System Invariants

These conditions are enforced in code rather than delegated to model quality.

| Invariant | Enforcement |
|---|---|
| SQL accuracy | Never execute LLM-generated SQL; expose tested Tools only |
| Numerical grounding | Do not create numbers or ratios absent from Tool output |
| Review evidence | Verify that Extractor evidence occurs in the source review |
| Policy access | Enforce user and policy scope before retrieval |
| Policy conflicts | Never let the Agent choose arbitrarily between equal-priority conflicts |
| Medical and safety | Leave the normal answer path and escalate for human review |
| Retrieval failure | Fall back from reranking to RRF; fail closed after evidence-assessment failure |

## Alternatives and Rejections

| Alternative | Decision | Reason |
|---|---|---|
| Retrieve everything from a Vector DB | Rejected | Exact counts, ratios, filters, and sorting are not guaranteed and relational strengths are lost |
| Generate SQL for each question | Rejected | Increases schema errors and variation in aggregation rules |
| Retrieve policy with FTS only | Rejected | Misses relevant policy when question and document wording differ |
| Replace first-stage retrieval with BGE-M3 Dense and Sparse | Rejected | Duplicates the existing FTS and embedding channels and increases operations |
| Introduce Graph RAG or Neo4j | Not currently selected | Document retrieval and structured aggregation matter more than multi-hop relation reasoning |
| Resolve statistics and policy in one prompt | Rejected | Over-delegates numbers, access, and evidence provenance to the model |

## Operational Defaults

| Item | Default | Meaning |
|---|---:|---|
| FTS candidates | 10 | Child candidates from the channel |
| Embedding candidates | 10 | Child candidates from the channel |
| Minimum vector similarity | 0.33 | Remove weak Vector candidates |
| RRF constant | 60 | Smooth rank differences across channels |
| Final evidence candidates | 5 | Parents sent to evidence assessment after priority resolution |
| BGE-M3 input | Query 256 / Parent 2,048 tokens | Maximum reranking lengths |
| BGE-M3 batch | 2 | Processing unit chosen for GPU memory control |
| Evidence timeout/retry | 15 seconds / 1 retry | Do not force an answer after failure |

These values are initial operating choices from the current data and evaluation
set, not universal relevance thresholds. They must be reevaluated when the
document or query distribution changes.

## Consequences and Limitations

### Benefits

- Quantitative analysis is explainable through reproducible SQL results.
- The Agent receives policy evidence only after access and validity filters.
- Answers keep customer experience separate from policy decisions.
- Reranker or validator failure does not become an unsupported answer.
- OpenAI and local models can share the same Tool, schema, and evaluation contracts.

### Accepted limitations

- Two execution paths and their failure behavior add components to operate.
- First-time Aspect analysis invokes the LLM for every uncached review.
- Complaints outside the fixed Aspect taxonomy may be absent from pattern results.
- When the BGE-M3 reranker is unavailable, policy retrieval depends on the RRF fallback.
- The LLM evidence decision may be wrong, so the system abstains without support.

## Revisit When

- Multi-hop reasoning across products, policies, departments, and exceptions becomes central.
- Document and Chunk volume exceeds practical PostgreSQL retrieval capacity.
- Frequent taxonomy changes make fixed review schemas too costly to maintain.
- Independent reranker operating cost exceeds its measured retrieval benefit.
- Evaluation shows that one retrieval path can match this design's accuracy and grounding.
