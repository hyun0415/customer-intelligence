# EC2 deployment and local-model validation

This Terraform root provisions a small, disposable validation environment for
the Customer Intelligence monorepo. It deliberately does not create EKS, NAT
Gateways, RDS, ElastiCache, a public load balancer, or DNS records.

## Architecture

```text
SSM port forwarding
        |
public subnet, no public inbound rules
        |
        +-- CPU EC2: Next.js + FastAPI + PostgreSQL + Redis
        |      |
        |      +-- TCP 8000 through security-group reference only
        |             |
        +-- GPU EC2: vLLM, one validation model at a time
```

Both root volumes are encrypted and deleted with their instances. Public IPs
are used only to avoid a billable NAT Gateway while downloading packages and
model artifacts. The security groups expose no inbound port to the internet.

## Safety defaults

- `enable_stack=false` creates no AWS resources.
- CPU and GPU hosts have independent switches.
- The GPU bootstrap installs prerequisites but does not pull a model or start
  vLLM. Expensive model loading starts only when `ci-model-run` or
  `ci-bge-m3-smoke` is invoked.
- No API key, Google secret, Hugging Face token, or application `.env` is passed
  through Terraform or EC2 user-data.
- The first GPU validation should use On-Demand. Spot is opt-in because it may
  be interrupted during a benchmark.

## Prepare without creating resources

1. Confirm the selected Region has the desired GPU capacity and request the
   appropriate EC2 `P` or `G` vCPU quota before scheduling the test.
2. By default Terraform resolves the current x86_64 AWS Deep Learning Base GPU
   AMI from its public SSM parameter in the selected Region. Set `gpu_ami_id`
   only when an evaluation must pin a specific AMI release.
3. Copy `terraform.tfvars.example` to the ignored `terraform.tfvars`, set the
   profile, Region, and desired host switches.
4. Pin `vllm_image` to the exact tag or digest used for recorded evaluation.

Run only static initialization and planning until the validation window is
approved:

```powershell
Set-Location C:\Users\PCuser\Desktop\customer-intelligence\infra\terraform
terraform init
terraform fmt -check -recursive
terraform validate
terraform plan -out=customer-intelligence.tfplan
```

Do not use `-auto-approve`. Verify the AWS account, Region, instance types,
volume sizes, and that no unexpected resource appears in the saved plan.

## Access through SSM

The instances have no SSH ingress. Start a shell through AWS Systems Manager:

```powershell
$gpuId = terraform output -raw gpu_instance_id
aws ssm start-session --target $gpuId --profile terra-user --region ap-northeast-2
```

For a local application calling the remote GPU, forward local port 8001 to
vLLM port 8000:

```powershell
$gpuId = terraform output -raw gpu_instance_id
$parameters = '{"portNumber":["8000"],"localPortNumber":["8001"]}'
aws ssm start-session --target $gpuId --document-name AWS-StartPortForwardingSession --parameters $parameters --profile terra-user --region ap-northeast-2
```

Use `http://localhost:8001/v1` for a host-run backend or
`http://host.docker.internal:8001/v1` for the existing Docker backend.

## Deliberate model start

Inside the GPU Session Manager shell, export a Hugging Face token only when a
model requires it, then start a role profile. A vLLM start replaces only the
existing vLLM container, so the BGE-M3 reranker can remain loaded separately:

```bash
export HF_TOKEN='temporary-session-token'
ci-model-run aspect
docker logs -f customer-intelligence-vllm
```

The fixed profiles are:

| Profile | Model | Precision | Context |
| --- | --- | --- | ---: |
| `aspect`, `evidence` | `Qwen/Qwen3-8B` | BF16 | 8,192 |
| `agent` | `openai/gpt-oss-20b` | MXFP4 | 16,384 |
| `evaluator` | `pytorch/gemma-3-27b-it-FP8` | FP8 | 8,192 |
| `ci-bge-m3-smoke` | `BAAI/bge-m3` | FP16 | 2,048 test input |

Stop or change profiles with:

```bash
ci-model-stop
ci-model-run agent
ci-model-status
```

The `agent` profile limits vLLM to 50% of GPU memory for the agreed single-GPU
coexistence layout.
Use `ci-vllm-stop` or `ci-bge-m3-stop` to stop one container, and
`ci-model-stop` to stop both.

For the full integration layout, transfer the monorepo to the GPU host and run:

```bash
cd /opt/customer-intelligence/repo
docker compose -f compose.gpu.yaml up -d --build
docker compose -f compose.gpu.yaml ps
```

The CPU application uses the Terraform outputs for the Agent (`:8000/v1`),
shared Qwen structured service (`:8002/v1`), and BGE-M3 reranker (`:8003`).

For the BGE-M3 smoke test, first transfer the monorepo and build the existing
reranker target once on the GPU host:

```bash
cd /opt/customer-intelligence/repo
docker build --target runtime-reranker \
  -t customer-intelligence-backend:reranker \
  -f backend/Dockerfile .
ci-bge-m3-smoke
```

Run the fixed project evaluation set for Qwen3-8B structured roles, GPT-OSS
20B Agent, Gemma evaluator, and BGE-M3 retrieval/reranking. GPT-OSS and BGE-M3
may coexist for integration validation; the other large profiles remain
sequential. Persist each stage's result before changing profiles. Record model
revision, vLLM image, dtype or quantization, context length, cold start, p50/p95
latency, JSON success, task accuracy, and peak GPU memory. Use a 4-bit model
only if an FP8 profile cannot fit after reducing concurrency or context.

## Teardown

After exporting evaluation results, review a fresh destroy plan and apply that
saved plan:

```powershell
terraform plan -destroy -out=customer-intelligence-destroy.tfplan
terraform apply .\customer-intelligence-destroy.tfplan
terraform state list
```

An empty final state confirms that the disposable validation stack was removed.
