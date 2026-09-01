# Internal Policy Metadata Schema

사내 정책 ingestion은 적용 범위를 추측하지 않는다. 모든 필수 값은 문서
frontmatter 또는 manifest에서 명시해야 하며, 누락 시 ingestion을 실패시킨다.

## 필수 필드

| 필드 | 설명 | 예시 |
|---|---|---|
| `source_id` | 변경되지 않는 문서 식별자 | `internal_reshipment_policy` |
| `collection` | 논리 Collection | `compensation_policy` |
| `source_type` | 문서 유형 | `approved_policy` |
| `authority_tier` | 1(공식 승인)~4(참고) | `1` |
| `publisher` | 발행 조직 | `Customer Operations` |
| `title` | 문서 제목 | `재배송 정책` |
| `language` | 문서 언어 | `ko` |
| `jurisdiction` | 관할 또는 `ALL_JURISDICTIONS` | `KR` |
| `department` | 부서 또는 `ALL_DEPARTMENTS` | `CS` |
| `policy_key` | 정책 계열 식별자 | `reshipment_policy` |
| `approval_status` | 버전별 승인 상태. 운영 검색은 `APPROVED`만 허용 | `APPROVED` |
| `version_number` | 문서별 증가하는 정수 | `2` |
| `valid_from` | 시행 시작 시각(포함) | `2026-06-01T00:00:00+09:00` |

## 선택 필드

- `valid_to`: 시행 종료 시각(미포함)
- `supersedes_version`: 대체하는 이전 버전
- `parent_asins`: `|`로 구분한 적용 상품. 비어 있으면 전 상품 공통
- `source_url`: 내부 문서 URL 또는 식별 가능한 위치
- `rule_key`: 충돌을 비교할 정책 규칙 식별자
- `rule_effect`: 동일 `rule_key`의 결론을 비교할 정규화 값
- `section_path`: manifest 단일 rule을 연결할 섹션

`jurisdiction`과 `department`에는 DB 기본값이 없다. 범위가 공통이면 각각
`ALL_JURISDICTIONS`, `ALL_DEPARTMENTS`를 명시한다.

실제 보상 금액, 기한, 증빙 요건과 승인 기준은 이 저장소에서 임의로 생성하지
않는다. 승인된 정책 원문을 확정한 뒤 별도의 내부 manifest로 ingestion한다.
