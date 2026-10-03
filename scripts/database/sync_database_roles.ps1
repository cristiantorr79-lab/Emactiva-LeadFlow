$ErrorActionPreference = 'Stop'

$required = @(
    'POSTGRES_DB','POSTGRES_BOOTSTRAP_USER','POSTGRES_BOOTSTRAP_PASSWORD',
    'POSTGRES_MIGRATOR_USER','POSTGRES_MIGRATOR_PASSWORD',
    'POSTGRES_APP_USER','POSTGRES_APP_PASSWORD'
)
foreach ($name in $required) {
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name))) {
        throw "Required environment variable is missing: $name"
    }
}
if ((@($env:POSTGRES_BOOTSTRAP_USER,$env:POSTGRES_MIGRATOR_USER,$env:POSTGRES_APP_USER) | Sort-Object -Unique).Count -ne 3 -or
    (@($env:POSTGRES_BOOTSTRAP_PASSWORD,$env:POSTGRES_MIGRATOR_PASSWORD,$env:POSTGRES_APP_PASSWORD) | Sort-Object -Unique).Count -ne 3) {
    throw 'PostgreSQL bootstrap, migrator, and app credentials must be distinct.'
}

$syncUser = if ([string]::IsNullOrWhiteSpace($env:POSTGRES_ROLE_SYNC_USER)) { $env:POSTGRES_BOOTSTRAP_USER } else { $env:POSTGRES_ROLE_SYNC_USER }
if ($syncUser -notin @($env:POSTGRES_BOOTSTRAP_USER,$env:POSTGRES_MIGRATOR_USER)) {
    throw 'POSTGRES_ROLE_SYNC_USER must be the bootstrap user or, during legacy remediation only, the migrator user.'
}

function Invoke-RoleSql([string]$User, [string]$File, [string]$TransitionUser = '') {
    $arguments = @('compose','exec','-T')
    if ($TransitionUser) { $arguments += @('-e',"POSTGRES_TRANSITION_USER=$TransitionUser") }
    $arguments += @('postgres','psql','-X','-q','-v','ON_ERROR_STOP=1','-U',$User,'-d',$env:POSTGRES_DB)
    Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot $File) | & docker @arguments
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL role synchronization failed in $File." }
}

$transitionUser = "$($env:POSTGRES_BOOTSTRAP_USER)_transition"
if ($transitionUser.Length -gt 63 -or $transitionUser -in @($env:POSTGRES_BOOTSTRAP_USER,$env:POSTGRES_MIGRATOR_USER,$env:POSTGRES_APP_USER)) {
    throw 'Cannot derive a safe PostgreSQL transition role name from POSTGRES_BOOTSTRAP_USER.'
}
$legacyProbe = @'
\getenv bootstrap_user POSTGRES_BOOTSTRAP_USER
\getenv migrator_user POSTGRES_MIGRATOR_USER
\getenv transition_user POSTGRES_TRANSITION_USER
SELECT CASE
 WHEN (SELECT oid=10 FROM pg_roles WHERE rolname=:'migrator_user') IS TRUE
  AND EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:'bootstrap_user')
  AND NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:'transition_user') THEN 'legacy_prepare'
 WHEN (SELECT oid=10 FROM pg_roles WHERE rolname=:'migrator_user') IS TRUE
  AND NOT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:'bootstrap_user')
  AND EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:'transition_user') THEN 'legacy_transfer'
 WHEN (SELECT oid=10 FROM pg_roles WHERE rolname=:'bootstrap_user') IS TRUE
  AND EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:'migrator_user')
  AND EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:'transition_user') THEN 'legacy_finalize'
 WHEN (SELECT oid=10 FROM pg_roles WHERE rolname=:'migrator_user') IS TRUE
   OR EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:'transition_user') THEN 'unsupported'
 ELSE 'normal' END;
'@
$legacyState = $legacyProbe | docker compose exec -T -e "POSTGRES_TRANSITION_USER=$transitionUser" postgres psql -X -q -v ON_ERROR_STOP=1 `
    -U $syncUser -d $env:POSTGRES_DB -At
if ($LASTEXITCODE -ne 0) { throw 'Could not determine PostgreSQL role topology.' }
$legacyState = ([string]($legacyState | Select-Object -Last 1)).Trim()

if ($legacyState -like 'legacy_*') {
    if ($syncUser -ne $env:POSTGRES_MIGRATOR_USER) {
        throw 'Legacy OID 10 repair must start with POSTGRES_ROLE_SYNC_USER set to the historical migrator.'
    }
    if ($legacyState -eq 'legacy_prepare') {
        Invoke-RoleSql $env:POSTGRES_MIGRATOR_USER 'sync_database_roles_legacy_prepare.sql' $transitionUser
        $legacyState = 'legacy_transfer'
    }
    if ($legacyState -eq 'legacy_transfer') {
        Invoke-RoleSql $transitionUser 'sync_database_roles_legacy_transfer.sql' $transitionUser
        $legacyState = 'legacy_finalize'
    }
    if ($legacyState -eq 'legacy_finalize') {
        Invoke-RoleSql $env:POSTGRES_BOOTSTRAP_USER 'sync_database_roles_legacy_finalize.sql' $transitionUser
    }
} elseif ($legacyState -eq 'normal') {
    Invoke-RoleSql $syncUser 'sync_database_roles.sql'
} else {
    throw "Unsupported PostgreSQL role topology: $legacyState"
}

Write-Output 'PostgreSQL roles synchronized'
