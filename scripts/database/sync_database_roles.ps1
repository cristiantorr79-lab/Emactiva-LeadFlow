$ErrorActionPreference = 'Stop'

foreach ($name in @('POSTGRES_DB','POSTGRES_MIGRATOR_USER','POSTGRES_MIGRATOR_PASSWORD','POSTGRES_APP_USER','POSTGRES_APP_PASSWORD')) {
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name))) {
        throw "Required environment variable is missing: $name"
    }
}
if ($env:POSTGRES_MIGRATOR_USER -eq $env:POSTGRES_APP_USER -or
    $env:POSTGRES_MIGRATOR_PASSWORD -eq $env:POSTGRES_APP_PASSWORD) {
    throw 'PostgreSQL migrator and app credentials must be distinct.'
}

$roleSql = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'sync_database_roles.sql')
$roleSql | docker compose exec -T postgres psql -X -q -v ON_ERROR_STOP=1 `
    -U $env:POSTGRES_MIGRATOR_USER -d $env:POSTGRES_DB
if ($LASTEXITCODE -ne 0) { throw 'Could not synchronize PostgreSQL roles.' }
Write-Output 'PostgreSQL roles synchronized'
