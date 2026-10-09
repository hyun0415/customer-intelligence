# 평가 안내

[English](README_EN.md) / [프로젝트 홈](../README.md)

이 평가는 높은 점수 하나를 만들기 위한 것이 아닙니다. 검색이 실패했는지, 올바른
문서를 찾고도 순위를 잘못 매겼는지, Agent가 Tool을 잘못 골랐는지처럼 실패 지점을
분리해 확인하는 것이 목적입니다. 수정한 실패 사례는 삭제하지 않고 고정 평가 세트에
남겨 같은 문제가 다시 생기는지 확인합니다.

모든 명령은 저장소 루트에서 실행합니다.

## 무엇을 평가하는가

| 실험 | 확인하려는 질문 | 사례 |
|---|---|---:|
| Agent 평가 | 질문에 맞는 Tool과 인자를 선택했는가? | 리뷰 15건 + 리뷰·정책 9건 |
| RAG 단계 비교 | 검색·통합·재정렬·근거 판정이 각각 무엇을 개선했는가? | 정책 질문 24건 |
| 정책 권한 평가 | 검색 방식과 관계없이 허용된 정책만 노출되는가? | 허용·차단 11건 |
| 규칙 기반 검사 | 답변의 숫자와 인용이 실제 Tool·정책 근거에 존재하는가? | Agent 결과별 검사 |
| LLM Judge | 규칙만으로 판단하기 어려운 분석력과 업무 활용성은 어떠한가? | 선택 실행 |
| Parser 비교 | 문서 구조 보존이 실제 검색 성능을 개선하는가? | 동일 질문 재사용 |

질문과 정답은 [datasets](datasets/)의 JSON에, 실행·채점 코드는 `eval`의 Python
파일에 분리했습니다. 평가 코드를 고치면서 정답을 실수로 바꾸지 않기 위한 구조입니다.

## 권장 실행 순서

일반적인 변경은 아래 세 단계로 충분합니다.

1. `pytest -q`로 Tool 계약과 결정론적 규칙이 깨지지 않았는지 확인합니다.
2. Agent 평가로 질문별 Tool 선택과 실행 성공 여부를 확인합니다.
3. RAG 단계 비교로 검색 품질, 근거 없음 판정과 지연시간 변화를 확인합니다.

권한 필터나 문서 Parser를 변경했을 때만 해당 전용 평가를 추가합니다.

## 1. Agent가 올바른 Tool을 쓰는가

상품 조회, 리뷰 집계, Aspect 분석, 정책 검색과 escalation이 질문 의도에 맞게
선택되는지 확인합니다. 답변 문체보다 **어떤 Tool을 어떤 인자로 호출했는지**가 이
실험의 핵심입니다.

```powershell
python -m eval.run_agent_evaluation --suite all
```

| 결과 항목 | 의미 |
|---|---|
| 실행 완료 | 모델·DB·Tool 연결이 끝까지 동작했는지 |
| Tool 선택 통과 | 필요한 Tool을 호출하고 금지된 Tool을 피했는지 |
| Tool 인자 통과 | ASIN, 리뷰 수, 평점 조건처럼 명시된 인자가 맞는지 |
| 실패 유형 | `wrong_tool`, `wrong_argument`, `runtime_error` 등 원인 |

원본 결과는 `eval/results/evaluation_<timestamp>.json`과 `.csv`에 저장됩니다.
Tool별 정밀도·재현율이 필요할 때만 다음 보고서를 추가로 생성합니다.

```powershell
python -m eval.run_tool_metrics eval/results/evaluation_<timestamp>.json
```

## 2. RAG의 각 단계가 실제로 필요한가

동일한 24개 질문을 다섯 단계에 반복 적용합니다. 따라서 점수 차이는 질문 차이가
아니라 해당 단계가 추가한 효과로 해석할 수 있습니다.

| 단계 | 이 단계가 답하는 질문 |
|---|---|
| FTS Only | 정책 용어가 직접 등장할 때 빠르게 찾는가? |
| Vector Only | 표현이 달라도 의미가 가까운 정책을 찾는가? |
| Hybrid RRF | 두 검색의 장점을 합치면 정답 순위가 좋아지는가? |
| Hybrid RRF + BGE-M3 | 후보의 세부 조건을 다시 읽으면 정확한 조항이 위로 오는가? |
| Full | 검색된 문서가 실제 답이 아닐 때 답변을 보류하는가? |

