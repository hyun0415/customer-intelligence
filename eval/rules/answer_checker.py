from dataclasses import dataclass

@dataclass
class AnswerCheckResult:

    answer_present: bool

    notes: list[str]

def check_answer(case):

    answer_present = bool(
        str(case.get("answer","")).strip()
    )

    notes = []

    if not answer_present:
        notes.append(
            "최종 답변이 비어 있습니다."
        )

    return AnswerCheckResult(
        answer_present,
        notes,
    )