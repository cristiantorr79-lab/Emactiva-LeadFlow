# Contratos conceptuales V1

## Entrada

JSON objeto, Content-Type application/json:

```json
{"event_id":"evt_123456","source":"website","lead":{"first_name":"Cristian","last_name":"Torres","email":"cristian@example.com","phone":"+56912345678","company":"Empresa Demo"}}
```

Obligatorios: event_id (string 1–200 caracteres, sin espacios extremos), source (string 1–100, patrón `[A-Za-z0-9_-]+`), lead (objeto) y lead.email (string). Opcionales: first_name, last_name, phone y company (strings de hasta 200 caracteres). No se convierten números ni null a strings. Campos desconocidos se ignoran y no se propagan. Campos omitidos no borran valores del CRM; cadenas opcionales vacías se omiten.

Email: trim → lowercase → formato; máximo 254 caracteres, una sola @, partes no vacías, sin espacios, dominio con etiquetas no vacías separadas por punto. La validación inicial es pragmática, no comprueba entrega ni DNS; formato inválido se rechaza. El email normalizado es la identidad de búsqueda; no se intenta normalizar teléfonos en este LAB.

## Estados y etapas

Estados: `received`, `processing`, `duplicate`, `retrying`, `success`, `failed`.

Transiciones: received → processing / duplicate / failed; processing → retrying / success / failed; retrying → processing / failed. success, duplicate y failed son terminales para la entrega automática. Una recuperación administrativa futura requiere diseño explícito.

El reclamo persistente recibe execution_id, source, event_id, idempotency_key y lead_identifier. Devuelve claimed, la misma execution_id y original_execution_id (NULL si obtuvo propiedad). Valida que la clave corresponda exactamente a SHA-256 UTF-8 de `source:event_id`. Los duplicados conservan clave NULL y apuntan al propietario; la escritura directa de tablas no forma parte del contrato de aplicación.

Stages: `validation`, `idempotency`, `crm_lookup`, `crm_create`, `crm_update`, `enrichment`, `crm_enrichment_update`, `alert`. Normalización pertenece a validation. Logging y respuesta son responsabilidades transversales, no stages adicionales. El resumen conserva la etapa principal al fallar; un evento independiente registra alert.

crm_action: null, `created` o `updated`; crm_contact_id es string opaco. enrichment_status: `not_started`, `processing`, `success`, `failed`. retry_count inicia en cero y cuenta reintentos acumulados. Cada evento de auditoría tiene attempt_number local (primer intento = 1).

## Respuestas

Éxito, HTTP 200:
```json
{"ok":true,"execution_id":"lf_exec_xxx","status":"success","crm_action":"created","duplicate":false}
```

Duplicado, HTTP 200 (confirma recepción, no éxito del procesamiento original):
```json
{"ok":true,"execution_id":"lf_exec_yyy","status":"duplicate","duplicate":true,"original_execution_id":"lf_exec_xxx"}
```

Validación, HTTP 400:
```json
{"ok":false,"execution_id":"lf_exec_xxx","status":"failed","error":{"type":"validation_error"}}
```

Otros fallos conservan la forma de error: HTTP 502 para dependencia definitiva y HTTP 503 para infraestructura local indisponible. No se copia ciegamente el HTTP del proveedor al cliente. Errores conceptuales: validation_error, authentication_error, authorization_error, technical_not_found, conflict_error, rate_limit, timeout, network_error, upstream_error, ambiguous_create, persistence_error e internal_error. Código y mensaje públicos, si se añaden, deben ser genéricos y sanitizados; sin stack traces ni secretos. El webhook síncrono futuro deberá dimensionar su timeout al presupuesto real de operaciones; no se presupone que 20 segundos cubran todo el flujo.

Respuesta diagnóstica LF-001.C para un evento nuevo, HTTP 200:
```json
{"ok":true,"execution_id":"lf_exec_xxx","status":"processing","duplicate":false}
```

Esta respuesta confirma recepción y propiedad del evento, no success comercial. El webhook local devuelve HTTP 401 ante autenticación ausente/incorrecta, HTTP 400 para validación, HTTP 422 cuando n8n rechaza JSON sintácticamente inválido antes de ejecutar el workflow y HTTP 503 cuando no puede persistir. Ninguna respuesta incluye PII, hashes, claves, detalles SQL ni stack traces.

## CRM Adapter (sin implementar)

- `lookupByEmail(normalized_email)` → `{found:false}` o `{found:true,contact:{id,email}}`; múltiples coincidencias son error de integridad.
- `createContact(lead, operation_key)` → `{contact_id, created:true}`. operation_key se deriva establemente de idempotency_key y la operación. Repetirla devuelve el mismo contacto. Email tiene unicidad atómica y lectura posterior consistente en el mock.
- `updateContact(contact_id, present_fields)` → `{contact_id}`. PATCH lógico: no borrar omitidos; email identifica el contacto y no se modifica en esta V1. Repetir los mismos campos no agrega efectos.
- `updateEnrichment(contact_id, enrichment_fields)` → `{contact_id}`; misma garantía de repetición segura.

Cada operación recibe configuración base URL/API key desde entorno y un timeout explícito que se definirá con el runtime. Errores se traducen a `{type,code,http_status,retry_after_seconds,ambiguous,message}` sanitizado; el núcleo determina retry. Un 404 de ruta o contacto de update es técnico; lookup sin coincidencia devuelve found:false. Un conflicto de creación requiere lookup, no retry ciego.

El mock futuro deberá simular disponibilidad, latencia, códigos HTTP, unicidad, creación completada con respuesta perdida y contadores de llamadas/contactos para LF-T13. No existe todavía servicio ejecutable.

## Enrichment Adapter (sin implementar)

`enrich({email,company?})` → `{enrichment_status:"success",data:{industry?,company_size?,website?}}`. Los campos son strings, company_size es categoría textual, website es URL pública; todos son opcionales. Solo esta lista se propaga a CRM y un resultado vacío válido es success. No sobreescribir nombres/email ni registrar la respuesta completa.

Error usa el mismo contrato sanitizado que CRM. El mock futuro permitirá secuencias configurables de resultados (timeout, 429, 400, 401, 500 y éxito), latencia y Retry-After; no se invoca API real. Configuración mediante ENRICHMENT_BASE_URL y ENRICHMENT_API_KEY. Slack usa SLACK_WEBHOOK_URL solo dentro de su adaptador, nunca en logs.
