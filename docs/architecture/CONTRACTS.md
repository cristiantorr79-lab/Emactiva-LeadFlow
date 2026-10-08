# Contratos conceptuales V1

## Entrada

JSON objeto, Content-Type application/json:

```json
{
  "event_id": "evt_demo_123",
  "source": "website",
  "lead": {
    "first_name": "Nombre Demo",
    "last_name": "Apellido Demo",
    "email": "lead.demo@example.test",
    "phone": "+15550100000",
    "company": "Empresa Sintetica"
  },
  "interaction": {
    "interest": "producto_a",
    "message": "Consulta sintetica de demostracion."
  }
}
```

Obligatorios: `event_id` técnico de 1–128 caracteres, patrón `[A-Za-z0-9][A-Za-z0-9._:-]{0,127}`, con al menos un dígito o separador técnico y sin forma de teléfono numérico; `source` de 1–64 caracteres, patrón `[A-Za-z][A-Za-z0-9_-]{0,63}`, que se normaliza a minúsculas y debe pertenecer a `LEADFLOW_ALLOWED_SOURCES`; `lead` objeto y `lead.email` string. Email, URL, teléfono, nombre o texto libre no son identificadores de evento válidos. Opcionales: first_name, last_name, phone y company (strings de hasta 200 caracteres). No se convierten números ni null a strings. Campos desconocidos se ignoran y no se propagan. Campos omitidos no borran valores del CRM; cadenas opcionales vacías se omiten.

Email: trim → lowercase → formato; máximo 254 caracteres, una sola @, partes no vacías, sin espacios, dominio con etiquetas no vacías separadas por punto. La validación inicial es pragmática, no comprueba entrega ni DNS; formato inválido se rechaza. El email normalizado es la identidad de búsqueda; no se intenta normalizar teléfonos en este LAB.

`interaction` es opcional y admite exclusivamente `interest` y `message`. `interest` es string de hasta 100 caracteres y debe pertenecer, tras trim, a `LEADFLOW_ALLOWED_INTERESTS`. `message` es string de hasta 2000 caracteres; recibe solo trim exterior y conserva contenido interno, saltos y Unicode. Strings vacíos tras trim se omiten, tipos incorrectos no se coercionan, campos desconocidos no se propagan y una interaction vacía equivale a omitida. Su contenido no forma parte de la identidad EVENT ni se incorpora al LEAD.

## Estados y etapas

Estados: `received`, `processing`, `duplicate`, `retrying`, `success`, `failed`.

Transiciones: received → processing / duplicate / failed; processing → retrying / success / failed; retrying → processing / failed. success, duplicate y failed son terminales para la entrega automática. Una interaction ambigua conserva la ejecución en `processing` para recovery y no se trata automáticamente como fallo terminal.

Recovery opera siempre sobre la ejecución original, conserva `idempotency_key` y reutiliza el checkpoint CRM. Reconcilia antes de repetir, no reejecuta ciegamente todo el flujo y no repite CREATE de contacto ni interaction a ciegas. Una interaction ambigua se reconcilia por `<idempotency_key>:crm_interaction`. Antes de continuar comprueba `RECOVERY_MAX_PROCESSING_AGE_SECONDS`, cuyo default y límite superior son 604800 segundos; una ejecución arrendada que excede ese máximo sin progreso termina en `failed` con `error_type=timeout` y `error_code=recovery_expired`.

## Retención y purga

`leadflow.purge_retained_data` aplica por lotes la política inicial configurable: success/duplicate 90 días desde `finished_at`, failed 180 días y processing/recovery máximo 7 días sin progreso. Una ejecución processing vencida se terminaliza primero como failed con código canónico; desde ese momento comienza su plazo terminal y no se borra en la misma operación. `execution_events` sigue el plazo de su padre y se elimina coordinadamente; el contexto recovery se elimina al terminalizar o al borrar su ejecución.

