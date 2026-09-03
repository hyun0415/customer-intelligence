import pytest

import src.model_clients as model_clients
from eval.evaluator.judge import LLMJudge
from eval.evaluator.schemas import RuleCheckResult
from src.analysis.schemas import ClassifiedReview
from src.model_clients import build_chat_model, build_structured_model
from src.model_config import ModelRole, ModelRoutingSettings
from src.rag.config import RagSettings


MODEL_ENV_NAMES = (
    "MODEL_PROVIDER",
    "OPENAI_MODEL",
    "REVIEW_EXTRACTOR_MODEL",
    "RAG_EVIDENCE_MODEL",
    "EVALUATOR_MODEL",
    "AGENT_MODEL_PROVIDER",
    "REVIEW_EXTRACTOR_MODEL_PROVIDER",
    "RAG_EVIDENCE_MODEL_PROVIDER",
    "EVALUATOR_MODEL_PROVIDER",
    "AGENT_REASONING_EFFORT",
    "REVIEW_EXTRACTOR_REASONING_EFFORT",
    "RAG_EVIDENCE_REASONING_EFFORT",
    "EVALUATOR_REASONING_EFFORT",
    "VLLM_BASE_URL",
    "VLLM_AGENT_MODEL",
    "VLLM_REVIEW_EXTRACTOR_MODEL",
    "VLLM_RAG_EVIDENCE_MODEL",
    "VLLM_EVALUATOR_MODEL",
)


def test_model_routing_defaults_are_role_specific(monkeypatch):
    for name in MODEL_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)

    settings = ModelRoutingSettings.from_env()

    assert settings.agent_model == "gpt-5.6-terra"
    assert settings.aspect_extractor_model == "gpt-5.6-luna"
    assert settings.evidence_model == "gpt-5.6-luna"
    assert settings.evaluator_model == "gpt-5.6-sol"


def test_model_routing_overrides_are_independent(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "agent-model")
    monkeypatch.setenv("REVIEW_EXTRACTOR_MODEL", "aspect-model")
    monkeypatch.setenv("RAG_EVIDENCE_MODEL", "evidence-model")
    monkeypatch.setenv("EVALUATOR_MODEL", "judge-model")

    settings = ModelRoutingSettings.from_env()

    assert settings.agent_model == "agent-model"
    assert settings.aspect_extractor_model == "aspect-model"
    assert settings.evidence_model == "evidence-model"
    assert settings.evaluator_model == "judge-model"
    assert RagSettings().evidence_model == "evidence-model"
    assert LLMJudge(client=object()).model == "judge-model"


def test_vllm_defaults_select_qwen_and_gemma(monkeypatch):
    for name in MODEL_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MODEL_PROVIDER", "vllm")
    monkeypatch.setenv("VLLM_BASE_URL", "http://inference.test/v1")

    settings = ModelRoutingSettings.from_env()

    assert settings.agent.model == "Qwen/Qwen3-30B-A3B-Instruct-2507"
    assert settings.aspect_extractor.model == "Qwen/Qwen3-8B"
    assert settings.evidence.model == "Qwen/Qwen3-8B"
    assert settings.evaluator.model == "google/gemma-3-27b-it"
    assert settings.aspect_extractor.disable_thinking is True
    assert settings.evaluator.base_url == "http://inference.test/v1"


def test_role_provider_override_supports_mixed_operation(monkeypatch):
    for name in MODEL_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.setenv("RAG_EVIDENCE_MODEL_PROVIDER", "vllm")
    monkeypatch.setenv("RAG_EVIDENCE_MODEL_BASE_URL", "http://qwen8:8000/v1")

    settings = ModelRoutingSettings.from_env()

    assert settings.agent.provider == "openai"
    assert settings.evidence.provider == "vllm"
    assert settings.evidence.model == "Qwen/Qwen3-8B"
    assert settings.evidence.base_url == "http://qwen8:8000/v1"


def test_invalid_provider_is_rejected(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "ollama")

    with pytest.raises(ValueError, match="openai 또는 vllm"):
        ModelRoutingSettings.from_env()


class FakeChatOpenAI:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.schema_call = None

    def with_structured_output(self, schema, **kwargs):
        self.schema_call = (schema, kwargs)
        return self


def test_vllm_client_uses_chat_completions_and_disables_qwen_thinking(
    monkeypatch,
):
    for name in MODEL_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MODEL_PROVIDER", "vllm")
    monkeypatch.setattr(model_clients, "ChatOpenAI", FakeChatOpenAI)

    client = build_chat_model(ModelRole.ASPECT_EXTRACTOR)

    assert client.kwargs["model"] == "Qwen/Qwen3-8B"
    assert client.kwargs["base_url"] == "http://localhost:8000/v1"
    assert client.kwargs["use_responses_api"] is False
    assert client.kwargs["temperature"] == 0.0
    assert client.kwargs["extra_body"] == {
        "chat_template_kwargs": {"enable_thinking": False}
    }


def test_structured_roles_use_strict_json_schema(monkeypatch):
    for name in MODEL_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(model_clients, "ChatOpenAI", FakeChatOpenAI)

    client = build_structured_model(
        ModelRole.ASPECT_EXTRACTOR,
        ClassifiedReview,
    )

    assert client.schema_call == (
        ClassifiedReview,
        {"method": "json_schema", "strict": True},
    )


def test_openai_role_preserves_reasoning_effort_override(monkeypatch):
    for name in MODEL_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("REVIEW_EXTRACTOR_REASONING_EFFORT", "medium")
    monkeypatch.setattr(model_clients, "ChatOpenAI", FakeChatOpenAI)

    client = build_chat_model(ModelRole.ASPECT_EXTRACTOR)

    assert client.kwargs["reasoning_effort"] == "medium"


def test_evaluator_uses_mocked_structured_client_without_network(monkeypatch):
    for name in MODEL_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)

    class FakeJudgeClient:
        schema_call = None
        messages = None

        def with_structured_output(self, schema, **kwargs):
            self.schema_call = (schema, kwargs)
            return self

        def invoke(self, messages):
            self.messages = messages
            return {
                "accuracy_score": 5,
                "grounding_score": 5,
                "analysis_score": 4,
                "actionability_score": 4,
                "strengths": ["근거와 일치"],
                "problems": [],
                "evidence": [],
                "suggestions": ["현재 방식 유지"],
                "review_notes": "근거에 충실한 답변이다.",
            }

    client = FakeJudgeClient()
    result = LLMJudge(client=client).evaluate(
        case={"id": "mock", "question": "질문", "answer": "답변"},
        rule_result=RuleCheckResult(
            answer_present=True,
            tool_outputs_present=True,
            tool_usage_pass=True,
            expected_args_pass=True,
        ),
    )

    assert result.accuracy_score == 5
    assert client.schema_call[1] == {"method": "json_schema", "strict": True}
    assert len(client.messages) == 2
