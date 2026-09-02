import json

from eval.rag_reranker_benchmark import parse_candidate_limits, preflight


def test_parse_candidate_limits_deduplicates_in_order():
    assert parse_candidate_limits("10,20,10") == [10, 20]


def test_preflight_counts_cases_and_candidates(tmp_path):
    input_path = tmp_path / "input.json"
    input_path.write_text(
        json.dumps(
            {
                "cases": [
                    {"candidates": [{}, {}]},
                    {"candidates": [{}]},
                ]
            }
        ),
        encoding="utf-8",
    )

    report = preflight(input_path)

    assert report["case_count"] == 2
    assert report["candidate_count"] == 3
    assert isinstance(report["safe_to_run"], bool)
