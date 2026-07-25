import os

from dotenv import load_dotenv
from openai import OpenAI

from eval.prompts.judge_prompt import build_judge_prompt

from .schemas import JudgeResult, RuleCheckResult


load_dotenv()


DEFAULT_MODEL = "gpt-5.6-sol"


class LLMJudge:
    def __init__(
        self,
        model: str | None = None,
        client: OpenAI | None = None,
    ):
        self.model = (
            model
            or os.getenv("EVALUATOR_MODEL")
            or DEFAULT_MODEL
        )
        self.client = client or OpenAI()

    def evaluate(
        self,
        case: dict,
        rule_result: RuleCheckResult,
    ) -> JudgeResult:
        prompt = build_judge_prompt(
            case=case,
            rule_result=rule_result.model_dump(),
        )

        response = self.client.responses.parse(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "당신은 Customer Intelligence Agent의 "
                        "엄격한 품질 평가자다. "
                        "Python 규칙 검사와 Tool 원본 출력을 "
                        "함께 검토하라."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            text_format=JudgeResult,
        )

        result = response.output_parsed

        if result is None:
            raise ValueError(
                "평가 모델이 구조화된 결과를 반환하지 않았습니다."
            )

        return result