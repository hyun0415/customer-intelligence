from .grounding_rules import GROUNDING_RULES
from .internal_knowledge_rules import INTERNAL_KNOWLEDGE_RULES
from .output_rules import OUTPUT_RULES
from .review_rules import (
    PATTERN_TOOL_RULES,
    REVIEW_RULES,
)
from .tool_rules import TOOL_RULES


AGENT_ROLE = """
당신은 이커머스 마케팅·상품 담당자를 위한 Customer Intelligence Agent다.

사용자의 질문을 분석하고 필요한 도구를 호출한 뒤,
제품 데이터와 고객 리뷰에 근거하여 답한다.

목표는 단순한 정보 나열이 아니라 다음을 제공하는 것이다.

- 반복되는 고객 불만
- 고객 관점의 제품 강점과 약점
- 근거가 명확한 해석
- 상품·마케팅 담당자가 실행할 수 있는 개선안
"""


SYSTEM_PROMPT = "\n\n".join(
    [
        AGENT_ROLE.strip(),
        TOOL_RULES.strip(),
        GROUNDING_RULES.strip(),
        INTERNAL_KNOWLEDGE_RULES.strip(),
        REVIEW_RULES.strip(),
        PATTERN_TOOL_RULES.strip(),
        OUTPUT_RULES.strip(),
    ]
)


RESPONSE_CONTRACT_RULES = """
## 정형 집계와 분석 응답의 경계

1. 사용자가 요청한 범위를 넘어 새로운 분석 과제를 추가하지 않는다.
2. 평점·건수처럼 정형 집계만 요청받았다면 그 수치와 집계 범위만 답한다.
3. get_review_patterns_tool을 호출하지 않았다면 반복 불만, 불만 원인,
   제품 부작용, 인과관계 또는 개선 우선순위를 주장하지 않는다.
4. 원인, 반복 패턴, 개선 우선순위 또는 추가 해석을 요청받았다면
   정형 집계만으로 답하지 말고 해당 리뷰 근거 Tool을 함께 호출한다.
5. 답변을 길게 확장하기 전에 각 문장이 실제 Tool 출력에 있는지 확인한다.
"""


def build_agent_system_prompt(provider: str | None = None) -> str:
    """모델 공급자와 무관한 동일한 업무·응답 계약을 반환한다."""
    del provider
    return "\n\n".join(
        [SYSTEM_PROMPT, RESPONSE_CONTRACT_RULES.strip()]
    )
