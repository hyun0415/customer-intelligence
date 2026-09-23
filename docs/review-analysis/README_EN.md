# Customer Review Analysis and Aspect Extraction

[한국어](README.md) · [Main documentation](../../README_EN.md)

This guide explains how a product-analysis question moves through SQL retrieval,
per-review Aspect Extraction, Python validation and aggregation, and finally back
to the Agent. The governing principle is: **deterministic code selects data and
computes numbers; the LLM is used only for semantic interpretation**.

## End-to-End Flow

```text
User question
  → Agent selects a tested SQL Tool
  → PostgreSQL returns a review sample and statistics
  → Aspect Extractor runs independently for each review
  → Python validates source evidence
  → Python aggregates counts and ratios
  → ReviewPatternResult
  → Final Agent explains recurring complaints and priorities
```

The Agent does not generate SQL. It identifies the product and analytical intent,
then chooses a predefined Tool whose code controls the filters and aggregation
rules.

## 1. Selecting the Review Sample

Recurring-complaint analysis uses `get_review_patterns_tool`. Its current default
selection contract is:

| Condition | Default |
|---|---:|
| Maximum rating | 3 stars or lower |
| Minimum helpful votes | At least 1 |
| Sort order | Helpful votes descending |
| Sample size | Up to 20 reviews |

The Tool stores these rules in `selection_criteria`. Ratios therefore represent
the **selected review sample**, not incidence across the entire customer
population, and the same sampling decision can be reproduced.

## 2. Per-Review Structured Extraction

The Aspect Extractor does not summarize the complete sample in one request. It
processes each review independently, returns multiple topics when directly
supported, and returns an empty list when no supported topic exists.

### Example Input

```text
Title: Leaking bottle and terrible smell
Body:  The bottle arrived leaking inside the box.
       The smell was so strong that I stopped using it.
```

### Example `ClassifiedReview`

```json
{
  "source_index": 3,
  "topics": [
    {
      "topic": "packaging",
      "sentiment": "negative",
      "is_direct_experience": true,
      "evidence": "The bottle arrived leaking inside the box.",
      "confidence": 0.98
    },
    {
      "topic": "odor",
      "sentiment": "negative",
      "is_direct_experience": true,
      "evidence": "The smell was so strong that I stopped using it.",
      "confidence": 0.97
    }
  ],
  "summary": "고객은 배송된 제품의 누액과 강한 냄새를 경험해 사용을 중단했습니다."
}
```

Python overwrites `source_index` with the review's position in the current sample;
it is not trusted as a model decision. `topic` is restricted to the fixed taxonomy
below.

| Key | Display label |
|---|---|
| `hair_dryness` | Hair dryness |
| `hair_damage` | Hair damage |
| `uneven_color` | Uneven color |
| `staining` | Staining |
| `odor` | Unpleasant odor |
| `packaging` | Packaging issue |
| `ineffective` | Ineffective result |
| `authenticity` | Authenticity or quality concern |
| `skin_reaction` | Skin reaction |

## 3. Python Source Validation and Aggregation

Extractor JSON is not aggregated as-is. Python lowercases the evidence and the
review title/body, normalizes repeated whitespace, and checks whether the quoted
evidence is **literally contained in the source review**. This is an exact
substring check rather than semantic retrieval, so a paraphrased or invented
quotation is rejected.

Validation and aggregation apply the following rules:

1. Remove topics outside the taxonomy and evidence absent from the source.
2. Keep only the highest-confidence duplicate of a topic within one review.
3. Aggregate only direct experiences with `negative` or `mixed` sentiment.
4. Exclude confidence below the default threshold of `0.8`.
5. Count the same Aspect at most once per review.
6. Compute `ratio = count / total sample size` and retain confidence and evidence.

The resulting `ReviewPatternResult` contains the sample size and selection rules,
per-Aspect counts and ratios, average confidence, review indexes, source evidence,
and review summaries. The final Agent receives this validated structure rather
than the Extractor's raw output.

## 4. Redis Review Cache

To avoid paying repeatedly for the same extraction, each validated
`ClassifiedReview` is stored in Redis. Its cache key is a SHA-256 hash of:

```text
Review title + review body
+ provider + model name + base URL + reasoning setting
+ Extractor cache version
```

The default TTL is 30 days. A different model or changed review text creates a
new entry. Prompt or extraction-rule changes require incrementing
`EXTRACTOR_CACHE_VERSION` to invalidate previous results. If Redis is unavailable
or cached JSON no longer satisfies the Pydantic schema, execution falls back to
normal extraction.

Cache lookup is per review, not per sample. If 10 of 20 selected reviews are
cached, those 10 reuse existing JSON; only the remaining 10 invoke the Extractor.
All 20 results are then aggregated together.

## Strengths and Limitations

| Type | Description |
|---|---|
| Strength | One review maps to one JSON result, making evidence tracing and failure isolation clear |
| Strength | Python removes unsupported quotations, invalid topics, and duplicate results |
| Strength | Code-fixed sampling and aggregation make numerical results reproducible |
| Strength | Per-review, per-model caching reduces repeated latency and API cost |
| Limitation | Every uncached review invokes the LLM sequentially, so the first 20-review analysis is relatively slow and expensive |
| Limitation | Complaints outside the fixed taxonomy may not appear in structured results |
| Limitation | Exact evidence matching rejects semantically equivalent paraphrases |
| Limitation | `summary` is generated text and does not have the deterministic guarantees of numbers or quotations |

The current MVP favors JSON consistency, source traceability, and isolated
failure over throughput. A suitable optimization is **bounded concurrency of
three to five independent review calls**, rather than combining every review in
one large prompt.

## Code and Validation

| Responsibility | File |
|---|---|
| Agent Tool and SQL sample selection | [`src/tools.py`](../../src/tools.py) |
| Extractor prompt, invocation, and evidence validation | [`src/analysis/review_extractor.py`](../../src/analysis/review_extractor.py) |
| Pydantic input/output schemas | [`src/analysis/schemas.py`](../../src/analysis/schemas.py) |
| Aspect taxonomy | [`src/analysis/taxonomy.py`](../../src/analysis/taxonomy.py) |
| Count and ratio aggregation | [`src/analysis/review_statistics.py`](../../src/analysis/review_statistics.py) |
| Redis cache | [`src/cache/review_cache.py`](../../src/cache/review_cache.py) |

```powershell
pytest -q tests/test_review_analysis.py tests/test_review_cache.py tests/test_tools.py
```
