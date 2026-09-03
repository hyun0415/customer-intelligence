import os
from dataclasses import dataclass
from enum import Enum
from typing import Literal


ModelProvider = Literal["openai", "vllm"]

DEFAULT_AGENT_MODEL = "gpt-5.6-terra"
DEFAULT_ASPECT_EXTRACTOR_MODEL = "gpt-5.6-luna"
DEFAULT_EVIDENCE_MODEL = "gpt-5.6-luna"
DEFAULT_EVALUATOR_MODEL = "gpt-5.6-sol"

DEFAULT_LOCAL_AGENT_MODEL = "Qwen/Qwen3-30B-A3B-Instruct-2507"
DEFAULT_LOCAL_ASPECT_EXTRACTOR_MODEL = "Qwen/Qwen3-8B"
DEFAULT_LOCAL_EVIDENCE_MODEL = "Qwen/Qwen3-8B"
DEFAULT_LOCAL_EVALUATOR_MODEL = "google/gemma-3-27b-it"


class ModelRole(str, Enum):
    AGENT = "agent"
    ASPECT_EXTRACTOR = "aspect_extractor"
    EVIDENCE = "evidence"
    EVALUATOR = "evaluator"


@dataclass(frozen=True)
class RoleModelSettings:
    role: ModelRole
    provider: ModelProvider
    model: str
    base_url: str | None
    api_key: str | None
    timeout_seconds: float
    max_retries: int
    reasoning_effort: str | None
    structured_output: bool
    disable_thinking: bool

    @property
    def cache_identity(self) -> str:
        return ":".join(
            (
                self.provider,
                self.model,
                self.base_url or "default",
                self.reasoning_effort or "none",
            )
        )

    def validate(self) -> None:
        if self.provider not in {"openai", "vllm"}:
            raise ValueError(f"지원하지 않는 model provider입니다: {self.provider}")
        if not self.model.strip():
            raise ValueError(f"{self.role.value} model은 비어 있을 수 없습니다.")
        if self.timeout_seconds <= 0 or self.max_retries < 0:
            raise ValueError("model timeout/retry 설정이 올바르지 않습니다.")
        if self.provider == "vllm" and not self.base_url:
            raise ValueError("vLLM provider에는 base_url이 필요합니다.")


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


def _optional_env(name: str) -> str | None:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else None


def _provider(name: str, fallback: ModelProvider) -> ModelProvider:
    value = _env(name, fallback).lower()
    if value not in {"openai", "vllm"}:
        raise ValueError(f"{name}은 openai 또는 vllm이어야 합니다.")
    return value  # type: ignore[return-value]


