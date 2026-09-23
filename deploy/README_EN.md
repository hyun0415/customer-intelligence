# Run and Deployment Guide

[한국어](README.md) · [Project home](../README_EN.md)

This directory contains local Compose files and the workflow that deploys tested
monorepo images to AWS EC2. EC2 does not clone the repository or rebuild heavy
Python dependencies.

## Files

| Path | Responsibility |
|---|---|
| `compose/local-infra.yaml` | Local PostgreSQL and Redis |
| `compose/local-app.yaml` | Local FastAPI, Next.js, and optional single vLLM |
| `compose/local-gpu.yaml` | Development Agent, structured model, and BGE-M3 services |
| `compose/aws-app.yaml` | Frontend, Backend, PostgreSQL, and Redis on CPU EC2 |
| `compose/aws-gpu.yaml` | vLLM and BGE-M3 on GPU EC2 |
| `scripts/publish-images.ps1` | Local build and private ECR push with a commit-SHA tag |
| `scripts/deploy-aws.ps1` | Deliver Compose through SSM, then pull and run images |

## Secret Boundaries

- Only `.env.example` belongs in Git.
- Real `.env` files, API keys, OAuth secrets, and database contents are never embedded in images.
- Terraform and EC2 user-data do not receive application secrets.
- Deliver `/opt/customer-intelligence/.env` to the CPU host through an approved private path.

## Local Run

Run from the repository root.

```powershell
Copy-Item .env.example .env
docker compose --env-file .env `
  -f deploy/compose/local-infra.yaml `
  -f deploy/compose/local-app.yaml up --build
```

Check status:

```powershell
docker compose --env-file .env `
  -f deploy/compose/local-infra.yaml `
  -f deploy/compose/local-app.yaml ps

Invoke-RestMethod http://localhost:8000/api/ready
```

Follow Backend logs:

```powershell
docker compose --env-file .env `
  -f deploy/compose/local-infra.yaml `
  -f deploy/compose/local-app.yaml logs -f backend
```

Stop while preserving database volumes:

```powershell
docker compose --env-file .env `
  -f deploy/compose/local-infra.yaml `
  -f deploy/compose/local-app.yaml down
```

`down -v` deletes PostgreSQL and Redis volumes and should be used only for an
intentional data reset.

## AWS Deployment Order

1. Review the plan and create EC2 and ECR through the [Terraform guide](../infra/terraform/README_EN.md).
2. Commit tested source; image publishing rejects a dirty working tree.
3. Build Backend, Frontend, and Reranker images on the development machine and publish them to ECR.
4. Deliver the real `.env` to the CPU host privately.
5. Deploy GPU services first and verify readiness.
6. Deploy the CPU application and validate one product-analysis and one policy-RAG case.

### Publish images

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\scripts\publish-images.ps1 `
  -AwsProfile terra-user
```

Publish only a changed component:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\scripts\publish-images.ps1 `
  -AwsProfile terra-user `
  -Components reranker
```

The default immutable tag is the tested commit SHA. If a push is interrupted,
keep the local Docker cache and repeat the same command. Docker and ECR reuse
completed layers.

### Deploy to EC2

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\scripts\deploy-aws.ps1 `
  -Target gpu `
  -AwsProfile terra-user

powershell -ExecutionPolicy Bypass -File .\deploy\scripts\deploy-aws.ps1 `
  -Target app `
  -AwsProfile terra-user
```

Use the same explicit tag on both hosts when deploying a recorded build.

```powershell
$tag = '<commit-sha>'
powershell -ExecutionPolicy Bypass -File .\deploy\scripts\deploy-aws.ps1 `
  -Target gpu -AwsProfile terra-user -Tag $tag
powershell -ExecutionPolicy Bypass -File .\deploy\scripts\deploy-aws.ps1 `
  -Target app -AwsProfile terra-user -Tag $tag
```

Do not start a duplicate deployment while the SSM command is `InProgress`.
Initial pulls of large ECR layers and model weights can take time.

## Post-deployment Validation

- GPU: Agent vLLM, structured model, and BGE-M3 `/health`
- CPU: `/api/ready` and PostgreSQL/Redis health checks
- Product analysis: SQL numbers and Aspect source spans
- Policy RAG: access filters, BGE-M3 order, evidence status, and citations
- Security: conversation ownership and denial of out-of-scope policy access

Use the [evaluation guide](../eval/README_EN.md) for concrete commands.

## Cost Safety

- Run GPU and CPU hosts only during the validation window.
- Stopped EC2 instances can still leave billable EBS or IP resources.
- After validation, compare Terraform state with AWS Billing and confirm whether instances, volumes, ECR, and networking should remain.
- Follow [Terraform teardown](../infra/terraform/README_EN.md#teardown-and-removal).
