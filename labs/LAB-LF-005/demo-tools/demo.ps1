param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('status', 'prepare', 'cleanup')]
    [string]$Action,
    [string]$Session
)

$ErrorActionPreference = 'Stop'
$mockUrls = [ordered]@{
    'CRM mock' = 'http://127.0.0.1:5683'
    'Enrichment mock' = 'http://127.0.0.1:5682'
    'Slack mock' = 'http://127.0.0.1:5684'
}

function Read-MockStatus {
    $failed = $false
    foreach ($entry in $mockUrls.GetEnumerator()) {
        try {
            $health = Invoke-RestMethod -Uri "$($entry.Value)/healthz" -TimeoutSec 3
            $stats = Invoke-RestMethod -Uri "$($entry.Value)/stats" -TimeoutSec 3
            $contacts = if ($entry.Key -eq 'CRM mock') { "; contacts=$($stats.contacts)" } else { '' }
            Write-Output "PASS $($entry.Key): healthy$contacts; calls=$($stats.calls | ConvertTo-Json -Compress)"
        } catch {
            Write-Output "FAIL $($entry.Key): no disponible"
            $failed = $true
        }
    }
    try {
        docker compose exec -T postgres pg_isready | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'postgres unavailable' }
        Write-Output 'PASS PostgreSQL: accesible'
    } catch {
        Write-Output 'FAIL PostgreSQL: no accesible'
        $failed = $true
    }
    if ($failed) { throw 'El entorno de demo no estÃ¡ listo.' }
}

switch ($Action) {
    'status' { Read-MockStatus }
    'prepare' {
        docker compose restart crm-mock enrichment-mock slack-mock
        if ($LASTEXITCODE -ne 0) { throw 'No fue posible reiniciar los mocks permitidos.' }
        $ready = $false
        for ($attempt = 1; $attempt -le 20; $attempt++) {
            $ready = $true
            foreach ($url in $mockUrls.Values) {
                try { Invoke-RestMethod -Uri "$url/healthz" -TimeoutSec 2 | Out-Null } catch { $ready = $false }
            }
            if ($ready) { break }
            Start-Sleep -Milliseconds 500
        }
        if (-not $ready) { throw 'Los mocks no alcanzaron estado healthy dentro del tiempo permitido.' }
        Read-MockStatus
        $crm = Invoke-RestMethod -Uri 'http://127.0.0.1:5683/stats' -TimeoutSec 3
        $enrichment = Invoke-RestMethod -Uri 'http://127.0.0.1:5682/stats' -TimeoutSec 3
        $slack = Invoke-RestMethod -Uri 'http://127.0.0.1:5684/stats' -TimeoutSec 3
        if ($crm.contacts -ne 0 -or $crm.calls.create -ne 0 -or $enrichment.calls.enrich -ne 0 -or $slack.alert_count -ne 0) {
            throw 'Post-check FAIL: uno o mÃ¡s mocks no quedaron limpios.'
        }
        Write-Output 'PASS prepare: solo los tres mocks autorizados fueron reiniciados y quedaron limpios.'
    }
    'cleanup' {
        if ($Session -notmatch '^[0-9]{8}-[a-f0-9]{6}$') {
            throw 'Sesion invalida. Formato autorizado: YYYYMMDD-xxxxxx para event_id demo-lf009-<session>-<n>.'
        }
        Write-Output "WARN cleanup solicitado para namespace demo-lf009-$Session-*"
        throw 'Cleanup PostgreSQL bloqueado de forma segura: event_id no se persiste y no existe una relacion demostrable session-to-execution_id. No se ejecuto DELETE. Use cleanup manual por execution_id explicitos hasta aprobar trazabilidad local de demo.'
    }
}
