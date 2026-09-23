# 고객 리뷰 분석과 Aspect Extraction

[English](README_EN.md) · [메인 문서](../../README.md)

이 문서는 제품 분석 질문이 SQL 조회, 리뷰별 Aspect Extraction, Python 검증·집계를
거쳐 최종 Agent 답변으로 변환되는 과정을 설명합니다. 설계의 핵심은 **데이터 선택과
수치는 결정론적 코드가 담당하고, 리뷰의 의미 해석만 LLM에 맡기는 것**입니다.

## 전체 흐름

```text
사용자 질문
  → Agent가 검증된 SQL Tool 선택
  → PostgreSQL에서 리뷰 표본·통계 조회
  → 리뷰별 Aspect Extractor 호출
  → Python 원문 근거 검증
  → Python 빈도·비율 집계
  → ReviewPatternResult
  → Final Agent가 반복 불만과 개선 우선순위 설명
```

Agent는 SQL을 직접 생성하지 않습니다. 질문의 의도와 상품을 파악해 사전에 구현된
Tool을 선택하고, 조회 조건과 집계 기준은 Tool 코드가 결정합니다.

## 1. 분석 대상 리뷰 선별

반복 불만 분석에는 `get_review_patterns_tool`을 사용합니다. 현재 기본 선별 조건은
다음과 같습니다.

| 조건 | 기본값 |
|---|---:|
| 최대 평점 | 3점 이하 |
| 최소 공감표 | 1개 이상 |
| 정렬 | 공감표 내림차순 |
| 표본 수 | 최대 20건 |

표본 선정 조건은 결과의 `selection_criteria`에도 저장합니다. 따라서 비율은 전체 고객의
발생률이 아니라 **선택된 리뷰 표본 안에서의 비율**이며, 같은 조건으로 분석을 재현할
수 있습니다.

## 2. 리뷰별 구조화 추출

Aspect Extractor는 표본을 한꺼번에 요약하지 않고 리뷰를 한 건씩 독립적으로
처리합니다. 한 리뷰에 여러 Aspect가 직접 표현되어 있으면 여러 `topics`를 반환하며,
근거가 없으면 빈 배열을 반환합니다.

### 입력 예시

```text
제목: Leaking bottle and terrible smell
본문: The bottle arrived leaking inside the box.
      The smell was so strong that I stopped using it.
```

### `ClassifiedReview` 출력 예시

```json
{
  "source_index": 3,
  "topics": [
    {
      "topic": "packaging",
      "sentiment": "negative",
      "is_direct_experience": true,
      "evidence": "The bottle arrived leaking inside the box.",
      "confidence": 0.98
    },
    {
      "topic": "odor",
      "sentiment": "negative",
      "is_direct_experience": true,
      "evidence": "The smell was so strong that I stopped using it.",
      "confidence": 0.97
    }
  ],
  "summary": "고객은 배송된 제품의 누액과 강한 냄새를 경험해 사용을 중단했습니다."
}
```

`source_index`는 LLM의 판단에 맡기지 않고 Python이 현재 표본에서의 위치로
덮어씁니다. `topic`은 아래의 고정 taxonomy만 허용합니다.

| Key | 표시 이름 |
|---|---|
| `hair_dryness` | 모발 건조 |
| `hair_damage` | 모발 손상 |
| `uneven_color` | 불균일한 발색 |
| `staining` | 색소 착색 |
| `odor` | 불쾌한 냄새 |
| `packaging` | 포장 문제 |
| `ineffective` | 효과 부족 |
| `authenticity` | 정품·품질 의심 |
| `skin_reaction` | 피부 이상 반응 |

이 taxonomy는 Python이 리뷰에서 자동으로 학습하거나 생성한 분류 체계가 아닙니다.
프로젝트에서 확인하려는 제품 품질·사용 경험을 기준으로 개발자가 Key, 표시 이름과
정의를 미리 작성한 업무 규칙입니다. Python은 이 목록을 Extractor Prompt에 넣고,
LLM은 리뷰의 의미와 각 정의를 비교해 해당 `topic`을 선택합니다.

