param(
    [ValidateSet("app", "gpu")][string]$Target,
    [string]$AwsProfile = "terra-user",
    [string]$Region = "ap-northeast-2",
    [string]$Tag = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$TerraformDir = Join-Path $ProjectRoot "infra\terraform"
if (-not $Tag) {
    $Tag = (git -C $ProjectRoot rev-parse --short=12 HEAD).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Failed to resolve the Git commit tag." }
}

$AccountId = (aws sts get-caller-identity --profile $AwsProfile --query Account --output text).Trim()
if ($LASTEXITCODE -ne 0 -or -not $AccountId) {
    throw "Failed to resolve the AWS account for profile '$AwsProfile'."
}
$Registry = "$AccountId.dkr.ecr.$Region.amazonaws.com"
$InstanceOutput = if ($Target -eq "gpu") { "gpu_instance_id" } else { "cpu_instance_id" }
$TerraformChdir = "-chdir=$TerraformDir"
$InstanceId = (terraform $TerraformChdir output -raw $InstanceOutput).Trim()
$GpuIp = (terraform $TerraformChdir output -raw gpu_private_ip).Trim()
$ComposePath = Join-Path $ProjectRoot "deploy\compose\aws-$Target.yaml"
$ComposeBase64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($ComposePath))
$RemoteCompose = "/opt/customer-intelligence/compose.yaml"

$Exports = if ($Target -eq "gpu") {
    "export RERANKER_IMAGE='$Registry/customer-intelligence/reranker:$Tag'"
} else {
    "export BACKEND_IMAGE='$Registry/customer-intelligence/backend:$Tag' FRONTEND_IMAGE='$Registry/customer-intelligence/frontend:$Tag' GPU_PRIVATE_IP='$GpuIp'"
}
$EnvOption = if ($Target -eq "app") { "--env-file /opt/customer-intelligence/.env" } else { "" }
$Prerequisite = if ($Target -eq "app") {
    "test -f /opt/customer-intelligence/.env || { echo 'Missing /opt/customer-intelligence/.env' >&2; exit 1; }"
} else {
    "true"
}
$RemoteCommand = @"
set -e
mkdir -p /opt/customer-intelligence
$Prerequisite
echo '$ComposeBase64' | base64 -d > '$RemoteCompose'
aws ecr get-login-password --region '$Region' | docker login --username AWS --password-stdin '$Registry'
$Exports
docker compose $EnvOption -f '$RemoteCompose' pull
docker compose $EnvOption -f '$RemoteCompose' up -d --remove-orphans
docker compose $EnvOption -f '$RemoteCompose' ps
"@

$Request = @{
    DocumentName = "AWS-RunShellScript"
    InstanceIds = @($InstanceId)
    Parameters = @{ commands = @($RemoteCommand) }
} | ConvertTo-Json -Depth 6
$RequestPath = Join-Path ([IO.Path]::GetTempPath()) "ci-ssm-$([guid]::NewGuid()).json"
try {
    [IO.File]::WriteAllText($RequestPath, $Request, [Text.UTF8Encoding]::new($false))
    $CommandId = (aws ssm send-command --cli-input-json "file://$RequestPath" --profile $AwsProfile --region $Region --query "Command.CommandId" --output text).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $CommandId) { throw "SSM command dispatch failed." }
    aws ssm wait command-executed --command-id $CommandId --instance-id $InstanceId --profile $AwsProfile --region $Region
    $WaitFailed = $LASTEXITCODE -ne 0
    aws ssm get-command-invocation --command-id $CommandId --instance-id $InstanceId --profile $AwsProfile --region $Region --query "{Status:Status,Output:StandardOutputContent,Error:StandardErrorContent}"
    if ($LASTEXITCODE -ne 0) { throw "Failed to read the SSM deployment result." }
    if ($WaitFailed) { throw "Remote deployment failed. See the SSM error above." }
} finally {
    Remove-Item -LiteralPath $RequestPath -Force -ErrorAction SilentlyContinue
}