@dataclass(frozen=True)
class ModelRoutingSettings:
    """역할별 모델과 OpenAI-compatible endpoint 설정."""

    agent: RoleModelSettings
    aspect_extractor: RoleModelSettings
    evidence: RoleModelSettings
    evaluator: RoleModelSettings

    @property
    def agent_model(self) -> str:
        return self.agent.model

    @property
    def aspect_extractor_model(self) -> str:
        return self.aspect_extractor.model

    @property
    def evidence_model(self) -> str:
        return self.evidence.model

    @property
    def evaluator_model(self) -> str:
        return self.evaluator.model

    def for_role(self, role: ModelRole | str) -> RoleModelSettings:
        normalized = ModelRole(role)
        return {
            ModelRole.AGENT: self.agent,
            ModelRole.ASPECT_EXTRACTOR: self.aspect_extractor,
            ModelRole.EVIDENCE: self.evidence,
            ModelRole.EVALUATOR: self.evaluator,
        }[normalized]

    def validate(self) -> None:
        for current in (
            self.agent,
            self.aspect_extractor,
            self.evidence,
            self.evaluator,
        ):
            current.validate()

    @classmethod
    def from_env(cls) -> "ModelRoutingSettings":
        default_provider = _provider("MODEL_PROVIDER", "openai")
        global_vllm_url = _env("VLLM_BASE_URL", "http://localhost:8000/v1")
        global_vllm_key = _env("VLLM_API_KEY", "local-vllm")

        def build_role(
            *,
            role: ModelRole,
            prefix: str,
            openai_model_env: str,
            openai_default: str,
            local_model_env: str,
            local_default: str,
            timeout_default: float,
            retries_default: int,
            reasoning_effort_default: str | None,
            structured_output: bool,
            disable_thinking: bool,
        ) -> RoleModelSettings:
            provider = _provider(f"{prefix}_MODEL_PROVIDER", default_provider)
            if provider == "openai":
                model = _env(openai_model_env, openai_default)
                base_url = _optional_env(f"{prefix}_MODEL_BASE_URL")
                api_key = _optional_env(f"{prefix}_API_KEY")
            else:
                model = _env(local_model_env, local_default)
                base_url = _env(f"{prefix}_MODEL_BASE_URL", global_vllm_url)
                api_key = _env(f"{prefix}_API_KEY", global_vllm_key)

            return RoleModelSettings(
                role=role,
                provider=provider,
                model=model,
                base_url=base_url,
                api_key=api_key,
                timeout_seconds=float(
                    _env(f"{prefix}_TIMEOUT_SECONDS", str(timeout_default))
                ),
                max_retries=int(
                    _env(f"{prefix}_MAX_RETRIES", str(retries_default))
                ),
                reasoning_effort=(
                    _env(
                        f"{prefix}_REASONING_EFFORT",
                        reasoning_effort_default,
                    )
                    if reasoning_effort_default is not None
                    else None
                ),
                structured_output=structured_output,
                disable_thinking=disable_thinking,
            )

        settings = cls(
            agent=build_role(
                role=ModelRole.AGENT,
                prefix="AGENT",
                openai_model_env="OPENAI_MODEL",
                openai_default=DEFAULT_AGENT_MODEL,
                local_model_env="VLLM_AGENT_MODEL",
                local_default=DEFAULT_LOCAL_AGENT_MODEL,
                timeout_default=float(_env("OPENAI_TIMEOUT_SECONDS", "90")),
                retries_default=int(_env("OPENAI_MAX_RETRIES", "2")),
                reasoning_effort_default="low",
                structured_output=False,
                disable_thinking=False,
            ),
            aspect_extractor=build_role(
                role=ModelRole.ASPECT_EXTRACTOR,
                prefix="REVIEW_EXTRACTOR",
                openai_model_env="REVIEW_EXTRACTOR_MODEL",
                openai_default=DEFAULT_ASPECT_EXTRACTOR_MODEL,
                local_model_env="VLLM_REVIEW_EXTRACTOR_MODEL",
                local_default=DEFAULT_LOCAL_ASPECT_EXTRACTOR_MODEL,
                timeout_default=60,
                retries_default=1,
                reasoning_effort_default="low",
                structured_output=True,
                disable_thinking=True,
            ),
            evidence=build_role(
                role=ModelRole.EVIDENCE,
                prefix="RAG_EVIDENCE",
                openai_model_env="RAG_EVIDENCE_MODEL",
                openai_default=DEFAULT_EVIDENCE_MODEL,
                local_model_env="VLLM_RAG_EVIDENCE_MODEL",
                local_default=DEFAULT_LOCAL_EVIDENCE_MODEL,
                timeout_default=15,
                retries_default=1,
                reasoning_effort_default="low",
                structured_output=True,
                disable_thinking=True,
            ),
            evaluator=build_role(
                role=ModelRole.EVALUATOR,
                prefix="EVALUATOR",
                openai_model_env="EVALUATOR_MODEL",
                openai_default=DEFAULT_EVALUATOR_MODEL,
                local_model_env="VLLM_EVALUATOR_MODEL",
                local_default=DEFAULT_LOCAL_EVALUATOR_MODEL,
                timeout_default=120,
                retries_default=1,
                reasoning_effort_default="low",
                structured_output=True,
                disable_thinking=False,
            ),
        )
        settings.validate()
        return settings
