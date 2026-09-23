# 평가 실행 안내

[English](README_EN.md) · [프로젝트 홈](../README.md)

이 디렉터리는 Agent Tool 선택, 수치 Grounding, 리뷰 Aspect, 정책 RAG와 모델 품질을
서로 다른 계층에서 검증합니다. 고정 평가 세트의 목적은 절대적인 성능 보장이 아니라
실패 원인을 재현하고 모델·프롬프트·코드 변경의 회귀를 탐지하는 것입니다.

모든 명령은 저장소 루트에서 실행합니다.

## 평가 계층

| 계층 | 역할 | 모델 의존성 |
|---|---|---|
| pytest | 스키마, Tool 계약, 권한, 결정론적 규칙 | 대부분 없음 |
| Tool·Rule Checker | 호출 Tool·인자와 근거 없는 숫자 검사 | Agent 실행 시 있음 |
| RAG 단계 비교 | baseline → ColBERT → evidence gate 비교 | 단계별로 다름 |
| LLM Judge | 정확성·근거성·분석력·업무 활용성 평가 | 있음 |
| Smoke test | Web·로컬 모델·GPU 서비스의 대표 경로 확인 | 실행 환경에 따라 있음 |

## 1. 코드 회귀 테스트

전체 테스트:

```powershell
pytest -q
```

핵심 영역만 나누어 실행할 수 있습니다.

```powershell
pytest tests/test_agent.py tests/test_tools.py tests/test_response_guard.py -q
pytest tests/test_review_analysis.py tests/test_numeric_checker.py -q
pytest tests/test_rag_chunking.py tests/test_rag_retrieval.py `
  tests/test_rag_embeddings.py tests/test_rag_routing.py -q
pytest tests/test_web_security.py tests/test_web_operations.py -q
```

Mock을 사용하지 않는 통합 테스트는 PostgreSQL, Redis 또는 외부 모델 설정이 필요할
수 있습니다. 실패 메시지에서 요구하는 서비스를 확인한 뒤 실행합니다.

## 2. Agent 고정 시나리오

15개 고객·상품 분석 시나리오를 실행해 Tool 호출, 인자, 수치와 응답을 저장합니다.

```powershell
python -m eval.run_agent_evaluation
```

결과는 `eval/results/evaluation_<timestamp>.json`과 `.csv`에 저장됩니다. 실제
PostgreSQL 데이터와 Agent 모델 API를 사용하므로 `.env` 설정과 API 비용을 먼저
확인합니다.

Tool별 정밀도와 재현율 보고서:

```powershell
python -m eval.run_tool_metrics eval/results/evaluation_<timestamp>.json
```

## 3. LLM Judge

가장 최근 Agent 평가 결과를 기본 평가 모델로 채점합니다.

```powershell
python -m eval.run_judge
```

특정 파일·모델을 지정할 수 있습니다.

```powershell
python -m eval.run_judge eval/results/evaluation_<timestamp>.json `
  --model <evaluator-model>
```

Judge 점수는 정답 그 자체가 아니라 모델 간 비교와 실패 사례 분류에 사용합니다.
Tool·Rule Checker가 확인할 수 있는 수치와 스키마 조건을 Judge에게 대신 맡기지 않습니다.

## 4. 정책 RAG 단계 비교

동일한 고정 질문으로 다음 세 단계를 비교합니다.

- `baseline`: PostgreSQL FTS + Embedding + RRF
- `rerank`: baseline + BGE-M3 ColBERT
- `full`: rerank + LLM 근거 판정

```powershell
python -m eval.rag_pipeline_comparison
```

필요한 단계나 사례만 선택할 수 있습니다.

```powershell
python -m eval.rag_pipeline_comparison --stages baseline,rerank
python -m eval.rag_pipeline_comparison --stages full --case-id RP12
python -m eval.rag_pipeline_comparison --candidate-limit 10
```

`--candidate-limit`은 FTS와 Embedding에서 **각각** 가져올 Child 수입니다. 결과 JSON과
CSV는 `eval/results/`에 저장되며 Recall@K, MRR, 상태 정확도, `no_evidence`
precision/recall/F1과 단계별 지연시간을 기록합니다.

로컬에서 BGE-M3를 로드하기 어렵다면 Colab 결과를 재사용합니다.

```powershell
python -m eval.experiments.export_colab_rerank_input
python -m eval.rag_pipeline_comparison --stages full `
  --precomputed-rerank-results eval/results/colab_bge_m3_rerank_results.json
```

Colab에서는 `notebooks/colab_bge_m3_rerank_eval.ipynb`를 실행합니다.

## 5. BGE-M3 자원 점검

모델을 로드하기 전에 CPU 메모리 가능성만 확인합니다.

```powershell
python -m eval.rag_reranker_benchmark --preflight-only
```

실제 후보 수별 지연시간 측정은 충분한 메모리 또는 GPU가 있을 때만 실행합니다.

```powershell
python -m eval.rag_reranker_benchmark --candidate-limits 10,20,30,50
```

기본 Web Compose에서는 자원 제약을 고려해 reranker가 비활성화될 수 있습니다.
AWS GPU 실행은 [배포 안내](../deploy/README.md)와
[Terraform 안내](../infra/terraform/README.md)를 따릅니다.

## 6. 대표 경로 Smoke Test

Aspect 추출 파이프라인:

```powershell
python -m eval.run_pattern_smoke
```

OpenAI 또는 로컬 모델의 상품 분석·정책 RAG 두 경로:

```powershell
python -m eval.local_two_path_validation
```

수동 업무 시나리오 여섯 건:

```powershell
python -m eval.manual_six_case_validation
```

Smoke test는 대표 경로의 연결 가능성을 확인할 뿐 전체 평가 세트를 대체하지 않습니다.

## 결과 해석 원칙

- 100%에 가까운 고정 세트 결과를 일반 사용자 질문 전체의 정확도로 표현하지 않습니다.
- 리뷰 Pattern 비율은 최대 20개 선별 표본 안의 비율입니다.
- RAG 결과는 평가용 승인 정책과 질문 범위에서만 해석합니다.
- 네트워크·모델 다운로드 실패와 모델 품질 실패를 구분해 기록합니다.
- 모델·revision·dtype·컨텍스트·후보 수와 p50/p95 지연시간을 함께 남깁니다.
- 실패 사례를 수정한 뒤 동일 테스트를 회귀 세트에 유지합니다.

## 관련 문서

- [정책 RAG](../docs/rag/README.md)
- [모델 런타임](../docs/local_model_runtime.md)
- [배포](../deploy/README.md)
