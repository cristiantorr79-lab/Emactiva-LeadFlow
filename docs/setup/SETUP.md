# Setup inicial

## Requisitos y estado

LF-001.D1 usa Docker 29.6.1, Docker Compose 5.1.4, PostgreSQL 17.6 (`postgres:17.6-bookworm`), n8n 2.28.6 (`n8nio/n8n:2.28.6`) y Python 3.14.3. PostgreSQL se publica en `127.0.0.1:5432`, n8n en `127.0.0.1:5680`, CRM mock en `127.0.0.1:5683` y enrichment mock en `127.0.0.1:5682`. El puerto 5678 pertenece a VetAtiende y no se modifica.

LF-002.1 añadió el servicio interno de adaptadores, publicado para pruebas en `127.0.0.1:5685`. `RETRY_MAX_ATTEMPTS` admite 1–3; ambos delays y `ADAPTER_HTTP_TIMEOUT_MS` deben ser positivos. Los defaults locales conservan 3 intentos, 5/15 segundos y 2000 ms. `ADAPTER_CALL_TIMEOUT_MS` limita la llamada Core→Adapter. HubSpot y Hunter fueron seleccionados posteriormente; sus credenciales se suministran desde entorno y el Adapter aplica el esquema de autenticación correspondiente.

## Development y production

`compose.yaml` es el entorno development probado: PostgreSQL, n8n, Adapter y mocks se publican solo en loopback para pruebas locales. `APP_ENV=development` permite los destinos mock explícitos. HTTP directo es válido únicamente en este entorno local controlado.

Production requiere `compose.production.yaml` y validación previa:

```powershell
$env:APP_ENV = 'production'
python scripts/validation/validate_deployment_config.py
docker compose -f compose.yaml -f compose.production.yaml config --quiet
```

La configuración production exige base de datos, claves de webhook/cifrado/recovery, `RECOVERY_ADAPTER_URL`, host público, upstreams HTTPS explícitos y las credenciales `CRM_API_KEY` y `ENRICHMENT_API_KEY`. Rechaza localhost y mocks y falla cerrado ante configuración incompleta. El override no publica puertos de n8n, PostgreSQL, Adapter ni mocks; los mocks quedan bajo perfil `development`. La frontera TLS/reverse proxy del deployment debe unirse a la red de la aplicación y dirigir HTTPS al puerto interno de n8n. No exponer directamente n8n ni considerar suficiente el header de autenticación sin TLS.

Los secretos se suministran fuera de Git mediante el entorno o el mecanismo de secretos de la infraestructura elegida. `.env` y variantes reales están ignorados. HubSpot y Hunter ya están seleccionados y sus endpoints son configurables; cada deployment productivo sigue requiriendo infraestructura TLS, credenciales, red y controles operacionales propios. Esta documentación no declara que exista un entorno productivo de cliente.

## Providers reales preparados

LF-002.5 selecciona `CRM_PROVIDER=hubspot` con `CRM_UPSTREAM_URL=https://api.hubapi.com` y `ENRICHMENT_PROVIDER=hunter` con `ENRICHMENT_UPSTREAM_URL=https://api.hunter.io`. Production exige `CRM_API_KEY` y `ENRICHMENT_API_KEY`; nunca se guardan en Git. HubSpot requiere una Service Key con lectura/escritura de contactos y Hunter una API key habilitada para Combined Enrichment. El Adapter envía ambas por headers, no por query string.

LF-011 validó interaction real en HubSpot mediante Tickets: `leadflow_interaction_key` es una propiedad única, cada Ticket se asocia al Contact confirmado y la misma key permite idempotencia y reconciliación concluyente. El soporte vive exclusivamente en el Adapter; el Core sigue CRM-agnostic. DSR HubSpot permanece `PARTIAL / NON-BLOCKING` y no debe presentarse como cobertura externa completa.

Los permisos HubSpot requeridos y validados son `crm.objects.contacts.read`, `crm.objects.contacts.write`, `crm.objects.tickets.read` y `crm.objects.tickets.write`. `HUBSPOT_TICKET_PIPELINE_ID` y `HUBSPOT_TICKET_STAGE_ID` se configuran externamente por entorno. LF-011 validó respectivamente `0` y `1` en su entorno de prueba; esos valores no son constantes universales y deben confirmarse para cada portal.

## Configuración de interaction

`LEADFLOW_ALLOWED_INTERESTS` define el catálogo permitido, separado por comas y con coincidencia exacta tras trim. `CRM_CAP_INTERACTION_WRITE`, `CRM_CAP_INTERACTION_IDEMPOTENCY` y `CRM_CAP_INTERACTION_RECONCILIATION` declaran por separado las garantías del provider. Las tres deben estar presentes cuando se procesa interaction; si falta una garantía requerida, el Adapter falla cerrado.

