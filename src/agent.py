import logging
from functools import lru_cache
from time import perf_counter

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage

from src.llm.clients import build_chat_model
from src.llm.config import ModelRole, ModelRoutingSettings
from src.prompts import build_agent_system_prompt
from src.response_contract import apply_response_contract
from src.tools import AGENT_TOOLS

load_dotenv()

logger = logging.getLogger("customer_intelligence.agent")


@lru_cache(maxsize=1)
def get_agent():
    """API 시작을 막지 않도록 Agent graph를 첫 요청에서 한 번만 생성한다."""
    started_at = perf_counter()
    model_settings = ModelRoutingSettings.from_env()
    model = build_chat_model(ModelRole.AGENT, settings=model_settings)
    agent = create_agent(
        model=model,
        tools=AGENT_TOOLS,
        system_prompt=build_agent_system_prompt(),
    )
    logger.info(
        "agent_initialized duration_ms=%.1f model=%s provider=%s",
        (perf_counter() - started_at) * 1000,
        model_settings.agent.model,
        model_settings.agent.provider,
    )
    return agent


def print_tool_trace(messages):
    print("\n도구 호출 기록")

    tool_called = False

    for message in messages:
        if isinstance(message, AIMessage):
            for tool_call in message.tool_calls:
                tool_called = True
                print(f"\n호출: {tool_call['name']}")
                print(f"입력: {tool_call['args']}")

        elif isinstance(message, ToolMessage):
            content = str(message.content)
            preview = content[:500]

            print(f"결과: {preview}")

            if len(content) > 500:
                print("... 결과 생략")

    if not tool_called:
        print("호출된 도구가 없습니다.")


def run_agent(question: str):
    """에이전트 실행 결과 전체를 반환한다."""
    return run_agent_messages([{"role": "user", "content": question}])


def run_agent_messages(messages: list[dict[str, str]]):
    """저장된 대화 이력을 포함해 에이전트를 실행한다."""
    if not messages:
        raise ValueError("에이전트에 전달할 메시지가 없습니다.")
    result = get_agent().invoke({"messages": messages})
    return apply_response_contract(result)


def extract_text(content) -> str:
    """AIMessage의 문자열 또는 블록 형태 응답에서 텍스트를 추출한다."""
    if isinstance(content, str):
        return content

    if not isinstance(content, list):
        return str(content)

    texts = []

    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text", "")

            if text:
                texts.append(text)

    return "\n".join(texts).strip()


def ask(question: str) -> str:
    result = run_agent(question)

    print_tool_trace(result["messages"])

    return extract_text(result["messages"][-1].content)


if __name__ == "__main__":
    question = """
    ASIN B005IHT8KI 제품의 전체 리뷰 통계를 확인하고,
    공감 투표가 높은 3점 이하 리뷰를 바탕으로
    고객들이 가장 공감한 불만 3가지를 분석해줘.

    각 불만에 대해 다음을 포함해줘.
    - 불만 요약
    - 대표 리뷰 근거와 helpful_vote
    - 해석
    - 상품 또는 판매 페이지 개선 제안
    """

    print("질문")
    print(question)

    print("\n답변")
    print(ask(question))
