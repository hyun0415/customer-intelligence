from pathlib import Path
from typing import Any

import yaml

from .models import LoadedPolicyDocument, PolicyMetadata
from .parsers import PolicyDocumentParser, SimplePolicyParser


def _markdown_frontmatter(text: str) -> dict[str, Any]:
    if not text.startswith("---\n"):
        return {}
    closing = text.find("\n---\n", 4)
    if closing == -1:
        raise ValueError("Markdown frontmatter의 닫는 구분자(---)가 없습니다.")
    parsed = yaml.safe_load(text[4:closing]) or {}
    if not isinstance(parsed, dict):
        raise TypeError("Markdown frontmatter는 key-value 객체여야 합니다.")
    return parsed


def load_policy_document(
    path: str | Path,
    metadata: PolicyMetadata | dict[str, Any] | None = None,
    parser: PolicyDocumentParser | None = None,
) -> LoadedPolicyDocument:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)

    suffix = path.suffix.lower()
    if suffix not in {".md", ".markdown", ".html", ".htm", ".pdf"}:
        raise ValueError(f"지원하지 않는 문서 형식입니다: {suffix}")

    document_parser = parser or SimplePolicyParser()
    parsed = document_parser.parse(path)
    raw_content = parsed.raw_content
    cleaned_content = parsed.cleaned_content
    parsed_metadata = (
        _markdown_frontmatter(raw_content)
        if suffix in {".md", ".markdown"}
        else {}
    )

    if metadata is None:
        if not parsed_metadata:
            raise ValueError("HTML/PDF 문서는 manifest metadata를 명시해야 합니다.")
        policy_metadata = PolicyMetadata.model_validate(parsed_metadata)
    elif isinstance(metadata, PolicyMetadata):
        policy_metadata = metadata
    else:
        merged = {**parsed_metadata, **metadata}
        policy_metadata = PolicyMetadata.model_validate(merged)

    if not cleaned_content:
        raise ValueError(f"문서에서 검색 가능한 텍스트를 추출하지 못했습니다: {path}")

    return LoadedPolicyDocument(
        path=path,
        metadata=policy_metadata,
        raw_content=raw_content,
        cleaned_content=cleaned_content,
        parser_name=parsed.parser_name,
        elements=parsed.elements,
    )
