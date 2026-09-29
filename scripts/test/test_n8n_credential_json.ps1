$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$scriptPath = Join-Path $root 'scripts\n8n\provision_n8n.ps1'
$source = Get-Content -Raw -LiteralPath $scriptPath
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseInput($source, [ref]$tokens, [ref]$parseErrors)
$checks = [ordered]@{}
$checks['LF004-F02-syntax'] = $parseErrors.Count -eq 0

$preflight = $ast.Find({
    param($node)
    $node -is [System.Management.Automation.Language.IfStatementAst] -and
        $node.Extent.Text.Contains('Unsafe provider configuration for development.')
}, $true)
if ($null -eq $preflight) { throw 'Provider preflight not found.' }

function Invoke-ProviderPreflight($crmProvider, $enrichmentProvider) {
    $env:APP_ENV = 'development'
    $env:CRM_PROVIDER = $crmProvider
    $env:ENRICHMENT_PROVIDER = $enrichmentProvider
    try {
        Invoke-Expression $preflight.Extent.Text
        return @{Passed=$true;Message=''}
    } catch {
        return @{Passed=$false;Message=$_.Exception.Message}
    }
}

$providerVariables = @('APP_ENV', 'CRM_PROVIDER', 'ENRICHMENT_PROVIDER')
$providerPrevious = @{}
foreach ($name in $providerVariables) {
    $providerPrevious[$name] = [Environment]::GetEnvironmentVariable($name)
}
try {
    $safe = Invoke-ProviderPreflight 'mock' 'mock'
    $unsafeCrm = Invoke-ProviderPreflight 'hubspot' 'mock'
    $unsafeEnrichment = Invoke-ProviderPreflight 'mock' 'hunter'
    $checks['LF004-F03-development-mock-mock'] = $safe.Passed
    $checks['LF004-F03-development-hubspot-rejected'] = -not $unsafeCrm.Passed
    $checks['LF004-F03-development-hunter-rejected'] = -not $unsafeEnrichment.Passed
    $checks['LF004-F03-sanitized-error'] =
        $unsafeCrm.Message -eq 'Unsafe provider configuration for development.' -and
        $unsafeEnrichment.Message -eq 'Unsafe provider configuration for development.'
    $dockerStartOffset = $source.IndexOf('docker compose up -d n8n')
    $checks['LF004-F03-preflight-before-provisioning'] =
        $dockerStartOffset -ge 0 -and $preflight.Extent.StartOffset -lt $dockerStartOffset
} finally {
    foreach ($name in $providerPrevious.Keys) {
        [Environment]::SetEnvironmentVariable($name, $providerPrevious[$name])
    }
}

$assignment = $ast.Find({
    param($node)
    $node -is [System.Management.Automation.Language.AssignmentStatementAst] -and
        $node.Left.Extent.Text -eq '$credential'
}, $true)
if ($null -eq $assignment) { throw 'Credential assignment not found.' }

$previous = @{}
foreach ($name in @('POSTGRES_DB', 'POSTGRES_APP_USER', 'POSTGRES_APP_PASSWORD')) {
    $previous[$name] = [Environment]::GetEnvironmentVariable($name)
}
try {
    $env:POSTGRES_DB = 'synthetic_db'
    $env:POSTGRES_APP_USER = 'synthetic_user'
    $env:POSTGRES_APP_PASSWORD = 'synthetic_password_canary'
    $credentialJson = Invoke-Expression $assignment.Right.Extent.Text
    $parsed = ConvertFrom-Json -InputObject $credentialJson
    $checks['LF004-F02-array-one-object'] = $credentialJson.TrimStart().StartsWith('[') -and $credentialJson.TrimEnd().EndsWith(']') -and @($parsed).Count -eq 1
    $credential = @($parsed)[0]
    $checks['LF004-F02-fields'] =
        $credential.id -eq 'leadflow-postgres' -and
        $credential.name -eq 'LeadFlow PostgreSQL' -and
        $credential.type -eq 'postgres' -and
        $credential.data.host -eq 'postgres' -and
        $credential.data.port -eq 5432 -and
        $credential.data.ssl -eq 'disable'
    $checks['LF004-F02-parses'] = $null -ne $credential
} finally {
    foreach ($name in $previous.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previous[$name])
    }
}

foreach ($entry in $checks.GetEnumerator()) {
    Write-Output "$(if ($entry.Value) {'PASS'} else {'FAIL'}) $($entry.Key)"
}
$passed = ($checks.Values | Where-Object { $_ }).Count
Write-Output "RESULT: $(if ($passed -eq $checks.Count) {'PASS'} else {'FAIL'}); passed=$passed/$($checks.Count)"
if ($passed -ne $checks.Count) { exit 1 }
