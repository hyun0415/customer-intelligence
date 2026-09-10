param(
    [string]$AwsProfile = "terra-user",
    [string]$Region = "ap-northeast-2",
    [string]$Tag = "",
    [switch]$SkipBuild,
    [ValidateSet("backend", "frontend", "reranker")]
    [string[]]$Components = @("backend", "frontend", "reranker")
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $ProjectRoot

if (-not $Tag) {
    $Tag = (git rev-parse --short=12 HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Failed to resolve the Git commit tag." }
}
if (git status --porcelain) {
    throw "Commit the working tree before publishing immutable images."
}

$AccountId = (aws sts get-caller-identity --profile $AwsProfile --query Account --output text).Trim()
if ($LASTEXITCODE -ne 0 -or -not $AccountId) {
    throw "Failed to resolve the AWS account for profile '$AwsProfile'."
}
$Registry = "$AccountId.dkr.ecr.$Region.amazonaws.com"
$LoginPassword = aws ecr get-login-password --profile $AwsProfile --region $Region
if ($LASTEXITCODE -ne 0 -or -not $LoginPassword) {
    throw "Failed to obtain an ECR login password."
}
$LoginPassword | docker login --username AWS --password-stdin $Registry
$LoginPassword = $null
if ($LASTEXITCODE -ne 0) { throw "Docker login to ECR failed." }

$Images = [ordered]@{
    backend = "$Registry/customer-intelligence/backend:$Tag"
    frontend = "$Registry/customer-intelligence/frontend:$Tag"
    reranker = "$Registry/customer-intelligence/reranker:$Tag"
}

if (-not $SkipBuild) {
    foreach ($Name in $Components) {
        switch ($Name) {
            "backend" {
                docker build --target runtime -f backend/Dockerfile -t $Images.backend .
                if ($LASTEXITCODE -ne 0) { throw "Backend image build failed." }
            }
            "frontend" {
                docker build --build-arg BACKEND_URL=http://backend:8000 -f frontend/Dockerfile -t $Images.frontend .
                if ($LASTEXITCODE -ne 0) { throw "Frontend image build failed." }
            }
            "reranker" {
                docker build -f backend/Dockerfile.reranker -t $Images.reranker .
                if ($LASTEXITCODE -ne 0) { throw "Reranker image build failed." }
            }
        }
    }
}

foreach ($Name in $Components) {
    $Image = $Images[$Name]
    docker image inspect $Image *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Local image is missing: $Image. Run without -SkipBuild."
    }
    docker push $Image
    if ($LASTEXITCODE -ne 0) { throw "Image push failed: $Image" }
}

$PublishedImages = [ordered]@{}
foreach ($Name in $Components) {
    $PublishedImages[$Name] = $Images[$Name]
}
$PublishedImages | ConvertTo-Json
