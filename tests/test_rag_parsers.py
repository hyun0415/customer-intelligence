from datetime import datetime, timezone

import pytest

from src.rag.chunker import ParentChildChunker
from src.rag.models import PolicyMetadata
from src.rag.parsers import DoclingPolicyParser, build_policy_parser


class FakeProvenance:
    def __init__(self, page_no):
        self.page_no = page_no


class FakeItem:
    def __init__(self, label, text, *, level=None, page_no=1):
        self.label = label
        self.text = text
        self.level = level
        self.prov = [FakeProvenance(page_no)]


class FakeTable(FakeItem):
    def export_to_markdown(self, document):
        assert document is not None
        return "| 기준 | 값 |\n|---|---:|\n| 기한 | 72시간 |"


class FakeDocument:
    def iterate_items(self):
        return iter(
            [
                (FakeItem("section_header", "1. 접수", level=1), 1),
                (FakeItem("text", "접수 기준입니다.", page_no=1), 2),
                (FakeTable("table", "", page_no=2), 2),
            ]
        )

    def export_to_markdown(self):
        return "# 1. 접수\n\n접수 기준입니다.\n\n| 기준 | 값 |"


class FakeResult:
    document = FakeDocument()


class FakeConverter:
    def convert(self, path):
        assert path.suffix == ".pdf"
        return FakeResult()


class FakeEncoding:
    def encode(self, text):
        return list(text.encode("utf-8"))

    def decode(self, tokens):
        return bytes(tokens).decode("utf-8", errors="ignore")


def metadata():
    return PolicyMetadata(
        source_id="test",
        collection="cs_sop",
        source_type="approved_policy",
        authority_tier=1,
        publisher="Test",
        title="테스트 정책",
        language="ko",
        jurisdiction="KR",
        department="CS",
        policy_key="test_policy",
        approval_status="APPROVED",
        version_number=1,
        valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def test_docling_parser_preserves_structure_without_importing_optional_package(tmp_path):
    path = tmp_path / "policy.pdf"
    path.write_bytes(b"fake")
    parser = DoclingPolicyParser(converter=FakeConverter())

    parsed = parser.parse(path)

    assert parsed.parser_name == "docling"
    assert [element.element_type for element in parsed.elements] == [
        "section_header",
        "text",
        "table",
    ]
    assert parsed.elements[-1].page_number == 2
    assert "72시간" in parsed.elements[-1].text


def test_docling_elements_feed_existing_parent_child_chunker(tmp_path):
    from src.rag.loaders import load_policy_document

    path = tmp_path / "policy.pdf"
    path.write_bytes(b"fake")
    document = load_policy_document(
        path,
        metadata(),
        parser=DoclingPolicyParser(converter=FakeConverter()),
    )

    chunks = ParentChildChunker(encoding=FakeEncoding()).chunk(document)

    assert {chunk.chunk_level for chunk in chunks} == {"parent", "child"}
    assert all(chunk.metadata["parser"] == "docling" for chunk in chunks)
    assert any(2 in chunk.metadata["page_numbers"] for chunk in chunks)
    assert any("table" in chunk.metadata["element_types"] for chunk in chunks)


def test_unknown_parser_is_rejected():
    with pytest.raises(ValueError, match="지원하지 않는 policy parser"):
        build_policy_parser("unknown")
