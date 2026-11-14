$ErrorActionPreference = 'Stop'
$port = if ($env:N8N_PORT) { $env:N8N_PORT } else { '5680' }
for ($attempt = 1; $attempt -le 60; $attempt++) {
    if ($env:LEADFLOW_N8N_PROBE_MODE -eq 'container') {
        docker compose exec -T n8n wget -q --spider http://127.0.0.1:5678/healthz
        if ($LASTEXITCODE -eq 0) { Write-Output 'n8n ready'; exit 0 }
        Start-Sleep -Seconds 1
        continue
    }
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port/healthz" -TimeoutSec 2
        if ($response.StatusCode -eq 200) { Write-Output 'n8n ready'; exit 0 }
    } catch { }
    Start-Sleep -Seconds 1
}
throw 'n8n did not become ready within 60 seconds.'
