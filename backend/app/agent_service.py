import asyncio
from uuid import UUID

from langchain_core.messages import AIMessage

from src.agent import extract_text, run_agent_messages
from src.auth.access import policy_access_context
from src.auth.product_context import ProductContext, product_context

from .execution import invoke_with_timeout
from .models import AgentResponse, CurrentUser, MessageView, SourceView
from .repository import WebRepository
from .tool_events import collect_run_metadata


class ConversationAgentService:
    def __init__(
        self,
        repository: WebRepository,
        *,
        timeout_seconds: float = 120,
    ) -> None:
        self.repository = repository
        self.timeout_seconds = timeout_seconds

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
        active_product = None
        if conversation.get("context_mode") == "product":
            active_product = ProductContext(
                parent_asin=conversation["product_parent_asin"],
                title=conversation.get("product_title") or "선택 상품",
            )
            history.insert(
                0,
                {
                    "role": "system",
                    "content": (
                        "이 대화에는 서버가 고정한 상품 컨텍스트가 있다. "
                        f"상품명={active_product.title}, "
                        f"parent_asin={active_product.parent_asin}. "
                        "모든 상품·리뷰·정책 조회에는 이 parent_asin을 사용한다. "
                        "사용자가 다른 상품을 요청하면 현재 대화의 상품을 바꾸지 말고 "
                        "새 상품 대화를 시작하도록 안내한다."
                    ),
                },
            )

        def invoke_agent():
            with (
                policy_access_context(user.policy_scopes),
                product_context(active_product),
            ):
                return run_agent_messages(history)

        result = await invoke_with_timeout(invoke_agent, self.timeout_seconds)
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
