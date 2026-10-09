import re
from dataclasses import dataclass

import tiktoken

from .config import RagSettings
from .models import ChunkDraft, LoadedPolicyDocument


@dataclass(frozen=True)
class _Section:
    path: str
    title: str
    text: str
    page_numbers: tuple[int, ...] = ()
    element_types: tuple[str, ...] = ()


class ParentChildChunker:
    def __init__(self, settings: RagSettings | None = None, encoding=None) -> None:
        self.settings = settings or RagSettings()
        self.settings.validate()
        self.encoding = encoding or tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        return len(self.encoding.encode(text))

    def _token_windows(self, text: str, maximum: int, overlap: int) -> list[str]:
        tokens = self.encoding.encode(text)
        if len(tokens) <= maximum:
            return [text.strip()]
        step = maximum - overlap
        windows = []
        for start in range(0, len(tokens), step):
            piece = self.encoding.decode(tokens[start : start + maximum]).strip()
            if piece:
                windows.append(piece)
            if start + maximum >= len(tokens):
                break
        return windows

    def _markdown_sections(self, text: str, fallback_title: str) -> list[_Section]:
        headings: list[tuple[int, str]] = []
        sections: list[_Section] = []
        buffer: list[str] = []
        current_title = fallback_title

        def flush() -> None:
            body = "\n".join(buffer).strip()
            if body:
                path = " > ".join(title for _, title in headings) or fallback_title
                sections.append(_Section(path=path, title=current_title, text=body))

        for line in text.splitlines():
            match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
            if not match:
                buffer.append(line)
                continue
            flush()
            buffer = []
            level = len(match.group(1))
            title = match.group(2).strip()
            headings = [(depth, value) for depth, value in headings if depth < level]
            headings.append((level, title))
            current_title = title
        flush()
        return sections or [
            _Section(path=fallback_title, title=fallback_title, text=text.strip())
        ]

    def _structured_sections(
        self, document: LoadedPolicyDocument
    ) -> list[_Section]:
        sections = []
        buffer = []
        page_numbers: set[int] = set()
        element_types: set[str] = set()
        current_path = document.metadata.title
        current_title = document.metadata.title

        def flush() -> None:
            text = "\n\n".join(buffer).strip()
            if text:
                sections.append(
                    _Section(
                        path=current_path,
                        title=current_title,
                        text=text,
                        page_numbers=tuple(sorted(page_numbers)),
                        element_types=tuple(sorted(element_types)),
                    )
                )

        for element in document.elements:
            if element.heading_level is not None:
                flush()
                buffer = []
                page_numbers = set()
                element_types = set()
                current_path = element.section_path or element.text
                current_title = element.section_title or element.text
                continue
            buffer.append(element.text)
            element_types.add(element.element_type)
            if element.page_number is not None:
                page_numbers.add(element.page_number)
        flush()
        return sections

    def _document_sections(self, document: LoadedPolicyDocument) -> list[_Section]:
        if document.elements:
            sections = self._structured_sections(document)
            if sections:
                return sections
        return self._markdown_sections(
            document.cleaned_content, document.metadata.title
        )

    @staticmethod
    def _rule_metadata(
        document: LoadedPolicyDocument, section: _Section
    ) -> tuple[str | None, str | None]:
        rules = document.metadata.metadata.get("rules", {})
        if not isinstance(rules, dict):
            return None, None
        rule = rules.get(section.path) or rules.get(section.title) or {}
        if not isinstance(rule, dict):
            return None, None
        return rule.get("rule_key"), rule.get("rule_effect")

    def chunk(self, document: LoadedPolicyDocument) -> list[ChunkDraft]:
        chunks: list[ChunkDraft] = []
        parent_index = 0
        child_index = 0

        for section in self._document_sections(document):
            parent_pieces = self._token_windows(
                section.text, self.settings.parent_max_tokens, 0
            )
            rule_key, rule_effect = self._rule_metadata(document, section)

            for parent_piece in parent_pieces:
                parent_tokens = self.count_tokens(parent_piece)
                chunks.append(
                    ChunkDraft(
                        chunk_level="parent",
                        chunk_index=parent_index,
                        section_path=section.path,
                        section_title=section.title,
                        chunk_text=parent_piece,
                        embedding_text=f"{document.metadata.title}\n{section.path}\n{parent_piece}",
                        token_count=parent_tokens,
                        rule_key=rule_key,
                        rule_effect=rule_effect,
                        metadata={
                            "parser": document.parser_name,
                            "page_numbers": list(section.page_numbers),
                            "element_types": list(section.element_types),
                        },
                    )
                )

                for child_piece in self._token_windows(
                    parent_piece,
                    self.settings.child_max_tokens,
                    self.settings.overlap_tokens,
                ):
                    chunks.append(
                        ChunkDraft(
                            chunk_level="child",
                            chunk_index=child_index,
                            parent_index=parent_index,
                            section_path=section.path,
                            section_title=section.title,
                            chunk_text=child_piece,
                            embedding_text=f"{document.metadata.title}\n{section.path}\n{child_piece}",
                            token_count=self.count_tokens(child_piece),
                            rule_key=rule_key,
                            rule_effect=rule_effect,
                            metadata={
                                "parser": document.parser_name,
                                "page_numbers": list(section.page_numbers),
                                "element_types": list(section.element_types),
                            },
                        )
                    )
                    child_index += 1
                parent_index += 1

        return chunks
