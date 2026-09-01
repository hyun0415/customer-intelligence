# Internal Policy RAG Scope

## 목적

고객 리뷰에서 발견된 불만과 사내 운영 정책을 결합해 환불, 재배송, 보상,
프로모션, escalation과 예외 승인 판단을 지원한다.

## 검색 책임 분리

- 상품, 리뷰, 평점, 기간, helpful vote와 집계: 기존 PostgreSQL SQL Tool
- 사내 정책, SOP, 제품 운영 가이드: PostgreSQL FTS + pgvector Hybrid RAG
- 두 근거가 필요한 질문: SQL Tool과 RAG Tool을 모두 호출

## Collection

- `compensation_policy`
- `promotion_policy`
- `product_operation_guides`
- `cs_sop`
- `exception_policy`

## Retrieval

- Parent 800~1,200 tokens, Child 300~450 tokens, overlap 50 tokens
- Child에 PostgreSQL `simple` FTS와 `text-embedding-3-small` 1,536차원 적용
- `ts_rank_cd`와 cosine search 순위를 RRF(`k=60`)로 결합
- 검색된 Child의 Parent 섹션을 최종 문맥으로 제공
- 복잡한 reranker는 초기 범위에서 제외

## 적용 범위와 정책 우선순위

- 상품 연결이 없으면 전 상품 공통 정책
- 관할 공통값: `ALL_JURISDICTIONS`
- 부서 공통값: `ALL_DEPARTMENTS`
- 현재 검색에서 만료 및 미래 시행 정책 제외
- 동일 사안은 상품 전용, 높은 authority, 최신 유효 정책 순으로 해결
- 동일 우선순위 충돌은 자동 해결하지 않음

## Grounding

답변은 고객 리뷰 근거, 내부 정책 근거, Agent 판단을 구분한다. 정책 근거가
없으면 운영 조치를 생성하지 않으며, 충돌이 해결되지 않으면 담당 부서 확인이
필요함을 알린다.

## 제외 범위

- Pinecone 및 별도 Vector DB
- Neo4j, Graph RAG, Ontology, Knowledge Graph
- Elasticsearch, OpenSearch
- 복잡한 reranker, 자동 crawling, 분산 ingestion

기존 Fanola, FDA, CIR 자료는 삭제하지 않지만 외부 지식 RAG PoC 자료로만
보존하며 메인 사내 정책 검색 대상에서는 제외한다.
