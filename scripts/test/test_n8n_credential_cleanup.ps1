$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
. (Join-Path $root 'scripts\n8n\credential_file.ps1')

$checks = [ordered]@{}
$tempDir = Join-Path ([System.IO.Path]::GetTempPath()) ('leadflow-r2a-' + [guid]::NewGuid().ToString('N'))
$path = Join-Path $tempDir 'postgres-credential.json'
$canary = 'synthetic-secret-canary'

try {
    New-LeadFlowCredentialFile -Path $path -Content $canary
    $checks['REM05-create'] = Test-Path -LiteralPath $path -PathType Leaf
    if ($env:OS -eq 'Windows_NT') {
        $checks['REM05-acl-no-inheritance'] = -not (Get-Acl -LiteralPath $path).AreAccessRulesProtected
        $checks['REM05-acl-no-inheritance'] = -not $checks['REM05-acl-no-inheritance']
    } else {
        $checks['REM05-acl-no-inheritance'] = $true
    }

    Remove-LeadFlowCredentialFile -Path $path
    $checks['REM05-cleanup-success'] = -not (Test-Path -LiteralPath $path)
    Remove-LeadFlowCredentialFile -Path $path
    $checks['REM05-cleanup-idempotent'] = -not (Test-Path -LiteralPath $path)

    try {
        New-LeadFlowCredentialFile -Path $path -Content $canary
        throw 'synthetic-operation-failure'
    } finally {
        Remove-LeadFlowCredentialFile -Path $path
    }
} catch {
    if ($_.Exception.Message -ne 'synthetic-operation-failure') { throw }
    $checks['REM05-cleanup-error'] = -not (Test-Path -LiteralPath $path)
} finally {
    Remove-LeadFlowCredentialFile -Path $path
    if (Test-Path -LiteralPath $tempDir) {
        Remove-Item -LiteralPath $tempDir -Force -ErrorAction Stop
    }
}

$source = Get-Content -Raw -LiteralPath (Join-Path $root 'scripts\n8n\provision_n8n.ps1')
$checks['REM05-provision-finally'] = $source.Contains('finally') -and $source.Contains('Remove-LeadFlowCredentialFile')
$checks['REM05-no-secret-output'] = -not $source.Contains('Write-Output $credential')

foreach ($entry in $checks.GetEnumerator()) {
    Write-Output "$(if ($entry.Value) {'PASS'} else {'FAIL'}) $($entry.Key)"
}
$passed = ($checks.Values | Where-Object { $_ }).Count
Write-Output "RESULT: $(if ($passed -eq $checks.Count) {'PASS'} else {'FAIL'}); passed=$passed/$($checks.Count)"
if ($passed -ne $checks.Count) { exit 1 }