`ADAPTER_ALLOWED_OPERATIONS` debe autorizar `crm.record_interaction` y `crm.reconcile_interaction`, además de las operaciones vigentes del flujo. La operation key estable `<idempotency_key>:crm_interaction` no contiene PII. `message` e `interest` no se escriben en logs, Slack ni respuestas públicas; el contexto mínimo usado por recovery se conserva estructurado y cifrado.

Antes de pruebas externas, confirmar en HubSpot las propiedades de contacto configuradas por `HUBSPOT_PROPERTY_INDUSTRY`, `HUBSPOT_PROPERTY_COMPANY_SIZE` y `HUBSPOT_PROPERTY_WEBSITE`. El default `leadflow_company_size` debe existir como propiedad textual. No se crean propiedades ni scopes automáticamente.

Las pruebas reales están bloqueadas por defecto. Para una ejecución posterior coordinada se deberán definir fuera de Git `RUN_REAL_PROVIDER_TESTS=1`, `ALLOW_REAL_HUBSPOT_WRITE=1`, `REAL_PROVIDER_ADAPTER_URL` y `REAL_PROVIDER_TEST_EMAIL`, además de las credenciales del runtime. El email debe ser sintético/controlado. `scripts/test/test_real_providers_opt_in.py` puede crear o actualizar un contacto y consumir créditos Hunter; no ejecutarlo como parte de regresiones normales. Actualmente no existe cleanup automático del contacto HubSpot de prueba.

Desde la raíz del repositorio en PowerShell:

```powershell
Copy-Item .env.example .env
```

Completar `.env` con tres identidades PostgreSQL distintas y passwords aleatorias: `POSTGRES_BOOTSTRAP_USER` (administración interna), `POSTGRES_MIGRATOR_USER` (DDL limitado al schema `leadflow`) y `POSTGRES_APP_USER` (runtime sin CREATE). `POSTGRES_USER` queda reservado internamente por Compose para el bootstrap; n8n usa exclusivamente el rol app. No versionar ni imprimir el archivo.

Prerequisitos del host Linux/Debian: Bash, Docker Engine y Docker Compose plugin. PowerShell no es necesario; Compose carga `.env` y el script consume la configuración validada dentro del contenedor PostgreSQL. Después de iniciar PostgreSQL, ejecutar:

```bash
docker compose up -d postgres
bash scripts/database/apply_migrations.sh
```

En Windows se mantiene la ruta PowerShell existente. Cargar las variables de `.env` en la sesión y ejecutar:

```powershell
Get-Content .env | Where-Object { $_ -match '^[A-Za-z_][A-Za-z0-9_]*=' } | ForEach-Object { $name, $value = $_ -split '=', 2; Set-Item "Env:$name" $value }
docker compose config --quiet
docker compose up -d postgres
./scripts/database/wait_postgres.ps1
./scripts/database/apply_migrations.ps1
docker compose up -d --build --wait crm-mock enrichment-mock
docker compose up -d --build --wait adapters
./scripts/n8n/provision_n8n.ps1
git status --short
git diff --check
```

Compose carga `.env`, pero los scripts también requieren sus variables en la sesión. `provision_n8n.ps1` genera una credencial PostgreSQL cifrada en `.local/`, importa el workflow y lo publica mediante la CLI documentada de n8n. La carpeta `.local/` está ignorada. Los mocks CRM, enrichment y Slack son servicios de development; el workflow y los adapters ya están integrados con sus contratos. Reiniciar los mocks reinicia sus datos en memoria.

La exigencia de variables en la sesión corresponde a los scripts PowerShell de Windows. La ruta Bash de migraciones no hace `source` de `.env`: obtiene nombres y configuración desde el entorno ya materializado por Compose dentro de PostgreSQL y nunca imprime passwords.

## Mocks LF-001.D1

CRM expone `POST /crm/lookup`, `POST /crm/contacts`, `GET /crm/contacts/{contact_id}`, `PATCH /crm/contacts/{contact_id}` y `PATCH /crm/contacts/{contact_id}/enrichment`. Enrichment expone `POST /enrich`. Ambos incluyen `GET /healthz`. Las URL base de las pruebas se configuran con `CRM_BASE_URL` y `ENRICHMENT_BASE_URL`; los puertos publicados admiten `CRM_MOCK_PORT` y `ENRICHMENT_MOCK_PORT`. Los valores de enrichment se configuran mediante `ENRICHMENT_INDUSTRY`, `ENRICHMENT_COMPANY_SIZE` y `ENRICHMENT_WEBSITE`.

`python scripts/test/test_mocks.py` ejecuta 12 comprobaciones HTTP reales: lookup, creación, idempotencia por `operation_key`, unicidad de email, updates parciales, enrichment y lista permitida de campos. `python scripts/test/test_n8n_mocks_integration.py` cubre el happy path integrado: creación, actualización, enrichment, persistencia success, duplicado sin nuevas llamadas y dos eventos para un único email. Las URL internas de n8n admiten `CRM_BASE_URL_N8N` y `ENRICHMENT_BASE_URL_N8N`. LF-001.D2 no añade simulación avanzada de errores, retries ni Slack.

