# LAB-LF-001 — Implementación de infraestructura base y núcleo inicial

Estado: **EN CURSO**

Fecha de apertura: **2026-09-23**

Objetivo general: pasar desde la arquitectura documental cerrada en LAB-LF-000 a una infraestructura ejecutable y comenzar la implementación real del núcleo LeadFlow.

## Baseline heredado

- LAB-LF-000: CERRADO — PASS.
- Commit heredado: `f95c2adc7546aa9324b1af38ea74220eba47415e`.
- Rama `main`; arquitectura y contratos base definidos.
- Migración no ejecutada y sin workflow n8n productivo al comenzar el LAB.

## LF-001.A — Auditoría de arranque

Resultado: **PASS CON HALLAZGOS**.

- H1 HIGH: borrar una recepción provisional con eventos podía ser impedido por la FK inmediata.
- H2 MEDIUM: `duplicate_of` no garantizaba por sí sola un propietario con clave no NULL.
- H3 LOW: `validate_lab.py` pertenece al baseline LAB-LF-000, no al gate general de LF-001.
- H4 INFO: los checks SQL estáticos no reemplazan pruebas reales PostgreSQL.

## LF-001.B — Persistencia base e idempotencia

Resultado: **PASS** (2026-09-23).

H1 se resuelve mediante `leadflow.claim_event`: crea una recepción, registra su evento y reclama con UPDATE sobre la misma fila. La excepción UNIQUE se maneja en la misma transacción y la recepción pasa a duplicate sin borrar historial.

H2 se garantiza en la operación oficial: el propietario se selecciona por la misma clave no NULL. El rol de aplicación recibe EXECUTE sobre funciones oficiales y lectura, sin INSERT/UPDATE/DELETE directo. La función rechaza una clave cuyos datos source/event_id no coincidan, y las pruebas cubren el caso negativo.

Infraestructura: Docker Compose con PostgreSQL 17.6-bookworm, publicado solo en `127.0.0.1`; volumen persistente, healthcheck y roles separados de migración/aplicación. El rol de aplicación tiene SELECT y EXECUTE de funciones oficiales, sin DML directo. Docker 29.6.1, Compose 5.1.4 y Python 3.14.3. n8n continúa pendiente, sin versión fijada.

La migración se aplicó desde una base limpia y quedó registrada como `001_initial`. La reaplicación falla de forma controlada y deja un único registro. DB-001–DB-018 y HASH-001: PASS (19/19). La prueba concurrente usó dos conexiones separadas y produjo `owners=1`, `duplicates=1`; propietario, referencias e historiales quedaron íntegros. El test crea una base temporal y la elimina al terminar.

Validadores: LF-001 PASS; histórico LF-000 18/18 PASS; sintaxis Python PASS; Compose PASS; `git diff --check` y `git diff --cached --check` PASS; escaneo de secretos PASS. El primer intento funcional detectó que `digest` no resolvía con el search_path endurecido; se calificó como `public.digest` y se repitió desde volumen limpio con resultado PASS.

Archivos creados: `compose.yaml`, scripts de readiness/migración, prueba PostgreSQL, validador LF-001 y este handoff. Modificados: README, arquitectura, contratos, setup y migración. `.env` local ignorado contiene credenciales aleatorias y no se versiona. No existe workflow n8n, CRM mock, enrichment mock ni integración Slack.

H1: **RESUELTO Y PROBADO** sin DELETE. H2: **RESUELTO Y PROBADO** mediante operación oficial, selección por clave, permisos mínimos y prueba negativa del DML directo. No quedan hallazgos HIGH o CRITICAL abiertos en el alcance de LF-001.B.

Estado Git previsto al cierre: rama `main`, un único commit `feat(lab-lf-001): implementar persistencia base e idempotencia`, working tree limpio, sin push. El hash se registra en el reporte de cierre de la etapa.

## LF-001.C — Integración inicial del núcleo n8n

Resultado: **PASS** (2026-09-23). LAB-LF-001 continúa **EN CURSO**.

n8n queda fijado en **2.28.6** mediante Docker Compose, persistente y expuesto solo en `127.0.0.1:5680`. El puerto 5678 pertenece a VetAtiende y no fue modificado. El workflow versionado `workflows/leadflow_core_initial.json` se importa y publica de forma reproducible; endpoint `POST /webhook/leadflow`.