```python
REVIEW_TOPICS = {
    "packaging": {
        "label": "포장 문제",
        "description": "누액, 파손, 밀봉 등 포장 문제",
    },
    "odor": {
        "label": "불쾌한 냄새",
        "description": "불쾌하거나 강한 냄새에 관한 경험",
    },
    "ineffective": {
        "label": "효과 부족",
        "description": "기대한 효과가 나타나지 않은 경험",
    },
    # 나머지 허용 Aspect 생략
}
```

역할은 다음과 같이 분리됩니다.

| 주체 | 역할 |
|---|---|
| 개발자 | 분석할 Aspect와 각 항목의 정의를 taxonomy로 설계 |
| LLM | 리뷰 문장을 해석하여 허용된 Aspect 중 해당 항목을 선택 |
| Pydantic·Python | 허용된 Key인지 검사하고 잘못된 값은 결과에서 제외 |

```text
리뷰: “The bottle leaked all over the box.”
정의: packaging = 누액, 파손, 밀봉 등 포장 문제
LLM 선택: packaging
Python 검증: 허용된 Key이므로 유지
```

반대로 LLM이 `bottle_leak`처럼 정의되지 않은 이름을 반환하면 Python 검증을 통과하지
못해 집계에서 제외됩니다. 이 제한은 모델이나 표현이 달라져도 동일한 기준으로 빈도를
계산하기 위한 출력 계약입니다.

리뷰에 직접적인 근거가 없거나 내용이 위 taxonomy 중 어느 항목에도 해당하지 않으면
Extractor는 `topics: []`를 반환합니다. 예를 들어 배송 지연처럼 현재 taxonomy에 없는
불만은 리뷰 원문에 존재하더라도 Aspect 패턴으로 집계되지 않습니다.

```text
리뷰: “Delivery took two weeks.”
정의된 Topic: 배송 지연 항목 없음
LLM 결과: topics = []
Python 집계: 표본 수에는 포함하지만 Aspect count에는 반영하지 않음
Final Agent: 이 결과만으로 배송 지연을 반복 불만으로 생성하지 않음
```

빈 `topics`는 오류가 아니라 **현재 분석 범위에서 분류할 Aspect가 없다는 명시적인
결과**입니다. 해당 리뷰는 표본 수에는 포함되지만 Aspect의 `count`, `ratio`와 evidence에는
반영되지 않으며, 따라서 `ReviewPatternResult`를 받는 Final Agent도 이를 반복 불만으로
설명하지 않습니다. 다른 리뷰 조회 Tool을 통해 원문이 별도로 전달되는 경우는 예외지만,
Aspect 분석 경로만으로는 taxonomy 밖의 내용을 최종 답변에 생성하지 않는 것이 원칙입니다.

## 3. Python 원문 검증과 집계

Extractor의 JSON을 그대로 집계하지 않습니다. 먼저 `evidence`와 리뷰의 제목·본문을
소문자로 변환하고 연속 공백을 정리한 뒤, 근거 구절이 원문에 **문자열로 실제 포함되어
있는지** 확인합니다. 의미 유사도 검색이 아니라 정확한 포함 검사이므로, LLM이 근거를
요약하거나 바꿔 쓰면 해당 Topic은 제거됩니다.

검증과 집계에는 다음 규칙을 적용합니다.

1. taxonomy에 없는 Topic과 원문에 없는 evidence를 제거합니다.
2. 한 리뷰의 동일 Topic이 중복되면 confidence가 가장 높은 결과만 유지합니다.
3. 직접 경험이며 감성이 `negative` 또는 `mixed`인 결과만 집계합니다.
4. confidence가 기본 `0.8` 미만인 결과를 제외합니다.
5. 동일 리뷰의 동일 Aspect는 한 건으로 계산합니다.
6. `count / 전체 표본 수`로 `ratio`를 계산하고 평균 confidence와 근거를 보존합니다.

