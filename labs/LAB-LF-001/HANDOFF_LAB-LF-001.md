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