El webhook exige `X-LeadFlow-Key` desde entorno, valida y normaliza el contrato, genera execution_id y hashes, y usa exclusivamente `claim_event` y `record_validation_failure`. NEW queda en processing y DUPLICATE conserva referencia al propietario. No existe success comercial, CRM, enrichment ni Slack.

Pruebas HTTP reales N8N-001–N8N-026: **26/26 PASS**. La prueba concurrente produjo exactamente **1 owner + 1 duplicate** con historiales íntegros. Se detuvo solo el PostgreSQL de LeadFlow y el webhook respondió HTTP 503 sanitizado; posteriormente se restauró el servicio. Se verificaron auth, validación, normalización, hashes, privacidad y ausencia de payload completo en tablas LeadFlow.

Regresión final: núcleo n8n **26/26 PASS**, persistencia LF-001.B **19/19 PASS**, validador LF-001 PASS, sintaxis Python PASS, Docker Compose PASS y revisiones Git/secretos PASS. El validador LF-000 queda como baseline histórico congelado y no aplica como gate después de añadir las variables n8n requeridas a `.env.example`.

Regresión de aprovisionamiento: `/healthz` podía responder antes de que el workflow publicado estuviera activo, iniciando pruebas durante esa ventana. `provision_n8n.ps1` ahora espera además una respuesta HTTP 401 del webhook sin credencial, que confirma registro y activación antes de continuar. La verificación dirigida posterior devolvió NEW processing con execution_id y DUPLICATE con original_execution_id correcto.

Archivos creados: `database/migrations/002_n8n_core.sql`, `workflows/leadflow_core_initial.json`, scripts de aprovisionamiento/readiness n8n y `scripts/test/test_n8n_core.py`. Modificados: `.env.example`, `.gitignore`, `compose.yaml`, runner de migraciones, README, arquitectura, contratos, setup, validador LF-001 y este handoff.

n8n minimiza persistencia con `EXECUTIONS_DATA_SAVE_ON_SUCCESS=none` y `EXECUTIONS_DATA_SAVE_ON_ERROR=none`. Credenciales y claves viven en `.env`/`.local`, ambos ignorados. No quedan hallazgos HIGH o CRITICAL dentro del alcance de LF-001.C.

Siguiente etapa prevista: **LAB-LF-001.D — Implementación de mocks CRM y enrichment contra los contratos existentes**.

## LF-001.D1 — Mocks CRM y enrichment, contratos básicos

Resultado: **PASS** (2026-09-24). LAB-LF-001 continúa **EN CURSO**.

Se implementaron dos servicios HTTP locales con Python **3.14.3-slim-bookworm**, sin dependencias externas. CRM mock se publica en `127.0.0.1:5683` y enrichment mock en `127.0.0.1:5682`; n8n LeadFlow permanece en 5680 y VetAtiende en 5678 sin cambios. Los servicios se ejecutan en memoria y reciben configuración únicamente por entorno.

CRM implementa lookup por email, creación idempotente por `operation_key`, unicidad atómica de email, update parcial y actualización de enrichment sin borrar campos omitidos. Enrichment acepta email con company opcional y devuelve success con únicamente industry, company_size y website.

Pruebas HTTP directas: **12/12 PASS**. Se cubrieron lookup inexistente/existente, CREATE, repetición idempotente, unicidad de email, updates parciales, updateEnrichment y las variantes válidas de enrichment. Los mocks todavía no están integrados al workflow n8n; no se añadieron retries, Slack ni simulaciones avanzadas de fallos.

Archivos creados: `mocks/Dockerfile`, `mocks/server.py` y `scripts/test/test_mocks.py`. Modificados: `compose.yaml`, `docs/setup/SETUP.md` y este handoff.

Siguiente etapa prevista: **LAB-LF-001.D2 — Integración controlada de los mocks con el workflow n8n**.

## LF-001.D2 — Integración controlada de mocks con n8n

Resultado: **PASS** (2026-09-24). LAB-LF-001 continúa **EN CURSO**.

El owner del evento consulta CRM por email normalizado, crea o actualiza el contacto, solicita enrichment, aplica únicamente sus campos permitidos y cierra la ejecución como `success` mediante la función oficial `complete_execution_success`. El CREATE usa una `operation_key` estable derivada de la clave de idempotencia. El camino duplicate conserva la respuesta previa y no llama CRM ni enrichment.

