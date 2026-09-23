# Evaluation Guide

[한국어](README.md) · [Project home](../README_EN.md)

This directory evaluates Agent Tool selection, numeric grounding, review
aspects, policy RAG, and model quality at separate layers. The fixed suite is a
regression and failure-analysis baseline, not a claim of universal accuracy.

Run every command from the repository root.

## Evaluation Layers

| Layer | Responsibility | Model dependency |
|---|---|---|
| pytest | Schemas, Tool contracts, access, deterministic rules | Mostly none |
| Tool and rule checkers | Tool arguments and unsupported numbers | Required for Agent runs |
| RAG stage comparison | Baseline → ColBERT → evidence gate | Depends on stage |
| LLM Judge | Accuracy, grounding, analysis, and actionability | Required |
| Smoke tests | Representative Web, local-model, and GPU paths | Environment-dependent |

## 1. Code Regression Tests

Full suite:

```powershell
pytest -q
```

Focused groups:

```powershell
pytest tests/test_agent.py tests/test_tools.py tests/test_response_guard.py -q
pytest tests/test_review_analysis.py tests/test_numeric_checker.py -q
pytest tests/test_rag_chunking.py tests/test_rag_retrieval.py `
  tests/test_rag_embeddings.py tests/test_rag_routing.py -q
pytest tests/test_web_security.py tests/test_web_operations.py -q
```

Integration tests that do not mock external dependencies may require PostgreSQL,
Redis, or model endpoints. Follow the dependency reported by the failing test.

## 2. Fixed Agent Scenarios

Run the 15 customer and product scenarios and store Tool calls, arguments,
numbers, and responses:

```powershell
python -m eval.run_agent_evaluation
```

Outputs are written to `eval/results/evaluation_<timestamp>.json` and `.csv`.
This run uses live PostgreSQL data and the configured Agent API, so verify `.env`
and API cost before execution.

Generate per-Tool precision and recall:

```powershell
python -m eval.run_tool_metrics eval/results/evaluation_<timestamp>.json
```

## 3. LLM Judge

Judge the latest Agent result with the configured evaluator:

```powershell
python -m eval.run_judge
```

Specify an input and model when needed:

```powershell
python -m eval.run_judge eval/results/evaluation_<timestamp>.json `
  --model <evaluator-model>
```

Judge scores support model comparison and failure classification. Deterministic
numeric and schema checks remain the responsibility of Tool and rule checkers.

## 4. Policy RAG Stage Comparison

The same fixed questions compare:

- `baseline`: PostgreSQL FTS + Embedding + RRF
- `rerank`: baseline + BGE-M3 ColBERT
- `full`: rerank + LLM evidence assessment

```powershell
python -m eval.rag_pipeline_comparison
```

Select stages, cases, or candidates:

```powershell
python -m eval.rag_pipeline_comparison --stages baseline,rerank
python -m eval.rag_pipeline_comparison --stages full --case-id RP12
python -m eval.rag_pipeline_comparison --candidate-limit 10
```

`--candidate-limit` is the number of Children retrieved from **each** FTS and
embedding channel. JSON and CSV outputs under `eval/results/` report Recall@K,
MRR, status accuracy, `no_evidence` precision/recall/F1, and stage latency.

Reuse Colab BGE-M3 scores when the local machine cannot load the model:

```powershell
python -m eval.experiments.export_colab_rerank_input
python -m eval.rag_pipeline_comparison --stages full `
  --precomputed-rerank-results eval/results/colab_bge_m3_rerank_results.json
```

Run `notebooks/colab_bge_m3_rerank_eval.ipynb` in Colab.

## 5. BGE-M3 Resource Checks

Check CPU-memory feasibility without loading the model:

```powershell
python -m eval.rag_reranker_benchmark --preflight-only
```

Measure latency by candidate count only on a host with sufficient memory or GPU:

```powershell
python -m eval.rag_reranker_benchmark --candidate-limits 10,20,30,50
```

The default Web Compose profile may disable the reranker because of local
resource limits. For GPU execution, see the [deployment guide](../deploy/README_EN.md)
and [Terraform guide](../infra/terraform/README_EN.md).

## 6. Representative Smoke Tests

Aspect extraction:

```powershell
python -m eval.run_pattern_smoke
```

Product analysis and policy RAG through OpenAI or local endpoints:

```powershell
python -m eval.local_two_path_validation
```

Six manual business scenarios:

```powershell
python -m eval.manual_six_case_validation
```

Smoke tests establish path connectivity, not full-suite quality.

## Interpretation Rules

- Do not present a near-perfect fixed-set result as accuracy on all user queries.
- Review Pattern ratios describe a selected sample of at most 20 reviews.
- RAG results apply only to the approved evaluation policies and questions.
- Record network or model-download failures separately from quality failures.
- Record model revision, dtype, context, candidates, and p50/p95 latency.
- Keep repaired failures in the regression suite.

## Related Guides

- [Policy RAG](../docs/rag/README_EN.md)
- [Model runtime](../docs/local_model_runtime.md)
- [Deployment](../deploy/README_EN.md)
