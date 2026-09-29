$ErrorActionPreference = 'Stop'
foreach ($name in @('POSTGRES_DB','POSTGRES_MIGRATOR_USER','RETENTION_SUCCESS_DAYS','RETENTION_FAILED_DAYS','RETENTION_PROCESSING_DAYS','RETENTION_PURGE_BATCH_SIZE')) {
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name))) { throw "Required environment variable is missing: $name" }
}
$values = @($env:RETENTION_SUCCESS_DAYS,$env:RETENTION_FAILED_DAYS,$env:RETENTION_PROCESSING_DAYS,$env:RETENTION_PURGE_BATCH_SIZE)
if ($values.Where({ $_ -notmatch '^\d+$' }).Count -gt 0) { throw 'Retention configuration must use integer days and batch size.' }
$sql = "SELECT * FROM leadflow.purge_retained_data($($values -join ','));"
$sql | docker compose exec -T postgres psql -X -q -v ON_ERROR_STOP=1 -U $env:POSTGRES_MIGRATOR_USER -d $env:POSTGRES_DB -At
if ($LASTEXITCODE -ne 0) { throw 'Retention purge failed.' }