Pruebas de integración D2: **10/10 PASS**. Se verificaron lead nuevo con contacto creado y enriquecido, contacto existente actualizado sin borrar campos omitidos, dos eventos distintos con el mismo email y un único contacto, repetición del mismo evento sin llamadas externas, persistencia terminal success y respuesta pública sin PII ni secretos. Regresiones: núcleo n8n **26/26 PASS** y mocks **12/12 PASS**.

Se añadió `003_n8n_happy_path.sql`, la prueba `test_n8n_mocks_integration.py`, configuración interna por entorno para URLs de mocks y contadores diagnósticos mínimos en los mocks. No se implementaron retries, Slack, recuperación de processing ni simulaciones de errores.

Siguiente etapa prevista: **LAB-LF-001.D3 — Simulación y manejo controlado de errores de dependencias**.

## LF-001.D3a — Simulación de errores en mocks

Resultado: **PASS** (2026-09-24). LAB-LF-001 continúa **EN CURSO**.

CRM y enrichment admiten simulación local determinista mediante `POST /control/failure` y limpieza mediante `DELETE /control/failure`. Los modos disponibles son timeout, HTTP 400, HTTP 401, HTTP 429 con `Retry-After` y HTTP 500; la configuración puede limitarse a una operación concreta. El mock no ejecuta retries y recupera inmediatamente el comportamiento normal al limpiar la simulación.

Pruebas directas: **18/18 PASS**. Se conservaron las 12 comprobaciones del happy path y pasaron timeout, 400, 401, 429 con cabecera, 500 y recuperación posterior. No se modificó el workflow n8n ni se implementaron retries, Slack o manejo de errores en el orquestador.

Archivos modificados en D3a: `mocks/server.py`, `scripts/test/test_mocks.py` y este handoff.

Siguiente etapa prevista: **LAB-LF-001.D3b — Manejo de errores y retries en n8n**.

## LF-001.D3b-1 — Errores y retries de enrichment en n8n

Resultado: **PASS** (2026-09-24). LAB-LF-001 continúa **EN CURSO**.

La llamada de enrichment clasifica HTTP 400 y 401 como fallos definitivos sin retry. Timeout, HTTP 429 y HTTP 500 se reintentan con un máximo de tres intentos totales; las esperas son 5 segundos y 15 segundos, y HTTP 429 usa el mayor valor entre el delay configurado y `Retry-After`. Solo se repite enrichment: el contacto CRM creado o actualizado se conserva y no se duplica.

La función oficial `record_enrichment_outcome` persiste las transiciones `processing → retrying → processing`, el contador acumulado y el resultado terminal sin conceder DML directo a n8n. Un fallo definitivo deja la ejecución global en `failed`, conserva la referencia CRM y devuelve HTTP 502 con error sanitizado. `retry_count` queda en 0 sin retry, 1 tras una recuperación en el segundo intento y 2 al agotar tres intentos.

Pruebas D3b-1: **9/9 PASS**. Se verificaron 400/401 sin retry, timeout/429/500 con retry, `Retry-After`, fallo temporal seguido de success, agotamiento en tres intentos, transiciones, contador, no duplicación CRM y respuesta pública sanitizada. Regresiones: happy path D2 **10/10 PASS** y mocks **18/18 PASS**.

Archivos D3b-1: `database/migrations/004_enrichment_retries.sql`, `scripts/test/test_n8n_enrichment_retries.py`, `workflows/leadflow_core_initial.json`, `mocks/server.py` y este handoff.

Siguiente etapa prevista: manejo de errores y retries de CRM. No iniciado.

## LF-001.D3b-2 — Errores y retries de CRM

Resultado: **PASS** (2026-09-24). LAB-LF-001 continúa **EN CURSO**.

CRM clasifica HTTP 400, 401, 403 y 404 técnico como fallos definitivos sin retry. Timeout, error temporal de red y HTTP 408, 429, 500, 502, 503 y 504 se reintentan por operación con un máximo de tres intentos totales, delays de 5 y 15 segundos y respeto del mayor valor entre el delay y `Retry-After` para 429.

CREATE trata HTTP 409 mediante lookup de reconciliación, sin retry ciego. Ante respuesta perdida o resultado ambiguo también ejecuta lookup antes de repetir CREATE; si el contacto existe, continúa con ese contacto. La clave de operación estable, la unicidad de email y la reconciliación evitaron contactos duplicados. `retry_count` queda en 0 sin retry, 1 tras recuperación en el segundo intento y 2 al agotar tres intentos.

