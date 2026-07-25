import json
import math
import re
from typing import Any
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

def normalize_number(value: str) -> str:
    value = value.strip().replace(",", "")

    if value.endswith("%"):
        number = float(value[:-1])
        return f"{number:.4f}%"

    number = float(value)

    if number.is_integer():
        return str(int(number))

    return f"{number:.6f}".rstrip("0").rstrip(".")


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
    Tool output에 등장하는 숫자 조합으로 만들 수 있는
    간단한 비율을 허용한다.

    예:
    1295 / 5226 * 100 = 24.78%
    """
    raw_numbers = extract_numbers(value)

    numeric_values = []

    for item in raw_numbers:
        if item.endswith("%"):
            continue

        try:
            number = float(item)

            if number > 0:
                numeric_values.append(number)
        except ValueError:
            continue

    percentages = set()

    # 계산량이 과도해지는 것을 방지한다.
    numeric_values = numeric_values[:100]

    for numerator in numeric_values:
        for denominator in numeric_values:
            if numerator > denominator or denominator == 0:
                continue

            percentage = numerator / denominator * 100

            if 0 <= percentage <= 100:
                percentages.add(f"{percentage:.4f}%")

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
    answer_numbers = extract_numbers(
        case.get("answer", "")
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

def extract_derived_numbers(value: Any) -> set[str]:
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

                total = sum(values)

                if total.is_integer():
                    derived.add(str(int(total)))
                else:
                    derived.add(
                        f"{total:.6f}".rstrip("0").rstrip(".")
                    )

        elif isinstance(item, dict):
            for field_value in item.values():
                walk(field_value)

    walk(value)

    return derived