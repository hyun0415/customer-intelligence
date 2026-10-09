# Evaluation Guide

[한국어](README.md) / [Project home](../README_EN.md)

The goal is not to produce one impressive aggregate score. The suite separates
failure causes: retrieval may miss the policy, reranking may order it poorly,
or the Agent may select the wrong Tool. Repaired failures stay in the fixed set
so later changes cannot silently reintroduce them.

Run all commands from the repository root.

## What is evaluated

| Experiment | Question it answers | Cases |
|---|---|---:|
| Agent evaluation | Did the Agent select the right Tool and arguments? | 15 review + 9 review-policy |
| RAG stage comparison | What does retrieval, fusion, reranking, and evidence assessment each improve? | 24 policy questions |
| Policy access evaluation | Do all retrieval paths expose only authorized policies? | 11 allow/deny cases |
| Deterministic checks | Do answer numbers and citations exist in Tool or policy evidence? | Applied per Agent result |
| LLM Judge | How strong are analysis and business usefulness beyond deterministic checks? | Optional |
| Parser comparison | Does preserving document structure improve retrieval? | Reuses the same questions |

Questions and Gold Labels are stored as JSON under [datasets](datasets/), while
execution and scoring remain in Python. This prevents a scoring change from
silently changing the answers it is supposed to measure.

## Recommended order

Most changes need only three steps:

1. Run `pytest -q` to verify Tool contracts and deterministic rules.
2. Run the Agent suite to check Tool selection and successful execution.
3. Run the RAG comparison to measure retrieval quality, abstention, and latency.

Add the access or Parser evaluation only when those parts change.

## 1. Does the Agent use the right Tool?

This suite covers product lookup, review aggregation, Aspect analysis, policy
retrieval, and escalation. Its primary concern is **which Tool was called with
which arguments**, not writing style.

```powershell
python -m eval.run_agent_evaluation --suite all
```

| Result | Meaning |
|---|---|
| Completed | Model, database, and Tool execution reached the end |
| Tool selection pass | Required Tools were called and forbidden Tools avoided |
| Tool argument pass | Explicit ASIN, review-count, and rating constraints matched |
| Failure labels | `wrong_tool`, `wrong_argument`, `runtime_error`, and related causes |

Raw JSON and CSV are written to `eval/results/evaluation_<timestamp>.*`.
Generate per-Tool precision and recall only when that breakdown is needed:

```powershell
python -m eval.run_tool_metrics eval/results/evaluation_<timestamp>.json
```

## 2. Is every RAG stage necessary?

The same 24 questions are applied to all five stages. Differences therefore
come from the stage being added, not from an easier or harder question set.

| Stage | Question it answers |
|---|---|
| FTS Only | Can direct policy terms be found quickly? |
| Vector Only | Can semantically similar wording find the policy? |
| Hybrid RRF | Does combining both channels improve answer rank? |
| Hybrid RRF + BGE-M3 | Does rereading detailed conditions promote the exact clause? |
| Full | Does the system abstain when a retrieved policy does not answer the question? |

### Final baseline

The following results use the same 24 questions and were recorded on 2026-10-09.

| Pipeline | Recall@5 | MRR | No-evidence F1 | p95 Latency |
|---|---:|---:|---:|---:|
| FTS Only | **1.000** | 0.865 | 0.667 | **67.4 ms** |
| Vector Only | 0.875 | 0.812 | 0.714 | 68.7 ms |
| Hybrid RRF | **1.000** | 0.896 | 0.667 | 115.9 ms |
| Hybrid RRF + BGE-M3 | **1.000** | **0.969** | 0.667 | 736.5 ms |
| Full | **1.000** | **0.969** | **1.000** | 5,703.3 ms |

Interpretation:

- FTS retrieved every answer but also returned related documents for questions
  that had no approved answer.
- RRF and BGE-M3 preserved recall while moving the correct clause upward.
- The Full evidence assessment removed related-but-insufficient candidates and
  correctly separated `no_evidence` cases.
- The most accurate Full path had a p95 latency of about 5.7 seconds, so quality
  and latency must be reported together.

### Full run

```powershell
python -m eval.rag_pipeline_comparison `
  --stages fts_only,vector_only,hybrid_rrf,hybrid_rrf_bge_m3,full `
  --candidate-limit 10 `
  --final-k 5 `
  --save-baseline eval/baselines/openai_rag_final.json
```

Each retrieval channel contributes at most ten short Child candidates, and five
final Parent policy sections are evaluated. These are fixed comparison
conditions, not values tuned to favor a model. See the
[Policy RAG guide](../docs/rag/README_EN.md) for retrieval internals.

