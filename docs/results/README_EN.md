# Published Evaluation Results

This directory publishes only the compact results needed to verify the final
project claims. Per-case execution logs and repeated experiment outputs are
generated under `eval/results/` and remain outside Git.

## Published scope

| File | Contents |
|---|---|
| `final_evaluation_summary.csv` | Final RAG stage comparison, Agent Tool metrics, and policy access results |
| `eval/datasets/` | Evaluation questions and explicit gold conditions |
| `eval/baselines/openai_rag_source_clause_20261018.json` | Final per-case Source and clause baseline |

The final RAG evaluation ran on 2026-10-18 with ten synthetic approved policies and
24 policy questions. Every retrieval channel used ten candidates and every stage
returned a final Parent `K=5`. BGE-M3 reranking ran through the Colab GPU service,
while the full pipeline used the OpenAI profile for evidence assessment.

Source Recall and MRR measure whether the correct policy document was found.
Clause Hit@5 and Clause MRR measure whether a retrieved Parent Chunk contains a
clause identified by `source_id + rule_key`. The per-case CSV also records all
retrieved Parent Chunk IDs, matching Parent Chunk IDs, and the first matching
rank.

The Agent suite covered 15 review questions and nine review-policy questions.
All 24 cases selected the required Tools, and both cases with explicit argument
gold labels passed. A separate 11-case access evaluation reported authorized
Recall@5 of 1.000, denial accuracy of 1.000, and zero out-of-scope exposures.

These results describe a small fixed regression set, not accuracy for arbitrary
enterprise data or general questions. See the [evaluation guide](../../eval/README_EN.md)
for commands and metric definitions.
