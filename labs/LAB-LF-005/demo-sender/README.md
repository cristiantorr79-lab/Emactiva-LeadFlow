# Emactiva LeadFlow — Demo Sender

Herramienta exclusiva de demostración. No es una interfaz productiva de LeadFlow, no modifica el core, no guarda historial y no incluye autenticación, base de datos ni secretos.

## Iniciar

Requisitos: Node.js 20+ y un entorno LeadFlow development/demo disponible con mocks.

En PowerShell, desde la raíz del repositorio:

```powershell
$env:DEMO_WEBHOOK_URL = 'http://127.0.0.1:5680/webhook/leadflow'
$env:DEMO_WEBHOOK_KEY = '<clave-del-entorno-demo>'
$env:DEMO_CRM_URL = 'http://127.0.0.1:5683/crm/contacts'
$env:DEMO_ALLOWED_INTERESTS = 'producto_a'
node .\labs\LAB-LF-005\demo-sender\server.mjs
```

Abrir `http://127.0.0.1:8095`. La vista CRM de solo lectura está en `http://127.0.0.1:8095/crm`. `DEMO_PORT` y `DEMO_HOST` son opcionales; el host seguro por defecto es loopback. `DEMO_ALLOWED_INTERESTS` es una lista separada por comas exclusiva de la demo; si se omite, el Sender reutiliza `LEADFLOW_ALLOWED_INTERESTS`. Sin allowlist válida, el selector queda deshabilitado y cualquier `interest` recibido se rechaza cerrado; V1 y `message` siguen disponibles. Las URLs y la clave se leen desde el entorno. La clave nunca se envía al navegador ni debe guardarse en este directorio.

## Uso

1. Confirmar datos sintéticos, seleccionar un interés permitido y escribir un mensaje sintético. Enviar para crear EVENT + LEAD + INTERACTION.
2. Abrir CRM Demo View y comprobar un contacto con una interacción.
3. Pulsar **Nuevo**: cambia solo `event_id`. Mantener el email, cambiar la interacción y enviar; el contacto se reutiliza y aparece una segunda interacción.
4. Reenviar sin cambiar `source` ni `event_id`: el resultado es `duplicate` y el CRM permanece con un contacto y dos interacciones.
5. Para comprobar compatibilidad V1, dejar interés y mensaje vacíos; el Sender omite por completo `interaction`.

La interfaz solo muestra campos canónicos permitidos. Una respuesta HTTP 202 por interacción ambigua se presenta como confirmación recuperable en proceso, sin detalles internos. No se muestran headers, tokens, PII adicional, payloads, stack traces ni respuestas internas completas. Esta es una herramienta de demostración, no una UI productiva.

## Limpieza

El Sender no persiste datos y se limpia al detener el proceso con `Ctrl+C`. Los datos creados en LeadFlow pertenecen al runtime de demo; aplicar únicamente su procedimiento autorizado de cleanup/retención. No apuntar esta herramienta a producción ni a proveedores reales para una demo.
