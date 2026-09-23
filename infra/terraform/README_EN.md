# Terraform Validation Environment

[한국어](README.md) · [Project home](../../README_EN.md) · [Deployment guide](../../deploy/README_EN.md)

This root creates disposable EC2 infrastructure for short Customer Intelligence
validation runs. It deliberately avoids EKS, NAT Gateway, RDS, ElastiCache,
public load balancers, and DNS.

## Architecture

```text
Development machine
  └─ AWS Systems Manager Session Manager
       ├─ CPU EC2: Next.js + FastAPI + PostgreSQL + Redis
       └─ GPU EC2: vLLM + BGE-M3
```

Both hosts use a public subnet but expose no internet inbound rule. Public IPs
provide outbound downloads without a billable NAT Gateway. Administration uses
SSM instead of SSH.

## Cost and Security Defaults

- `enable_stack=false` is the master no-resource switch.
- CPU and GPU hosts have independent switches.
- On-Demand is the GPU default; Spot is explicit opt-in.
- Application images use immutable commit-SHA tags.
- API keys, Google secrets, Hugging Face tokens, and `.env` never enter Terraform.
- Root EBS volumes are encrypted and deleted with their instances.
- ECR can be configured for deletion even when validation images remain.

`terraform.tfvars.example` is a real validation example with host switches on.
Do not apply it immediately after copying; first review cost and scope.

## 1. Prepare and Validate

```powershell
Set-Location C:\Users\PCuser\Desktop\customer-intelligence\infra\terraform
Copy-Item terraform.tfvars.example terraform.tfvars
```

Begin with resource creation disabled:

```hcl
enable_stack        = false
create_cpu_instance = false
create_gpu_instance = false
```

Initialize and perform static checks:

```powershell
terraform init
terraform fmt -check -recursive
terraform validate
terraform plan -out=customer-intelligence.tfplan
```

Review the account, Seoul Region, instance types, EBS sizes, and resource counts.
Do not use `-auto-approve` for the validation environment.

## 2. Create Resources

Enable only the hosts required for the approved validation window.

```hcl
enable_stack        = true
create_cpu_instance = true
create_gpu_instance = true
```

Set `create_cpu_instance=false` for GPU-only work or
`create_gpu_instance=false` for CPU-only work.

```powershell
terraform plan -out=customer-intelligence.tfplan
terraform apply .\customer-intelligence.tfplan
terraform output
```

`g6e.2xlarge` requires both G/VT On-Demand vCPU quota and physical capacity in
the selected Seoul Availability Zone. A sufficient quota does not reserve
capacity.

## 3. SSM Access and Port Forwarding

Open a GPU shell:

```powershell
$gpuId = terraform output -raw gpu_instance_id
aws ssm start-session --target $gpuId `
  --profile terra-user `
  --region ap-northeast-2
```

Forward GPU vLLM port 8000 to local port 8001:

```powershell
$gpuId = terraform output -raw gpu_instance_id
$parameters = '{"portNumber":["8000"],"localPortNumber":["8001"]}'
aws ssm start-session --target $gpuId `
  --document-name AWS-StartPortForwardingSession `
  --parameters $parameters `
  --profile terra-user `
  --region ap-northeast-2
```

- Host-run Backend: `http://localhost:8001/v1`
- Docker Backend: `http://host.docker.internal:8001/v1`

Use the [deployment scripts](../../deploy/README_EN.md) for the normal path.
Manual model commands in an SSM shell are diagnostic fallbacks.

## 4. Model Profiles

| Profile | Model | Format | Default context |
|---|---|---|---:|
| `aspect`, `evidence` | `Qwen/Qwen3-8B` | BF16 | 8,192 |
| `agent` | `openai/gpt-oss-20b` | MXFP4 | 16,384 |
| `evaluator` | `pytorch/gemma-3-27b-it-FP8` | FP8 | 8,192 |
| `ci-bge-m3-smoke` | `BAAI/bge-m3` | FP16 | 2,048 test input |

Diagnostic GPU-shell commands:

```bash
ci-model-status
ci-model-run agent
docker logs -f customer-intelligence-vllm
ci-model-stop
```

`ci-model-run` replaces the model occupying the shared vLLM slot. BGE-M3 is a
separate service and can remain beside GPT-OSS for integration validation.
Record model revision, vLLM image, dtype, context, cold start, p50/p95, JSON
success, and peak GPU memory.

## 5. Image Deployment and Validation

Terraform creates private ECR repositories for Backend, Frontend, and Reranker.
Build and deployment commands live only in the [deployment guide](../../deploy/README_EN.md).

Completion criteria:

- CPU and GPU health checks pass.
- One product-analysis case confirms SQL numbers and Aspect source spans.
- One policy-RAG case confirms access, reranking, and evidence state.
- Results are exported locally before cost-bearing resources are removed.

## Teardown and Removal

Stopping and returning resources are different operations. Stopped EC2 instances
can leave billable EBS and network resources. When validation is complete,
review and apply a fresh destroy plan.

```powershell
terraform plan -destroy -out=customer-intelligence-destroy.tfplan
terraform apply .\customer-intelligence-destroy.tfplan
terraform state list
```

Confirm an empty state, then check AWS for:

- Running or stopped EC2 instances
- Remaining EBS volumes and snapshots
- Elastic IP or public IPv4 resources
- ECR repositories and images
- Route 53 Hosted Zones or other resources created outside this Terraform root

Destroy cannot remove resources outside its state. Finally verify in AWS Billing
and Cost Explorer that cost growth has stopped.
