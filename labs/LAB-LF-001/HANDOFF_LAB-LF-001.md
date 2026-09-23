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

Siguiente etapa prevista: **LAB-LF-001.C — Integración inicial del núcleo n8n con la persistencia validada**, sin proveedores reales.