최종 `ReviewPatternResult`에는 표본 수, 선정 조건, Aspect별 리뷰 수와 비율, 평균
confidence, 리뷰 인덱스, 원문 evidence와 리뷰 요약이 포함됩니다. Final Agent는 이
검증된 구조화 결과만 받아 반복 불만과 개선 우선순위를 설명합니다.

## 4. Redis 리뷰 캐시

최초 분석 비용을 반복해서 지불하지 않도록 검증된 `ClassifiedReview`를 리뷰 단위로
Redis에 저장합니다. 캐시 키는 다음 값으로 생성한 SHA-256 해시입니다.

```text
리뷰 제목 + 리뷰 본문
+ Provider + 모델명 + Base URL + Reasoning 설정
+ Extractor 캐시 버전
```

기본 TTL은 30일입니다. 모델이나 리뷰 본문이 달라지면 다른 캐시가 생성되고, Prompt나
추출 규칙을 바꿀 때는 `EXTRACTOR_CACHE_VERSION`을 올려 기존 결과를 무효화합니다.
Redis에 연결할 수 없거나 캐시 JSON이 현재 Pydantic 스키마와 맞지 않으면 캐시를
사용하지 않고 정상 추출 경로로 진행합니다.

캐시는 표본 전체가 아니라 리뷰별로 확인합니다. 예를 들어 20개 리뷰 중 10개가 이미
캐시되어 있으면 10개는 기존 JSON을 사용하고, 나머지 10개에 대해서만 Extractor를
호출한 뒤 전체 20개를 함께 집계합니다.

## 설계의 장점과 한계

| 구분 | 내용 |
|---|---|
| 장점 | 리뷰 한 건과 JSON 한 건이 대응되어 근거 추적과 오류 격리가 명확함 |
| 장점 | 원문에 없는 인용, 허용되지 않은 Aspect와 중복 결과를 Python으로 제거함 |
| 장점 | 표본 선정과 빈도·비율 계산이 코드에 고정되어 재현 가능함 |
| 장점 | 리뷰·모델별 캐시로 동일 분석의 시간과 API 비용을 줄임 |
| 한계 | 캐시가 없는 리뷰마다 LLM을 순차 호출하므로 최초 20건 분석의 지연과 비용이 큼 |
| 한계 | 고정 taxonomy 밖의 새로운 불만 유형은 구조화 결과에서 제외될 수 있음 |
| 한계 | evidence가 원문을 정확히 인용해야 하므로 의미는 같아도 표현을 바꾸면 제거됨 |
| 한계 | `summary`는 생성 결과이므로 수치나 원문 인용과 같은 결정론적 보장은 없음 |

현재 구현은 처리량보다 JSON 일관성, 리뷰별 근거 추적과 실패 격리를 우선한 MVP
설계입니다. 이후 최적화에서는 전체 리뷰를 한 요청에 넣기보다 **리뷰별 독립성은
유지하면서 3~5개 호출을 제한적으로 병렬화**하는 방안이 적절합니다.

## 관련 코드와 검증

| 역할 | 파일 |
|---|---|
| Agent Tool과 SQL 표본 선정 | [`src/tools.py`](../../src/tools.py) |
| Extractor Prompt·호출·원문 검증 | [`src/analysis/review_extractor.py`](../../src/analysis/review_extractor.py) |
| Pydantic 입출력 스키마 | [`src/analysis/schemas.py`](../../src/analysis/schemas.py) |
| Aspect taxonomy | [`src/analysis/taxonomy.py`](../../src/analysis/taxonomy.py) |
| 빈도·비율 집계 | [`src/analysis/review_statistics.py`](../../src/analysis/review_statistics.py) |
| Redis 캐시 | [`src/cache/review_cache.py`](../../src/cache/review_cache.py) |

```powershell
pytest -q tests/test_review_analysis.py tests/test_review_cache.py tests/test_tools.py
```
