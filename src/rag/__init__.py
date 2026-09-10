"""Internal policy Hybrid RAG components with lazy public imports."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .models import KnowledgeSearchRequest, KnowledgeSearchResponse
    from .retriever import HybridRetriever

__all__ = ["HybridRetriever", "KnowledgeSearchRequest", "KnowledgeSearchResponse"]


def __getattr__(name: str) -> Any:
    if name == "HybridRetriever":
        from .retriever import HybridRetriever

        return HybridRetriever
    if name in {"KnowledgeSearchRequest", "KnowledgeSearchResponse"}:
        from .models import KnowledgeSearchRequest, KnowledgeSearchResponse

        return {
            "KnowledgeSearchRequest": KnowledgeSearchRequest,
            "KnowledgeSearchResponse": KnowledgeSearchResponse,
        }[name]
    raise AttributeError(name)
