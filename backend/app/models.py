from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator

from src.auth.access import PolicyAccessGrant


class UserRole(str, Enum):
    EMPLOYEE = "employee"
    MANAGER = "manager"
    ADMIN = "admin"


class CurrentUser(BaseModel):
    user_id: int
    email: EmailStr
    display_name: str
    role: UserRole
    is_active: bool = True
    policy_scopes: list[PolicyAccessGrant] = Field(default_factory=list)


class DevLoginRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=200)


class ConversationCreate(BaseModel):
    title: str = Field(default="새 대화", min_length=1, max_length=200)
    context_mode: Literal["general", "product"] = "general"
    product_parent_asin: str | None = None

    @model_validator(mode="after")
    def validate_product_context(self):
        if self.context_mode == "product" and not self.product_parent_asin:
            raise ValueError("상품 대화에는 product_parent_asin이 필요합니다.")
        if self.context_mode == "general" and self.product_parent_asin is not None:
            raise ValueError("일반 대화에는 상품을 연결할 수 없습니다.")
        return self


class ConversationSummary(BaseModel):
    conversation_id: UUID
    title: str
    created_at: datetime
    updated_at: datetime
    context_mode: Literal["general", "product"] = "general"
    product_parent_asin: str | None = None
    product_title: str | None = None
    product_store: str | None = None


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)


class SourceView(BaseModel):
    source_id: str
    title: str
    version_number: int | None = None
    section_title: str | None = None
    metadata: dict = Field(default_factory=dict)


class MessageView(BaseModel):
    message_id: UUID
    role: str
    content: str
    response_status: str | None = None
    created_at: datetime
    sources: list[SourceView] = Field(default_factory=list)


class ConversationDetail(ConversationSummary):
    messages: list[MessageView]


class AgentResponse(BaseModel):
    message: MessageView
    status: str
    sources: list[SourceView] = Field(default_factory=list)


class ScopeReplaceRequest(BaseModel):
    scopes: list[PolicyAccessGrant]


class UserAccessUpdate(BaseModel):
    role: UserRole
    is_active: bool


class EscalationUpdate(BaseModel):
    status: str = Field(pattern="^(open|acknowledged|resolved)$")


class DashboardProduct(BaseModel):
    parent_asin: str
    title: str
    store: str | None = None
    average_rating: float | None = None
    review_count: int
    negative_count: int
    negative_ratio: float
    verified_count: int
    verified_ratio: float


class RatingBucket(BaseModel):
    rating: int
    review_count: int


class RepresentativeReview(BaseModel):
    review_id: int
    rating: float
    review_title: str | None = None
    review_text: str | None = None
    reviewed_at: datetime
    helpful_vote: int
    verified_purchase: bool


class DashboardProductDetail(DashboardProduct):
    rating_distribution: list[RatingBucket]
    representative_reviews: list[RepresentativeReview]
    min_review_at: datetime | None = None
    max_review_at: datetime | None = None
