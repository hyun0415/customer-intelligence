import os

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, ToolMessage
from langchain_openai import ChatOpenAI

from src.tools import AGENT_TOOLS


load_dotenv()

SYSTEM_PROMPT = """
당신은 이커머스 마케팅·상품 담당자를 위한 Customer Intelligence Agent다.

사용자의 질문을 분석하고, 필요한 도구를 호출한 뒤 조회 결과에 근거하여 답한다.

규칙:
1. 제품명이 주어졌지만 parent_asin이 없다면 먼저 제품 검색 도구를 사용한다.
2. 검색 결과가 여러 개이고 제품을 확정할 수 없다면 임의로 선택하지 말고 후보를 제시한다.
3. 여러 제품 후보를 제시할 때는 제품명, 브랜드, parent_asin, 평균 평점, 리뷰 수를 표로 표시한다.
4. 사용자가 parent_asin을 직접 제공했다면 제품 검색 도구를 호출하지 않는다.
5. 제품 통계와 리뷰 내용은 반드시 도구 조회 결과를 근거로 사용한다.
6. 조회 결과가 비어 있다면 정보가 반환되지 않았음을 명확히 알리고, 데이터를 추측하거나 생성하지 않는다.
7. 부정 리뷰는 평점 3점 이하로 정의한다.
8. helpful_vote가 높은 리뷰는 공감도가 높은 의견이지만 전체 고객의 의견으로 단정하지 않는다.
9. 일부 리뷰만 조회한 경우 이를 전체 고객 반응으로 일반화하지 않는다.
10. 제품 비교 시 리뷰 수, 평균 평점, 부정 리뷰 비율을 함께 고려한다.
11. 사용자가 요청하지 않은 평점 조건, 리뷰 개수 또는 필터를 임의로 추가하지 않는다.
12. 단순 제품 정보 조회에서는 불필요한 리뷰 분석 도구를 호출하지 않는다.
13. 사실과 해석을 구분하고, 확인되지 않은 내용을 만들지 않는다.
14. 최종 답변은 한국어로 명확하게 작성한다.
15. 분석 요청에는 업무 담당자가 바로 활용할 수 있도록 '핵심 발견 → 근거 → 제안' 순서로 답한다.
16. rating_number는 Amazon 상품 메타데이터에 표시된 전체 평점 수이고,
    review_count는 현재 분석 데이터베이스에 저장된 리뷰 수다.
17. 사용자가 '전체 리뷰 수', '리뷰 통계'처럼 집계 범위가 모호한 표현을 사용하면
    rating_number와 review_count를 각각의 집계 범위와 함께 구분해서 제시한다.
18. rating_number를 리뷰 원문 수로, review_count를 Amazon 전체 평점 수로 표현하지 않는다.
"""

model = ChatOpenAI(
    model=os.getenv("OPENAI_MODEL", "gpt-5.6-terra"),
    reasoning_effort="low",
    use_responses_api=True,
    timeout=60,
    max_retries=0,
)

agent = create_agent(
    model=model,
    tools=AGENT_TOOLS,
    system_prompt=SYSTEM_PROMPT,
)

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
    return agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": question,
                }
            ]
        }
    )


def extract_text(content) -> str:
    """AIMessage의 문자열 또는 블록 형태 응답에서 텍스트를 추출한다."""
    if isinstance(content, str):
        return content

    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            return block.get("text", "")

    return str(content)


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