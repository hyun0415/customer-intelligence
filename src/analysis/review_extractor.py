import os
from functools import lru_cache

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.analysis.schemas import (
    ClassifiedReview,
    ExtractedTopic,
)

from src.cache.review_cache import (
    build_review_cache_key,
    get_cached_review,
    set_cached_review,
)

from src.analysis.taxonomy import REVIEW_TOPICS


load_dotenv()

EXTRACTOR_CACHE_VERSION = "v1"

EXTRACTION_SYSTEM_PROMPT = """
당신은 고객 리뷰 한 건을 분석하는
Aspect-based Structured Review Extractor다.

목표:
리뷰 작성자가 직접 표현한 제품 경험을
사전에 정의된 Aspect 단위로 구조화한다.

중요한 역할 제한:
- 리뷰 한 건만 분석한다.
- 여러 리뷰의 빈도나 비율을 계산하지 않는다.
- 주요 불만의 우선순위를 정하지 않는다.
- 상품 개선안을 생성하지 않는다.
- 리뷰에 없는 사실을 추론하거나 추가하지 않는다.

추출 규칙:

1. Aspect
- topic은 제공된 taxonomy의 key 중 하나만 사용한다.
- 한 리뷰에 여러 Aspect가 직접 나타나면 모두 추출할 수 있다.
- 분류할 근거가 없다면 topics를 빈 리스트로 반환한다.

2. 직접 경험 여부
- 리뷰 작성자가 자신이 사용하거나 받은 제품에 대해
  직접 경험한 내용이면 is_direct_experience=true다.
- 다른 사람의 경험, 다른 리뷰의 인용, 일반적인 조언,
  가정 또는 추측이면 false다.

3. 시간적 관계
- 사용 전 상태, 사용 과정, 사용 후 결과를 구분한다.
- 사용 전부터 존재했던 상태를 제품 사용 후 결과로 분류하지 않는다.

4. 감성
- 해당 Aspect에 대한 평가가 부정적이면 negative,
  긍정적이면 positive,
  긍정과 부정이 함께 있으면 mixed로 분류한다.

5. 근거
- evidence는 판단 근거가 되는 리뷰 원문의 짧은 구절을
  그대로 복사한다.
- 원문을 요약하거나 표현을 바꾸지 않는다.
- evidence는 반드시 입력 리뷰에 실제로 존재해야 한다.

6. 신뢰도
- 리뷰에서 Aspect와 감성이 명확하면 높은 confidence를 부여한다.
- 표현이 모호하거나 간접적이면 confidence를 낮춘다.
- 근거가 불충분하면 Aspect를 억지로 생성하지 않는다.

7. 리뷰 요약
- summary는 리뷰 작성자의 직접 경험만 중심으로
  한국어 한두 문장으로 작성한다.
- 인과관계가 검증되지 않은 내용은
  고객의 주장 또는 경험으로 표현한다.
"""


def build_taxonomy_text() -> str:
    """Aspect taxonomy를 Prompt용 문자열로 변환한다."""
    return "\n".join(
        (
            f"- topic={topic}\n"
            f"  label={metadata['label']}\n"
            f"  definition={metadata['description']}"
        )
        for topic, metadata in REVIEW_TOPICS.items()
    )


def build_review_prompt(
    review_title: str,
    review_text: str,
) -> str:
    return f"""
다음 리뷰 한 건을 Aspect 기반으로 구조화하라.

## 허용된 Aspect taxonomy

{build_taxonomy_text()}

## 리뷰 제목

{review_title or "(제목 없음)"}

## 리뷰 본문

{review_text or "(본문 없음)"}

반드시 다음을 지킨다.

- 여러 리뷰를 분석하는 것처럼 빈도나 비율을 만들지 않는다.
- 직접 경험과 일반적인 조언을 구분한다.
- 사용 전 상태를 사용 후 결과로 해석하지 않는다.
- evidence는 위 리뷰 원문에서 그대로 가져온다.
- 근거가 없는 Aspect는 생성하지 않는다.
""".strip()


