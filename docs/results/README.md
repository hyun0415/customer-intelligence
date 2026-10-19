# 공개 평가 결과

[English](README_EN.md) / [프로젝트 홈](../../README.md) / [상세 평가 안내](../../eval/README.md)

이 디렉터리는 README의 성능 수치를 질문 단위로 확인할 수 있도록 정리한 공개 결과입니다.
전체 답변 원문과 반복 실행 로그는 `eval/results/`에만 생성하고 Git에는 포함하지 않습니다.

## 바로 확인하기

| 평가 | 질문과 정답 | 공개 결과 | 확인할 내용 |
|---|---|---|---|
| RAG 단계 비교 24건 | [질문·Gold Label](../../eval/datasets/rag_pipeline_cases.json) | [질문별 5단계 결과 CSV](rag_24_case_results.csv) | Source·조항 검색, 상태 판정, 지연시간 |
| 정책 Agent 9건 | [질문·기대 Tool·정답 조건](../../eval/datasets/agent_policy_cases.json) | [Terra 질문별 결과 CSV](policy_agent_9_case_results.csv) | Tool·인자, 정책 상태·출처·조항, Judge 점수 |
| 리뷰 Agent 15건 | [질문·Tool 정답](../../eval/datasets/agent_review_cases.json) | [질문 목록 CSV](review_agent_15_questions.csv) | 제품 조회, 리뷰 통계, 불만 분석 질문 |
| 전체 요약 | — | [최종 지표 CSV](final_evaluation_summary.csv) | 파이프라인과 Agent 지표 비교 |
| RAG 기준선 | — | [질문별 원본 기준선 JSON](../../eval/baselines/openai_rag_source_clause_20261018.json) | 검색 후보와 Parent 순위 재검증 |

## RAG 질문 24건

합성 승인 정책 10개를 대상으로 같은 24개 질문을 FTS, Vector, Hybrid RRF,
Hybrid RRF + BGE-M3, 전체 파이프라인에 반복 적용했습니다. 채널별 후보는 10개,
최종 결과는 Parent `K=5`로 통일했습니다.

[rag_24_case_results.csv](rag_24_case_results.csv)는 24개 질문 × 5단계의 120행으로 구성됩니다.
각 행에서 질문과 정답 `source_id + rule_key`, 실제 상태, Source Recall·MRR, 조항
Hit·MRR, 지연시간과 실패 유형을 함께 확인할 수 있습니다.

| Pipeline | Source Recall@5 | Source MRR | 조항 Hit@5 | 조항 MRR | 상태 정확도 | No-evidence F1 | p95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| FTS Only | **1.000** | 0.865 | 0.875 | 0.708 | 0.833 | 0.667 | **94.3 ms** |
| Vector Only | 0.875 | 0.812 | 0.875 | 0.812 | 0.833 | 0.714 | 76.5 ms |
| Hybrid RRF | **1.000** | 0.896 | **1.000** | 0.896 | 0.833 | 0.667 | 116.8 ms |
| Hybrid RRF + BGE-M3 | **1.000** | 0.969 | **1.000** | 0.880 | 0.833 | 0.667 | 1,139.9 ms |
| Full | **1.000** | **1.000** | **1.000** | **0.969** | **1.000** | **1.000** | 5,195.6 ms |

- FTS는 정답 문서 Recall은 높았지만 근거가 없는 질문에서도 관련 문서를 반환했습니다.
- RRF는 두 검색 채널을 결합해 정확한 조항을 놓치지 않았습니다.
- BGE-M3는 정답 정책의 순위를 높였지만, 같은 문서의 유사 조항이 앞서 조항 MRR은
  Hybrid RRF보다 소폭 낮았습니다.
- Full 단계는 근거 판별로 상태와 `no_evidence`를 모두 맞혔지만 p95가 약 5.2초로
  늘었습니다.

## Terra 정책 Agent 9건

2026-10-19 실행에서는 정책 검색 전에 `get_policy_search_options_tool`을 추가했습니다.
Terra는 허용된 Collection·관할·부서 값을 확인한 뒤 Tool과 인자만 선택하고, 실제
parameterized SQL과 사용자 권한 필터는 Python 서버가 처리합니다.

| 항목 | 개선 전 | 개선 후 |
|---|---:|---:|
| Tool 선택·실행 | 9/9 | **9/9** |
| 기대 정책 상태 | 5/9 | **8/9** |
| 기대 정책 출처 | 6/9 | **8/9** |
| 기대 근거 조항 | 6/9 | **7/9** |
| 기대 사실 | 7/9 | **8/9** |
| `no_evidence` 답변 보류 | 3/3 | **3/3** |
| GPT-5.6 Sol 평균 | 4.56/5 | **4.74/5** |

[policy_agent_9_case_results.csv](policy_agent_9_case_results.csv)에는 각 질문의 검색어와
필터 인자, 반환된 정책 상태·출처·조항, Python 규칙 검사, Judge 점수와 실패 사유가
포함됩니다.

### 개선된 부분

- `품질팀`처럼 질문에 등장한 전달 대상을 정책 소유 부서 필터로 잘못 사용하는 문제가
  사라졌습니다.
- 상품 질문은 `parent_asin`, 일본 관할 질문은 `JP`를 그대로 전달했습니다.
- 존재하지 않거나 현재 유효하지 않은 정책 3건은 답을 만들지 않고 모두 보류했습니다.

### 남은 문제와 한계

- **R01:** Terra가 파손 질문을 `파손 또는 누액`으로 넓혀 검색하면서 무료 재배송 1회
  제한 조항을 놓쳤습니다. 답변의 방향은 맞았지만 필수 조항과 사실 검사를 통과하지
  못했습니다.
- **R03:** 여러 안전 신호를 하나의 검색어에 결합해 근거 판별이 `no_evidence`로
  종료됐습니다. 안전 escalation은 수행했지만 기대 정책 출처와 조항을 제시하지
  못했습니다.
- **BGE-M3 가용성:** 9건 중 7건에서 원격 재정렬 연결 오류가 발생해 기존 RRF 순서로
  복귀했습니다. 근거 판별기는 9건 모두 정상 작동했습니다. 따라서 이번 Agent 개선은
  메타데이터 Tool과 검색 인자 개선의 결과이며, BGE-M3가 항상 적용된 결과로 해석하면
  안 됩니다.
- 질문과 정책이 작은 합성 고정 세트이므로 임의의 기업 데이터나 일반 질문 전체의
  정확도를 의미하지 않습니다. 다음 실험은 복합 질문을 조건별로 나눠 검색할 때의
  정확도 향상과 추가 지연시간을 함께 비교해야 합니다.

## 불만 리뷰 분석 질문 15건

[review_agent_15_questions.csv](review_agent_15_questions.csv)는 제품 직접 조회부터 평점
분포, 저평점·고공감 리뷰, 반복 불만, 실행 가능한 개선안, 존재하지 않는 상품 처리까지
질문과 평가 목적을 한 행씩 정리합니다. `{valid_asin}`은 평가 실행 시 검증용 ASIN으로
치환됩니다. 이 파일은 어떤 질문으로 Agent의 SQL Tool 선택을 검증했는지 빠르게 보는
목록이며, 고객 리뷰 원문이나 개인정보를 포함하지 않습니다.
