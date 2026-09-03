from typing import TypeVar

from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from src.model_config import ModelRole, ModelRoutingSettings, RoleModelSettings


SchemaT = TypeVar("SchemaT", bound=BaseModel)


def build_chat_model(
    role: ModelRole | str,
    *,
    settings: ModelRoutingSettings | None = None,
    model_override: str | None = None,
    timeout_override: float | None = None,
    max_retries_override: int | None = None,
) -> ChatOpenAI:
    """OpenAI 또는 OpenAI-compatible vLLM ChatModel을 생성한다."""
    routing = settings or ModelRoutingSettings.from_env()
    config = routing.for_role(role)
    kwargs: dict = {
        "model": model_override or config.model,
        "timeout": (
            config.timeout_seconds
            if timeout_override is None
            else timeout_override
        ),
        "max_retries": (
            config.max_retries
            if max_retries_override is None
            else max_retries_override
        ),
    }

    if config.provider == "openai":
        kwargs["use_responses_api"] = True
        if config.reasoning_effort:
            kwargs["reasoning_effort"] = config.reasoning_effort
        if config.base_url:
            kwargs["base_url"] = config.base_url
        if config.api_key:
            kwargs["api_key"] = config.api_key
    else:
        kwargs.update(
            {
                "base_url": config.base_url,
                "api_key": config.api_key,
                "use_responses_api": False,
            }
        )
        if config.structured_output:
            kwargs["temperature"] = 0.0
        if config.disable_thinking:
            kwargs["extra_body"] = {
                "chat_template_kwargs": {"enable_thinking": False}
            }

    return ChatOpenAI(**kwargs)


def build_structured_model(
    role: ModelRole | str,
    schema: type[SchemaT],
    *,
    settings: ModelRoutingSettings | None = None,
    model_override: str | None = None,
    timeout_override: float | None = None,
    max_retries_override: int | None = None,
):
    routing = settings or ModelRoutingSettings.from_env()
    config = routing.for_role(role)
    if not config.structured_output:
        raise ValueError(f"{config.role.value} 역할은 구조화 출력 역할이 아닙니다.")
    model = build_chat_model(
        role,
        settings=routing,
        model_override=model_override,
        timeout_override=timeout_override,
        max_retries_override=max_retries_override,
    )
    return model.with_structured_output(
        schema,
        method="json_schema",
        strict=True,
    )


def role_settings(
    role: ModelRole | str,
    settings: ModelRoutingSettings | None = None,
) -> RoleModelSettings:
    return (settings or ModelRoutingSettings.from_env()).for_role(role)