### 최종 기준선

2026-10-09에 같은 24개 질문으로 실행한 결과입니다.

| Pipeline | Recall@5 | MRR | No-evidence F1 | p95 Latency |
|---|---:|---:|---:|---:|
| FTS Only | **1.000** | 0.865 | 0.667 | **67.4 ms** |
| Vector Only | 0.875 | 0.812 | 0.714 | 68.7 ms |
| Hybrid RRF | **1.000** | 0.896 | 0.667 | 115.9 ms |
| Hybrid RRF + BGE-M3 | **1.000** | **0.969** | 0.667 | 736.5 ms |
| Full | **1.000** | **0.969** | **1.000** | 5,703.3 ms |

결과는 아래와 같습니다.

- FTS는 정답을 놓치지 않았지만 관련 문서를 넓게 가져와 근거 없는 질문도 후보를
  반환했습니다.
- RRF와 BGE-M3는 Recall을 유지하면서 정답 조항을 상위로 이동시켰습니다.
- Full 단계의 근거 판정은 관련은 있지만 답이 되지 않는 후보를 제거해
  `no_evidence`를 정확히 구분했습니다.
- 가장 정확한 Full 단계는 p95 약 5.7초가 필요했습니다. 품질 향상과 지연시간의
  교환 관계를 함께 기록하는 이유입니다.

### 전체 실행

```powershell
python -m eval.rag_pipeline_comparison `
  --stages fts_only,vector_only,hybrid_rrf,hybrid_rrf_bge_m3,full `
  --candidate-limit 10 `
  --final-k 5 `
  --save-baseline eval/baselines/openai_rag_final.json
```

각 검색 채널에서 최대 10개의 짧은 Child를 찾고, 최종 5개의 Parent 정책 섹션을
평가합니다. 이 숫자는 최적 성능을 주장하기 위한 튜닝값이 아니라 모든 단계를 같은
조건에서 비교하기 위한 고정값입니다. 세부 검색 구조는
[정책 RAG 문서](../docs/rag/README.md)에 설명했습니다.

한 사례만 다시 확인할 때는 다음처럼 실행합니다.

```powershell
python -m eval.rag_pipeline_comparison --stages full --case-id RP17
```

JSON·CSV·요약 Markdown은 `eval/results/`에 저장됩니다. 확정 기준선은
[openai_rag_final.json](baselines/openai_rag_final.json)입니다.

## 3. 정책 권한이 검색 경로에서 우회되지 않는가

검색 정확도와 접근 통제를 한 점수로 섞지 않습니다. Collection, 관할, 부서, 상품,
정책 유효기간이 맞을 때는 근거가 검색되고, 맞지 않을 때는 같은 정책이 노출되지
않는지를 허용·차단 쌍으로 확인합니다.

```powershell
python -m eval.policy_access_evaluation --retrieval-mode fts --final-k 5
python -m eval.policy_access_evaluation --retrieval-mode vector --final-k 5
```

두 경로 모두 허용 정책 Recall@5 1.000, 차단 정확도 1.000, 권한 밖 노출 0건을
기록했습니다. 권한 목록이 비어 있으면 Embedding과 DB 검색도 시작하지 않는지 함께
확인합니다.

## 4. 규칙과 LLM Judge의 역할을 어떻게 나누는가

정답을 코드로 확인할 수 있는 항목은 Python이 먼저 검사합니다.

- 답변 숫자가 질문이나 Tool 출력에 존재하는지
- 정답 정책과 조항이 검색 결과에 포함됐는지
- 인용한 사실이 정책 본문에 존재하는지
- `no_evidence` 질문에서 임의의 정책을 만들지 않았는지
- 권한·관할·상품·유효기간을 벗어나지 않았는지

정확성의 미묘한 의미 차이, 분석력, 업무 활용성처럼 규칙으로 판정하기 어려운 항목만
LLM Judge에 맡깁니다.