Un hold activo en `retention_holds` suspende únicamente la ejecución indicada. Exige motivo técnico, owner, aprobador, inicio y revisión futura acotada; no existe hold global ni indefinido. La función es idempotente, preserva propietarios requeridos por duplicados todavía retenidos y escribe en `retention_purge_runs` solo fecha y conteos técnicos. Esta evidencia mínima se conserva 180 días y no contiene email, payload, `lead_identifier` ni otros datos personales directos.

## Operaciones DSR administrativas

La interfaz DSR está separada del webhook público. `scripts/admin/dsr_admin.py` recibe por stdin una solicitud previamente verificada y usa identidades lógicas `DSR_OPERATOR` y `DSR_APPROVER`; DELETE y RESTRICT exigen aprobador distinto del operador. LOCATE devuelve solo presencia/conteos, EXPORT expone campos técnicos minimizados, ANNOTATE agrega un código trazable sin reescribir historial, DELETE elimina las superficies PostgreSQL controlables y RESTRICT bloquea procesamiento futuro.

El titular se correlaciona transitoriamente mediante `lead_identifier`; la evidencia persistente usa un `subject_token` HMAC no reversible. DELETE y RESTRICT crean un tombstone mínimo que no contiene email, nombre, teléfono, payload ni `lead_identifier`. El Core calcula el mismo token y `claim_event` rechaza sujetos borrados o restringidos. Solicitudes repetidas reutilizan `request_id`; resultados ambiguos o sujetos a hold no ejecutan operaciones destructivas.

Cada solicitud aplicable crea acciones idempotentes para HubSpot y Hunter en estado pending, sin presumir capacidades ni SLA. Slack queda `not_applicable/no_subject_data` mientras no reciba PII del titular. Los resultados externos se limitan a provider, action, status, referencia técnica, timestamps y código sanitizado; pendientes o fallos mantienen el resultado global partial.

La frontera de proceso recovery envía password y SQL por stdin a `psql`. Un fallo de proceso se representa como `recovery_database_error` con etapa `database`; una excepción recuperable que puede persistirse termina con `recovery_unexpected_error`. No se propaga stderr, SQL, email, connection string, token ni stack trace al resultado visible.

El reclamo persistente recibe `execution_id`, `source` canónico, `event_id` transitorio, `idempotency_key` y `lead_identifier`. Devuelve `claimed`, la misma `execution_id` y `original_execution_id` (NULL si obtuvo propiedad). Valida que la clave corresponda exactamente a SHA-256 UTF-8 de `source:event_id`, pero no persiste el `event_id` crudo. Los duplicados conservan clave NULL y apuntan al propietario; la escritura directa de tablas no forma parte del contrato de aplicación. Los rechazos solo conservan códigos canónicos y nunca el identificador rechazado.

Stages: `validation`, `idempotency`, `crm_lookup`, `crm_create`, `crm_update`, `crm_interaction`, `enrichment`, `crm_enrichment_update`, `alert`. Normalización pertenece a validation. Logging y respuesta son responsabilidades transversales, no stages adicionales. El resumen conserva la etapa principal al fallar; un evento independiente registra alert.

crm_action: null, `created` o `updated`; crm_contact_id es string opaco. `interaction_status`: `not_required`, `pending`, `ambiguous` o `confirmed`; `ambiguous` es recuperable y no terminal. enrichment_status: `not_started`, `processing`, `success`, `failed`. retry_count inicia en cero y cuenta reintentos acumulados. Cada evento de auditoría tiene attempt_number local (primer intento = 1).

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

Interaction ambigua recuperable, HTTP 202:
```json
{"ok":false,"execution_id":"lf_exec_xxx","status":"processing","recoverable":true,"error":{"type":"ambiguous_interaction"}}
```

Esta respuesta pública no incluye `message`, `interest`, email, payload, contexto de recovery, secretos, headers, tokens ni stack traces.

Otros fallos conservan la forma de error: HTTP 502 para dependencia definitiva y HTTP 503 para infraestructura local indisponible. No se copia ciegamente el HTTP del proveedor al cliente. Errores conceptuales: validation_error, authentication_error, authorization_error, technical_not_found, conflict_error, rate_limit, timeout, network_error, upstream_error, ambiguous_create, persistence_error e internal_error. Código y mensaje públicos, si se añaden, deben ser genéricos y sanitizados; sin stack traces ni secretos. El webhook síncrono futuro deberá dimensionar su timeout al presupuesto real de operaciones; no se presupone que 20 segundos cubran todo el flujo.

