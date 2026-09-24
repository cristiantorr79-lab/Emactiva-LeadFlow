$ErrorActionPreference = 'Stop'
$port = if ($env:N8N_PORT) { $env:N8N_PORT } else { '5680' }
for ($attempt = 1; $attempt -le 60; $attempt++) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port/healthz" -TimeoutSec 2
        if ($response.StatusCode -eq 200) { Write-Output 'n8n ready'; exit 0 }
    } catch { }
    Start-Sleep -Seconds 1
}
throw 'n8n did not become ready within 60 seconds.'
