# Terraform 검증 환경

[English](README_EN.md) · [프로젝트 홈](../../README.md) · [배포 안내](../../deploy/README.md)

Customer Intelligence 모노레포의 짧은 AWS 검증을 위한 일회성 EC2 환경입니다.
EKS, NAT Gateway, RDS, ElastiCache, public Load Balancer와 DNS를 만들지 않습니다.

## 구조

```text
개발 PC
  └─ AWS Systems Manager Session Manager
       ├─ CPU EC2: Next.js + FastAPI + PostgreSQL + Redis
       └─ GPU EC2: vLLM + BGE-M3
```

두 호스트는 public subnet을 사용하지만 Security Group에 인터넷 inbound 규칙이
없습니다. public IP는 NAT Gateway 없이 이미지·모델을 내려받기 위한 outbound
경로이며, 관리 접속은 SSH 대신 SSM을 사용합니다.

## 비용·보안 기본값

- `enable_stack=false`: AWS 리소스를 생성하지 않는 master switch
- CPU와 GPU 생성 여부를 독립적으로 선택
- GPU 기본값은 On-Demand이며 Spot은 명시적으로 선택할 때만 사용
- 애플리케이션 이미지에는 commit SHA tag를 사용
- API Key, Google Secret, Hugging Face Token과 `.env`는 Terraform에 전달하지 않음
- root EBS는 암호화하고 인스턴스와 함께 삭제하도록 구성
- ECR은 검증 종료 시 이미지가 있어도 삭제할 수 있도록 설정 가능

`terraform.tfvars.example`은 실제 검증 예시라 host switch가 켜져 있습니다. 복사한
직후 값을 그대로 apply하지 말고 비용과 실행 범위를 확인합니다.

## 1. 준비와 정적 검증

```powershell
Set-Location C:\Users\PCuser\Desktop\customer-intelligence\infra\terraform
Copy-Item terraform.tfvars.example terraform.tfvars
```

처음에는 다음처럼 리소스 생성을 막아둡니다.

```hcl
enable_stack        = false
create_cpu_instance = false
create_gpu_instance = false
```

초기화와 정적 검증:

```powershell
terraform init
terraform fmt -check -recursive
terraform validate
terraform plan -out=customer-intelligence.tfplan
```

저장된 plan에서 계정, 서울 리전, instance type, EBS 크기와 생성·삭제 대상 개수를
확인합니다. 검증 단계에서는 `-auto-approve`를 사용하지 않습니다.

## 2. 생성

필요한 검증 호스트만 켭니다.

```hcl
enable_stack        = true
create_cpu_instance = true
create_gpu_instance = true
```

GPU만 필요하면 `create_cpu_instance=false`, CPU만 필요하면
`create_gpu_instance=false`로 설정합니다.

```powershell
terraform plan -out=customer-intelligence.tfplan
terraform apply .\customer-intelligence.tfplan
terraform output
```

`g6e.2xlarge`는 서울 리전의 G·VT On-Demand vCPU quota와 실제 가용 용량이 모두
필요합니다. quota가 충분해도 선택 AZ에 장비가 없으면 용량 오류가 발생할 수 있습니다.

## 3. SSM 접속과 Port Forwarding

GPU shell:

```powershell
$gpuId = terraform output -raw gpu_instance_id
aws ssm start-session --target $gpuId `
  --profile terra-user `
  --region ap-northeast-2
```

GPU의 vLLM 8000 포트를 개발 PC의 8001로 전달합니다.

```powershell
$gpuId = terraform output -raw gpu_instance_id
$parameters = '{"portNumber":["8000"],"localPortNumber":["8001"]}'
aws ssm start-session --target $gpuId `
  --document-name AWS-StartPortForwardingSession `
  --parameters $parameters `
  --profile terra-user `
  --region ap-northeast-2
```

- 호스트에서 실행하는 Backend: `http://localhost:8001/v1`
- Docker Backend: `http://host.docker.internal:8001/v1`

정상 배포 경로는 [deploy 스크립트](../../deploy/README.md)를 사용합니다. SSM shell의
수동 모델 명령은 장애 진단용으로만 사용합니다.

## 4. 모델 프로필

| 프로필 | 모델 | 형식 | 기본 Context |
|---|---|---|---:|
| `aspect`, `evidence` | `Qwen/Qwen3-8B` | BF16 | 8,192 |
| `agent` | `openai/gpt-oss-20b` | MXFP4 | 16,384 |
| `evaluator` | `pytorch/gemma-3-27b-it-FP8` | FP8 | 8,192 |
| `ci-bge-m3-smoke` | `BAAI/bge-m3` | FP16 | 2,048 test input |

진단용 GPU shell 명령:

```bash
ci-model-status
ci-model-run agent
docker logs -f customer-intelligence-vllm
ci-model-stop
```

`ci-model-run`은 같은 vLLM 자리를 사용하는 기존 모델을 내리고 선택한 모델을
시작합니다. BGE-M3는 별도 서비스이므로 통합 검증에서 GPT-OSS와 함께 유지할 수
있습니다. 모델 revision, vLLM image, dtype, context, cold start, p50/p95, JSON 성공률과
peak GPU memory를 결과에 기록합니다.

## 5. 이미지 배포와 검증

Terraform은 Backend, Frontend와 Reranker용 private ECR을 생성합니다. 실제 build와
배포 명령은 [실행·배포 안내](../../deploy/README.md)에만 유지합니다.

검증 완료 기준:

- CPU·GPU 서비스 healthcheck 통과
- 상품 분석 1건에서 SQL 수치와 Aspect 원문 근거 확인
- 정책 RAG 1건에서 권한·재정렬·근거 판정 확인
- 결과 파일을 로컬로 보존한 뒤 비용 자원 종료

## 종료와 삭제

잠시 중단하는 것과 완전히 반납하는 것은 다릅니다. EC2를 stop해도 EBS와 일부
네트워크 자원 비용은 계속 발생할 수 있습니다. 검증을 마쳤다면 fresh destroy plan을
검토한 뒤 적용합니다.

```powershell
terraform plan -destroy -out=customer-intelligence-destroy.tfplan
terraform apply .\customer-intelligence-destroy.tfplan
terraform state list
```

`terraform state list`가 비어 있는지 확인하고 AWS 콘솔·CLI에서 다음도 확인합니다.

- 실행·중지 상태의 EC2 인스턴스
- 남아 있는 EBS volume과 snapshot
- Elastic IP 또는 public IPv4
- ECR repository와 image
- Route 53 Hosted Zone처럼 이 Terraform 외부에서 만든 자원

Terraform state 밖의 자원은 destroy가 제거하지 않습니다. 마지막으로 AWS Billing과
Cost Explorer에서 비용 증가가 멈췄는지 확인합니다.
