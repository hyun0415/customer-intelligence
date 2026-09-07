def build_conversation_title(content: str, maximum: int = 32) -> str:
    """첫 질문을 비용 없이 읽기 쉬운 대화 제목으로 축약한다."""
    normalized = " ".join(content.split()).strip()
    if not normalized:
        return "새 대화"
    if len(normalized) <= maximum:
        return normalized
    return normalized[: maximum - 1].rstrip() + "…"
