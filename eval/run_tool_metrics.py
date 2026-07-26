import argparse
import json
from pathlib import Path

from eval.reports.tool_metrics import (
    build_tool_metrics,
    save_tool_metrics_csv,
    save_tool_metrics_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "input_path",
        type=Path,
        help="Agent 평가 JSON 파일 경로",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = args.input_path

    results = json.loads(
        input_path.read_text(
            encoding="utf-8",
        )
    )

    metrics = build_tool_metrics(results)

    json_path = input_path.with_name(
        f"tool_metrics_{input_path.stem}.json"
    )
    csv_path = input_path.with_name(
        f"tool_metrics_{input_path.stem}.csv"
    )

    save_tool_metrics_json(
        metrics=metrics,
        output_path=json_path,
    )
    save_tool_metrics_csv(
        per_tool_metrics=metrics[
            "per_tool_metrics"
        ],
        output_path=csv_path,
    )

    print("Tool Metrics 생성 완료")
    print(f"- JSON: {json_path}")
    print(f"- CSV: {csv_path}")


if __name__ == "__main__":
    main()