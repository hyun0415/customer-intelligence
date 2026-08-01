from collections.abc import Callable

from .judge import LLMJudge
from .rule_checker import run_rule_checks
from .schemas import RuleCheckResult


SCORE_WEIGHTS = {
    "accuracy_score": 0.35,
    "grounding_score": 0.30,
    "analysis_score": 0.20,
    "actionability_score": 0.15,
}


def calculate_total_score(scores: dict) -> float:
    total = sum(
        float(scores[name]) * weight
        for name, weight in SCORE_WEIGHTS.items()
    )

    return round(total, 2)


def has_existing_scores(case: dict) -> bool:
    score_fields = [
        "accuracy_score",
        "grounding_score",
        "analysis_score",
        "actionability_score",
    ]

    return all(
        case.get(field) not in ("", None)
        for field in score_fields
    )


def cap_score(
    score: int,
    maximum: int,
) -> int:
    return min(score, maximum)


def apply_rule_caps(
    scores: dict,
    rule_result: RuleCheckResult,
) -> tuple[dict, list[str]]:
    """
    명백한 규칙 위반이 있을 때 LLM Judge 점수의 상한을 적용한다.

    LLM 점수를 완전히 대체하지 않고,
    결정적 오류만 강제로 반영한다.
    """
    final_scores = dict(scores)
    adjustments = []

    if not rule_result.answer_present:
        final_scores["accuracy_score"] = 1
        final_scores["grounding_score"] = 1
        final_scores["analysis_score"] = 1
        final_scores["actionability_score"] = 1
        adjustments.append(
            "답변이 비어 있어 모든 점수를 1점으로 조정했습니다."
        )
        return final_scores, adjustments

    if not rule_result.tool_usage_pass:
        final_scores["accuracy_score"] = cap_score(
            final_scores["accuracy_score"],
            2,
        )
        final_scores["grounding_score"] = cap_score(
            final_scores["grounding_score"],
            2,
        )
        adjustments.append(
            "필수 Tool 선택 또는 실행 실패로 "
            "accuracy와 grounding을 "
            "최대 2점으로 제한했습니다."
        )

    if not rule_result.expected_args_pass:
        final_scores["accuracy_score"] = cap_score(
            final_scores["accuracy_score"],
            3,
        )
        final_scores["grounding_score"] = cap_score(
            final_scores["grounding_score"],
            3,
        )
        adjustments.append(
            "Tool 인자 불일치로 accuracy와 grounding을 "
            "최대 3점으로 제한했습니다."
        )

    if (
        not rule_result.tool_outputs_present
        and rule_result.tool_usage_pass
    ):
        final_scores["grounding_score"] = cap_score(
            final_scores["grounding_score"],
            2,
        )
        adjustments.append(
            "Tool 원본 출력이 없어 grounding을 "
            "최대 2점으로 제한했습니다."
        )

    unsupported_count = len(
        rule_result.unsupported_numbers
    )

    if unsupported_count >= 3:
        final_scores["accuracy_score"] = cap_score(
            final_scores["accuracy_score"],
            3,
        )
        adjustments.append(
            "검증되지 않은 숫자 후보가 3개 이상이므로 "
            "accuracy를 최대 3점으로 제한했습니다."
        )

    elif unsupported_count >= 1:
        final_scores["accuracy_score"] = cap_score(
            final_scores["accuracy_score"],
            4,
        )
        adjustments.append(
            "검증되지 않은 숫자 후보가 있어 "
            "accuracy를 최대 4점으로 제한했습니다."
        )

    return final_scores, adjustments


def evaluate_case(
    case: dict,
    judge: LLMJudge,
    overwrite: bool = False,
) -> dict:
    evaluated_case = dict(case)

    if case.get("status") != "completed":
        evaluated_case["judge_status"] = "skipped"
        evaluated_case["review_notes"] = (
            case.get("review_notes")
            or "Agent 실행이 완료되지 않아 채점을 건너뛰었습니다."
        )
        return evaluated_case

    if has_existing_scores(case) and not overwrite:
        evaluated_case["judge_status"] = "already_scored"
        return evaluated_case

    try:
        # 1단계: Python Rule Checker
        rule_result = run_rule_checks(case)

        # 2단계: GPT-5-sol Judge
        judge_result = judge.evaluate(
            case=case,
            rule_result=rule_result,
        )

        judge_output = judge_result.model_dump()

        review_notes = judge_output.pop("review_notes")
        strengths = judge_output.pop("strengths")
        problems = judge_output.pop("problems")
        evidence = judge_output.pop("evidence")
        suggestions = judge_output.pop("suggestions")

        # 3단계: 규칙 기반 최종 보정
        final_scores, adjustments = apply_rule_caps(
            scores=judge_output,
            rule_result=rule_result,
        )

        total_score = calculate_total_score(
            final_scores
        )

        evaluated_case.update(final_scores)
        evaluated_case["total_score"] = total_score
        evaluated_case["review_notes"] = review_notes

        evaluated_case["rule_check"] = (
            rule_result.model_dump()
        )
        evaluated_case["score_adjustments"] = adjustments
        evaluated_case["raw_judge_scores"] = judge_output
        evaluated_case["strengths"] = strengths
        evaluated_case["problems"] = problems
        evaluated_case["evidence"] = evidence
        evaluated_case["suggestions"] = suggestions
        evaluated_case["review_notes"] = review_notes

        evaluated_case["judge_status"] = "completed"
        evaluated_case["judge_error"] = ""

    except Exception as error:
        evaluated_case["judge_status"] = "error"
        evaluated_case["judge_error"] = str(error)

        if not evaluated_case.get("review_notes"):
            evaluated_case["review_notes"] = (
                f"자동 채점 실패: {error}"
            )

    return evaluated_case


def evaluate_cases(
    cases: list[dict],
    judge: LLMJudge,
    overwrite: bool = False,
    on_case_completed: Callable[
        [dict, int, int],
        None,
    ] | None = None,
) -> list[dict]:
    evaluated_cases = []
    total = len(cases)

    for index, case in enumerate(cases, start=1):
        evaluated_case = evaluate_case(
            case=case,
            judge=judge,
            overwrite=overwrite,
        )

        evaluated_cases.append(evaluated_case)

        if on_case_completed:
            on_case_completed(
                evaluated_case,
                index,
                total,
            )

    return evaluated_cases