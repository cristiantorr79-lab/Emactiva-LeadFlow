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

En production, `LEADFLOW_WEBHOOK_KEY` es obligatorio y no puede ser débil. El Core solo continúa cuando el header `X-LeadFlow-Key` coincide mediante comparación temporalmente segura; una clave ausente en configuración o solicitud falla cerrada con respuesta sanitizada. La autenticación de aplicación no sustituye HTTPS/TLS para exposición pública.

## CRM Adapter

- `lookupByEmail(normalized_email)` → `{found:false}` o `{found:true,contact:{id,email}}`; múltiples coincidencias son error de integridad.
- `createContact(lead, operation_key)` → `{contact_id, created:true}`. operation_key se deriva establemente de idempotency_key y la operación. Repetirla devuelve el mismo contacto. Email tiene unicidad atómica y lectura posterior consistente en el mock.
- `updateContact(contact_id, present_fields)` → `{contact_id}`. PATCH lógico: no borrar omitidos; email identifica el contacto y no se modifica en esta V1. Repetir los mismos campos no agrega efectos.
- `updateEnrichment(contact_id, enrichment_fields)` → `{contact_id}`; misma garantía de repetición segura.

Cada operación recibe URL upstream, API key y timeout desde entorno. La API key no se transmite hasta definir el esquema de autenticación del proveedor. Los errores se traducen al contrato sanitizado; un 404 de ruta o contacto de update es técnico, mientras lookup sin coincidencia devuelve `found:false`. Un conflicto de creación requiere lookup, no retry ciego.

Los mocks locales simulan disponibilidad, latencia, códigos HTTP, unicidad, creación completada con respuesta perdida y contadores de llamadas/contactos. Siguen siendo los únicos destinos externos actuales.

## Enrichment Adapter

`enrich({email,company?})` → `{enrichment_status:"success",data:{industry?,company_size?,website?}}`. Los campos son strings, company_size es categoría textual, website es URL pública; todos son opcionales. Solo esta lista se propaga a CRM y un resultado vacío válido es success. No sobreescribir nombres/email ni registrar la respuesta completa.

Error usa el mismo contrato sanitizado que CRM. El mock local permite resultados configurables de timeout, 429, 400, 401, 403, 5xx y éxito, además de latencia y Retry-After; no se invoca API real. Configuración mediante `ENRICHMENT_UPSTREAM_URL` y `ENRICHMENT_API_KEY`. La URL de alerta permanece dentro de su adaptador y nunca aparece en logs.

## Conformidad de adaptadores LF-002.2

Un adaptador es conforme cuando traduce su proveedor al contrato canónico de LeadFlow y supera `scripts/test/test_adapter_conformance.py`. El proveedor no necesita exponer el mismo HTTP ni JSON: esa traducción pertenece al adaptador y no al Core.

El CRM Adapter debe buscar por email normalizado de forma determinista; representar ausencia como `found:false`; devolver un identificador opaco y estable al encontrar, crear o actualizar; mantener `operation_key` estable en CREATE; aplicar updates parciales sin borrar campos omitidos; y limitar enrichment a `industry`, `company_size` y `website`. Los errores y respuestas no pueden incluir PII, credenciales, headers ni contenido crudo del proveedor.

Cada CRM Adapter declara este capability profile booleano:

```json
{
  "consistent_lookup_after_create": true,
  "unique_email": true,
  "idempotent_create_operation_key": true,
  "conflict_reconciliation": true
}
```

Después de un CREATE ambiguo siempre se intenta lookup antes de considerar otro CREATE. Repetir CREATE solo es seguro si existe idempotencia por `operation_key`, o si el proveedor combina unicidad de email con lookup consistente posterior a CREATE. Sin esas garantías, el adaptador termina conservadoramente con `type/code = ambiguous_create`, `ambiguous:true`; nunca repite CREATE a ciegas. HTTP 409 no es retry genérico: solo permite reconciliación mediante lookup cuando `conflict_reconciliation` está declarado.

El Enrichment Adapter recibe `{email, company?}` y devuelve success con un objeto `data` que contiene exclusivamente strings opcionales `industry`, `company_size` y `website`. Un resultado vacío es válido. Campos desconocidos o de tipo incorrecto se descartan. Timeout, red temporal, 429 y 5xx temporales siguen el presupuesto vigente; 400/401/403 son terminales. `Retry-After` válido se conserva y se compara con el delay local.

El error canónico entre adaptador y Core es:

```json
{
  "type": "rate_limit",
  "code": "http_429",
  "http_status": 429,
  "retry_after_seconds": 7,
  "ambiguous": false,
  "message": "upstream dependency failed"
}
```

`type` expresa la clase estable; `code` el código sanitizado; `http_status` puede ser null para timeout/red; `retry_after_seconds` solo aplica cuando existe; `ambiguous` distingue resultado desconocido de fallo confirmado; y `message` siempre es genérico. Ningún campo puede copiar payloads, secretos, PII, URLs firmadas o stack traces. La clasificación y los máximos 3 intentos con delays 5/15 s permanecen sin cambios respecto de LF-001.

## Providers seleccionados LF-002.5

`CRM_PROVIDER=hubspot` implementa lookup por email mediante Contacts Search y create/update mediante Contacts Object API versionada. Autentica exclusivamente con `Authorization: Bearer` construido dentro del Adapter. Su capability profile es conservador: `consistent_lookup_after_create=false`, `unique_email=false`, `idempotent_create_operation_key=false`, `conflict_reconciliation=true`. Tras timeout de CREATE se hace lookup; si no identifica inequívocamente el contacto, devuelve `ambiguous_create` sin segundo CREATE.

Solo se envían email y los campos LeadFlow presentes. Enrichment se traduce a propiedades HubSpot configurables. `company_size` usa por defecto la propiedad textual `leadflow_company_size`, cuya creación y acceso deberán confirmarse en la prueba externa; no se fuerza a un campo numérico incompatible.

`ENRICHMENT_PROVIDER=hunter` usa Combined Enrichment con el email y autentica mediante `X-API-KEY`. HTTP 404 se traduce a success sin datos; 401 y 451 son permanentes; 403 representa rate limit documentado; 429 conserva `Retry-After`, y cuando identifica cuota/uso agotado termina sin retry como `quota_exhausted`. Timeout y 5xx mantienen la política temporal vigente. Solo `industry`, `company_size` y `website` pueden salir del Adapter.

HubSpot y Hunter son terceros/destinos externos del flujo de datos. Las pruebas reales deberán usar datos sintéticos o controlados. La revisión formal de base jurídica, transferencias, retención, derechos y gestión de terceros queda para LAB-LF-003; este contrato no declara cumplimiento legal.
