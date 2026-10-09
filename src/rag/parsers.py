from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .cleaners import clean_html, clean_markdown, normalize_text
from .models import PolicyDocumentElement


@dataclass(frozen=True)
class ParsedPolicyContent:
    raw_content: str
    cleaned_content: str
    elements: list[PolicyDocumentElement]
    parser_name: str


class PolicyDocumentParser(Protocol):
    name: str

    def parse(self, path: Path) -> ParsedPolicyContent: ...


class SimplePolicyParser:
    name = "simple"

    def parse(self, path: Path) -> ParsedPolicyContent:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader
            except ImportError as exc:
                raise RuntimeError(
                    "PDF ingestion에는 pypdf 패키지가 필요합니다."
                ) from exc

            reader = PdfReader(path)
            pages = [page.extract_text() or "" for page in reader.pages]
            cleaned = normalize_text("\n\n".join(pages))
            elements = [
                PolicyDocumentElement(
                    element_type="page_text",
                    text=normalize_text(text),
                    page_number=index,
                )
                for index, text in enumerate(pages, start=1)
                if normalize_text(text)
            ]
            return ParsedPolicyContent(cleaned, cleaned, elements, self.name)

        raw = path.read_text(encoding="utf-8")
        cleaned = clean_markdown(raw) if suffix in {".md", ".markdown"} else clean_html(raw)
        return ParsedPolicyContent(raw, cleaned, [], self.name)


class DoclingPolicyParser:
    name = "docling"

    def __init__(
        self,
        *,
        enable_ocr: bool = False,
        enable_table_structure: bool = False,
        document_timeout_seconds: float = 120,
        converter: Any | None = None,
    ) -> None:
        self.enable_ocr = enable_ocr
        self.enable_table_structure = enable_table_structure
        self.document_timeout_seconds = document_timeout_seconds
        self._converter = converter

    def _build_converter(self):
        try:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import DocumentConverter, PdfFormatOption
        except ImportError as exc:
            raise RuntimeError(
                "Docling parser에는 선택 의존성 docling이 필요합니다. "
                "requirements-docling.txt를 설치하세요."
            ) from exc

        options = PdfPipelineOptions(
            do_ocr=self.enable_ocr,
            do_table_structure=self.enable_table_structure,
            document_timeout=self.document_timeout_seconds,
            force_backend_text=not self.enable_ocr,
        )
        return DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=options)
            }
        )

    @staticmethod
    def _label(item: Any) -> str:
        label = getattr(item, "label", None)
        return str(getattr(label, "value", label) or item.__class__.__name__).lower()

    @staticmethod
    def _page_number(item: Any) -> int | None:
        provenance = getattr(item, "prov", None) or []
        return getattr(provenance[0], "page_no", None) if provenance else None

    @staticmethod
    def _item_text(item: Any, document: Any) -> str:
        if "table" in DoclingPolicyParser._label(item) and hasattr(
            item, "export_to_markdown"
        ):
            return str(item.export_to_markdown(document)).strip()
        return str(getattr(item, "text", "") or "").strip()

    def _elements(self, document: Any) -> list[PolicyDocumentElement]:
        elements = []
        headings: list[tuple[int, str]] = []
        for item, tree_level in document.iterate_items():
            label = self._label(item)
            text = self._item_text(item, document)
            if not text:
                continue

            heading_level = None
            if "section_header" in label or label in {"title", "heading"}:
                heading_level = int(getattr(item, "level", tree_level or 1))
                heading_level = min(max(heading_level, 1), 6)
                headings = [entry for entry in headings if entry[0] < heading_level]
                headings.append((heading_level, text))

            section_path = " > ".join(title for _, title in headings)
            elements.append(
                PolicyDocumentElement(
                    element_type=label,
                    text=text,
                    section_path=section_path,
                    section_title=headings[-1][1] if headings else "",
                    heading_level=heading_level,
                    page_number=self._page_number(item),
                )
            )
        return elements

    def parse(self, path: Path) -> ParsedPolicyContent:
        if path.suffix.lower() != ".pdf":
            raise ValueError("Docling parser 비교는 현재 PDF 문서만 지원합니다.")
        converter = self._converter or self._build_converter()
        result = converter.convert(path)
        document = result.document
        cleaned = normalize_text(document.export_to_markdown())
        return ParsedPolicyContent(
            raw_content=cleaned,
            cleaned_content=cleaned,
            elements=self._elements(document),
            parser_name=self.name,
        )


def build_policy_parser(
    parser_name: str,
    *,
    enable_ocr: bool = False,
    enable_table_structure: bool = False,
    document_timeout_seconds: float = 120,
) -> PolicyDocumentParser:
    normalized = parser_name.strip().lower()
    if normalized == "simple":
        return SimplePolicyParser()
    if normalized == "docling":
        return DoclingPolicyParser(
            enable_ocr=enable_ocr,
            enable_table_structure=enable_table_structure,
            document_timeout_seconds=document_timeout_seconds,
        )
    raise ValueError(f"지원하지 않는 policy parser입니다: {parser_name}")
