# LAB-LF-002 — Adaptadores reales, seguridad y operación

Estado: **EN CURSO**

Fecha de apertura: **2026-09-25**

Baseline: rama `main`, commit `412338448a6d74261220ea9b6d300f7dc72e88b1`, LAB-LF-001 cerrado PASS.

## LF-002.1 — Desacoplamiento y configuración de adaptadores

Resultado: **PASS** (2026-09-25).

Se creó una frontera HTTP interna con tres responsabilidades: CRM Adapter, Enrichment Adapter y Alert Adapter. El Core conserva estados, idempotencia, persistencia y respuestas; el servicio `adapters` concentra endpoints upstream, formatos de mocks, clasificación HTTP, retries, reconciliación 409/CREATE ambiguo, whitelist de enrichment y envío sanitizado de alertas. Los mocks siguen siendo los únicos destinos externos de esta etapa.

Configuración activa: `RETRY_MAX_ATTEMPTS` (1–3), delays positivos, `ADAPTER_HTTP_TIMEOUT_MS` positivo y timeout Core→adaptador. Los defaults siguen siendo 3 intentos, 5/15 segundos y 2000 ms. `CRM_API_KEY` y `ENRICHMENT_API_KEY` llegan a la frontera, pero no se transmiten porque el esquema de autenticación depende del proveedor futuro; no se asumió Bearer ni otro header.

Pruebas focalizadas: adaptadores **10/10 PASS**. Regresiones afectadas: mocks **18/18**, happy path **10/10**, enrichment retries **9/9**, CRM retries/reconciliación **11/11** y alertas **7/7**, total **55/55 PASS**. No se modificó recovery y no se conectó ningún proveedor real.

Archivos principales: `adapters/Dockerfile`, `adapters/server.py`, `compose.yaml`, `.env.example`, workflow Core, prueba focalizada, arquitectura, setup y este handoff.

Continuidad aprobada:

1. **LF-002.2 — Contratos y pruebas de conformidad de adaptadores.** Definir y automatizar el comportamiento que deberá cumplir cualquier futuro proveedor CRM/enrichment antes de seleccionarlo o conectarlo.
2. **LF-002.3 — Recovery desacoplado.**
3. **LF-002.4 — Seguridad y preparación de despliegue.**
4. **LF-002.5 — Selección de proveedor real, integración externa controlada y regresión final.**