Suite CRM: **11/11 PASS**. Se verificaron lookup 400/401 sin retry, lookup 500 temporal, CREATE 500, reconciliación 409, CREATE ambiguo, update 500, agotamiento, contador, bloqueo de enrichment ante fallo CRM terminal, respuesta sanitizada y ausencia de duplicados. Regresiones: enrichment D3b-1 **9/9 PASS**, happy path D2 **10/10 PASS** y mocks **18/18 PASS**.

Durante la validación dirigida se detectó que `Persist CRM Failure` persistía el fallo pero emitía cero items, por lo que la rama terminaba antes de `Respond CRM Failure` y el webhook devolvía un cuerpo vacío. Se corrigió con `alwaysOutputData: true`; la respuesta se construye desde `CRM Flow` y la normalización. Las pruebas dirigidas posteriores de CRM simple y retry 500 temporal terminaron con respuesta no vacía, `execution_id` y estado coherente.

Validaciones finales: sintaxis Python/JSON PASS, `git diff --check` PASS, `git diff --cached --check` PASS y revisión de secretos PASS. No se implementaron Slack ni recuperación de ejecuciones en processing.

Archivos D3b-2: `database/migrations/005_crm_retries.sql`, `scripts/test/test_n8n_crm_retries.py`, `workflows/leadflow_core_initial.json`, `mocks/server.py` y este handoff.

## Cierre LAB-LF-001.D — CRM, enrichment y manejo de errores

Resultado: **PASS** (2026-09-24). LAB-LF-001 continúa **EN CURSO**.

- D1 — mocks CRM y enrichment: PASS.
- D2 — integración happy path con n8n: PASS.
- D3a — simulación determinista de errores: PASS.
- D3b-1 — clasificación y retries de enrichment: PASS.
- D3b-2 — clasificación, retries y reconciliación CRM: PASS.

Regresión final: CRM **11/11 PASS**, enrichment **9/9 PASS**, integración happy path **10/10 PASS** y mocks **18/18 PASS**. Los retries se limitan a la operación fallida, con tres intentos totales, delays de 5 y 15 segundos y respeto de `Retry-After` para 429. HTTP deterministas no reintentables fallan de inmediato.

CREATE ambiguo y HTTP 409 se reconcilian mediante lookup antes de cualquier repetición. La idempotencia de CREATE, la unicidad de email y las pruebas confirmaron ausencia de contactos duplicados. No quedan hallazgos abiertos dentro del alcance de la etapa D.

Validaciones de cierre: sintaxis Python/JSON PASS, Docker Compose PASS, validador LF-001 PASS, `git diff --check` PASS, `git diff --cached --check` PASS y revisión de secretos PASS.

Siguiente etapa prevista: integración de alerta Slack. No iniciada.

## LF-001.E1 — Alerta de fallo definitivo con receptor local

Resultado: **PASS** (2026-09-24). LAB-LF-001 continúa **EN CURSO**.

Se añadió un receptor Slack local en el servicio de mocks, publicado solo en `127.0.0.1:5684`. Recibe `POST /webhook`, conserva únicamente `execution_id`, `stage` y `error_code`, expone contador y última alerta mediante `GET /stats`, y permite limpiar el estado con `DELETE /alerts`. n8n obtiene la URL desde `SLACK_WEBHOOK_URL`, cuyo valor local predeterminado apunta a `http://slack-mock:8080/webhook`.

Las rutas de fallo definitivo de CRM y enrichment persisten primero el fallo principal y después intentan una alerta. La función oficial `record_alert_result` registra el resultado como evento de etapa `alert` sin cambiar el estado terminal ni reemplazar el error principal. Una caída del receptor produce `slack_delivery_failed`, mantiene la ejecución en `failed` y no genera alertas recursivas.

Pruebas E1: **7/7 PASS**. Se verificaron alerta única por fallo CRM, alerta única por fallo enrichment, payload sin PII ni secretos, ausencia de alertas en success y duplicate, preservación del error principal cuando falla Slack y ausencia de recursión. Regresiones mínimas: CRM **11/11 PASS**, enrichment **9/9 PASS** y mocks **18/18 PASS**.

Archivos E1: `database/migrations/006_alert_events.sql`, `scripts/test/test_n8n_alerts.py`, `mocks/server.py`, `compose.yaml`, `workflows/leadflow_core_initial.json` y este handoff. No se conectó Slack real ni se implementó recuperación de ejecuciones en processing.

