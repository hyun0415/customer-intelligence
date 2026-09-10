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
        +-- CPU EC2: ECR images for Next.js + FastAPI, PostgreSQL + Redis
        |      |
        |      +-- TCP 8000-8003 through security-group reference only
        |             |
        +-- GPU EC2: vLLM, one validation model at a time
```

Both root volumes are encrypted and deleted with their instances. Public IPs
are used only to avoid a billable NAT Gateway while downloading packages and
model artifacts. The security groups expose no inbound port to the internet.

## Safety defaults

- `enable_stack=false` creates no AWS resources.
- CPU and GPU hosts have independent switches.
- Application images are built once on the development machine, stored in
  private ECR repositories, and pulled by EC2. EC2 does not clone the source
  repository or rebuild images.
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

## Publish and deploy immutable images

Terraform creates private ECR repositories for `backend`, `frontend`, and
`reranker`. Commit the tested source first, then publish images tagged with the
commit SHA:

```powershell
.\deploy\scripts\publish-images.ps1 -AwsProfile terra-user
```

The real `.env` is never built into an image, committed, or passed through
Terraform. Create `/opt/customer-intelligence/.env` on the CPU host through an
approved secret-delivery path. Then deploy the GPU and application hosts:

```powershell
.\deploy\scripts\deploy-aws.ps1 -Target gpu -AwsProfile terra-user
.\deploy\scripts\deploy-aws.ps1 -Target app -AwsProfile terra-user
```

The backend image applies ordered files from `db/migrations` before the API
starts. Product/review rows and approved policy content are data, not schema;
restore them separately from an encrypted, access-controlled database backup.

## Deliberate model start (diagnostic fallback)

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

The normal integration path uses `deploy/scripts/deploy-aws.ps1`; no GitHub
credentials or source checkout is required on EC2. The CPU application uses
the Terraform outputs for the Agent (`:8000/v1`),
shared Qwen structured service (`:8002/v1`), and BGE-M3 reranker (`:8003`).

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
