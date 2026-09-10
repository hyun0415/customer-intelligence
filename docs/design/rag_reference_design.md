# Legacy External RAG Starter Corpus

> 이 자료는 외부 지식 RAG PoC용으로 보존됩니다. 현재 메인 RAG 범위는
> `docs/rag_scope.md`의 사내 운영 정책 RAG이며 아래 자료를 기본 검색 대상으로
> ingestion하지 않습니다.

This package defines a small, official-source corpus for the Customer Intelligence Agent.

## Included

- `data/rag/source_manifest.csv`
- Manufacturer, regulatory, and ingredient-safety source notes
- `download_official_sources.ps1`
- `docs/rag_scope.md`

The original source URLs are stored in the manifest. Run the PowerShell script from the
repository root to download the official HTML and PDF files into the requested folders.

## Usage

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\download_official_sources.ps1
```

The script writes `data/rag/download_log.csv`.

## Scope

- Exact Fanola No Yellow Shampoo official pages
- One officially recommended aftercare product
- FDA labeling, claims, hair-dye, and adverse-event guidance
- CIR assessments for three ingredients listed on the official product page

General blogs, retailer descriptions, community posts, Graph RAG, and ontology sources are excluded.
