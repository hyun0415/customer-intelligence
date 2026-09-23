# 정책 Hybrid RAG

[English](README_EN.md) · [프로젝트 홈](../../README.md)

사내 환불·재배송·보상·프로모션·제품 운영·CS SOP를 검색하는 경로입니다.
상품·리뷰의 개수와 비율은 SQL Tool이 담당하고, 비정형 정책 문서만 이 RAG 경로가
담당합니다.

## 검색 계약

- 운영 검색은 `APPROVED` 상태의 현재 유효 버전만 사용합니다.
- 상품, Collection, 관할, 부서와 로그인 사용자의 접근 권한을 SQL 조건으로 강제합니다.
- 질문과 비슷하다는 이유만으로 정책을 적용하지 않습니다.
- 최종 근거 판정이 `sufficient`인 Parent만 Agent 문맥으로 전달합니다.
- 근거 부족은 `no_evidence`, 동일 우선순위 충돌은 `policy_conflict`로 종료합니다.

## Parent와 Child

| 단위 | 기본 크기 | 역할 |
|---|---:|---|
| Parent | 800~1,200 tokens | 조건·예외·승인 기준을 포함하는 완결된 정책 섹션 |
| Child | 300~450 tokens | FTS와 Embedding에서 관련 위치를 정밀하게 찾는 검색 단위 |
| Overlap | 50 tokens | Child 경계에서 문맥이 끊기는 현상 완화 |

Child에는 FTS 인덱스와 Dense Embedding을 저장합니다. Parent는 검색된 Child의 상위
섹션으로 불러오며, BGE-M3 재정렬·LLM 근거 판정·최종 인용에 사용합니다.

Parent를 재정렬하는 이유는 검색 문장 주변의 기한, 예외와 승인 조건까지 평가하기
위해서입니다. Child만 최종 근거로 사용하면 관련 문장은 찾더라도 같은 섹션의 제한
조건을 누락할 수 있습니다. ColBERT MaxSim은 Parent를 단일 평균 벡터로 압축하지
않고 질문 토큰마다 가장 가까운 Parent 토큰을 찾기 때문에 이 구조에 적합합니다.

## 실행 흐름

### 1. 범위 필터

검색 전에 다음 조건을 적용합니다.

- 승인 상태와 `valid_from / valid_to`
- 상품 전용 또는 전 상품 공통 범위
- Collection, 관할, 부서
- 서버가 로그인 사용자에게 부여한 정책 접근 범위

권한 목록이 비어 있으면 Embedding API와 DB 검색을 호출하지 않고 즉시
`no_evidence`를 반환합니다.

### 2. 질문 Embedding과 두 검색 채널

질문의 Dense Embedding은 요청 시 생성하고, 미리 저장된 Child Embedding과 비교합니다.
FTS와 Embedding은 한쪽 결과를 다른 쪽의 입력으로 사용하는 순차 필터가 아니라
독립적인 두 검색 채널입니다.

| 채널 | 검색 대상 | 기본 후보 수 | 기준 |
|---|---|---:|---|
| PostgreSQL FTS | Child | 최대 10 | `plainto_tsquery('simple')` + `ts_rank_cd` |
| pgvector | Child | 최대 10 | cosine similarity, 기본 하한 0.33 |

FTS는 BM25가 아닙니다. PostgreSQL의 cover-density ranking인 `ts_rank_cd`를
사용합니다. 명시적인 키워드 일치는 Vector 유사도 하한과 관계없이 유지됩니다.

Embedding 구성은 실행 프로필에 따라 달라집니다.

| 프로필 | 모델 | 차원 |
|---|---|---:|
| `openai` 기본 | `text-embedding-3-small` | 1,536 |
| `local` | 원격 `BAAI/bge-m3` Dense 출력 | 1,024 |

DB에 저장된 `model_key`, 버전과 차원이 현재 실행 설정과 모두 일치해야 Vector 후보로
사용됩니다.

### 3. Parent 단위 RRF

두 채널의 Child를 `parent_chunk_id`로 묶습니다. 동일 채널에서 같은 Parent의 Child가
여러 개 검색돼도 가장 높은 순위 하나만 사용하므로 빈도 가점은 없습니다. 검색된
Child ID는 설명 가능성을 위해 `matched_child_ids`에 모두 기록합니다.

같은 Parent가 FTS와 Embedding 양쪽에서 발견되면 두 채널 점수를 합산합니다.

```text
RRF(parent) = 1 / (60 + FTS rank) + 1 / (60 + Vector rank)
```

`60`은 후보 개수가 아니라 순위 차이를 완화하는 RRF 상수입니다. 채널별 최대 10개
Child가 서로 다른 Parent에 속하면 RRF 후보는 최대 20개 Parent가 되며, Parent가
겹치면 더 적어집니다.

