from pathlib import Path
from typing import Any

import yaml

from .cleaners import clean_html, clean_markdown, normalize_text
from .models import LoadedPolicyDocument, PolicyMetadata


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


def _load_pdf(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("PDF ingestion에는 pypdf 패키지가 필요합니다.") from exc

    reader = PdfReader(path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return normalize_text("\n\n".join(pages))


def load_policy_document(
    path: str | Path,
    metadata: PolicyMetadata | dict[str, Any] | None = None,
) -> LoadedPolicyDocument:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)

    suffix = path.suffix.lower()
    if suffix not in {".md", ".markdown", ".html", ".htm", ".pdf"}:
        raise ValueError(f"지원하지 않는 문서 형식입니다: {suffix}")

    if suffix == ".pdf":
        raw_content = _load_pdf(path)
        cleaned_content = raw_content
        parsed_metadata: dict[str, Any] = {}
    else:
        raw_content = path.read_text(encoding="utf-8")
        parsed_metadata = (
            _markdown_frontmatter(raw_content) if suffix in {".md", ".markdown"} else {}
        )
        cleaned_content = (
            clean_markdown(raw_content)
            if parsed_metadata or suffix in {".md", ".markdown"}
            else clean_html(raw_content)
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
    )
