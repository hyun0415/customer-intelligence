import ast
import json
from dataclasses import dataclass
from typing import Any

from langchain_core.messages import ToolMessage


@dataclass(frozen=True)
class AgentRunMetadata:
    status: str
    sources: list[dict[str, Any]]
    escalation: dict[str, str] | None


def _tool_payload(message: ToolMessage) -> dict[str, Any] | None:
    if isinstance(message.content, dict):
        return message.content
    if isinstance(message.content, str):
        for parser in (json.loads, ast.literal_eval):
            try:
                value = parser(message.content)
                return value if isinstance(value, dict) else None
            except (ValueError, SyntaxError):
                continue
    return None


def collect_run_metadata(messages: list[Any]) -> AgentRunMetadata:
    status = "answer"
    sources_by_id: dict[str, dict[str, Any]] = {}
    escalation = None

    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        payload = _tool_payload(message)
        if payload is None:
            continue
        if message.name == "escalate_case_tool" or payload.get("status") == "escalation":
            status = "escalation"
            escalation = {
                "category": str(payload.get("category", "other")),
                "reason": str(payload.get("reason", "담당자 확인 필요")),
            }
            continue
        if message.name != "search_internal_knowledge_tool":
            continue
        rag_status = payload.get("status")
        if status != "escalation" and rag_status == "policy_conflict":
            status = "conflict"
        elif status == "answer" and rag_status == "no_evidence":
            status = "no_evidence"
        for source in payload.get("sources", []):
            source_id = source.get("source_id")
            if source_id:
                sources_by_id[source_id] = {
                    "source_id": source_id,
                    "title": source.get("title", source_id),
                    "version_number": source.get("version_number"),
                    "section_title": source.get("section_title"),
                    "metadata": {
                        "collection": source.get("collection"),
                        "authority_tier": source.get("authority_tier"),
                    },
                }
    return AgentRunMetadata(status, list(sources_by_id.values()), escalation)
