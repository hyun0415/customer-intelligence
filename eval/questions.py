EVAL_CASES = [
    {
        "id": "E01",
        "category": "제품 조회",
        "question": (
            "ASIN {valid_asin} 제품의 제목, 브랜드, 가격, "
            "평균 평점과 전체 리뷰 수를 알려줘."
        ),
        "expected_tools": ["get_product_tool"],
        "forbidden_tools": ["search_product_tool"],
        "evaluation_focus": "ASIN 직접 조회와 기본 정보의 정확성",
    },
    {
        "id": "E02",
        "category": "제품 검색",
        "question": "Fanola No Yellow Shampoo 제품을 찾아줘.",
        "expected_tools": ["search_product_tool"],
        "forbidden_tools": [],
        "evaluation_focus": "제품명이 주어졌을 때 검색 도구 사용",
    },
    {
        "id": "E03",
        "category": "모호한 검색",
        "question": (
            "shampoo 제품을 찾아줘. 하나를 임의로 선택하지 말고 "
            "관련 후보를 여러 개 ASIN과 함께 보여줘."
        ),
        "expected_tools": ["search_product_tool"],
        "forbidden_tools": [],
        "evaluation_focus": "여러 후보와 식별 가능한 ASIN 제시",
    },
    {
        "id": "E04",
        "category": "평점 분석",
        "question": (
            "ASIN {valid_asin} 제품의 평점 분포와 "
            "3점 이하 부정 리뷰 비율을 분석해줘."
        ),
        "expected_tools": ["get_rating_distribution_tool"],
        "optional_tools": ["get_product_tool"],
        "forbidden_tools": ["search_product_tool"],
        "evaluation_focus": "평점 분포와 부정 비율의 근거 있는 해석",
    },
    {
        "id": "E05",
        "category": "불만 분석",
        "question": (
            "ASIN {valid_asin}에서 helpful_vote가 높은 "
            "3점 이하 리뷰 20개를 바탕으로 주요 불만 3가지를 분석해줘."
        ),
        "required_tools": ["get_review_patterns_tool"],
        "optional_tools": ["get_helpful_reviews_tool"],
        "forbidden_tools": ["search_product_tool"],
        "evaluation_focus": "고공감 부정 리뷰에서 구체적인 불만 도출",
    },
    {
        "id": "E06",
        "category": "조건 해석",
        "question": (
            "ASIN {valid_asin}에서 평점 제한 없이 "
            "helpful_vote가 높은 리뷰 10개를 요약해줘."
        ),
        "expected_tools": ["get_helpful_reviews_tool"],
        "expected_args": {
            "get_helpful_reviews_tool": {
                "limit": 10,
                "min_helpful_votes": 1
            }
        },
        "forbidden_tools": ["search_product_tool"],
        "evaluation_focus": "요청하지 않은 평점 조건을 추가하지 않는지",
    },
    {
        "id": "E07",
        "category": "조건 해석",
        "question": (
            "ASIN {valid_asin}의 helpful_vote가 1 이상인 "
            "3점 이하 리뷰를 정확히 7개 조회해줘."
        ),
        "expected_tools": ["get_helpful_reviews_tool"],
        "expected_args": {
            "get_helpful_reviews_tool": {
                "limit": 7,
                "rating_max": 3,
                "min_helpful_votes": 1,
            }
        },
        "forbidden_tools": ["search_product_tool"],
        "evaluation_focus": "limit, rating_max, min_helpful_votes 전달",
    },
    {
        "id": "E08",
        "category": "반복 불만",
        "question": (
            "ASIN {valid_asin}의 공감도 높은 부정 리뷰를 조사해서 "
            "여러 리뷰에서 반복되는 고객 불만을 찾아줘."
        ),
        "required_tools": [
            "get_review_patterns_tool",
        ],
        "optional_tools": [
            "get_helpful_reviews_tool",
        ],
        "forbidden_tools": ["search_product_tool"],
        "evaluation_focus": "개별 리뷰를 나열하지 않고 반복 패턴 도출",
    },
    {
        "id": "E09",
        "category": "강약점 분석",
        "question": (
            "ASIN {valid_asin} 제품의 고객 관점 강점과 약점을 분석해줘. "
            "평점 통계와 실제 리뷰를 모두 근거로 사용해줘."
        ),
        "forbidden_tools": ["search_product_tool"],
        "required_tools": [
            "get_product_tool",
            "get_rating_distribution_tool",
            "get_review_patterns_tool",
        ],
        "optional_tools": [
            "get_helpful_reviews_tool",
            "get_negative_reviews_tool",
            "get_recent_reviews_tool",
        ],
        "any_of_tools": [
            "get_helpful_reviews_tool",
            "get_recent_reviews_tool",
            "get_negative_reviews_tool",
        ],
        "evaluation_focus": "정량 통계와 정성 리뷰의 결합",
    },
    {
        "id": "E10",
        "category": "개선안",
        "question": (
            "ASIN {valid_asin}의 주요 불만을 분석하고 "
            "상품 담당자가 실행할 수 있는 개선안 3가지를 제안해줘."
        ),
        "required_tools": [
            "get_review_patterns_tool",
        ],
        "optional_tools": [
            "get_product_tool",
            "get_rating_distribution_tool",
            "get_helpful_reviews_tool",
            "get_negative_reviews_tool",
        ],
        "forbidden_tools": ["search_product_tool"],
        "evaluation_focus": "불만 근거와 개선안 사이의 논리적 연결",
    },
    {
        "id": "E11",
        "category": "마케팅 활용",
        "question": (
            "ASIN {valid_asin}의 리뷰를 바탕으로 마케팅에서 강조할 점과 "
            "과장하면 안 되는 점을 구분해줘."
        ),
        "expected_tools": [
            "get_product_tool",
            "get_helpful_reviews_tool",
        ],
        "optional_tools": [
            "get_negative_reviews_tool",
            "get_rating_distribution_tool",
            "get_recent_reviews_tool",
            "get_review_patterns_tool",
        ],
        "forbidden_tools": ["search_product_tool"],
        "evaluation_focus": "리뷰 근거 기반 메시지와 위험 요소 구분",
    },
    {
        "id": "E12",
        "category": "통계 해석",
        "question": (
            "ASIN {valid_asin}은 평균 평점만 보면 좋은 제품인지 평가해줘. "
            "평점 분포와 부정 리뷰도 함께 고려해줘."
        ),
        "required_tools": [
            "get_product_tool",
            "get_rating_distribution_tool",
        ],
        "any_of_tools": [
            "get_negative_reviews_tool",
            "get_helpful_reviews_tool",
        ],
        "forbidden_tools": ["search_product_tool"],
        "evaluation_focus": "평균 평점 하나에 의존하지 않는 해석",
    },
    {
        "id": "E13",
        "category": "표본 한계",
        "question": (
            "ASIN {valid_asin}의 helpful_vote 상위 리뷰 5개로 "
            "고객 반응을 요약하되 분석의 한계도 설명해줘."
        ),
        "expected_tools": ["get_helpful_reviews_tool"],
        "forbidden_tools": ["search_product_tool"],
        "evaluation_focus": "소수·고공감 리뷰의 표본 편향 명시",
    },
    {
        "id": "E14",
        "category": "예외 처리",
        "question": (
            "ASIN {invalid_asin} 제품의 상세 정보와 리뷰 통계를 알려줘."
        ),
        "expected_tools": ["get_product_tool"],
        "forbidden_tools": ["search_product_tool"],
        "evaluation_focus": "없는 제품을 추측하지 않고 명확하게 안내",
    },
    {
        "id": "E15",
        "category": "검색 실패",
        "question": (
            "zxqv-not-existing-product-92837 제품을 찾아서 "
            "고객 반응을 분석해줘."
        ),
        "expected_tools": ["search_product_tool"],
        "forbidden_tools": [],
        "evaluation_focus": "검색 결과가 없을 때 임의의 제품을 생성하지 않는지",
    },
]