### 4. BGE-M3 ColBERT 재정렬

RRF로 통합된 Parent 후보 전체를 BGE-M3 `multi-vector` 점수로 다시 정렬합니다.
BGE-M3의 Dense·Sparse 점수는 이 단계에서 사용하지 않고 ColBERT 점수만 사용합니다.

Late Interaction은 질문 토큰별로 Parent 토큰과의 유사도를 계산하고 가장 높은 값을
선택하는 MaxSim을 집계합니다. 기본 제한은 질문 256 tokens, Parent 2,048 tokens,
batch 2입니다.

Reranker가 timeout 또는 실행 오류를 반환하면 기본적으로 기존 RRF 순서로 복귀하고
오류 종류를 retrieval metadata에 기록합니다.

### 5. 결정론적 정책 우선순위와 충돌

이 단계는 LLM 분류가 아닙니다. PostgreSQL의 metadata를 Python 규칙으로 비교합니다.

| 판단 | 사용 데이터 |
|---|---|
| 동일 정책 사안 | `rag_chunks.rule_key` |
| 정규화된 결론 | `rag_chunks.rule_effect` |
| 상품 전용 여부 | `rag_document_products.parent_asin` |
| 정책 권위 | `rag_documents.authority_tier` |
| 시행 시점 | `rag_document_versions.valid_from` |

동일 `rule_key`에서는 상품 전용, 낮은 Authority Tier 숫자, 최신 시행일 순으로
우선합니다. 이 세 조건이 모두 같은 후보의 `rule_effect`가 다르면 자동으로 하나를
선택하지 않고 `policy_conflict`를 반환합니다.

### 6. 최종 후보와 LLM 근거 판정

우선순위 처리 후 기본 상위 5개 Parent를 근거 판정기에 전달합니다. Tool의 `limit`은
1~20 범위에서 변경할 수 있습니다. 구조화 LLM은 다음 상태만 판정합니다.

- `sufficient`: 질문의 핵심 조건을 정책이 직접 뒷받침함
- `insufficient`: 주제는 유사하지만 금액·기한·자격·예외 등 핵심 조건이 부족함
- `conflict`: 제공된 근거들이 양립할 수 없는 결론을 제시함

판정기가 실패하면 답변을 강행하지 않고 `no_evidence`로 닫습니다. `sufficient`로
선택된 Parent만 최종 Agent가 인용합니다.

## 정책 적재

정책 metadata 규칙은 [policy_metadata_schema.md](policy_metadata_schema.md)를
참고합니다. 실제 승인 정책은 manifest로 명시하며 적용 범위를 추측하지 않습니다.

```powershell
psql -f db/migrations/004_policy_rag.sql
psql -f db/migrations/010_multi_model_embeddings.sql
python -m src.rag.ingestion <internal-policy-manifest.csv>
```

예시 manifest는 [internal_policy_manifest.example.csv](internal_policy_manifest.example.csv)에
있습니다. 실제 정책 원문과 비밀값은 저장소에 포함하지 않습니다.

## 주요 설정

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `RAG_CANDIDATE_LIMIT` | `10` | FTS와 Embedding 채널별 Child 후보 수 |
| `RAG_RRF_K` | `60` | RRF 완충 상수 |
| `RAG_MINIMUM_RELEVANCE_SIMILARITY` | `0.33` | Vector 후보 최소 cosine similarity |
| `RAG_RERANKER_ENABLED` | `true` | BGE-M3 재정렬 사용 여부 |
| `RAG_RERANKER_BASE_URL` | 없음 | 별도 GPU reranker 주소 |
| `RAG_RERANKER_FALLBACK_TO_RRF` | `true` | 재정렬 실패 시 RRF 복귀 |
| `RAG_EVIDENCE_VALIDATION_ENABLED` | `true` | LLM 근거 판정 사용 여부 |
| `RAG_EVIDENCE_TIMEOUT_SECONDS` | `15` | 근거 판정 timeout |

## 코드와 검증

- 검색·통합·우선순위: `src/rag/retriever.py`
- Embedding provider: `src/rag/embeddings.py`
- BGE-M3 재정렬: `src/rag/rerankers.py`
- 근거 판정: `src/rag/evidence.py`
- DB 스키마: `db/migrations/004_policy_rag.sql`
- 설계 결정: [ADR-001](../adr/001-hybrid-sql-rag-architecture.md)
- 평가 명령: [평가 안내](../../eval/README.md)

빠른 회귀 테스트:

```powershell
pytest tests/test_rag_chunking.py tests/test_rag_retrieval.py `
  tests/test_rag_embeddings.py tests/test_rag_routing.py -q
```
