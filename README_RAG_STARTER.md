# RAG Starter Corpus

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
