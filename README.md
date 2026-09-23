# Customer Intelligence Agent

[English](README_EN.md)

대량의 고객 리뷰에는 제품 개선에 필요한 신호가 있지만, 현업 담당자가 리뷰를 직접
선별하고 통계를 계산한 뒤 관련 정책까지 별도로 찾아야 한다는 한계가 있습니다. 이
프로젝트는 이러한 분절된 업무를 하나의 대화로 통합하여 **정량 지표와 실제 리뷰
근거, 적용 가능한 정책을 함께 확인할 수 있도록 만든 Customer Intelligence Agent**입니다.

LLM의 유연성은 활용하되, 숫자와 권한처럼 오류 비용이 큰 영역은 모델에 맡기지
않았습니다. 리뷰 통계는 사전에 검증한 SQL Tool로 계산하고, 정책은 사용자 권한과
유효기간을 먼저 적용한 Hybrid RAG로 검색합니다. 자연어 질의의 편의성을 유지하면서
**잘못된 수치 생성, 근거 없는 정책 안내, 권한 밖 문서 노출**을 줄이는 데 초점을
맞췄습니다.

## 핵심 설계

| 적용 경로 | 해결하려는 한계 | 적용한 설계 | 기대 효과 |
|---|---|---|---|
| **리뷰 분석** | LLM이 SQL을 직접 생성하면 조회 조건과 집계 기준이 달라질 수 있음 | 검증된 SQL Tool만 선택하도록 제한 | 동일한 기준의 정량 지표 제공 |
| **리뷰 분석** | 평점 통계만으로는 구체적인 불만 원인을 파악하기 어려움 | 저평점 리뷰에서 Aspect·감성·근거 구절을 추출하고 Python으로 원문 검증·집계 | 반복 불만과 개선 우선순위를 실제 리뷰 근거와 함께 확인 |
| **정책 RAG** | 키워드 검색과 의미 검색은 서로 다른 정책을 놓칠 수 있음 | PostgreSQL FTS와 Embedding 검색을 RRF로 결합하고 BGE-M3 MaxSim으로 재정렬 | 정확한 규정 용어와 의미적 유사성을 함께 반영 |
| **정책 RAG** | 검색 문서가 불충분해도 LLM이 답변을 만들어낼 수 있음 | 근거를 `sufficient / insufficient / conflict`로 판정 | 근거 부족과 정책 충돌을 명시하고 임의 안내 방지 |
| **정책 RAG** | 모든 사용자에게 동일한 정책을 노출하면 접근 범위를 통제하기 어려움 | Collection·관할·부서 필터와 RBAC를 서버에서 강제 | 허용된 최신 유효 정책만 검색 |
| **공통 평가** | 높은 평가 점수만으로는 실제 안정성을 설명하기 어려움 | Tool 정확성·수치 Grounding·근거성·업무 활용성을 자동 평가 | 모델 교체 시 품질과 비용을 같은 기준으로 비교 |

## 구현 범위

Amazon Reviews 2023의 Beauty and Personal Care 상품 547개와 리뷰 105,060건을 분석
대상으로 구성했습니다. 리뷰 분석, 정책 검색, 근거 판정과 권한 통제에 Google OIDC
로그인, Redis 세션, 대화 소유권 관리를 연결하여 단순한 RAG 데모가 아니라 **현업
사용 흐름을 검증할 수 있는 MVP**로 구현했습니다.

## 시스템 흐름

### 고객 리뷰 분석

![고객 리뷰 분석 Agent의 모델 입력과 출력](docs/assets/diagrams/customer-review-agent-model-io.png)

Agent가 사전에 구현된 SQL Tool을 선택하면 PostgreSQL이 표본과 통계를 반환합니다.
Aspect Extractor는 리뷰별 불만 유형과 근거 구절을 구조화하고, Python은 근거가 실제
원문에 존재하는지 확인한 뒤 빈도와 표본 내 비율을 집계합니다. 최종 Agent는 검증된
구조화 결과만 사용합니다.

Extractor의 입출력 스키마, Python 원문 검증, Redis 캐시와 리뷰별 호출의 장단점은
[고객 리뷰 분석 문서](docs/review-analysis/README.md)에 정리했습니다.

