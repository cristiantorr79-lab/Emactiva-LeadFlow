# Emactiva LeadFlow — Demo Sender

Herramienta exclusiva de demostración. No es una interfaz productiva de LeadFlow, no modifica el core, no guarda historial y no incluye autenticación, base de datos ni secretos.

## Iniciar

Requisitos: Node.js 20+ y un entorno LeadFlow development/demo disponible con mocks.

En PowerShell, desde la raíz del repositorio:

```powershell
$env:DEMO_WEBHOOK_URL = 'http://127.0.0.1:5680/webhook/leadflow'
$env:DEMO_WEBHOOK_KEY = '<clave-del-entorno-demo>'
$env:DEMO_CRM_URL = 'http://127.0.0.1:5683/crm/contacts'
node .\labs\LAB-LF-005\demo-sender\server.mjs
```

Abrir `http://127.0.0.1:8095`. La vista CRM de solo lectura está en `http://127.0.0.1:8095/crm`. `DEMO_PORT` y `DEMO_HOST` son opcionales; el host seguro por defecto es loopback. Las URLs y la clave se leen desde el entorno; `DEMO_CRM_URL` tiene como default seguro el CRM mock local mostrado arriba. La clave nunca se envía al navegador ni debe guardarse en este directorio.

## Uso

1. Confirmar que los valores son sintéticos; los defaults usan `example.com`.
2. Pulsar **Enviar lead** y observar `success`, `execution_id` y `crm_action` si el runtime los devuelve.
3. Pulsar nuevamente sin cambiar `source` ni `event_id` para observar `duplicate` sin efectos externos repetidos.
4. Pulsar **Nuevo** antes de otro caso independiente.

La interfaz solo muestra campos canónicos permitidos. No presenta headers, tokens, stack traces ni la respuesta interna completa.

## Limpieza

El Sender no persiste datos y se limpia al detener el proceso con `Ctrl+C`. Los datos creados en LeadFlow pertenecen al runtime de demo; aplicar únicamente su procedimiento autorizado de cleanup/retención. No apuntar esta herramienta a producción ni a proveedores reales para una demo.
