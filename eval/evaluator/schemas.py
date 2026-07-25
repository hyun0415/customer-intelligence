from pydantic import BaseModel, Field


class AnswerCheckResult(BaseModel):
    answer_present: bool
    notes: list[str] = Field(default_factory=list)


class ToolCheckResult(BaseModel):
    tool_outputs_present: bool
    tool_usage_pass: bool
    expected_args_pass: bool
    missing_expected_args: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class NumericCheckResult(BaseModel):
    unsupported_numbers: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class RuleCheckResult(BaseModel):
    answer_present: bool
    tool_outputs_present: bool
    tool_usage_pass: bool
    expected_args_pass: bool
    missing_expected_args: list[str] = Field(default_factory=list)
    unsupported_numbers: list[str] = Field(default_factory=list)
    rule_notes: list[str] = Field(default_factory=list)


class JudgeResult(BaseModel):
    accuracy_score: int = Field(ge=1, le=5)
    grounding_score: int = Field(ge=1, le=5)
    analysis_score: int = Field(ge=1, le=5)
    actionability_score: int = Field(ge=1, le=5)
    review_notes: str = Field(min_length=1)