### 정책 Hybrid RAG

![정책 Hybrid RAG 검색과 근거 판정](docs/assets/diagrams/policy-hybrid-rag-flow.png)

승인 상태·유효기간·상품·Collection·관할·부서·사용자 권한을 먼저 적용합니다.
PostgreSQL FTS와 Embedding 검색이 Child Chunk 후보를 각각 생성하고, RRF가 Parent
기준으로 통합합니다. BGE-M3가 Parent 섹션을 재정렬한 뒤 구조화 LLM이 질문을 직접
뒷받침하는 근거인지 `sufficient / insufficient / conflict`로 판정합니다.

상세 후보 수, Child/Parent 역할, 정책 우선순위와 실패 처리는
[정책 RAG 문서](docs/rag/README.md)에 정리했습니다.

## 서비스 화면

| 정책 근거와 답변 보류 | 리뷰 통계와 반복 불만 |
|---|---|
| ![정책 근거와 근거 부족 상태](docs/assets/screenshots/policy-grounding-and-no-evidence.png) | ![반복 불만 유형](docs/assets/screenshots/aspect-pattern-evidence.png) |

정책 근거가 부족하면 내용을 추측하지 않고 `no_evidence`로 종료합니다. 리뷰 패턴의
비율은 선별 표본 내 비율로 표시하며 전체 고객 발생률로 확대 해석하지 않습니다.

## 설계 원칙

- SQL의 정확성, 정책 권한, 원문 근거와 안전 경계는 코드가 보장합니다.
- 언어적 해석 품질은 모델 교체와 평가 세트로 관리합니다.
- Tool 결과에 없는 수치·정책·인과관계·안전성 정보를 생성하지 않습니다.
- 동일 우선순위 정책이 충돌하면 Agent가 임의로 결론을 선택하지 않습니다.
- 의료·안전 질문은 일반 답변과 분리해 사람의 검토로 전환합니다.
- OpenAI와 로컬 모델은 같은 Tool·스키마·평가 계약을 사용합니다.

## 기술 스택

| 영역 | 기술 |
|---|---|
| Agent·LLM | Python, LangGraph, LangChain, OpenAI API, vLLM |
| 분석 | SQL, pandas, Pydantic, Aspect Term Extraction |
| RAG | PostgreSQL FTS, pgvector, RRF, BGE-M3 ColBERT MaxSim |
| Web | FastAPI, Next.js, TypeScript |
| 인증·상태 | Google OIDC, Redis, HttpOnly Cookie, PostgreSQL 감사 로그 |
| 배포·평가 | Docker Compose, Terraform, EC2, ECR, pytest, LLM Judge |

## 평가 방식과 해석 범위

평가는 높은 단일 점수를 제시하기보다 시스템이 보장하는 부분과 모델 품질로 남겨둔
부분을 구분합니다.

| 평가 계층 | 확인 내용 | 해석 범위 |
|---|---|---|
| Tool | 필수·선택·금지 Tool과 인자 | 정의된 업무 시나리오의 라우팅 회귀 |
| Rule Checker | SQL 결과에 없는 숫자, 근거 구절, 표본 표현 | 시스템 불변조건 위반 탐지 |
| Policy RAG | 권한, 검색, 재정렬, 근거 충분성, 충돌 | 승인된 평가 정책과 질문 범위 |
| LLM Judge | 정확성, 근거성, 분석력, 업무 활용성 | 모델 간 상대 비교와 실패 원인 기록 |
| 보안·안전 | 대화 소유권, RBAC, escalation | 자동 판단을 제한하는 경계 검증 |

15개 고객·상품 분석 시나리오와 정책 RAG 단계별 평가를 구성했습니다. 고정 세트 통과는
모든 임의 질문의 성능을 보장하지 않으므로, 실패 사례와 회귀 방지 규칙을 함께
기록합니다. 자세한 실행 방법은 [평가 안내](eval/README.md)를 참고하세요.

## 빠른 실행

저장소 루트에서 `.env.example`을 복사한 뒤 실제 비밀값은 Git에 포함하지 않는
`.env`에만 설정합니다.

