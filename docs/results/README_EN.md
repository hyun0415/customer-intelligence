# Published Evaluation Results

This directory publishes only the compact results needed to verify the final
project claims. Per-case execution logs and repeated experiment outputs are
generated under `eval/results/` and remain outside Git.

## Published scope

| File | Contents |
|---|---|
| `final_evaluation_summary.csv` | Final RAG stage comparison, Agent Tool metrics, and policy access results |
| `eval/datasets/` | Evaluation questions and explicit gold conditions |
| `eval/baselines/openai_rag_final.json` | Final per-case baseline for later comparisons |

The final evaluation ran on 2026-10-09 with ten synthetic approved policies and
24 policy questions. Every retrieval channel used ten candidates and every stage
returned a final Parent `K=5`. BGE-M3 reranking ran through the Colab GPU service,
while the full pipeline used the OpenAI profile for evidence assessment.

The Agent suite covered 15 review questions and nine review-policy questions.
All 24 cases selected the required Tools, and both cases with explicit argument
gold labels passed. A separate 11-case access evaluation reported authorized
Recall@5 of 1.000, denial accuracy of 1.000, and zero out-of-scope exposures.

These results describe a small fixed regression set, not accuracy for arbitrary
enterprise data or general questions. See the [evaluation guide](../../eval/README_EN.md)
for commands and metric definitions.
