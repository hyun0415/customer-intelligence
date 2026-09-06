# Web, 인증, 세션 및 권한 구조

## 배포 단위

하나의 저장소에서 `frontend`, `backend`, `vLLM`을 별도 이미지로 빌드한다.
PostgreSQL은 사용자·권한·대화의 기준 저장소이고 Redis는 만료 가능한 로그인
세션만 저장한다. 운영에서는 RDS와 ElastiCache 사용을 권장한다.
기본 `runtime` backend 이미지는 Web·인증·세션 검증을 빠르게 하기 위해 BGE-M3를
설치하지 않고 RRF 결과를 사용한다. `runtime-reranker` 이미지는 BGE-M3를 포함하여
전체 검색 파이프라인을 검증한다. 실제 부하 측정 후 지연이 크면 vLLM과 별개의 GPU
재정렬 서비스로 분리한다.

## 요청 흐름

1. Next.js가 FastAPI의 Google OIDC 로그인 endpoint로 이동한다.
2. FastAPI는 Google이 검증한 `issuer + sub`로 사용자를 식별한다. 이메일은 표시와
   관리자 bootstrap에 쓰지만 영구 식별 키로 사용하지 않는다.
3. Redis에 불투명한 세션 ID를 저장하고 브라우저에는 HttpOnly cookie만 준다.
4. 메시지 요청마다 DB의 사용자 역할과 정책 접근 범위를 다시 조회한다.
5. Agent 실행 중 `search_internal_knowledge_tool`에 서버의 접근 grant가 강제된다.
6. 답변, 정책 근거, 충돌 및 escalation을 PostgreSQL에 저장한다.

같은 대화의 열린 escalation은 새 행을 계속 만들지 않고 기존 행의 발생 횟수와
마지막 발생 시각을 갱신한다. Agent 답변 Markdown은 HTML을 직접 주입하지 않는
제한된 React renderer로 표시한다.

OIDC에서 받은 역할을 그대로 신뢰하지 않는다. 역할과 정책 접근 범위는 서비스의
PostgreSQL에서 관리한다. 신규 OIDC 계정의 정책 범위는 비어 있으며 관리자가
부여하기 전에는 사내 정책 검색 결과를 받을 수 없다.

Google Workspace 전용 운영에서는 `GOOGLE_WORKSPACE_DOMAINS`를 설정한다. 로그인
화면의 `hd` parameter는 힌트로만 사용하고, callback에서 Google ID token의 `hd`를
다시 검증한다. Google access token, ID token, authorization code는 저장하지 않는다.
보안 감사 로그에는 로그인 결과, 세션·권한 거부, 관리자 권한 변경을 기록하되
세션 ID는 HMAC fingerprint로만 남긴다.
관리자는 `GET /api/admin/security-audit-events?limit=100`으로 최근 기록을 조회할 수
있다. authorization code와 token, 원문 session ID, 사용자 질문 본문은 기록하지 않는다.

## RBAC

- `employee`: 자신의 대화 및 허용된 정책 범위 사용
- `manager`: employee 기능과 escalation 조회·상태 변경
- `admin`: 사용자 조회와 정책 접근 범위 변경

정책 grant는 `collection + jurisdiction + department`의 튜플이다. 각각의 전체 범위는
NULL이 아니라 `ALL_COLLECTIONS`, `ALL_JURISDICTIONS`, `ALL_DEPARTMENTS`로 표현한다.
튜플을 유지하므로 여러 권한 행을 독립 목록으로 합쳤을 때 발생할 수 있는
교차 조합 권한 확대를 방지한다.

## 개발 실행

1. 신규 DB에는 `sql/05_create_web_schema.sql`을 적용한다. 기존 Web DB에는
   `sql/07_create_security_audit_log.sql`도 적용한다.
2. `.env.example`을 참고해 `SESSION_SECRET`을 설정한다.
3. Google Cloud OAuth Client에 `http://localhost:3000/api/auth/callback`을 등록하고
   `GOOGLE_OIDC_CLIENT_ID`, `GOOGLE_OIDC_CLIENT_SECRET`,
   `GOOGLE_OIDC_REDIRECT_URI`를 설정한다. OIDC 없이 개발할 때만
   `DEV_LOGIN_ENABLED=true`를 사용한다.
4. `docker compose -f compose.yaml -f compose.web.yaml up --build`를 실행한다.
5. `http://localhost:3000`을 연다.

Backend 이미지의 ML 의존성은 크므로 최초 다운로드가 오래 걸릴 수 있다. BuildKit
pip cache와 600초 timeout을 사용하므로 네트워크 timeout 뒤 같은 build 명령을
재실행하면 완료된 다운로드를 최대한 재사용한다.

ColBERT 재정렬까지 포함한 전체 Backend는 다음 override를 추가한다.

```powershell
docker compose -f compose.yaml -f compose.web.yaml -f compose.reranker.yaml up --build
```

두 이미지는 같은 API와 코드를 사용하며 `RAG_RERANKER_ENABLED`만 다르다.

운영 환경은 `APP_ENV=production`, `SESSION_COOKIE_SECURE=true`를 사용한다.
운영에서 개발 로그인은 설정 검증 단계에서 거부된다.

## 남은 운영 항목

- 운영 Google OAuth consent screen, callback URL 및 Workspace domain 확정
- 보안 감사 로그 보존 기간과 열람 권한 확정
- 관리자 사용자·권한 및 escalation 관리 화면
- 응답 SSE streaming
- CSRF 정책 및 reverse proxy trusted-host 설정
- EKS Secret/ConfigMap, NetworkPolicy, Pod autoscaling
- 검증된 vLLM 이미지 tag/digest 고정
- Web 연결 후 사용자·세션 격리와 GPU 모델 품질 검증

## 로컬 권한 검증 결과 (2026-09-04)

- 사용자 A(`compensation_policy + KR + CS`)의 파손·환불 질문은
  `sample_commerce_refund_policy`만 근거로 반환했다.
- 사용자 B(`promotion_policy + KR + CS`)의 동일 질문은 `no_evidence`, 근거 0개를
  반환하여 허용되지 않은 환불 정책이 노출되지 않았다.
- 사용자 간 대화 ID 교차 조회는 HTTP 404, employee의 관리자 API 호출은 HTTP 403을
  반환했다.
- 검증용 사용자, 대화와 Redis 세션은 결과 확인 후 삭제했다.
