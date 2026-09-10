import json
import os
import sys
from pathlib import Path
from time import perf_counter

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

from langchain_core.messages import AIMessage, ToolMessage  # noqa: E402

from src.agent import extract_text, run_agent  # noqa: E402
from src.model_config import ModelRoutingSettings  # noqa: E402


CASES = [
    {
        "id": "PRODUCT-01",
        "path": "product_analysis",
        "question": (
            "ASIN B00TYAGMP4 상품의 반복 불만과 개선 우선순위를 "
            "리뷰 원문 근거와 함께 알려줘."
        ),
        "required_tool": "get_review_patterns_tool",
    },
    {
        "id": "RAG-01",
        "path": "policy_rag",
        "question": "동일 주문의 동일 사고에 무료 재배송은 몇 회까지 가능한가?",
        "required_tool": "search_internal_knowledge_tool",
        "expected_source_id": "sample_commerce_reshipment_policy",
    },
]


def _tool_trace(messages) -> tuple[list[dict], list[dict]]:
    calls = []
    outputs = []
    for message in messages:
        if isinstance(message, AIMessage):
            calls.extend(
                {"name": call["name"], "args": call.get("args", {})}
                for call in message.tool_calls
            )
        elif isinstance(message, ToolMessage):
            content = str(message.content)
            try:
                parsed = json.loads(content)
            except json.JSONDecodeError:
                parsed = content
            outputs.append({"name": message.name, "content": parsed})
    return calls, outputs


def _contains_source(outputs: list[dict], source_id: str) -> bool:
    return source_id in json.dumps(outputs, ensure_ascii=False, default=str)


def main() -> None:
    settings = ModelRoutingSettings.from_env()
    report = {
        "configuration": {
            "agent": settings.agent.model,
            "aspect_extractor": settings.aspect_extractor.model,
            "evidence": settings.evidence.model,
            "reranker_enabled": os.getenv("RAG_RERANKER_ENABLED", "true"),
            "reranker_base_url_configured": bool(
                os.getenv("RAG_RERANKER_BASE_URL")
            ),
        },
        "cases": [],
    }

    for case in CASES:
        started_at = perf_counter()
        try:
            result = run_agent(case["question"])
            messages = result["messages"]
            calls, outputs = _tool_trace(messages)
            tool_names = [call["name"] for call in calls]
            tool_pass = case["required_tool"] in tool_names
            source_pass = True
            if case.get("expected_source_id"):
                source_pass = _contains_source(outputs, case["expected_source_id"])
            answer = extract_text(messages[-1].content)
            report["cases"].append(
                {
                    **case,
                    "status": "completed",
                    "latency_seconds": round(perf_counter() - started_at, 3),
                    "tool_calls": calls,
                    "tool_outputs": outputs,
                    "tool_pass": tool_pass,
                    "source_pass": source_pass,
                    "pass": tool_pass and source_pass and bool(answer.strip()),
                    "answer": answer,
                }
            )
        except Exception as exc:
            report["cases"].append(
                {
                    **case,
                    "status": "failed",
                    "latency_seconds": round(perf_counter() - started_at, 3),
                    "pass": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    output = PROJECT_ROOT / "eval/results/local_two_path_validation.json"
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    for result in report["cases"]:
        print(
            f"{result['id']}: pass={result['pass']} "
            f"latency={result['latency_seconds']}s"
        )
        if not result["pass"]:
            print(result.get("error", "required tool/source/answer check failed"))
    print(output)


if __name__ == "__main__":
    main()
