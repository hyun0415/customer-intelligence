import argparse
import json
import platform
from pathlib import Path
from statistics import mean, median
from time import perf_counter

import psutil
from pydantic import BaseModel

from src.rag.config import RagSettings
from src.rag.rerankers import BGEM3ColbertReranker

DEFAULT_INPUT = Path("eval/results/colab_rerank_input.json")
DEFAULT_OUTPUT = Path("eval/results/rag_reranker_cpu_benchmark.json")


class SystemSnapshot(BaseModel):
    processor: str
    physical_cpu: int | None
    logical_cpu: int | None
    total_ram_gib: float
    available_ram_gib: float
    process_rss_gib: float


def system_snapshot() -> SystemSnapshot:
    memory = psutil.virtual_memory()
    return SystemSnapshot(
        processor=platform.processor(),
        physical_cpu=psutil.cpu_count(logical=False),
        logical_cpu=psutil.cpu_count(logical=True),
        total_ram_gib=round(memory.total / 2**30, 3),
        available_ram_gib=round(memory.available / 2**30, 3),
        process_rss_gib=round(psutil.Process().memory_info().rss / 2**30, 3),
    )


def percentile(values: list[float], ratio: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = max(0, min(len(ordered) - 1, int(ratio * len(ordered) + 0.999) - 1))
    return ordered[index]


def parse_candidate_limits(value: str) -> list[int]:
    limits = list(dict.fromkeys(int(part.strip()) for part in value.split(",")))
    if not limits or any(limit <= 0 for limit in limits):
        raise argparse.ArgumentTypeError("candidate limit은 양수여야 합니다.")
    return limits


def preflight(input_path: Path) -> dict:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    snapshot = system_snapshot()
    # BGE-M3 약 5.7억 파라미터의 FP32 가중치와 런타임 버퍼를 고려한 보수적 하한.
    estimated_required_gib = 5.0
    return {
        "system": snapshot.model_dump(),
        "case_count": len(payload["cases"]),
        "candidate_count": sum(len(case["candidates"]) for case in payload["cases"]),
        "estimated_minimum_available_ram_gib": estimated_required_gib,
        "safe_to_run": snapshot.available_ram_gib >= estimated_required_gib,
        "reason": (
            "가용 메모리가 보수적 실행 하한 이상입니다."
            if snapshot.available_ram_gib >= estimated_required_gib
            else "가용 메모리가 BGE-M3 CPU FP32 실행의 보수적 하한보다 적습니다."
        ),
    }


def benchmark(input_path: Path, candidate_limits: list[int]) -> dict:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    before_load = system_snapshot()
    load_started = perf_counter()
    reranker = BGEM3ColbertReranker(
        RagSettings(
            reranker_enabled=True,
            reranker_device="cpu",
            evidence_validation_enabled=False,
        )
    )
    reranker._get_model()
    load_ms = (perf_counter() - load_started) * 1000
    after_load = system_snapshot()

    limit_results = []
    for limit in candidate_limits:
        latencies = []
        for case in payload["cases"]:
            candidates = case["candidates"][:limit]
            started = perf_counter()
            reranker.score(
                case["question"],
                [candidate["content"] for candidate in candidates],
            )
            latencies.append((perf_counter() - started) * 1000)
        limit_results.append(
            {
                "candidate_limit": limit,
                "latency_mean_ms": mean(latencies),
                "latency_p50_ms": median(latencies),
                "latency_p95_ms": percentile(latencies, 0.95),
            }
        )

    return {
        "preflight": preflight(input_path),
        "model_load_ms": load_ms,
        "before_load": before_load.model_dump(),
        "after_load": after_load.model_dump(),
        "process_rss_growth_gib": round(
            after_load.process_rss_gib - before_load.process_rss_gib, 3
        ),
        "limits": limit_results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="BGE-M3 ColBERT CPU 메모리와 후보 수별 지연시간을 측정합니다."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--candidate-limits",
        type=parse_candidate_limits,
        default=parse_candidate_limits("10,20,30,50"),
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="모델을 로드하지 않고 메모리 실행 가능성만 확인합니다.",
    )
    args = parser.parse_args()

    report = (
        {"preflight": preflight(args.input)}
        if args.preflight_only
        else benchmark(args.input, args.candidate_limits)
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"- JSON: {args.output}")


if __name__ == "__main__":
    main()
