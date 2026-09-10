from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage

from eval.prompts.judge_prompt import build_judge_prompt
from eval.prompts.evaluator_prompt import EVALUATOR_SYSTEM_PROMPT
from src.llm.clients import build_chat_model
from src.llm.config import DEFAULT_EVALUATOR_MODEL, ModelRole, ModelRoutingSettings

from .schemas import JudgeResult, RuleCheckResult


load_dotenv()


DEFAULT_MODEL = DEFAULT_EVALUATOR_MODEL


class LLMJudge:
    def __init__(
        self,
        model: str | None = None,
        client=None,
    ):
        settings = ModelRoutingSettings.from_env()
        self.model = model or settings.evaluator_model
        self.client = client or build_chat_model(
            ModelRole.EVALUATOR,
            settings=settings,
            model_override=model,
        )

    def evaluate(
        self,
        case: dict,
        rule_result: RuleCheckResult,
    ) -> JudgeResult:
        prompt = build_judge_prompt(
            case=case,
            rule_result=rule_result.model_dump(),
        )

        structured_client = self.client.with_structured_output(
            JudgeResult,
            method="json_schema",
            strict=True,
        )
        result = structured_client.invoke(
            [
                SystemMessage(content=EVALUATOR_SYSTEM_PROMPT),
                HumanMessage(content=prompt),
            ]
        )
        if not isinstance(result, JudgeResult):
            result = JudgeResult.model_validate(result)
        return result
