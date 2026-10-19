# Published Evaluation Results

[한국어](README.md) / [Project home](../../README_EN.md) / [Evaluation guide](../../eval/README_EN.md)

This directory exposes the per-question evidence behind the headline metrics.
Full answers and repeated run logs remain under the ignored `eval/results/`
directory and are not published.

## Direct links

| Evaluation | Questions and Gold Labels | Published results | What it verifies |
|---|---|---|---|
| 24-case RAG comparison | [Questions and Gold Labels](../../eval/datasets/rag_pipeline_cases.json) | [Five-stage per-question CSV](rag_24_case_results.csv) | Source and clause retrieval, status, latency |
| Nine-case policy Agent | [Questions, expected Tools, and labels](../../eval/datasets/agent_policy_cases.json) | [Per-question Terra results](policy_agent_9_case_results.csv) | Tools, arguments, policy evidence, Judge score |
| 15-case review Agent | [Questions and Tool labels](../../eval/datasets/agent_review_cases.json) | [Question list CSV](review_agent_15_questions.csv) | Product lookup, review metrics, complaint analysis |
| Overall summary | — | [Final metrics CSV](final_evaluation_summary.csv) | Pipeline and Agent metrics |
| RAG baseline | — | [Per-question baseline JSON](../../eval/baselines/openai_rag_source_clause_20261018.json) | Retrieved Parents and ranks |

## The 24 RAG questions

The same 24 questions were evaluated against ten synthetic approved policies
using FTS, Vector, Hybrid RRF, Hybrid RRF + BGE-M3, and the full pipeline. Every
channel used ten candidates and every stage returned a final Parent `K=5`.

[rag_24_case_results.csv](rag_24_case_results.csv) contains 120 rows: 24 questions
across five stages. Each row includes its Gold `source_id + rule_key`, actual
status, Source Recall and MRR, clause Hit and MRR, latency, and failure labels.

| Pipeline | Source Recall@5 | Source MRR | Clause Hit@5 | Clause MRR | Status accuracy | No-evidence F1 | p95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| FTS Only | **1.000** | 0.865 | 0.875 | 0.708 | 0.833 | 0.667 | **94.3 ms** |
| Vector Only | 0.875 | 0.812 | 0.875 | 0.812 | 0.833 | 0.714 | 76.5 ms |
| Hybrid RRF | **1.000** | 0.896 | **1.000** | 0.896 | 0.833 | 0.667 | 116.8 ms |
| Hybrid RRF + BGE-M3 | **1.000** | 0.969 | **1.000** | 0.880 | 0.833 | 0.667 | 1,139.9 ms |
| Full | **1.000** | **1.000** | **1.000** | **0.969** | **1.000** | **1.000** | 5,195.6 ms |

- FTS found every target Source but still returned related documents for
  questions without sufficient evidence.
- RRF combined the two channels without losing an expected clause.
- BGE-M3 improved target-policy rank, while a similar clause from the same
  document sometimes preceded the target and slightly reduced clause MRR.
- The Full stage classified every status and no-evidence case correctly, with
  p95 latency increasing to about 5.2 seconds.

## Nine Terra policy-Agent cases

The 2026-10-19 run added `get_policy_search_options_tool` before policy search.
Terra reads the allowed Collections, jurisdictions, and departments, then
selects only the Tools and arguments. The Python server executes parameterized
SQL and enforces user-specific access filters.

| Metric | Before | After |
|---|---:|---:|
| Tool selection and execution | 9/9 | **9/9** |
| Expected policy status | 5/9 | **8/9** |
| Expected policy Source | 6/9 | **8/9** |
| Expected evidence clause | 6/9 | **7/9** |
| Expected facts | 7/9 | **8/9** |
| Correct abstention after `no_evidence` | 3/3 | **3/3** |
| Average GPT-5.6 Sol evaluation | 4.56/5 | **4.74/5** |

[policy_agent_9_case_results.csv](policy_agent_9_case_results.csv) records each
query, search arguments, returned policy status, Sources and clauses,
deterministic checks, Judge scores, and failure reasons.

### Improvements

- Reporting targets such as the quality team are no longer mistaken for a
  policy-owner department filter.
- Product questions preserve `parent_asin`, and the Japan-scope question passes
  `JP` without silently substituting the available KR scope.
- All three unavailable or expired-policy questions abstained rather than
  inventing an answer.

### Remaining issues and limitations

- **R01:** Terra broadened a damage question to “damage or leakage,” so the
  one-free-reshipment clause was not retrieved. The answer direction was
  reasonable, but the required clause and fact checks failed.
- **R03:** several safety signals were combined into one broad query, causing
  evidence assessment to return `no_evidence`. Safety escalation ran, but the
  expected policy Source and clause were not cited.
- **BGE-M3 availability:** remote reranking failed in seven of nine cases and
  the system fell back to the existing RRF order. Evidence assessment completed
  in all nine cases. The Agent improvement therefore measures the metadata Tool
  and argument handling, not consistently applied BGE-M3 reranking.
- This is a small fixed suite over synthetic policies, not an estimate of
  accuracy on arbitrary enterprise data. The next experiment should compare
  condition-specific searches for compound questions against their additional
  Tool calls and latency.

## The 15 complaint-analysis questions

[review_agent_15_questions.csv](review_agent_15_questions.csv) lists one case per
row, covering direct product lookup, rating distribution, low-rated helpful
reviews, repeated complaints, actionable recommendations, and nonexistent
products. `{valid_asin}` is replaced by the test ASIN at runtime. This file makes
the SQL-Tool routing questions easy to inspect without publishing customer
review text or personal data.
