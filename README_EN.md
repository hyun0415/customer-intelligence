# Customer Intelligence Agent

[한국어](README.md)

A customer intelligence agent that analyzes product and review data to identify recurring complaints, product strengths and weaknesses, and evidence-based improvement priorities.

## Project Goal

The project is designed to reduce the amount of manual review reading and summarization required by marketing, product planning, and VOC teams. Users can ask natural-language questions and receive analyses such as:

- Product information and review overview
- Rating distribution and low-rating ratio analysis
- Helpful review and recurring complaint pattern analysis
- Evidence-based product strength and weakness analysis
- Product, detail-page, and operational improvement recommendations
- Separation of defensible marketing messages from claims that should not be overstated
- Safe handling of missing products and failed searches

## Data

- Dataset: Amazon Reviews 2023
- Category: Beauty and Personal Care
- Products: 555
- Reviews: 203,648
- Negative or neutral reviews rated 3 stars or below: 50,187

`rating_number` represents the total number of ratings shown in Amazon product metadata. `review_count` represents the number of review texts stored in the analysis database.

When the aggregation source is not explicitly included in a Tool response, the agent describes `review_count` as the **retrieved review count** instead of making unsupported claims about its relationship to Amazon's total rating count.

## How It Works

1. The user asks a question about a product or customer response.
2. The agent selects the required retrieval and analysis Tools.
3. The Tools query product and review data from PostgreSQL.
4. The review pattern pipeline runs when recurring complaint analysis is required.
5. The agent combines quantitative statistics, review evidence, and sample limitations.
6. The final response provides key findings and actionable recommendations.

## Core Design Principles

- Do not search for a product when an ASIN is already provided.
- Do not add rating, date, or review-count filters that the user did not request.
- Do not infer complaint causes or customer experiences from rating distributions alone.
- Separate reviewer experiences and claims from verified product information.
- Preserve the category labels returned by the Pattern Tool.
- Distinguish sample-level ratios from population-level incidence rates.
- Do not present unverified authenticity, safety, or causal claims as facts.

## Tech Stack

- Python
- LangGraph / LangChain
- OpenAI API
- PostgreSQL / pgvector
- Docker Compose
- pandas / Parquet
- pytest

## Agent Evaluation

The agent was evaluated on 15 customer and product analysis scenarios using a live PostgreSQL database and the OpenAI API.

The evaluation framework has three layers:

- **Tool evaluation:** validates required, optional, and forbidden Tools and their arguments
- **Rule Checker:** detects unsupported numbers, Tool failures, and sample or aggregation mistakes
- **LLM Judge:** scores accuracy, grounding, analysis, and actionability on a five-point scale

### Latest Full Evaluation Results

| Metric | Result |
|---|---:|
| Completed scenarios | 15 / 15 |
| Completion rate | 100% |
| Tool selection pass | 15 / 15 |
| Tool precision | 1.00 |
| Required Tool recall | 1.00 |
| Tool F1 | 1.00 |
| Forbidden Tool calls | 0 |
| Unlisted Tool calls | 0 |
| Rule-adjusted cases | 0 |
| Average accuracy | 5.00 / 5.00 |
| Average grounding | 4.93 / 5.00 |
| Average analysis | 5.00 / 5.00 |
| Average actionability | 5.00 / 5.00 |
| Average total score | **4.98 / 5.00** |

During the full evaluation, the ambiguous-search case E03 received a grounding score of 4 because the answer described the source of `review_count` beyond what the Tool output explicitly supported. The search-result wording was subsequently changed to **retrieved review count**, and the agent was instructed not to infer its relationship to Amazon's total rating count. The E03 regression test and individual reevaluation then passed.

### Evaluation Coverage

The evaluation set covers:

- Product lookup and product-name search
- Ambiguous search with multiple candidates
- Rating distribution and low-rating ratios
- Complaint analysis based on highly helpful low-rating reviews
- Natural-language condition translation into Tool arguments
- Recurring complaint and review pattern analysis
- Product strengths, weaknesses, and improvement recommendations
- Marketing claim validation and overstatement risk
- Statistical interpretation and sample limitations
- Missing-product and empty-search handling

### Representative Cases

| Case | Capability | Result |
|---|---|---|
| E03 | Multiple candidates for an ambiguous search | Filters out a non-product result and returns several candidates with ASINs |
| E05 | VOC analysis from helpful low-rating reviews | Connects recurring complaint frequency, evidence, impact, and improvements while stating sample limitations |
| E09 | Combined product, rating, and review-pattern analysis | Produces strengths, weaknesses, and action items from quantitative and qualitative evidence |
| E11 | Marketing analysis | Uses helpful reviews and complaint patterns to separate supportable messages from claims that should not be overstated |
| E15 | Search failure and hallucination prevention | Does not substitute a nonexistent product and requests additional identifying information |

## Testing

Run the full test suite:

```powershell
pytest -q
```

Run selected Agent integration tests:

```powershell
pytest tests/test_agent.py -q -k "ambiguous_product_name"
pytest tests/test_agent.py -q -k "marketing_analysis"
```

Run the Agent evaluation and LLM Judge through the `eval/` module:

```powershell
python -m eval.run_agent_evaluation
python -m eval.run_judge <evaluation-json-path>
```

Integration tests and evaluations call the OpenAI API and therefore require available API credits.

## Project Status

Completed work includes:

- Parquet-to-PostgreSQL data loading and data quality checks
- Product and review retrieval Tools
- LangGraph Agent and Tool-routing rules
- Recurring complaint Pattern analysis pipeline
- Fifteen evaluation scenarios and automated evaluation workflow
- Numeric Checker, Rule Checker, and LLM Judge
- Regression tests for Agent Tool routing and grounding

## Roadmap

1. Build a FastAPI-based Agent API
2. Add a Streamlit or web frontend
3. Store and retrieve analysis results
4. Improve semantic review search with embeddings
5. Support time-range, product-group, and competitor comparisons
6. Document Docker-based execution and deployment
7. Add environment-variable, initial-data-load, and API startup instructions

## Notes

This README currently focuses on the problem definition, analysis architecture, and evaluation results. Environment variable examples and the complete execution workflow will be added after the API and deployment structure are finalized.

## Source Data

The agent combines deterministic SQL retrieval for structured product and
review data with hybrid RAG for internal operational policies. PostgreSQL FTS
and pgvector generate candidates, BGE-M3 multi-vector scoring reranks them with
ColBERT late interaction, and a structured LLM check permits only directly
supported evidence to reach the Agent.

Install the optional local reranking dependencies before running policy search:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-rag-rerank.txt
```

Compare the PostgreSQL baseline, ColBERT reranking, and full evidence-validation
pipeline with the same fixed Korean cases:

```powershell
python -m eval.rag_pipeline_comparison
```

JSON and CSV reports are written under `eval/results/` without applying an
arbitrary acceptance threshold.

The evaluated default is 10 candidates per retrieval channel. Reranker
failures fall back to RRF order by default
(`RAG_RERANKER_FALLBACK_TO_RRF=true`), while evidence-validation failures
remain fail-closed as `no_evidence`. The evidence timeout/retry defaults are 15
seconds and one retry.

See [ADR-001](docs/adr/001-hybrid-sql-rag-architecture.md).