Re-run one repaired case with:

```powershell
python -m eval.rag_pipeline_comparison --stages full --case-id RP17
```

JSON, CSV, and Markdown summaries are written under `eval/results/`. The final
baseline is [openai_rag_final.json](baselines/openai_rag_final.json).

## 3. Can retrieval bypass policy access rules?

Access control is evaluated separately from search quality. Allow/deny pairs
verify collection, jurisdiction, department, product, and policy-effective-date
scope on both lexical and Vector paths.

```powershell
python -m eval.policy_access_evaluation --retrieval-mode fts --final-k 5
python -m eval.policy_access_evaluation --retrieval-mode vector --final-k 5
```

Both paths reported 1.000 authorized Recall@5, 1.000 denial accuracy, and zero
out-of-scope exposures. The suite also checks that empty grants skip embedding
and database retrieval entirely.

## 4. How are deterministic rules separated from the LLM Judge?

Python first checks everything that can be decided without another model:

- answer numbers occur in the question or Tool output;
- the expected policy and clause were retrieved;
- cited facts occur in policy content;
- unsupported questions do not invent a policy answer; and
- collection, product, jurisdiction, department, and validity scope hold.

Only nuanced semantic accuracy, analytical quality, and actionability remain
for the optional LLM Judge.

```powershell
python -m eval.run_judge eval/results/evaluation_<timestamp>.json
```

Judge scores supplement deterministic checks; they do not replace Gold Labels.

## 5. Does a Parser change improve retrieval?

Adding Docling does not itself prove an improvement. Simple Parser and Docling
outputs must be ingested into equivalent clean database snapshots and evaluated
with the same 24 questions.

```powershell
pip install -r requirements-docling.txt
python -m src.rag.ingestion <pdf-manifest.csv> --parser docling

python -m eval.rag_pipeline_comparison --parser-label docling
python -m eval.parser_comparison `
  eval/results/simple_report.json `
  eval/results/docling_report.json
```

OCR and table reconstruction remain off for normal text-layer PDFs. Enable them
only for confirmed scans or structurally important complex tables. The included
policies are Markdown, so no Parser advantage is currently claimed.

## 6. Using Colab when BGE-M3 does not fit locally

Colab GPU can act as a temporary reranking service. Run
`notebooks/colab_bge_m3_reranker_api.ipynb`, then set the URL and API key emitted
by the notebook in the current PowerShell session.

```powershell
$env:RAG_RERANKER_BASE_URL = "https://<current-ngrok-url>"
$env:RAG_RERANKER_API_KEY = "<same-colab-secret>"
Invoke-RestMethod "$env:RAG_RERANKER_BASE_URL/health"
```

The URL changes after a Colab restart. Send only the synthetic evaluation
policies through the public tunnel, never real internal documents.

## 7. Fast connectivity and code checks

| Purpose | Command |
|---|---|
| Full code tests | `pytest -q` |
| Review Aspect smoke path | `python -m eval.run_pattern_smoke` |
| Product-analysis and policy-RAG connectivity | `python -m eval.local_two_path_validation` |
| Manual business scenarios | `python -m eval.manual_six_case_validation` |
| BGE-M3 memory preflight | `python -m eval.rag_reranker_benchmark --preflight-only` |

Smoke tests confirm connectivity; they do not replace the fixed 24-case suite.

## Data and output locations

| Path | Contents |
|---|---|
| `eval/datasets/agent_review_cases.json` | 15 product and review Agent questions |
| `eval/datasets/agent_policy_cases.json` | 9 combined review-policy questions |
| `eval/datasets/rag_pipeline_cases.json` | 24 RAG questions and Gold Evidence |
| `eval/datasets/policy_access_cases.json` | 11 access allow/deny cases |
| `eval/results/` | Per-run JSON, CSV, and Markdown |
| `eval/baselines/` | Results frozen for later comparison |

Gold Evidence prefers stable policy `source_id` and
`policy_key:clause_number` identifiers. Multiple valid clauses are represented
as alternative accepted evidence.

## Interpretation limits

- Do not describe the 24-case synthetic result as accuracy on arbitrary queries.
- Tool argument accuracy applies only to cases with explicit argument labels.
- Separate network and model-runtime failures from model-quality failures.
- Preserve model, candidate count, and p50/p95 latency with every result.
- Keep repaired failures in the fixed suite.

## Related guides

- [Policy RAG](../docs/rag/README_EN.md)
- [Model runtime](../docs/local_model_runtime.md)
- [Deployment](../deploy/README_EN.md)