Siguiente etapa prevista: **LAB-LF-001.E2**. No iniciada.

## Cierre LAB-LF-001.E — Alertas de fallo definitivo

Resultado: **PASS** (2026-09-25). LAB-LF-001 continúa **EN CURSO**.

E1 finalizó con **7/7 PASS**. El receptor Slack local se utilizó únicamente para pruebas; `SLACK_WEBHOOK_URL` permite sustituirlo por un webhook Slack real mediante configuración, sin modificar el workflow. No se conectó ningún servicio Slack real.

La alerta contiene exclusivamente `execution_id`, `stage` y `error_code`. El fallo de Slack conserva el estado `failed` y el error principal, registra un evento separado de etapa `alert` y no genera alertas recursivas.

Validaciones de cierre: validador LF-001 PASS, sintaxis Python/JSON PASS, Docker Compose PASS, `git diff --check` PASS, `git diff --cached --check` PASS y revisión de secretos PASS.

Siguiente etapa prevista: recuperación controlada de ejecuciones en `processing`. No iniciada.

## LF-001.F1 — Detección de ejecuciones processing interrumpidas

Resultado: **PASS** (2026-09-25). LAB-LF-001 continúa **EN CURSO**.

La operación oficial `leadflow.claim_stale_processing_executions` identifica únicamente ejecuciones con estado `processing`, `idempotency_key` presente y `updated_at` anterior a un umbral configurable entre 60 segundos y 7 días. La operación no cambia el estado, no libera ni elimina la clave de idempotencia y no reanuda CRM, enrichment o alertas.

El claim usa una lease configurable de 30 a 3600 segundos y selección transaccional con `FOR UPDATE SKIP LOCKED`. Dos recuperadores concurrentes no pueden obtener simultáneamente la misma ejecución. La fila conserva etapa, referencias CRM y contador de retries para una reconciliación futura; una ejecución antigua no se considera segura para reejecución ciega.

Pruebas F1: **7/7 PASS**. Se verificaron exclusión de processing reciente, detección de processing antiguo, exclusión de success/failed/duplicate, conservación de `idempotency_key`, propiedad concurrente única, ausencia de llamadas CRM/enrichment y permanencia de las claves. No se implementó reanudación, worker ni scheduler.

Archivos F1: `database/migrations/007_recovery_candidates.sql`, `scripts/test/test_recovery_candidates.py` y este handoff.

Siguiente etapa prevista: **LAB-LF-001.F2 — recuperación controlada con reconciliación previa**. No iniciada.

## LF-001.F2a — Reconciliación CRM de ejecuciones interrumpidas

Resultado: **PASS** (2026-09-25). LAB-LF-001 continúa **EN CURSO**.

Una ejecución `processing` con lease vigente puede obtener contexto mediante `get_recovery_crm_context` y persistir el resultado mediante `record_recovery_crm_reconciliation`; el rol de aplicación conserva solo EXECUTE y no recibe DML directo. La reconciliación valida que el email controlado corresponda al `lead_identifier`, consulta CRM por email antes de cualquier CREATE y usa la misma `operation_key` estable `idempotency_key + ':crm_create'`.

Si lookup encuentra el contacto, se reutiliza y persiste su `crm_contact_id`. Si no existe, CREATE solo se emite con la clave idempotente; ante timeout o respuesta ambigua se repite lookup antes de decidir. La ejecución permanece en `processing`, mantiene `idempotency_key`, `retry_count` y lease, y registra un evento `recovery_reused` o `recovery_created`. No se ejecuta enrichment ni se cierra success.

Pruebas F2a: **9/9 PASS**. Se verificaron reutilización de contacto existente, CREATE seguro, reconciliación de resultado ambiguo, repetición con la misma operation_key sin duplicados, exclusión concurrente, reclaim tras lease vencida, claves intactas, ausencia de enrichment y auditoría. Regresión F1: **7/7 PASS**.

El email normalizado no se persiste para recovery; el reconciliador lo recibe como entrada controlada y verifica su hash. La fuente durable de esa entrada deberá resolverse antes de automatizar F2b, sin debilitar la política de PII.

Archivos F2a: `database/migrations/008_recovery_crm_reconciliation.sql`, `scripts/recovery/reconcile_crm.py`, `scripts/test/test_recovery_crm_reconciliation.py` y este handoff. F1 permanece sin commit.

Siguiente etapa prevista: F2b, continuación controlada desde el contacto CRM reconciliado. No iniciada.

