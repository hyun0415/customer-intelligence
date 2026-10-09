import argparse
import json
from pathlib import Path
from typing import Any

STAGE_ALIASES = {"baseline": "hybrid_rrf", "rerank": "hybrid_rrf_bge_m3"}
METRICS = ("recall_at_k", "mrr", "no_evidence_f1", "latency_p95_ms")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _case_ids(report: dict[str, Any]) -> set[str]:
    return {case["case_id"] for case in report.get("cases", [])}


def compare_parser_reports(
    simple: dict[str, Any], docling: dict[str, Any]
) -> list[dict[str, Any]]:
    if _case_ids(simple) != _case_ids(docling):
        raise ValueError("Simple과 Docling 보고서의 평가 case가 다릅니다.")
    simple_config = simple.get("configuration", {})
    docling_config = docling.get("configuration", {})
    for key in ("candidate_limit_per_channel", "final_k"):
        if (
            key in simple_config
            and key in docling_config
            and simple_config[key] != docling_config[key]
        ):
            raise ValueError(f"Parser 비교의 {key} 설정이 다릅니다.")

    def by_stage(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
        return {
            STAGE_ALIASES.get(item["stage"], item["stage"]): item
            for item in report.get("stages", [])
        }

    simple_stages = by_stage(simple)
    docling_stages = by_stage(docling)
    rows = []
    for stage in sorted(simple_stages.keys() & docling_stages.keys()):
        left = simple_stages[stage]
        right = docling_stages[stage]
        rows.append(
            {
                "stage": stage,
                "simple": {metric: left[metric] for metric in METRICS},
                "docling": {metric: right[metric] for metric in METRICS},
                "delta_docling_minus_simple": {
                    metric: float(right[metric]) - float(left[metric])
                    for metric in METRICS
                },
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="동일한 RAG 고정 세트의 Simple/Docling 결과를 비교합니다."
    )
    parser.add_argument("simple_report", type=Path)
    parser.add_argument("docling_report", type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("eval/results/parser_comparison.json"),
    )
    args = parser.parse_args()
    rows = compare_parser_reports(_load(args.simple_report), _load(args.docling_report))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Parser comparison: {args.output}")


if __name__ == "__main__":
    main()
