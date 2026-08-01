from .grounding_rules import GROUNDING_RULES
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
        REVIEW_RULES.strip(),
        PATTERN_TOOL_RULES.strip(),
        OUTPUT_RULES.strip(),
    ]
)