## LF-001.F2b-1 — Contexto durable seguro para recovery

Resultado: **PASS** (2026-09-25). LAB-LF-001 continúa **EN CURSO**.

El email normalizado necesario para recovery se guarda únicamente como ciphertext PGP simétrico con AES-256 en `leadflow.recovery_contexts`. La tabla contiene solo `execution_id`, `email_ciphertext` y `created_at`; no almacena payload, nombre, teléfono ni clave. `RECOVERY_CONTEXT_KEY` proviene del entorno, queda vacío en `.env.example` y su valor real permanece únicamente en `.env` ignorado.

El workflow persiste el contexto cifrado después del claim y antes del primer efecto CRM mediante `store_recovery_context`. El rol de aplicación no tiene SELECT ni DML sobre la tabla sensible. `get_recovery_crm_context` descifra únicamente para el worker que mantiene una lease vigente, verifica SHA-256 contra `lead_identifier` y no incluye el email en eventos, logs ni respuestas del reconciliador.

Un trigger elimina el contexto sensible cuando la ejecución cambia a `success`, `failed` o `duplicate`; la FK también aplica borrado en cascada si se elimina la ejecución. Una clave incorrecta no devuelve el email ni detalles del fallo de descifrado.

Pruebas F2b-1: **7/7 PASS**. Se verificaron ciphertext sin email plano, recuperación con secreto correcto, no exposición con secreto incorrecto, coincidencia del hash, denegación de lectura directa al rol de aplicación, limpieza terminal y esquema mínimo. Regresión F2a: **9/9 PASS**.

Archivos F2b-1: `database/migrations/009_recovery_encrypted_context.sql`, `.env.example`, `compose.yaml`, `workflows/leadflow_core_initial.json`, `scripts/recovery/reconcile_crm.py`, `scripts/test/test_recovery_encrypted_context.py`, ajuste de la prueba F2a y este handoff. F1+F2a permanecen sin commit.

Siguiente etapa prevista: continuación controlada con enrichment desde el contacto CRM reconciliado. No iniciada.

## LF-001.F2b-2 — Continuación y cierre de recovery

Resultado: **PASS** (2026-09-25). LAB-LF-001 continúa **EN CURSO**.

Una ejecución reclamada y reconciliada usa exclusivamente el email descifrado por `get_recovery_crm_context` y el `crm_contact_id` ya persistido. Recovery ejecuta enrichment con la política vigente: HTTP 400/401 sin retry; timeout, 429 y 5xx con hasta tres intentos totales, delays de 5 y 15 segundos y respeto de `Retry-After`. Después aplica únicamente los campos permitidos al contacto reconciliado, sin ejecutar CREATE CRM.

`complete_recovery_enrichment` exige estado `processing`, contacto CRM y lease vigente. En success cierra la ejecución, conserva la clave de idempotencia, invalida la lease y dispara la eliminación del contexto cifrado. En fallo definitivo persiste primero el error principal, limpia contexto y lease, envía la alerta sanitizada existente y registra su resultado sin reemplazar el fallo principal.

Pruebas F2b-2: **10/10 PASS**. Se verificaron success con contacto existente y creado/reconciliado, retry temporal seguido de success, fallo terminal con alerta, ausencia de CREATE adicional y duplicados CRM, limpieza del contexto, conservación de `idempotency_key`, invalidación de lease y rechazo de una segunda recuperación terminal.

## Cierre LAB-LF-001.F — Recuperación controlada

Resultado: **PASS** (2026-09-25). LAB-LF-001 continúa **EN CURSO**.

Recovery cubre detección de ejecuciones `processing` antiguas, lease con exclusión concurrente, reconciliación CRM previa, contexto mínimo cifrado, continuación de enrichment con retries y cierre terminal success/failed. No existe scheduler y ninguna recuperación repite CREATE ciegamente.

Regresiones de cierre: F1 **7/7 PASS**, F2a **9/9 PASS**, F2b-1 **7/7 PASS** y F2b-2 **10/10 PASS**. No quedan hallazgos abiertos dentro del alcance de recovery.

Archivos acumulados F: migraciones `007`–`010`, scripts manuales de recovery, cuatro suites de pruebas, configuración segura de entorno, integración de almacenamiento cifrado en el workflow y este handoff.

Siguiente etapa prevista: cierre final y validación integral de LAB-LF-001. No iniciada.
