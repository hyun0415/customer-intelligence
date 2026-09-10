import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()

# ColBERT 재정렬은 별도로 검증했으므로 이번 실행은 OpenAI Agent와 SQL/RAG
# 도구 연결을 빠르게 확인한다. 실행 전에 환경변수를 지정하면 덮어쓰지 않는다.
os.environ.setdefault("RAG_RERANKER_ENABLED", "false")

from langchain_core.messages import AIMessage, ToolMessage  # noqa: E402

from src.agent import extract_text, run_agent  # noqa: E402
from src.llm.config import ModelRoutingSettings  # noqa: E402


OUTPUT_PATH = Path("eval/results/manual_six_case_validation.txt")
JSON_OUTPUT_PATH = Path("eval/results/manual_six_case_validation.json")

CASES = [
    {
        "id": "RAG-정상",
        "question": "동일 주문의 동일 사고에 무료 재배송은 몇 회까지 가능한가?",
        "expected_tools": ["search_internal_knowledge_tool"],
    },
    {
        "id": "RAG-근거없음",
        "question": "배송 분실 시 1억원의 현금 보상이 승인되어 있는가?",
        "expected_tools": ["search_internal_knowledge_tool"],
    },
    {
        "id": "RAG-안전",
        "question": (
            "고객이 입원과 의료 증상을 언급하면 어떤 절차를 "
            "우선해야 하는가?"
        ),
        "expected_tools": ["search_internal_knowledge_tool"],
    },
    {
        "id": "SQL-상품상세",
        "question": (
            "ASIN B005IHT8KI 제품의 제목, 브랜드, 가격, 평균 평점과 "
            "전체 리뷰 수를 알려줘."
        ),
        "expected_tools": ["get_product_tool"],
    },
    {
        "id": "SQL-평점집계",
        "question": (
            "ASIN B005IHT8KI 제품의 평점 분포와 3점 이하 리뷰 "
            "비율을 알려줘."
        ),
        "expected_tools": ["get_rating_distribution_tool"],
    },
    {
        "id": "SQL-조건조회",
        "question": (
            "ASIN B005IHT8KI에서 helpful_vote가 1 이상인 3점 이하 "
            "리뷰를 공감 투표순으로 정확히 3개 조회해줘."
        ),
        "expected_tools": ["get_helpful_reviews_tool"],
    },
]


def collect_tool_calls(messages) -> list[dict]:
    calls = []
    for message in messages:
        if isinstance(message, AIMessage):
            calls.extend(message.tool_calls)
    return calls


def collect_tool_outputs(messages) -> list[dict]:
    outputs = []
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        outputs.append(
            {
                "name": message.name,
                "content": str(message.content),
            }
        )
    return outputs


def render_text(report: dict) -> str:
    lines = [
        "수동 6개 질문 검증 결과",
        "",
        f"모델 설정: {report['models']}",
        f"ColBERT 재정렬 활성화: {report['reranker_enabled']}",
    ]

    for result in report["cases"]:
        lines.extend(
            [
                "",
                "=" * 72,
                f"[{result['id']}] {result['question']}",
                f"실행 상태: {result['status']}",
                f"사용 도구: {result.get('actual_tools', [])}",
                f"필수 도구 통과: {result.get('tool_pass', False)}",
            ]
        )

        if result["status"] == "completed":
            lines.extend(["최종 답변:", result["answer"]])
        else:
            lines.append(f"오류: {result['error']}")

    return "\n".join(lines) + "\n"


def main() -> None:
    model_settings = ModelRoutingSettings.from_env()
    report = {
        "models": {
            "agent": model_settings.agent_model,
            "aspect_extractor": model_settings.aspect_extractor_model,
            "evidence": model_settings.evidence_model,
            "evaluator": model_settings.evaluator_model,
        },
        "reranker_enabled": os.getenv("RAG_RERANKER_ENABLED", "false"),
        "cases": [],
    }

    for case in CASES:
        print(f"실행 중: {case['id']}", flush=True)
        try:
            result = run_agent(case["question"])
            messages = result["messages"]
            tool_calls = collect_tool_calls(messages)
            actual_tools = [call["name"] for call in tool_calls]
            expected_tools = set(case["expected_tools"])

            report["cases"].append(
                {
                    **case,
                    "status": "completed",
                    "actual_tools": actual_tools,
                    "tool_calls": tool_calls,
                    "tool_outputs": collect_tool_outputs(messages),
                    "tool_pass": expected_tools.issubset(actual_tools),
                    "answer": extract_text(messages[-1].content),
                }
            )
        except Exception as exc:
            report["cases"].append(
                {
                    **case,
                    "status": "failed",
                    "tool_pass": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(render_text(report), encoding="utf-8")
    JSON_OUTPUT_PATH.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    passed = sum(case.get("tool_pass", False) for case in report["cases"])
    print(f"완료: 필수 도구 {passed}/{len(CASES)} 통과")
    print(f"텍스트 결과: {OUTPUT_PATH.resolve()}")
    print(f"JSON 결과: {JSON_OUTPUT_PATH.resolve()}")


if __name__ == "__main__":
    main()
