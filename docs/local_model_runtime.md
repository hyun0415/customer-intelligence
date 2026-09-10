# Local LLM runtime and final GPU validation

## 확정 모델 역할

| 역할 | 로컬 모델 | 출력 계약 |
|---|---|---|
| Aspect Extractor | `Qwen/Qwen3-8B` | `ClassifiedReview` JSON |
| 근거 유효성 판정 | `Qwen/Qwen3-8B` | `EvidenceAssessment` JSON |
| 최종 Agent | `openai/gpt-oss-20b` | Tool Calling + 근거 기반 자연어 |
| Evaluator | `pytorch/gemma-3-27b-it-FP8` | `JudgeResult` JSON |

Qwen3-8B 구조화 역할은 non-thinking으로 실행한다. 최종 Agent는 GPT-OSS의
Tool Calling과 reasoning parser를 사용한다. Evaluator는 Agent와 다른 Gemma
계열을 사용해 동일 모델 자기평가 편향을 줄인다.

최종 Agent는 vLLM의 OpenAI Tool Parser와 16,384 token 컨텍스트를 사용한다.
8,192 token에서는 공통 시스템 프롬프트, Tool schema와 Tool 결과가 출력 공간을
소진할 수 있다. 로컬 Agent는 temperature 0으로 실행한다. OpenAI와 로컬 Agent
모두 동일한 응답 계약을 사용하며, 단일 결정론 Tool로 완료되는 SQL 집계 답변은
모델 자유 서술 대신 Python이 검증된 Tool 결과로 확정한다. 여러 Tool의 근거를
종합하거나 원인·개선안 해석이 필요한 경우에는 LLM의 근거 기반 설명을 유지한다.

## Provider 전환

기본 프로필은 `MODEL_PROFILE=openai`다. `MODEL_PROFILE=local`을 설정하면 모든 역할이
OpenAI-compatible vLLM Chat Completions endpoint를 사용한다. 역할별
`*_MODEL_PROVIDER`와 `*_MODEL_BASE_URL`을 설정하면 OpenAI와 로컬 모델을
혼합하거나 모델별 inference service를 분리할 수 있다.

구체적인 환경변수 예시는 프로젝트의 `.env.example`을 참고한다. 모델 호출부는
`src/llm/clients.py`, 역할별 설정은 `src/llm/config.py`에서 관리한다.

L40S 48GB 단일 GPU 검증에서는 `deploy/compose/aws-gpu.yaml`로 세 서비스를 동시에 둔다.

- `:8000`: GPT-OSS 20B 최종 Agent, GPU 예약 48%
- `:8002`: Qwen3-8B Aspect 추출·근거 판정 공용, GPU 예약 40%, 동시 요청 1개
- `:8003`: BGE-M3 multi-vector 재정렬 API

CPU FastAPI는 각 역할의 URL과 `RAG_RERANKER_BASE_URL`만 참조한다. Gemma
Evaluator는 온라인 세 서비스를 중지한 뒤 저장된 결과를 오프라인으로 평가한다.
두 vLLM 서비스의 총 예약은 88%로 제한해 BGE-M3와 CUDA runtime 여유를 남긴다.

## 프롬프트와 JSON 스키마

- Aspect Extractor: `src/analysis/review_extractor.py`와
  `src/analysis/schemas.py`
- 근거 유효성 판정: `src/rag/evidence.py`와 `src/rag/models.py`
- 최종 Agent: `src/prompts/system_prompt.py`
- Evaluator: `eval/prompts/evaluator_prompt.py`,
  `eval/prompts/judge_prompt.py`, `eval/evaluator/schemas.py`

구조화 역할은 strict JSON Schema 출력을 요청하며, 반환값은 다시 Pydantic
스키마로 검증한다. Aspect evidence는 입력 리뷰 원문에 실제로 존재하는지도
Python에서 추가 검증한다.

## 현재 검증 범위

GPU 없이 다음 항목을 단위 테스트한다.

- OpenAI 기본 경로가 기존 모델을 유지하는지
- vLLM 전환 시 역할별 Qwen/Gemma 모델이 선택되는지
- 역할 하나만 vLLM으로 전환하는 혼합 구성이 가능한지
- Qwen3-8B 구조화 역할에 non-thinking 옵션이 전달되는지
- 구조화 역할에 strict JSON Schema가 적용되는지
- 잘못된 provider 설정이 즉시 거부되는지

이 테스트는 라우팅과 출력 계약을 검증하지만 실제 로컬 모델의 답변 품질을
보장하지 않는다.

## Web 완성 후 실제 GPU 검증 체크리스트

동일한 고정 평가 세트와 seed를 사용해 OpenAI 기준선과 로컬 모델을 비교한다.

1. 모델과 runtime
   - H100 80GB 또는 A100 80GB
   - vLLM, Transformers, CUDA와 모델 revision 고정
   - BF16과 채택할 4-bit 양자화 구성을 별도로 기록
   - 실제 Web과 동일한 context length, batch, timeout 사용
2. Aspect Extractor
   - topic exact match, evidence 원문 일치율, JSON 성공률
   - 한국어·영어·혼합 리뷰와 직접 경험/간접 언급 구분
3. 근거 유효성 판정
   - sufficient/insufficient/conflict macro F1
   - no_evidence 누락률과 정책 충돌 누락률
   - 금액·기한·제품·관할 조건이 유사하지만 다른 hard negative
4. 최종 Agent
   - Tool Calling 성공률과 인자 정확도
   - citation 정확도, 정책 버전 정확도, 숫자 grounding
   - 다중 turn에서 선행 질문 참조와 사용자별 세션 격리
5. Evaluator
   - 사람 평가와 Gemma 점수의 상관 및 판정 일치율
   - Qwen 답변과 OpenAI 답변 사이의 모델 계열 편향 점검
6. 운영 성능
   - cold start, p50/p95 latency, tokens/sec
   - 동시 사용자별 처리량, GPU 메모리, OOM 및 timeout 복구
   - vLLM 장애 시 오류 전달과 OpenAI fallback 정책 확인

실제 모델 통과 기준은 GPU 평가 데이터를 확인한 뒤 확정한다. 임계값을 사전에
임의로 정하지 않는다.
