# LAB-LF-002 — Adaptadores reales, seguridad y operación

Estado: **CERRADO — PASS**

Fecha de apertura: **2026-09-25**

Fecha de cierre: **2026-09-26**

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

## LF-002.2 — Contratos y pruebas de conformidad de adaptadores

Resultado: **PASS** (2026-09-25).

Se formalizaron contratos ejecutables para CRM y enrichment sin seleccionar ni conectar proveedores reales. CRM cubre lookup determinista, CREATE con `operation_key`, idempotencia, update parcial, whitelist de enrichment, reconciliación 409 y tratamiento conservador de CREATE ambiguo. Enrichment cubre entrada canónica, salida success, opcionales, whitelist, errores permanentes, temporales, timeout y `Retry-After`. El error canónico define `type`, `code`, `http_status`, `retry_after_seconds`, `ambiguous` y `message`, siempre sanitizados.

El capability profile mínimo declara `consistent_lookup_after_create`, `unique_email`, `idempotent_create_operation_key` y `conflict_reconciliation`. Un segundo CREATE tras resultado ambiguo solo se permite con operation key idempotente o con unicidad más lookup consistente; un perfil insuficiente termina `ambiguous_create` sin repetir CREATE.

La suite reutilizable `scripts/test/test_adapter_conformance.py` verifica estos criterios contra la frontera de adaptadores: **26/26 PASS**. Regresiones directas: adaptadores LF-002.1 **10/10 PASS**, enrichment retries **9/9 PASS** y CRM retries/reconciliación **11/11 PASS**. Los mocks continúan como destinos externos actuales, las API keys siguen sin esquema asumido, recovery no fue modificado y no existe proveedor real conectado.

Continuidad: **LF-002.3 — Recovery desacoplado.**

## LF-002.3 — Recovery desacoplado

Resultado: **PASS** (2026-09-25).

Recovery consume ahora exclusivamente la frontera canónica mediante `RECOVERY_ADAPTER_URL`: CRM usa `/crm/process`, enrichment usa `/enrichment/enrich`, la actualización enriquecida usa `/crm/update-enrichment/{contact_id}` y las alertas usan `/alert`. Se eliminaron del código los fallbacks implícitos a los mocks locales y las variables upstream específicas. La ausencia o invalidez de la URL del Adapter produce un fallo controlado.

El Adapter conserva `operation_key`, reconciliación, perfil de capacidades, retries, clasificación y whitelist. Un CREATE ambiguo con capacidades insuficientes termina como `ambiguous_create` mediante una operación PostgreSQL oficial, libera la lease e impide otra creación insegura. La migración `011_recovery_adapter_failure.sql` también persiste el retry count devuelto por el Adapter y formaliza el cierre terminal de CRM, enrichment y actualización de enrichment.

Pruebas focalizadas: frontera recovery→Adapter **11/11 PASS**, reconciliación CRM recovery **9/9 PASS** y continuación/cierre recovery **10/10 PASS**; total **30/30 PASS**. No fue necesario repetir conformidad, suites generales CRM/enrichment ni regresión LF-001. Los mocks siguen siendo los destinos upstream, no existe proveedor real conectado y no se modificó el Core.

Continuidad: **LF-002.4 — Seguridad y preparación de despliegue.**

## LF-002.4 — Seguridad y preparación de despliegue

Resultado: **PASS** (2026-09-25).

Se hizo explícita la separación `APP_ENV=development|production`. Development conserva mocks y puertos publicados únicamente en loopback. Production usa `compose.production.yaml`: exige configuración crítica y upstreams HTTPS explícitos, rechaza localhost/mocks, elimina la publicación de puertos de n8n, PostgreSQL, Adapter y mocks, y deja los mocks bajo perfil development. El Adapter ejecuta como usuario no privilegiado y falla al iniciar ante configuración productiva insegura.

`validate_deployment_config.py` comprueba base de datos, autenticación del webhook, claves de cifrado/recovery, URL del Adapter de recovery, host público y destinos externos sin mostrar valores. `CRM_API_KEY` y `ENRICHMENT_API_KEY` siguen sin ser obligatorias hasta definir autenticación real en LF-002.5. `.gitignore` ya protege `.env`, variantes, claves y artefactos locales.

El webhook mantuvo comparación temporalmente segura: clave válida continúa; clave incorrecta o ausente devuelve 401; configuración productiva ausente falla cerrada. La exposición pública requiere HTTPS/TLS mediante una frontera externa; n8n y servicios internos no deben publicarse directamente.