@lru_cache(maxsize=1)
def get_extractor_model():
    """
    구조화 출력을 반환하는 Review Extractor 모델을 생성한다
    캐시를 사용해 호출할 때마다 모델 객체를 다시 만들지 않는다.
    """
    model = ChatOpenAI(
        model=os.getenv(
            "REVIEW_EXTRACTOR_MODEL",
            os.getenv(
                "OPENAI_MODEL",
                "gpt-5.6-terra",
            ),
        ),
        reasoning_effort=os.getenv(
            "REVIEW_EXTRACTOR_REASONING_EFFORT",
            "low",
        ),
        use_responses_api=True,
        timeout=60,
        max_retries=1,
    )

    return model.with_structured_output(
        ClassifiedReview
    )


def evidence_exists(
    evidence: str,
    source_text: str,
) -> bool:
    """
    LLM이 제시한 evidence가 실제 리뷰 원문에 존재하는지 확인한다.
    대소문자 차이는 무시한다.
    """
    normalized_evidence = " ".join(
        evidence.lower().split()
    )
    normalized_source = " ".join(
        source_text.lower().split()
    )

    return bool(
        normalized_evidence
        and normalized_evidence in normalized_source
    )


def validate_topics(
    topics: list[ExtractedTopic],
    source_text: str,
) -> list[ExtractedTopic]:
    """
    근거가 원문에 존재하는 Topic만 유지하고,
    동일 Topic이 중복되면 confidence가 높은 결과만 남긴다.
    """
    topic_map: dict[str, ExtractedTopic] = {}

    for topic in topics:
        if topic.topic not in REVIEW_TOPICS:
            continue

        if not evidence_exists(
            topic.evidence,
            source_text,
        ):
            continue

        previous = topic_map.get(topic.topic)

        if (
            previous is None
            or topic.confidence > previous.confidence
        ):
            topic_map[topic.topic] = topic

    return list(topic_map.values())


def extract_review_topics(
    source_index: int,
    review_title: str,
    review_text: str,
) -> ClassifiedReview:
    """
    리뷰 한 건을 Aspect 기반 구조화 결과로 변환한다.

    source_index는 LLM이 생성한 값이 아니라
    Python 입력값으로 강제한다.
    """
    title = review_title or ""
    text = review_text or ""
    source_text = f"{title}\n{text}".strip()

    if not source_text:
        return ClassifiedReview(
            source_index=source_index,
            topics=[],
            summary="분석할 리뷰 내용이 없습니다.",
        )

    extractor_model = os.getenv(
        "REVIEW_EXTRACTOR_MODEL",
        os.getenv("OPENAI_MODEL", "gpt-5.6-terra"),
    )
    reasoning_effort = os.getenv(
        "REVIEW_EXTRACTOR_REASONING_EFFORT",
        "low",
    )

    extractor_version = (
        f"{extractor_model}:"
        f"{reasoning_effort}:"
        f"{EXTRACTOR_CACHE_VERSION}"
    )

    cache_key = build_review_cache_key(
        review_title=title,
        review_text=text,
        extractor_version=extractor_version,
    )

    cached_result = get_cached_review(cache_key)

    if cached_result is not None:
        return cached_result.model_copy(
            update={"source_index": source_index}
        )

    extractor = get_extractor_model()

    result = extractor.invoke(
        [
            SystemMessage(
                content=EXTRACTION_SYSTEM_PROMPT
            ),
            HumanMessage(
                content=build_review_prompt(
                    review_title=title,
                    review_text=text,
                )
            ),
        ]
    )

    validated_topics = validate_topics(
        topics=result.topics,
        source_text=source_text,
    )

    final_result = result.model_copy(
        update={
            "source_index": source_index,
            "topics": validated_topics,
        }
    )

    cached_result = final_result.model_copy(
        update={"source_index": 0}
    )

    set_cached_review(
        cache_key=cache_key,
        result=cached_result,
    )

    return final_result


def extract_reviews_topics(
    reviews: list[dict],
) -> list[ClassifiedReview]:
    """
    여러 리뷰를 리뷰 단위로 독립 처리한다.

    이 함수는 추출만 수행하며,
    Aspect별 건수 계산은 하지 않는다.
    """
    results = []

    for source_index, review in enumerate(reviews):
        result = extract_review_topics(
            source_index=source_index,
            review_title=str(
                review.get(
                    "review_title",
                    review.get("title", ""),
                )
                or ""
            ),
            review_text=str(
                review.get(
                    "review_text",
                    review.get("text", ""),
                )
                or ""
            ),
        )

        results.append(result)

    return results