```powershell
Copy-Item .env.example .env
docker compose --env-file .env `
  -f deploy/compose/local-infra.yaml `
  -f deploy/compose/local-app.yaml up --build
```

- Web: `http://localhost:3000`
- API 준비 상태: `http://localhost:8000/api/ready`

핵심 회귀 검증은 다음 세 명령으로 시작합니다.

```powershell
pytest -q
python -m eval.run_agent_evaluation
python -m eval.rag_pipeline_comparison --stages baseline,rerank,full
```

Agent 평가와 전체 RAG 평가는 PostgreSQL 데이터와 OpenAI API 설정이 필요합니다.
세부 옵션, 비용이 발생하는 검증과 로컬 모델 실행은 분야별 문서에서 분리했습니다.

## 프로젝트 구조

실행과 핵심 로직을 이해하는 데 필요한 주요 경로만 표시했습니다. 개발 환경의 캐시,
생성 결과와 단순 보조 파일은 생략했습니다.

```text
customer-intelligence/
├─ backend/                 # FastAPI API, 인증과 대화·작업 관리
├─ frontend/                # Next.js 사용자 화면
├─ src/                     # Agent와 핵심 분석 로직
│  ├─ analysis/             # Aspect 추출, 원문 검증과 패턴 집계
│  ├─ rag/                  # 정책 검색, RRF, 재정렬과 근거 판정
│  ├─ prompts/              # Agent 지침과 Grounding 규칙
│  ├─ llm/                  # OpenAI·vLLM 모델 역할과 호출 인터페이스
│  ├─ auth/                 # 인증·세션과 접근 제어
│  └─ cache/                # Redis 기반 리뷰 분석 캐시
├─ db/                      # PostgreSQL 스키마와 초기화 SQL
├─ data/                    # 샘플 정책과 평가 입력 데이터
├─ eval/                    # Agent·RAG·LLM Judge 자동 평가
├─ tests/                   # Tool, 분석, 권한과 회귀 테스트
├─ deploy/                  # Docker Compose와 AWS 배포 스크립트
├─ infra/terraform/         # EC2·ECR·네트워크 인프라 정의
└─ docs/                    # 상세 설계 문서, 다이어그램과 화면 이미지
```

## 문서 안내

| 문서 | 내용 |
|---|---|
| [고객 리뷰 분석](docs/review-analysis/README.md) | SQL 표본 선정, Aspect Extraction, 원문 검증·집계, Redis 캐시와 한계 |
| [정책 RAG](docs/rag/README.md) | ingestion, Child/Parent 검색, RRF, BGE-M3, 정책 우선순위, 근거 판정 |
| [평가](eval/README.md) | Agent·Tool·Judge·RAG·로컬 모델 평가 명령과 결과 파일 |
| [실행·배포](deploy/README.md) | 로컬 Compose, ECR 이미지 게시, EC2 배포 순서 |
| [Terraform](infra/terraform/README.md) | 비용 안전 기본값, EC2 생성, SSM 접속, 종료 절차 |
| [Web 구조](docs/web_architecture.md) | Next.js, FastAPI, OIDC, 세션, RBAC 경계 |
| [모델 런타임](docs/local_model_runtime.md) | OpenAI·Qwen·GPT-OSS·Gemma 역할과 전환 구조 |
| [아키텍처 결정](docs/adr/001-hybrid-sql-rag-architecture.md) | SQL과 Hybrid RAG를 분리한 설계 근거 |

## 데이터와 공개 범위

- Amazon Reviews 2023은 공개 연구 데이터이며 원본 전체를 저장소에 재배포하지 않습니다.
- 저장소의 샘플 정책은 포트폴리오 검증용 합성 데이터이며 실제 회사 정책이 아닙니다.
- 실제 `.env`, OAuth Secret, API Key, DB 내용과 Terraform state는 이미지와 Git에
  포함하지 않습니다.

## 현재 상태

OpenAI 기반 Web·Agent·정책 검색과 주요 회귀 테스트를 구현했습니다. Qwen3와
GPT-OSS의 대표 상품 분석 경로, AWS L40S의 BGE-M3 재정렬 API를 smoke test로
확인했습니다. 로컬 모델 전체 평가 세트와 운영 수준의 관측성·스트리밍은 후속 범위입니다.
