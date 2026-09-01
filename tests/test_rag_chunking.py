from datetime import datetime, timezone

import pytest

from src.rag.chunker import ParentChildChunker
from src.rag.config import ALL_DEPARTMENTS, ALL_JURISDICTIONS, RagSettings
from src.rag.embeddings import attach_embeddings
from src.rag.loaders import load_policy_document
from src.rag.models import PolicyMetadata


class FakeEmbeddings:
    def embed_documents(self, texts):
        return [[float(index)] * 1536 for index, _ in enumerate(texts)]

    def embed_query(self, text):
        return [0.0] * 1536


class FakeEncoding:
    def encode(self, text):
        return list(text.encode("utf-8"))

    def decode(self, tokens):
        return bytes(tokens).decode("utf-8", errors="ignore")


def metadata(**overrides):
    values = {
        "source_id": "test_policy",
        "collection": "compensation_policy",
        "source_type": "approved_policy",
        "authority_tier": 1,
        "publisher": "Test Operations",
        "title": "테스트 정책",
        "language": "ko",
        "jurisdiction": ALL_JURISDICTIONS,
        "department": ALL_DEPARTMENTS,
        "policy_key": "test_policy",
        "approval_status": "APPROVED",
        "version_number": 1,
        "valid_from": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    values.update(overrides)
    return PolicyMetadata(**values)


def test_scope_is_required_and_has_no_implicit_default():
    with pytest.raises(ValueError):
        metadata(jurisdiction="")
    with pytest.raises(ValueError):
        metadata(department="")


def test_markdown_sections_create_parent_and_child_chunks(tmp_path):
    path = tmp_path / "policy.md"
    path.write_text(
        "# 공통 원칙\n\n증빙과 적용 범위를 확인한다.\n\n"
        "## 예외\n\n정책에 없는 조치는 담당 부서 확인이 필요하다.",
        encoding="utf-8",
    )
    document = load_policy_document(path, metadata())
    settings = RagSettings(
        parent_min_tokens=10,
        parent_max_tokens=30,
        child_min_tokens=5,
        child_max_tokens=12,
        overlap_tokens=2,
    )
    chunks = ParentChildChunker(settings, encoding=FakeEncoding()).chunk(document)
    parents = [chunk for chunk in chunks if chunk.chunk_level == "parent"]
    children = [chunk for chunk in chunks if chunk.chunk_level == "child"]

    assert len(parents) >= 2
    assert children
    assert all(child.parent_index is not None for child in children)
    assert any("예외" in child.section_path for child in children)


def test_only_children_receive_embeddings(tmp_path):
    path = tmp_path / "policy.md"
    path.write_text("# 정책\n\n검색 가능한 정책 문장이다.", encoding="utf-8")
    chunks = ParentChildChunker(encoding=FakeEncoding()).chunk(
        load_policy_document(path, metadata())
    )
    embedded = attach_embeddings(chunks, FakeEmbeddings())

    assert all(
        chunk.embedding is None for chunk in embedded if chunk.chunk_level == "parent"
    )
    assert all(
        len(chunk.embedding) == 1536
        for chunk in embedded
        if chunk.chunk_level == "child"
    )


def test_html_requires_explicit_manifest_metadata(tmp_path):
    path = tmp_path / "policy.html"
    path.write_text("<h1>정책</h1><p>본문</p>", encoding="utf-8")
    with pytest.raises(ValueError, match="manifest metadata"):
        load_policy_document(path)

    loaded = load_policy_document(path, metadata())
    assert loaded.cleaned_content == "정책\n\n본문"
