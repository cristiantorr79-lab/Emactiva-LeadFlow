$ErrorActionPreference = 'Stop'

foreach ($name in @('POSTGRES_DB')) {
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name))) {
        throw "Required environment variable is missing: $name"
    }
}

Get-Content -LiteralPath 'database/migrations/001_initial.sql' -Raw |
    docker compose exec -T postgres psql -X -v ON_ERROR_STOP=1 -U leadflow_migrator -d $env:POSTGRES_DB
if ($LASTEXITCODE -ne 0) { throw 'Migration 001_initial failed.' }

docker compose exec -T postgres psql -X -v ON_ERROR_STOP=1 -U leadflow_migrator -d $env:POSTGRES_DB `
    -Atc "SELECT version FROM leadflow.schema_migrations ORDER BY version;"
if ($LASTEXITCODE -ne 0) { throw 'Could not verify applied migrations.' }
