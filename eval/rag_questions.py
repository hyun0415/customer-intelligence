RAG_EVAL_CASES = [
    {
        "id": "R01",
        "question": "ASIN {valid_asin}에서 파손 불만이 반복될 때 재배송이 가능한가?",
        "required_tools": [
            "get_review_patterns_tool",
            "search_internal_knowledge_tool",
        ],
        "focus": "리뷰 근거와 재배송 정책 근거 분리",
    },
    {
        "id": "R02",
        "question": "이미 보상 쿠폰을 받은 고객에게 추가 쿠폰 지급이 가능한가?",
        "required_tools": ["search_internal_knowledge_tool"],
        "focus": "보상과 프로모션 중복 정책 검색",
    },
    {
        "id": "R03",
        "question": "ASIN {valid_asin}의 반복 불만은 escalation 대상인가?",
        "required_tools": [
            "get_review_patterns_tool",
            "search_internal_knowledge_tool",
        ],
        "focus": "반복 불만과 CS SOP 결합",
    },
    {
        "id": "R04",
        "question": "내부 정책에 없는 보상 기준을 알려줘.",
        "required_tools": ["search_internal_knowledge_tool"],
        "focus": "근거 없음과 hallucination 방지",
    },
    {
        "id": "R05",
        "question": "2026년 3월에 유효했던 재배송 정책을 알려줘.",
        "required_tools": ["search_internal_knowledge_tool"],
        "focus": "effective_at과 정책 버전 정확성",
    },
]
