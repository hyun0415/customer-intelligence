import pytest

from eval.parser_comparison import compare_parser_reports


def report(parser, case_ids, recall):
    return {
        "configuration": {
            "parser": parser,
            "candidate_limit_per_channel": 10,
            "final_k": 5,
        },
        "stages": [
            {
                "stage": "hybrid_rrf",
                "recall_at_k": recall,
                "mrr": 0.5,
                "no_evidence_f1": 0.8,
                "latency_p95_ms": 100,
            }
        ],
        "cases": [{"case_id": case_id} for case_id in case_ids],
    }


def test_parser_comparison_requires_same_cases_and_calculates_delta():
    rows = compare_parser_reports(
        report("simple", ["R1"], 0.5),
        report("docling", ["R1"], 0.75),
    )

    assert rows[0]["delta_docling_minus_simple"]["recall_at_k"] == 0.25

    with pytest.raises(ValueError, match="평가 case가 다릅니다"):
        compare_parser_reports(
            report("simple", ["R1"], 0.5),
            report("docling", ["R2"], 0.75),
        )


def test_parser_comparison_requires_same_retrieval_limits():
    simple = report("simple", ["R1"], 0.5)
    docling = report("docling", ["R1"], 0.75)
    docling["configuration"]["final_k"] = 10

    with pytest.raises(ValueError, match="final_k 설정이 다릅니다"):
        compare_parser_reports(simple, docling)
