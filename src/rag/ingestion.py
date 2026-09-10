import argparse
import csv
from datetime import datetime
from pathlib import Path
from typing import Any

from .chunker import ParentChildChunker
from .config import RagSettings
from .embeddings import EmbeddingProvider, attach_embeddings, build_embedding_provider
from .loaders import load_policy_document
from .models import PolicyMetadata
from .repository import RagRepository


def _split_values(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split("|") if item.strip()]


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def metadata_from_manifest_row(row: dict[str, str]) -> PolicyMetadata:
    required = {
        "source_id",
        "collection",
        "source_type",
        "authority_tier",
        "publisher",
        "title",
        "language",
        "jurisdiction",
        "department",
        "policy_key",
        "approval_status",
        "version_number",
        "valid_from",
    }
    missing = sorted(name for name in required if not row.get(name, "").strip())
    if missing:
        raise ValueError(f"manifest 필수 값이 없습니다: {missing}")

    metadata: dict[str, Any] = {}
    if row.get("rule_key"):
        metadata["rules"] = {
            row.get("section_path") or row["title"]: {
                "rule_key": row["rule_key"],
                "rule_effect": row.get("rule_effect") or None,
            }
        }

    return PolicyMetadata(
        source_id=row["source_id"],
        collection=row["collection"],
        source_type=row["source_type"],
        authority_tier=int(row["authority_tier"]),
        publisher=row["publisher"],
        title=row["title"],
        source_url=row.get("source_url") or None,
        language=row["language"],
        jurisdiction=row["jurisdiction"],
        department=row["department"],
        policy_key=row["policy_key"],
        approval_status=row["approval_status"],
        version_number=int(row["version_number"]),
        valid_from=_parse_datetime(row["valid_from"]),
        valid_to=_parse_datetime(row.get("valid_to")),
        supersedes_version=int(row["supersedes_version"])
        if row.get("supersedes_version")
        else None,
        parent_asins=_split_values(row.get("parent_asins")),
        metadata=metadata,
    )


class RagIngestionService:
    def __init__(
        self,
        repository: RagRepository | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        chunker: ParentChildChunker | None = None,
        settings: RagSettings | None = None,
    ) -> None:
        self.settings = settings or RagSettings()
        self.repository = repository or RagRepository(settings=self.settings)
        self.embedding_provider = embedding_provider or build_embedding_provider(self.settings)
        self.chunker = chunker or ParentChildChunker(self.settings)

    def ingest(self, path: str | Path, metadata: PolicyMetadata) -> int:
        document = load_policy_document(path, metadata)
        chunks = self.chunker.chunk(document)
        chunks = attach_embeddings(
            chunks, self.embedding_provider, self.settings.embedding_dimensions
        )
        return self.repository.upsert_document(document, chunks)

    def ingest_manifest(self, manifest_path: str | Path) -> list[dict[str, Any]]:
        manifest_path = Path(manifest_path)
        results = []
        with manifest_path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if (row.get("ingest") or "yes").strip().lower() not in {
                    "yes",
                    "true",
                    "1",
                }:
                    continue
                metadata = metadata_from_manifest_row(row)
                local_path = Path(row["local_path"])
                if not local_path.is_absolute():
                    project_relative = Path.cwd() / local_path
                    manifest_relative = manifest_path.parent / local_path
                    local_path = (
                        project_relative
                        if project_relative.exists()
                        else manifest_relative
                    )
                version_id = self.ingest(local_path, metadata)
                results.append(
                    {"source_id": metadata.source_id, "document_version_id": version_id}
                )
        return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Internal policy RAG manifest ingestion"
    )
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    results = RagIngestionService().ingest_manifest(args.manifest)
    for result in results:
        print(f"{result['source_id']}: version_id={result['document_version_id']}")


if __name__ == "__main__":
    main()