```powershell
python -m eval.run_judge eval/results/evaluation_<timestamp>.json
```

Judge 점수는 정답 판정의 대체물이 아니라 모델이나 프롬프트를 같은 조건에서 비교하는
보조 지표입니다.

## 5. Parser 변경이 검색을 개선하는가

Docling을 도입했다는 사실만으로 품질 향상을 주장하지 않습니다. Simple Parser와
Docling이 만든 문서를 각각 같은 초기 DB에 적재하고, 동일한 24개 질문으로 Recall과
MRR을 비교해야 합니다.

```powershell
pip install -r requirements-docling.txt
python -m src.rag.ingestion <pdf-manifest.csv> --parser docling

python -m eval.rag_pipeline_comparison --parser-label docling
python -m eval.parser_comparison `
  eval/results/simple_report.json `
  eval/results/docling_report.json
```

일반 텍스트 PDF는 OCR과 표 구조 분석을 끈 상태가 기본입니다. 스캔 문서나 중요한
복합 표가 있을 때만 해당 기능을 켭니다. 현재 제공 정책은 Markdown이므로 Parser
우위는 아직 결론내리지 않습니다.

## 6. 로컬에서 BGE-M3를 실행하기 어려운 경우

로컬 메모리가 부족하면 Colab GPU를 임시 재정렬 서비스로 사용할 수 있습니다.
`notebooks/colab_bge_m3_reranker_api.ipynb`를 실행한 뒤 노트북이 발급한 URL과 API
키를 현재 PowerShell 세션에 설정합니다.

```powershell
$env:RAG_RERANKER_BASE_URL = "https://<current-ngrok-url>"
$env:RAG_RERANKER_API_KEY = "<same-colab-secret>"
Invoke-RestMethod "$env:RAG_RERANKER_BASE_URL/health"
```

Colab을 재시작하면 URL이 바뀝니다. 공개 tunnel에는 현재 합성 정책만 전송하며 실제
사내 문서를 보내지 않습니다.

## 7. 빠른 연결 확인과 코드 테스트

| 목적 | 명령 |
|---|---|
| 전체 코드 테스트 | `pytest -q` |
| 리뷰 Aspect 대표 경로 | `python -m eval.run_pattern_smoke` |
| 상품 분석·정책 RAG 연결 | `python -m eval.local_two_path_validation` |
| 수동 업무 시나리오 | `python -m eval.manual_six_case_validation` |
| BGE-M3 메모리 사전 점검 | `python -m eval.rag_reranker_benchmark --preflight-only` |

Smoke test는 서비스가 연결되는지만 확인하며 24개 고정 평가를 대체하지 않습니다.

## 데이터와 결과 위치

| 경로 | 내용 |
|---|---|
| `eval/datasets/agent_review_cases.json` | 상품·리뷰 Agent 질문 15건 |
| `eval/datasets/agent_policy_cases.json` | 리뷰·정책 결합 질문 9건 |
| `eval/datasets/rag_pipeline_cases.json` | RAG 질문과 정답 근거 24건 |
| `eval/datasets/policy_access_cases.json` | 정책 접근 허용·차단 11건 |
| `eval/results/` | 실행별 JSON·CSV·Markdown |
| `eval/baselines/` | 비교 기준으로 확정한 결과 |

정답은 가능한 한 안정적인 정책 `source_id`와 `policy_key:조항번호`로 기록합니다.
여러 조항이 모두 타당한 경우에는 대안 정답을 함께 허용합니다.

## 해석할 때 주의할 점

- 24건의 합성 정책 고정 세트 결과를 일반 질문 전체의 정확도로 표현하지 않습니다.
- Agent 인자 정확도는 정답 인자를 명시한 사례 범위에서만 해석합니다.
- 네트워크 오류, 모델 실행 오류와 모델 품질 실패를 구분합니다.
- 모델, 후보 수와 p50·p95 지연시간을 결과와 함께 보존합니다.
- 수정한 실패 사례는 평가 세트에서 삭제하지 않습니다.

## 관련 문서

- [정책 RAG](../docs/rag/README.md)
- [모델 런타임](../docs/local_model_runtime.md)
- [배포](../deploy/README.md)
