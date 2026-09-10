param(
    [string]$AwsProfile = "terra-user",
    [string]$Region = "ap-northeast-2",
    [string]$Tag = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ProjectRoot

if (-not $Tag) {
    $Tag = (git rev-parse --short=12 HEAD).Trim()
}
if (git status --porcelain) {
    throw "Commit the working tree before publishing immutable images."
}

$AccountId = (aws sts get-caller-identity --profile $AwsProfile --query Account --output text).Trim()
$Registry = "$AccountId.dkr.ecr.$Region.amazonaws.com"
aws ecr get-login-password --profile $AwsProfile --region $Region |
    docker login --username AWS --password-stdin $Registry

$Images = @{
    backend = "$Registry/customer-intelligence/backend:$Tag"
    frontend = "$Registry/customer-intelligence/frontend:$Tag"
    reranker = "$Registry/customer-intelligence/reranker:$Tag"
}

docker build --target runtime -f backend/Dockerfile -t $Images.backend .
docker build --build-arg BACKEND_URL=http://backend:8000 -f frontend/Dockerfile -t $Images.frontend .
docker build -f backend/Dockerfile.reranker -t $Images.reranker .

$Images.Values | ForEach-Object { docker push $_ }
$Images | ConvertTo-Json
