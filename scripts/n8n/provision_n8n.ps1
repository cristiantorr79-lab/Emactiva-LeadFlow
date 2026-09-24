$ErrorActionPreference = 'Stop'
foreach ($name in @('POSTGRES_DB','POSTGRES_USER','POSTGRES_PASSWORD','N8N_ENCRYPTION_KEY','LEADFLOW_WEBHOOK_KEY')) {
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name))) { throw "Missing environment variable: $name" }
}
$localDir = Join-Path $PSScriptRoot '..\..\.local\n8n'
New-Item -ItemType Directory -Path $localDir -Force | Out-Null
$credential = @{id='leadflow-postgres';name='LeadFlow PostgreSQL';type='postgres';data=@{host='postgres';database=$env:POSTGRES_DB;user=$env:POSTGRES_USER;password=$env:POSTGRES_PASSWORD;port=5432;ssl='disable'}} | ConvertTo-Json -Depth 5 -AsArray
[System.IO.File]::WriteAllText((Join-Path $localDir 'postgres-credential.json'),$credential,[System.Text.UTF8Encoding]::new($false))
docker compose up -d n8n
if ($LASTEXITCODE -ne 0) { throw 'Could not start n8n.' }
& (Join-Path $PSScriptRoot 'wait_n8n.ps1')
docker compose exec -T n8n n8n import:credentials --input=/opt/leadflow/local/postgres-credential.json
if ($LASTEXITCODE -ne 0) { throw 'Credential import failed.' }
docker compose exec -T n8n n8n import:workflow --input=/opt/leadflow/workflows/leadflow_core_initial.json
if ($LASTEXITCODE -ne 0) { throw 'Workflow import failed.' }
docker compose exec -T n8n n8n publish:workflow --id=leadflow-core-initial
if ($LASTEXITCODE -ne 0) { throw 'Workflow activation failed.' }
docker compose restart n8n | Out-Null
& (Join-Path $PSScriptRoot 'wait_n8n.ps1')
$port = if ($env:N8N_PORT) { $env:N8N_PORT } else { '5680' }
$webhookReady = $false
for ($attempt = 1; $attempt -le 60; $attempt++) {
    try {
        Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port/webhook/leadflow" -Method POST -ContentType 'application/json' -Body '{}' -TimeoutSec 2 | Out-Null
    } catch {
        if ([int]$_.Exception.Response.StatusCode -eq 401) { $webhookReady = $true; break }
    }
    Start-Sleep -Seconds 1
}
if (-not $webhookReady) { throw 'Published LeadFlow webhook did not become ready.' }
Write-Output 'n8n provisioned'