Respuesta diagnóstica LF-001.C para un evento nuevo, HTTP 200:
```json
{"ok":true,"execution_id":"lf_exec_xxx","status":"processing","duplicate":false}
```

Esta respuesta confirma recepción y propiedad del evento, no success comercial. El webhook local devuelve HTTP 401 ante autenticación ausente/incorrecta, HTTP 400 para validación, HTTP 422 cuando n8n rechaza JSON sintácticamente inválido antes de ejecutar el workflow y HTTP 503 cuando no puede persistir. Ninguna respuesta incluye PII, hashes, claves, detalles SQL ni stack traces.

En production, `LEADFLOW_WEBHOOK_KEY` es obligatorio y no puede ser débil. El Core solo continúa cuando el header `X-LeadFlow-Key` coincide mediante comparación temporalmente segura; una clave ausente en configuración o solicitud falla cerrada con respuesta sanitizada. La autenticación de aplicación no sustituye HTTPS/TLS para exposición pública.

## Identidad interna del Adapter

Toda operación funcional del Adapter exige el header `X-LeadFlow-Adapter-Key`. Core y recovery obtienen su valor de `ADAPTER_SERVICE_KEY`; el Adapter compara la identidad en tiempo constante y autoriza la operación contra `ADAPTER_ALLOWED_OPERATIONS`. Ambos parámetros son obligatorios, externos al código y no deben registrarse. Una identidad ausente o inválida devuelve `401`; una identidad válida sin permiso devuelve `403`; las respuestas son canónicas y no incluyen la credencial. `/healthz` queda fuera de este contrato para permitir el healthcheck local.

Las operaciones configurables son `crm.process`, `crm.update_enrichment`, `crm.record_interaction`, `crm.reconcile_interaction`, `enrichment.enrich`, `alert.send` y `crm.capabilities`. Esta identidad de aplicación es portable y no depende de IP, dominio o proveedor. La red, TLS interno, IAM y rotación efectiva del secreto se verifican en el entorno desplegado.

## CRM Adapter

- `lookupByEmail(normalized_email)` → `{found:false}` o `{found:true,contact:{id,email}}`; múltiples coincidencias son error de integridad.
- `createContact(lead, operation_key)` → `{contact_id, created:true}`. operation_key se deriva establemente de idempotency_key y la operación. Repetirla devuelve el mismo contacto. Email tiene unicidad atómica y lectura posterior consistente en el mock.
- `updateContact(contact_id, present_fields)` → `{contact_id}`. PATCH lógico: no borrar omitidos; email identifica el contacto y no se modifica en esta V1. Repetir los mismos campos no agrega efectos.
- `updateEnrichment(contact_id, enrichment_fields)` → `{contact_id}`; misma garantía de repetición segura.
- `recordInteraction(contact_id, interaction, operation_key)` registra la consulta solo después de confirmar el contacto CRM. La clave estable es `<idempotency_key>:crm_interaction`, no contiene PII y se usa también para reconciliación.

Cada operación recibe URL upstream, credencial y timeout desde entorno. HubSpot usa Bearer y Hunter `X-API-KEY`, construidos dentro del Adapter. Los errores se traducen al contrato sanitizado; un 404 de ruta o contacto de update es técnico, mientras lookup sin coincidencia devuelve `found:false`. Un conflicto de creación requiere lookup, no retry ciego. Las capabilities de interaction —write, idempotency y reconciliation— son independientes; si falta alguna requerida, el Adapter falla cerrado antes del efecto.

Los mocks locales simulan disponibilidad, latencia, códigos HTTP, unicidad, resultados ambiguos y contadores de llamadas/contactos/interactions. Son destinos de development; HubSpot y Hunter ya están seleccionados y configurados como providers reales detrás del Adapter.

## Enrichment Adapter

