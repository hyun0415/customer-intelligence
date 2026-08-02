import json
import math
import re
from typing import Any
import ast
import itertools
from dataclasses import dataclass
from eval.evaluator.schemas import NumericCheckResult


@dataclass
class NumericCheckResult:

    unsupported_numbers:list[str]
    notes:list[str]

NUMBER_PATTERN = re.compile(
    r"(?<![A-Za-z0-9.])"
    r"-?\d[\d,]*(?:\.\d+)?%?"
)

DECIMAL_PATTERN = re.compile(
    r"Decimal\(['\"](-?\d+(?:\.\d+)?)['\"]\)"
)

def parse_structured_string(value: str) -> Any:
    """
    JSON 또는 Python repr 형태의 문자열을
    리스트·딕셔너리로 안전하게 복원한다.

    예:
    "[{'review_count': 10}, {'review_count': 20}]"
    """
    stripped = value.strip()

    if not stripped:
        return value

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # Decimal('24.78') → 24.78
    normalized = DECIMAL_PATTERN.sub(
        r"\1",
        stripped,
    )

    try:
        return ast.literal_eval(normalized)
    except (ValueError, SyntaxError):
        return value

def normalize_number(value: str) -> str:
    value = value.strip().replace(",", "")

    if value.endswith("%"):
        number = float(value[:-1])
        return f"{number:.4f}%"

    number = float(value)

    if number.is_integer():
        return str(int(number))

    return f"{number:.6f}".rstrip("0").rstrip(".")

def normalize_structured_value(value: Any) -> Any:
    if isinstance(value, str):
        parsed = parse_structured_string(value)

        if parsed is value:
            return value

        if parsed == value:
            return value

        return normalize_structured_value(parsed)

    if isinstance(value, list):
        return [
            normalize_structured_value(item)
            for item in value
        ]

    if isinstance(value, dict):
        return {
            key: normalize_structured_value(item)
            for key, item in value.items()
        }

    return value

def extract_numbers(value: Any) -> set[str]:
    text = json.dumps(
        value,
        ensure_ascii=False,
        default=str,
    )

    numbers = set()

    for match in NUMBER_PATTERN.findall(text):
        try:
            numbers.add(normalize_number(match))
        except ValueError:
            continue

    return numbers


def extract_derived_percentages(value: Any) -> set[str]:
    """
    Tool Output의 직접 숫자와 파생 숫자를 사용해
    계산 가능한 비율을 허용한다.

    예:
    - 5161 / 5226 * 100 = 98.8%
    - (637 + 3294) / 5226 * 100 = 75.2%
    """
    normalized_value = normalize_structured_value(value)

    direct_numbers = extract_numbers(normalized_value)
    derived_numbers = extract_derived_numbers(normalized_value)

    numeric_values = []

    for item in direct_numbers | derived_numbers:
        if item.endswith("%"):
            continue

        try:
            number = float(item)

            if number > 0:
                numeric_values.append(number)
        except ValueError:
            continue

    numeric_values = sorted(set(numeric_values))

    percentages = set()

    for numerator in numeric_values:
        for denominator in numeric_values:
            if denominator == 0:
                continue

            if numerator > denominator:
                continue

            percentage = numerator / denominator * 100

            if 0 <= percentage <= 100:
                percentages.add(
                    f"{percentage:.4f}%"
                )

    return percentages


def numbers_are_close(
    left: str,
    right: str,
    tolerance: float = 0.11,
) -> bool:
    left_is_percent = left.endswith("%")
    right_is_percent = right.endswith("%")

    if left_is_percent != right_is_percent:
        return False

    try:
        left_value = float(left.rstrip("%"))
        right_value = float(right.rstrip("%"))
    except ValueError:
        return False

    return math.isclose(
        left_value,
        right_value,
        abs_tol=tolerance,
        rel_tol=0.001,
    )


def find_unsupported_numbers(case: dict) -> list[str]:
    answer_text = str(case.get("answer", ""))

    answer_numbers = extract_numbers(answer_text)

    # 백분율 합계 100%는 계산 구조상 허용한다.
    if re.search(r"\b100(?:\.0+)?\s*%", answer_text):
        answer_numbers.discard(
            normalize_number("100%")
        )

    # 백분율 계산식의 × 100은 계산 상수로 허용한다.
    if re.search(
        r"(?:×|\*|x)\s*100\b",
        answer_text,
        flags=re.IGNORECASE,
    ):
        answer_numbers.discard(
            normalize_number("100")
        )

    allowed_numbers = extract_numbers(
        {
            "question": case.get("question", ""),
            "tool_calls": case.get("tool_calls", []),
            "tool_outputs": case.get("tool_outputs", []),
        }
    )

    tool_outputs = case.get("tool_outputs", [])

    derived_percentages = extract_derived_percentages(
        tool_outputs
    )

    derived_numbers = extract_derived_numbers(
        tool_outputs
    )

    unsupported = []

    for answer_number in sorted(answer_numbers):
        direct_match = any(
            numbers_are_close(
                answer_number,
                allowed,
            )
            for allowed in allowed_numbers
        )

        percentage_match = any(
            numbers_are_close(
                answer_number,
                percentage,
            )
            for percentage in derived_percentages
        )

        derived_number_match = any(
            numbers_are_close(
                answer_number,
                derived,
            )
            for derived in derived_numbers
        )

        if not (
            direct_match
            or percentage_match
            or derived_number_match
        ):
            unsupported.append(answer_number)

    return unsupported

def check_numbers(case: dict) -> NumericCheckResult:
    unsupported_numbers = find_unsupported_numbers(case)

    notes = []

    if unsupported_numbers:
        notes.append(
            "Tool 출력 또는 질문에서 직접 확인되지 않는 "
            f"숫자가 발견되었습니다: {unsupported_numbers}"
        )

    return NumericCheckResult(
        unsupported_numbers=unsupported_numbers,
        notes=notes,
    )

def format_derived_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))

    return f"{value:.6f}".rstrip("0").rstrip(".")


def extract_derived_numbers(value: Any) -> set[str]:
    """
    Tool Output에서 직접 계산 가능한 숫자를 생성한다.

    허용 범위:
    - 리스트 길이
    - 같은 필드의 전체 합계
    - 같은 필드 값 두 개의 합계

    예:
    - 검색 결과 2개
    - 4점 637건 + 5점 3,294건 = 3,931건
    """
    normalized_value = normalize_structured_value(value)
    derived = set()

    def walk(item: Any) -> None:
        if isinstance(item, list):
            derived.add(str(len(item)))

            values_by_key: dict[str, list[float]] = {}

            for element in item:
                if isinstance(element, dict):
                    for key, field_value in element.items():
                        if (
                            isinstance(field_value, (int, float))
                            and not isinstance(field_value, bool)
                        ):
                            values_by_key.setdefault(
                                key,
                                [],
                            ).append(float(field_value))

                walk(element)

            for values in values_by_key.values():
                if len(values) < 2:
                    continue

                # 같은 필드 전체 합계
                total = sum(values)
                derived.add(
                    format_derived_number(total)
                )

                # 같은 필드의 두 값 합계
                for left, right in itertools.combinations(
                    values,
                    2,
                ):
                    pair_sum = left + right
                    derived.add(
                        format_derived_number(pair_sum)
                    )

        elif isinstance(item, dict):
            for field_value in item.values():
                walk(field_value)

    walk(normalized_value)

    return derived