from eval.rules.numeric_checker import find_unsupported_numbers


def test_percentage_formula_multiplier_is_allowed():
    case = {
        "question": "부정 리뷰 비율을 계산해줘.",
        "answer": "1,295 ÷ 5,226 × 100 = 24.8%",
        "tool_calls": [],
        "tool_outputs": [
            {
                "output": {
                    "negative_count": 1295,
                    "review_count": 5226,
                }
            }
        ],
    }

    assert find_unsupported_numbers(case) == []

def test_percentage_total_is_allowed():
    case = {
        "question": "평점 분포를 계산해줘.",
        "answer": "전체 평점 비율의 합계는 100.00%입니다.",
        "tool_calls": [],
        "tool_outputs": [],
    }

    assert find_unsupported_numbers(case) == []