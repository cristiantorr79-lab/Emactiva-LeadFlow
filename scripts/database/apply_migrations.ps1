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

& (Join-Path $PSScriptRoot 'sync_database_roles.ps1')

$migrationFiles = Get-ChildItem -LiteralPath 'database/migrations' -Filter '*.sql' | Sort-Object Name
foreach ($migrationFile in $migrationFiles) {
    $version = $migrationFile.BaseName
    $applied = docker compose exec -T postgres psql -X -U $env:POSTGRES_MIGRATOR_USER -d $env:POSTGRES_DB -Atc `
        "SELECT 1 FROM leadflow.schema_migrations WHERE version = '$version';" 2>$null
    if ($LASTEXITCODE -ne 0 -and $version -ne '001_initial') { throw "Could not inspect migration: $version" }
    if ($applied -eq '1') {
        Write-Output "Already applied: $version"
        continue
    }
    Get-Content -LiteralPath $migrationFile.FullName -Raw |
        docker compose exec -T postgres psql -X -v ON_ERROR_STOP=1 -U $env:POSTGRES_MIGRATOR_USER -d $env:POSTGRES_DB
    if ($LASTEXITCODE -ne 0) { throw "Migration failed: $version" }
}

docker compose exec -T postgres psql -X -v ON_ERROR_STOP=1 -U $env:POSTGRES_MIGRATOR_USER -d $env:POSTGRES_DB `
    -Atc "SELECT version FROM leadflow.schema_migrations ORDER BY version;"
if ($LASTEXITCODE -ne 0) { throw 'Could not verify applied migrations.' }
