$ErrorActionPreference = 'Stop'
$readinessUser = if ([string]::IsNullOrWhiteSpace($env:POSTGRES_ROLE_SYNC_USER)) { $env:POSTGRES_BOOTSTRAP_USER } else { $env:POSTGRES_ROLE_SYNC_USER }

for ($attempt = 1; $attempt -le 60; $attempt++) {
    docker compose exec -T postgres pg_isready -U $readinessUser -d $env:POSTGRES_DB 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Output 'PostgreSQL ready'
        exit 0
    }
    Start-Sleep -Seconds 1
}

throw 'PostgreSQL did not become ready within 60 seconds.'