## Migración

`apply_migrations.ps1` detecta versiones aplicadas y envía únicamente migraciones pendientes por stdin con `ON_ERROR_STOP=1`. En una instalación nueva ejecuta la migración histórica e inmutable `001_initial` como bootstrap, transfiere selectivamente al migrator los objetos funcionales no-extension de `leadflow` y ejecuta 002–021 como migrator restringido. En un volumen cuyo ledger ya contiene 001 no vuelve a ejecutarla. `001_initial` crea persistencia y reclamo; `002_n8n_core` añade `record_validation_failure`; `003_n8n_happy_path` añade la persistencia de `success`. El rol de aplicación conserva lectura y ejecución de funciones oficiales, sin DML directo.

Las migraciones vigentes de LF-008 son: `018_lead_interaction.sql`, soporte principal de interaction, checkpoint y recovery ampliado; `019_recovery_context_lookup.sql`, corrección del lookup de recovery; `020_recovery_interaction_validation.sql`, validación JSONB de interaction; y `021_crm_interaction_failure.sql`, fail-closed y persistencia de fallos en `crm_interaction`. No se editan ni se marcan manualmente como aplicadas.

`sync_database_roles.ps1` crea o actualiza idempotentemente los roles y fuerza `NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION` tanto en migrator como app. El migrator recibe `CONNECT` y `USAGE, CREATE` solo sobre `leadflow`; app recibe `CONNECT` y `USAGE`, nunca `CREATE`. El bootstrap instala `pgcrypto` antes de las migraciones. La ejecución especial de 001 conserva intacto su contenido histórico sin conceder CREATE sobre la base ni CREATEROLE al migrator.

En un volumen anterior donde el migrator es el bootstrap histórico OID 10, definir una sola vez `POSTGRES_ROLE_SYNC_USER` con el nombre del migrator y ejecutar `apply_migrations.ps1`. La reparación aborta antes de renombrar roles si el bootstrap destino posee objetos, existen memberships inesperadas, el topology no coincide o hay objetos de usuario no soportados fuera de `leadflow`. Si las guardas pasan, usa tres sesiones: renombra temporalmente el bootstrap nuevo vacío, conserva el OID 10 renombrándolo al nombre bootstrap, crea un migrator restringido, transfiere selectivamente schema/tablas/secuencias/rutinas/tipos propios de `leadflow`, conserva extensiones con el OID 10 y elimina el rol transitorio solo tras demostrar que está vacío. Después se verifican roles/ownership/runtime y se retira `POSTGRES_ROLE_SYNC_USER`. No usa `REASSIGN OWNED` global. Los secretos siguen siendo configuración de ENVIRONMENT fuera de Git; la separación y los grants son controles SYSTEM.

En Linux esa misma reparación se ejecuta con `bash scripts/database/apply_migrations.sh`; en Windows, con `./scripts/database/apply_migrations.ps1`. Ambos reutilizan los mismos SQL validados y distinguen instalación nueva de volumen heredado.

No ejecutar con valores vacíos. La migración incorpora BEGIN/COMMIT y un ledger `leadflow.schema_migrations`. La inserción de versión ocurre antes del DDL de negocio; una repetición falla por PK y revierte la transacción, sin eliminar datos. Es **segura bajo este mecanismo, no un script de repetición silenciosa**. ON_ERROR_STOP y una conexión psql dedicada son obligatorios. No editar una migración aplicada ni marcar versiones manualmente.

Verificación posterior: consultar schema_migrations, inspeccionar `\d leadflow.executions` y `\d leadflow.execution_events`, probar una clave repetida y confirmar violación UNIQUE dentro de una transacción de prueba que termine en ROLLBACK. Antes de desplegar, comprobar también dos conexiones concurrentes. Estas pruebas requieren PostgreSQL y no se confunden con el validador estático.

## Validación disponible

Para instalación/configuración, validar como mínimo que Compose resuelva sin errores, que el ledger alcance la migration 021, que los healthchecks configurados respondan y que `git diff --check` no reporte defectos. Las suites funcionales y validadores históricos se ejecutan solo cuando el alcance del cambio los requiere; no forman parte de cada setup rutinario.

El webhook local es `POST http://127.0.0.1:5680/webhook/leadflow` y exige `X-LeadFlow-Key`. Clave ausente, incorrecta o configuración vacía se rechazan sin devolver ni registrar la clave. Un evento nuevo recorre el flujo vigente hasta `success`, fallo sanitizado o estado recuperable; un reenvío exacto queda `duplicate` sin repetir efectos externos.

Para detener sin borrar datos: `docker compose stop`. Para retirar contenedor y red conservando datos: `docker compose down`. `docker compose down -v` elimina deliberadamente la base local. Las pruebas crean una base temporal aislada y la eliminan al finalizar.