Pruebas focalizadas de seguridad: **14/14 PASS**. Regresión directa Adapter: **10/10 PASS**. Compose development y production: PASS. No se ejecutaron suites históricas no afectadas. Limitaciones aceptadas: todavía no existe infraestructura TLS/reverse proxy, proveedor real ni esquema de autenticación CRM/enrichment; se definirán en LF-002.5. No se realizó commit ni push.

Continuidad: **LF-002.5 — selección/configuración definitiva de proveedores reales, integración externa controlada y regresión final.**

## LF-002.5 — HubSpot + Hunter

Resultado: **PASS** (2026-09-26).

Se seleccionaron HubSpot para CRM y Hunter Combined Enrichment. `CRM_PROVIDER` y `ENRICHMENT_PROVIDER` mantienen mocks en development y exigen `hubspot`/`hunter` en production. HubSpot usa Bearer con Service Key, Contacts Search y Contacts Object API; Hunter usa `X-API-KEY` y nunca incluye la clave en la URL. El Core y recovery no incorporan reglas de proveedor.

HubSpot declara capacidades conservadoras: lookup consistente, unicidad e idempotencia de CREATE no se presumen; solo se habilita reconciliación de conflicto. Un CREATE ambiguo no se repite si lookup no demuestra contacto existente. Hunter descarta toda respuesta salvo `industry`, `company_size` y `website`; no-data es success vacío, cuota y restricción legal son permanentes, y rate limit/timeout/5xx conservan la política canónica.

La validación externa real de HubSpot quedó **PASS** contra `https://api.hubapi.com`. Las rutas CRM v3 de lookup, CREATE y update fueron corregidas y validadas. Las propiedades `industry`, `website` y `leadflow_company_size` quedaron confirmadas como texto; `leadflow_company_size` fue creada manualmente en HubSpot y la escritura real de las tres propiedades de enrichment quedó validada. El contacto sintético controlado fue eliminado y el cleanup posterior confirmó `count=0` y `cleanup_verified=true`.

La validación externa real de Hunter quedó **PASS** contra `https://api.hunter.io`, usando el endpoint y autenticación `X-API-KEY` reales. Un correo Outlook webmail devolvió HTTP 400 con error `invalid_email`; el Adapter traduce exclusivamente esa condición a enrichment success con `data={}`, por tratarse de un lead válido no enriquecible. Otros HTTP 400 continúan como fallo. No existen listas hardcodeadas de proveedores webmail y LeadFlow no presupone que el lead pertenezca a una empresa.

El supuesto PASS inicial de Hunter no fue evidencia externa válida: `CRM_UPSTREAM_URL` y `ENRICHMENT_UPSTREAM_URL` todavía apuntaban a mocks. La evidencia válida es la ejecución Hunter-only posterior, que terminó `REAL-HUNTER: PASS` y `RESULT: PASS` después de la corrección específica para `invalid_email`.

Durante la regresión final, `test_adapters.py` se ejecutó inicialmente cuando el Adapter todavía apuntaba a proveedores reales. Esto creó accidentalmente tres contactos sintéticos de prueba en HubSpot. Los tres fueron identificados y eliminados; cada DELETE devolvió HTTP 204. Después se recreó el Adapter en development con `CRM_PROVIDER=mock`, `ENRICHMENT_PROVIDER=mock`, `CRM_UPSTREAM_URL=http://crm-mock:8080` y `ENRICHMENT_UPSTREAM_URL=http://enrichment-mock:8080`, y la regresión local se repitió correctamente contra mocks.

Resultados finales: `test_adapters.py` **10/10 PASS**; conformidad **26/26 PASS**; seguridad de despliegue **14/14 PASS**; mocks **18/18 PASS**; alertas n8n **7/7 PASS**; núcleo n8n **26/26 PASS** con concurrencia 1 owner + 1 duplicate; retries CRM **11/11 PASS**; retries enrichment **9/9 PASS**; integración n8n/mocks **10/10 PASS**; persistencia **19/19 PASS** con concurrencia 1 owner + 1 duplicate; providers **44/44 PASS**; frontera recovery **11/11 PASS**; cierre recovery **10/10 PASS**; reconciliación CRM recovery **9/9 PASS**; contexto cifrado **7/7 PASS**; candidatos recovery **PASS** sin atribuir un conteo no conservado en la evidencia.

LAB-LF-002 queda **CERRADO — PASS**. HubSpot y Hunter permanecen como terceros y destinos de datos sujetos a revisión formal. Este cierre técnico no declara cumplimiento legal.

Continuidad: **LAB-LF-003 — Auditoría de privacidad y protección de datos**, usando la Política Global de Privacidad, Datos y Cumplimiento de Emactiva definida fuera de este proyecto técnico.