`enrich({email,company?})` → `{enrichment_status:"success",data:{industry?,company_size?,website?}}`. Los campos son strings, company_size es categoría textual, website es URL pública; todos son opcionales. Solo esta lista se propaga a CRM y un resultado vacío válido es success. No sobreescribir nombres/email ni registrar la respuesta completa.

Error usa el mismo contrato sanitizado que CRM. El mock local permite resultados configurables de timeout, 429, 400, 401, 403, 5xx y éxito, además de latencia y Retry-After. En development se usa el mock; `ENRICHMENT_PROVIDER=hunter` selecciona el provider real. Configuración mediante `ENRICHMENT_UPSTREAM_URL` y `ENRICHMENT_API_KEY`. La URL de alerta permanece dentro de su adaptador y nunca aparece en logs.

## Conformidad de adaptadores LF-002.2

Un adaptador es conforme cuando traduce su proveedor al contrato canónico de LeadFlow y supera `scripts/test/test_adapter_conformance.py`. El proveedor no necesita exponer el mismo HTTP ni JSON: esa traducción pertenece al adaptador y no al Core.

El CRM Adapter debe buscar por email normalizado de forma determinista; representar ausencia como `found:false`; devolver un identificador opaco y estable al encontrar, crear o actualizar; mantener `operation_key` estable en CREATE; aplicar updates parciales sin borrar campos omitidos; y limitar enrichment a `industry`, `company_size` y `website`. Los errores y respuestas no pueden incluir PII, credenciales, headers ni contenido crudo del proveedor.

Cada CRM Adapter declara este capability profile booleano:

