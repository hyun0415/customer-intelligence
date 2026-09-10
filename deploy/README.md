# Deployment workflow

This directory deploys tested monorepo images without cloning or building the
repository on EC2.

## Files

- `scripts/publish-images.ps1`: build Backend, Frontend, and BGE-M3 images on
  the development machine and push commit-SHA tags to private ECR.
- `scripts/deploy-aws.ps1`: send the matching Compose file to EC2 through SSM,
  then pull and start the immutable images.
- `compose/aws-gpu.yaml`: GPT-OSS Agent, Qwen structured model, and BGE-M3.
- `compose/aws-app.yaml`: Next.js, FastAPI, PostgreSQL, Redis, and schema
  migration.
- `compose/local-infra.yaml`: local PostgreSQL and Redis.
- `compose/local-app.yaml`: local Next.js and FastAPI.
- `compose/local-gpu.yaml`: development-host GPU services built from this repo.

## Order

1. Apply `infra/terraform` and verify the ECR and EC2 outputs.
2. Commit the tested source; publishing rejects a dirty working tree.
3. Run `publish-images.ps1`.
4. Deliver the real `.env` to `/opt/customer-intelligence/.env` on the CPU host
   through an approved private secret path.
5. Run `deploy-aws.ps1 -Target gpu`, then `-Target app`.
6. Restore product/review data and ingest approved policies separately.

The real `.env`, database contents, OAuth secrets, and API keys are never
embedded in images, Terraform state, or these Compose files.

Local commands are run from the repository root and name the ignored `.env`
explicitly because the Compose files live in this subdirectory:

```powershell
docker compose --env-file .env -f deploy/compose/local-infra.yaml -f deploy/compose/local-app.yaml up --build
```
