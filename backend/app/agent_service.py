import asyncio
from uuid import UUID

from langchain_core.messages import AIMessage

from src.agent import extract_text, run_agent_messages
from src.auth.access import policy_access_context

from .models import AgentResponse, CurrentUser, MessageView, SourceView
from .repository import WebRepository
from .tool_events import collect_run_metadata


class ConversationAgentService:
    def __init__(self, repository: WebRepository) -> None:
        self.repository = repository

    async def respond(
        self,
        *,
        user: CurrentUser,
        conversation_id: UUID,
        content: str,
    ) -> AgentResponse:
        await asyncio.to_thread(
            self.repository.add_message,
            user_id=user.user_id,
            conversation_id=conversation_id,
            role="user",
            content=content,
        )
        conversation = await asyncio.to_thread(
            self.repository.get_conversation,
            user.user_id,
            conversation_id,
        )
        if conversation is None:
            raise KeyError(conversation_id)
        history = [
            {"role": message["role"], "content": message["content"]}
            for message in conversation["messages"][-20:]
        ]

        def invoke_agent():
            with policy_access_context(user.policy_scopes):
                return run_agent_messages(history)

        result = await asyncio.to_thread(invoke_agent)
        answer_message = next(
            (
                message
                for message in reversed(result["messages"])
                if isinstance(message, AIMessage) and message.content
            ),
            None,
        )
        if answer_message is None:
            raise RuntimeError("Agent가 최종 답변을 반환하지 않았습니다.")
        answer = extract_text(answer_message.content)
        metadata = collect_run_metadata(result["messages"])
        saved = await asyncio.to_thread(
            self.repository.add_message,
            user_id=user.user_id,
            conversation_id=conversation_id,
            role="assistant",
            content=answer,
            response_status=metadata.status,
            sources=metadata.sources,
        )
        if metadata.escalation:
            await asyncio.to_thread(
                self.repository.create_escalation,
                user_id=user.user_id,
                conversation_id=conversation_id,
                message_id=saved["message_id"],
                category=metadata.escalation["category"],
                reason=metadata.escalation["reason"],
            )
        message = MessageView.model_validate(saved)
        return AgentResponse(
            message=message,
            status=metadata.status,
            sources=[SourceView.model_validate(item) for item in saved["sources"]],
        )