```json
{
  "consistent_lookup_after_create": true,
  "unique_email": true,
  "idempotent_create_operation_key": true,
  "conflict_reconciliation": true,
  "interaction_write": true,
  "interaction_idempotency": true,
  "interaction_reconciliation": true
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

Los códigos técnicos cumplen `^[a-z][a-z0-9_-]{0,99}$`; cualquier código externo desconocido o anómalo se sustituye por el código canónico derivado del estado HTTP. Los IDs de proveedor son strings opacos de 1–200 caracteres y cumplen `^[A-Za-z0-9][A-Za-z0-9._:-]{0,199}$`; LeadFlow no interpreta su estructura. Un ID fuera del contrato produce una respuesta controlada y nunca se propaga.

`industry` admite texto no vacío de hasta 200 caracteres y `company_size` hasta 100; caracteres de control, tipos incorrectos y valores mayores se descartan. `website` admite como máximo 2048 caracteres, exige HTTP/HTTPS, host válido y ausencia de userinfo; se normalizan esquema y host, y se eliminan query y fragment. Esquemas peligrosos, credenciales embebidas y URLs inválidas se descartan sin realizar fetch. La salida contiene exclusivamente `industry`, `company_size` y `website`; payloads y campos adicionales del proveedor no atraviesan el Adapter.

## Providers seleccionados LF-002.5

`CRM_PROVIDER=hubspot` implementa lookup por email mediante Contacts Search y create/update mediante Contacts Object API versionada. Autentica exclusivamente con `Authorization: Bearer` construido dentro del Adapter. Su capability profile es conservador: `consistent_lookup_after_create=false`, `unique_email=false`, `idempotent_create_operation_key=false`, `conflict_reconciliation=true`. Tras timeout de CREATE se hace lookup; si no identifica inequívocamente el contacto, devuelve `ambiguous_create` sin segundo CREATE.

Solo se envían email y los campos LeadFlow presentes. Enrichment se traduce a propiedades HubSpot configurables. `company_size` usa por defecto la propiedad textual `leadflow_company_size`, cuya creación y acceso deberán confirmarse en la prueba externa; no se fuerza a un campo numérico incompatible.

`ENRICHMENT_PROVIDER=hunter` usa Combined Enrichment con el email y autentica mediante `X-API-KEY`. HTTP 404 se traduce a success sin datos; 401 y 451 son permanentes; 403 representa rate limit documentado; 429 conserva `Retry-After`, y cuando identifica cuota/uso agotado termina sin retry como `quota_exhausted`. Timeout y 5xx mantienen la política temporal vigente. Solo `industry`, `company_size` y `website` pueden salir del Adapter.

HubSpot y Hunter son terceros/destinos externos del flujo de datos. Las pruebas reales deberán usar datos sintéticos o controlados. La revisión formal de base jurídica, transferencias, retención, derechos y gestión de terceros queda para LAB-LF-003; este contrato no declara cumplimiento legal.

LF-011 validó INTERACTION real en HubSpot mediante Tickets, exclusivamente dentro del Adapter. La propiedad única `leadflow_interaction_key` representa la operation key de LeadFlow, permite idempotencia y reconciliación concluyente por key, y el Ticket se asocia al Contact confirmado. El Core conserva el contrato neutral y no incorpora semántica de HubSpot.

LAB-LF-012 expone en el Adapter las operaciones neutrales `crm.dsr_locate`, `crm.dsr_export` y `crm.dsr_correct`. LOCATE y EXPORT hacen lookup exacto por email verificado, consideran únicamente Tickets con `leadflow_interaction_key` y no persisten el payload exportado. CORRECT limita Contact a `first_name`, `last_name`, `phone` y `company`, prohíbe email y reconcilia por lectura posterior. `verified_email` es transitorio y nunca forma parte de evidencia, logs o errores. ANNOTATE permanece local y su acción HubSpot se registra `not_applicable`.

LF012-T02 añade `crm.dsr_delete` en `POST /crm/dsr-delete`. La ruta no acepta `ADAPTER_SERVICE_KEY`: exige exclusivamente `DSR_ADAPTER_SERVICE_KEY` mediante `X-LeadFlow-DSR-Adapter-Key`, además de una solicitud DELETE aprobada y una acción `hubspot/delete/pending` demostrables en PostgreSQL por el coordinador administrativo. Operador y aprobador deben ser distintos, y las claves normal y destructiva no pueden coincidir. El Adapter inventaría primero la superficie completa de Tickets asociados y falla cerrado ante paginación; archiva solo Tickets con `leadflow_interaction_key`, reconcilia cada ID, ejecuta GDPR delete del Contact por `contactId` y confirma ausencia por lookup exacto antes de declarar éxito. La API pública de Tickets solo demuestra archive/papelera, por lo que esa superficie conserva WARN. El DELETE real terminó PASS; RESTRICT local sigue vigente, pero no existe `crm.dsr_restrict` y HubSpot se registra `failed/capability_not_available` como NOT_VERIFIED, sin propiedad o flag ficticio.

La migración `023_dsr_delete_reconciliation.sql` permite una única transición adicional: `hubspot/delete/failed` con código allowlisted `contact_deletion_ambiguous` puede ejecutar `crm.dsr_locate` con la identidad normal y, solo ante ausencia concluyente, cerrar como `completed/reconciled_absent`. Esa rama nunca vuelve a invocar `/crm/dsr-delete`; cualquier otro fallo, presencia, ambigüedad de lectura o aprobación inválida permanece fail-closed.

# Interaction (LF-008)

`interaction` es opcional y admite sólo `interest` (máximo 100, allowlist `LEADFLOW_ALLOWED_INTERESTS`) y `message` (máximo 2000). Ambos deben ser strings; vacío tras trim equivale a omitido. `message` sólo recibe trim exterior y conserva contenido interno, saltos de línea y Unicode. Campos desconocidos no se propagan.

El adapter neutral ofrece `recordInteraction(contact_id, interaction, operation_key)` y reconciliación por la misma clave. El contacto CRM debe estar confirmado previamente. La respuesta contiene únicamente éxito, identificador opaco, resolución `created`/`reused`, reintentos y error sanitizado. Un lookup negativo sólo habilita repetición cuando declara ausencia concluyente.

LeadFlow no registra ni devuelve el mensaje. El contexto local cifrado existe únicamente durante processing/recovery. La interacción ya confirmada vive en el CRM externo: retención, exportación, corrección y eliminación en ese sistema dependen del provider adapter y de la configuración contractual del cliente; borrar el contexto local no borra el objeto externo.
