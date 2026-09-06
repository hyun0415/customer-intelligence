from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

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


class ConversationSummary(BaseModel):
    conversation_id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)


class SourceView(BaseModel):
    source_id: str
    title: str
    version_number: int | None = None
    section_title: str | None = None


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
