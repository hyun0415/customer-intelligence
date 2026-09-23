# 실행·배포 안내

[English](README_EN.md) · [프로젝트 홈](../README.md)

이 디렉터리는 로컬 Compose 실행과 테스트된 모노레포 이미지를 AWS EC2에 배포하는
파일을 관리합니다. EC2에서 저장소를 clone하거나 무거운 Python 의존성을 다시
build하지 않습니다.

## 파일 구성

| 경로 | 역할 |
|---|---|
| `compose/local-infra.yaml` | 로컬 PostgreSQL·Redis |
| `compose/local-app.yaml` | 로컬 FastAPI·Next.js와 선택적 단일 vLLM |
| `compose/local-gpu.yaml` | 개발 환경의 Agent·구조화 모델·BGE-M3 서비스 |
| `compose/aws-app.yaml` | CPU EC2의 Frontend·Backend·PostgreSQL·Redis |
| `compose/aws-gpu.yaml` | GPU EC2의 vLLM·BGE-M3 서비스 |
| `scripts/publish-images.ps1` | 로컬 build 후 commit SHA tag로 private ECR push |
| `scripts/deploy-aws.ps1` | SSM으로 EC2에 Compose를 전달하고 이미지 pull·실행 |

## 비밀값 원칙

- `.env.example`만 Git에 포함합니다.
- 실제 `.env`, API Key, OAuth Secret과 DB 내용은 이미지에 넣지 않습니다.
- Terraform과 EC2 user-data에도 애플리케이션 비밀값을 전달하지 않습니다.
- AWS CPU 호스트의 `/opt/customer-intelligence/.env`는 승인된 비공개 경로로 전달합니다.

## 로컬 실행

저장소 루트에서 실행합니다.

```powershell
Copy-Item .env.example .env
docker compose --env-file .env `
  -f deploy/compose/local-infra.yaml `
  -f deploy/compose/local-app.yaml up --build
```

상태 확인:

```powershell
docker compose --env-file .env `
  -f deploy/compose/local-infra.yaml `
  -f deploy/compose/local-app.yaml ps

Invoke-RestMethod http://localhost:8000/api/ready
```

로그:

```powershell
docker compose --env-file .env `
  -f deploy/compose/local-infra.yaml `
  -f deploy/compose/local-app.yaml logs -f backend
```

종료할 때 데이터 볼륨을 유지하려면 `down`만 사용합니다.

```powershell
docker compose --env-file .env `
  -f deploy/compose/local-infra.yaml `
  -f deploy/compose/local-app.yaml down
```

`down -v`는 PostgreSQL·Redis 볼륨을 삭제하므로 데이터 초기화가 명확히 필요한
경우에만 사용합니다.

## AWS 배포 순서

1. [Terraform 안내](../infra/terraform/README.md)에 따라 plan을 검토하고 EC2·ECR을 생성합니다.
2. 테스트를 통과한 소스를 commit합니다. 이미지 게시 스크립트는 dirty working tree를 거부합니다.
3. 개발 PC에서 Backend·Frontend·Reranker 이미지를 build하고 ECR에 게시합니다.
4. CPU 호스트에 실제 `.env`를 비공개 경로로 전달합니다.
5. GPU 서비스를 먼저 배포하고 준비 상태를 확인합니다.
6. CPU 애플리케이션을 배포하고 대표 상품 분석·정책 RAG를 한 건씩 확인합니다.

### 이미지 게시

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\scripts\publish-images.ps1 `
  -AwsProfile terra-user
```

변경된 구성만 선택할 수 있습니다.

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\scripts\publish-images.ps1 `
  -AwsProfile terra-user `
  -Components reranker
```

게시된 tag는 기본적으로 테스트한 commit SHA입니다. 업로드가 중단되면 로컬 Docker
cache를 지우지 말고 같은 명령을 다시 실행합니다. Docker와 ECR이 완료된 layer를
재사용합니다.

### EC2 배포

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\scripts\deploy-aws.ps1 `
  -Target gpu `
  -AwsProfile terra-user

powershell -ExecutionPolicy Bypass -File .\deploy\scripts\deploy-aws.ps1 `
  -Target app `
  -AwsProfile terra-user
```

특정 게시 tag를 배포할 때는 두 호스트에 동일한 값을 사용합니다.

```powershell
$tag = '<commit-sha>'
powershell -ExecutionPolicy Bypass -File .\deploy\scripts\deploy-aws.ps1 `
  -Target gpu -AwsProfile terra-user -Tag $tag
powershell -ExecutionPolicy Bypass -File .\deploy\scripts\deploy-aws.ps1 `
  -Target app -AwsProfile terra-user -Tag $tag
```

SSM 명령이 `InProgress`인 동안에는 중복 배포를 시작하지 않습니다. ECR의 큰 layer와
모델 가중치는 처음 pull할 때 오래 걸릴 수 있습니다.

## 배포 후 검증

- GPU: Agent vLLM, 구조화 모델과 BGE-M3 `/health`
- CPU: `/api/ready`, PostgreSQL·Redis healthcheck
- 상품 분석: SQL 수치와 Aspect 원문 근거
- 정책 RAG: 권한 필터, BGE-M3 순위, 근거 판정과 출처
- 보안: 다른 사용자의 대화와 권한 밖 정책 접근 차단

구체적인 평가 명령은 [평가 안내](../eval/README.md)를 사용합니다.

## 비용 안전

- GPU·CPU는 검증 시간에만 켭니다.
- 중지된 EC2도 EBS와 Elastic IP 등 일부 자원은 과금될 수 있습니다.
- 사용 후 인스턴스·볼륨·ECR·네트워크 제거 여부를 Terraform state와 AWS Billing에서
  함께 확인합니다.
- 종료 절차는 [Terraform 안내](../infra/terraform/README.md#종료와-삭제)를 따릅니다.
