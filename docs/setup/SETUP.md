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

LF-011 validó interaction real en HubSpot mediante Tickets: `leadflow_interaction_key` es una propiedad única, cada Ticket se asocia al Contact confirmado y la misma key permite idempotencia y reconciliación concluyente. El soporte vive exclusivamente en el Adapter; el Core sigue CRM-agnostic. LAB-LF-012 implementa LOCATE, EXPORT dirigido, CORRECT y DELETE externo. El runner opt-in de LF012-T03 completó el DELETE real y su reconciliación segura con `RESULT: PASS`; Ticket archive conserva `WARN` porque no demuestra destrucción física irreversible interna del proveedor, y RESTRICT HubSpot permanece `NOT_VERIFIED / capability_not_available`. No debe presentarse como cobertura DSR externa completa.

Los permisos HubSpot requeridos y validados son `crm.objects.contacts.read`, `crm.objects.contacts.write`, `crm.objects.tickets.read` y `crm.objects.tickets.write`. `HUBSPOT_TICKET_PIPELINE_ID` y `HUBSPOT_TICKET_STAGE_ID` se configuran externamente por entorno. LF-011 validó respectivamente `0` y `1` en su entorno de prueba; esos valores no son constantes universales y deben confirmarse para cada portal.

La configuración de Tickets usa `HUBSPOT_INTERACTION_KEY_PROPERTY`, `HUBSPOT_TICKET_MESSAGE_PROPERTY` y `HUBSPOT_TICKET_INTEREST_PROPERTY`; sus defaults son `leadflow_interaction_key`, `content` y `leadflow_interest`. La propiedad textual `leadflow_interest` debe existir en el portal. LeadFlow no amplía scopes para crear schema automáticamente.

## Configuración de interaction

`LEADFLOW_ALLOWED_INTERESTS` define el catálogo permitido, separado por comas y con coincidencia exacta tras trim. `CRM_CAP_INTERACTION_WRITE`, `CRM_CAP_INTERACTION_IDEMPOTENCY` y `CRM_CAP_INTERACTION_RECONCILIATION` declaran por separado las garantías del provider. Las tres deben estar presentes cuando se procesa interaction; si falta una garantía requerida, el Adapter falla cerrado.

`ADAPTER_ALLOWED_OPERATIONS` debe autorizar `crm.record_interaction`, `crm.reconcile_interaction`, `crm.dsr_locate`, `crm.dsr_export` y `crm.dsr_correct`, además de las operaciones vigentes del flujo. La operation key estable `<idempotency_key>:crm_interaction` no contiene PII. `message` e `interest` no se escriben en logs, Slack ni respuestas públicas; el contexto mínimo usado por recovery se conserva estructurado y cifrado.

DELETE DSR usa una identidad distinta: configure `DSR_ADAPTER_SERVICE_KEY` con al menos 32 caracteres, con valor diferente de `ADAPTER_SERVICE_KEY`, y entréguela únicamente como `X-LeadFlow-DSR-Adapter-Key` a `/crm/dsr-delete`. El Adapter rechaza configuración con identidades iguales. No agregue esta llave al flujo normal ni reutilice `ADAPTER_SERVICE_KEY`. Si la llave destructiva falta, la ruta permanece fail-closed. La coordinación debe partir de `dsr_admin.py`; no invoque el endpoint directamente porque la aprobación independiente y el estado `hubspot/delete/pending` se verifican en PostgreSQL antes de la llamada. RESTRICT externo HubSpot no está disponible.

La validación destructiva real de LF012-T03 dispone de `scripts/test/test_lf012_real_hubspot_delete_opt_in.py` y está bloqueada por defecto. Solo una ejecución coordinada puede definir simultáneamente `RUN_REAL_DSR_DELETE_TESTS=1`, `ALLOW_REAL_HUBSPOT_DELETE=1`, `REAL_PROVIDER_ADAPTER_URL`, un `REAL_DSR_DELETE_TEST_EMAIL` sintético/controlado exacto y las identidades/configuración DSR y PostgreSQL requeridas. Antes de cualquier escritura, el runner exige que `crm.dsr_locate` demuestre ausencia concluyente del email; un Contact preexistente, ambigüedad o fallo bloquean sin cleanup ni escritura. Después crea Contact e INTERACTION mediante el Adapter, ejecuta DELETE exclusivamente por `dsr_admin.py`, reconcilia ausencia, comprueba evidencia e intenta cleanup en `finally` con el mismo `request_id`. Ticket continúa siendo archive operativo con WARN; no equivale a borrado físico demostrado.

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

### Aprovisionamiento n8n en Linux

Producción no usa `.env` ni el archivo temporal de PowerShell. `scripts/n8n/provision_n8n.py` reutiliza `LF015-SECRET-MAP-2` y `GcpSecretManagerProvider`: valida la identidad administrada y resuelve en memoria la contraseña del rol PostgreSQL app junto con el entorno runtime. Exige `LEADFLOW_COMPOSE_PROJECT` explícito y usa siempre `compose.yaml` + `compose.production.yaml` con `--project-name`.

El preflight no importa ni publica. Requiere n8n ya iniciado, valida Compose, exporta el workflow para comparar `id/name/settings/nodes/connections` y usa la exportación individual documentada `export:credentials --id=leadflow-postgres --decrypted` para comparar exclusivamente esa credencial (`id/name/type/data`) con la configuración resuelta. Nunca ejecuta una exportación descifrada masiva. Los temporales se crean dentro del contenedor con `umask 077`, se fuerzan a `0600` y un `trap` instalado antes del primer `mktemp` los elimina incluso si falla una creación posterior; ningún secreto se devuelve al host. Una salida individual vacía acredita ausencia; errores, IDs distintos o formas múltiples/inválidas son ambiguos y bloquean. El estado se clasifica como ausente, equivalente, divergente o ambiguo. Equivalente no se reimporta; parcial importa solo lo ausente; divergente exige autorización específica y ambiguo bloquea:

```bash
export LEADFLOW_COMPOSE_PROJECT='<proyecto-core-aprobado>'
export LEADFLOW_SECRET_MAP_FILE='/ruta/externa/lf015-runtime-map-v2.json'
python3 scripts/n8n/provision_n8n.py preflight --map "$LEADFLOW_SECRET_MAP_FILE"
# Solo para una divergencia conocida y aprobada (usar únicamente el flag necesario):
python3 scripts/n8n/provision_n8n.py preflight --map "$LEADFLOW_SECRET_MAP_FILE" \
  --authorize-replace-workflow --authorize-active-replacement
```

La ejecución requiere autorización de provisión; publicar es un gate independiente. La credencial JSON viaja por stdin, nunca por argumentos, stdout o archivo del host. Dentro del contenedor usa `umask 077`, se importa desde un temporal y se elimina aun ante fallo. La importación conserva los IDs estables `leadflow-postgres` y `leadflow-core-initial`; después se reconcilian contenido y actividad. Un workflow nuevo queda inactivo sin `--authorize-publish`. Un workflow activo equivalente permanece activo sin mutación. Reemplazar uno activo exige además `--authorize-active-replacement` y conserva su actividad. Ante retorno ambiguo de import/publish se inspecciona el estado antes de continuar; nunca se repite automáticamente la mutación.

```bash
# Importar credencial y workflow, sin publicar:
python3 scripts/n8n/provision_n8n.py apply --map "$LEADFLOW_SECRET_MAP_FILE" --authorize-provision

# Instalación/reconciliación aprobada con publicación explícita:
python3 scripts/n8n/provision_n8n.py apply --map "$LEADFLOW_SECRET_MAP_FILE" \
  --authorize-provision --authorize-replace-credential \
  --authorize-replace-workflow --authorize-active-replacement --authorize-publish
```

El resultado solo informa fase, PASS/FAIL y `error_id` sanitizado. No ejecutar simultáneamente dos provisiones ni cambiar `N8N_ENCRYPTION_KEY`: la clave debe coincidir con el volumen existente. Esta ruta no sustituye bootstrap, roles o migraciones PostgreSQL.

### Preparación productiva reproducible para M01

Orden obligatorio y fail-closed:

1. Fijar checkout/commit aprobado y verificar host Linux, espacio, hora, Docker Engine, plugin Compose y Python. Confirmar que los mapas externos existen con permisos `0600`; no mostrar Compose renderizado ni `docker inspect` de entornos.
2. Definir proyectos Core, Bridge y Gateway distintos y nombres de redes externos aprobados. Rechazar recursos preexistentes cuyo label Compose no coincida; no reutilizar volúmenes entre proyectos.
3. Verificar localmente las imágenes fijadas antes de mutar: `postgres:17.6-bookworm`, `n8nio/n8n:2.28.6`, `leadflow-adapters:python-3.14.3`, `leadflow-web-bridge:python-3.14.3`, `leadflow-web-gateway-rate-gate:python-3.14.3` y `caddy:2.11.3-alpine`. Una imagen ausente o con procedencia/digest no aprobado detiene; pull/build requiere una ventana de suministro separada.
4. Ejecutar los preflight seguros de Core, Bridge y Gateway con sus mapas independientes. Confirmar separación de proyectos, redes esperadas, ausencia de puertos internos publicados y disponibilidad de las redes externas; ningún preflight ejecuta `up`.
5. En instalación nueva, ejecutar el bootstrap PostgreSQL autorizado, sincronizar roles y aplicar migraciones antes del runtime. En volumen existente, omitir bootstrap y comprobar el ledger sin regenerar identidades.
6. Iniciar Core mediante el cargador runtime; exigir healthchecks de PostgreSQL, n8n y Adapter. Ejecutar el preflight/provisionador Linux anterior. Solo después iniciar Bridge y Gateway mediante sus cargadores, manteniendo el orden interno→externo.
7. Verificar IDs/labels, redes, volúmenes, health, workflow publicado cuando fue autorizado, cero puertos internos y únicamente 443 en la frontera. Ante fallo, detener el componente nuevo; no usar `down -v`, no borrar certificados ni recrear proyectos sanos.

**Infraestructura comprobada en LAB-LF-015:** Compose separado para Core/Bridge/Gateway, identidad administrada y resolución Secret Manager, seis servicios productivos, red interna/externa configurada, HTTPS por 443, backup/restore aislado y controles de cleanup documentados. Esta evidencia pertenece al piloto observado y no acredita automáticamente otro cliente/host.

**Mínimos ENVIRONMENT:** Linux compatible, Docker/Compose y Python disponibles; checkout/hash aprobado; imágenes/digests disponibles; disco y permisos del socket; identidad runtime con acceso mínimo a versiones concretas de secretos; mapas externos `0600`; redes/proyectos/volúmenes exclusivos; reloj/DNS/egress requeridos; PostgreSQL inicializado o clasificado inequívocamente; n8n sano con clave de cifrado estable; firewall/TLS y rollback autorizados. Todos deben verificarse en el destino.

**Recomendaciones:** fijar digests además de tags, usuario operativo sin privilegios innecesarios, monitoreo de disco/certificado/health, ventana y snapshot previo, inventario firmado de imágenes y revisión periódica de IAM. No son sustitutos de los mínimos.

**NOT_VERIFIED:** ejecución del nuevo provisionador en Linux/n8n real, comportamiento efectivo de la CLI 2.28.6 en ese host, reconciliación de una instalación parcial real, disponibilidad/digests de imágenes en un destino nuevo, permisos Docker/Secret Manager, redes y capacidad/egress de otro cliente. Estos puntos pasan al gate ENVIRONMENT de M01.

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

`apply_migrations.ps1` detecta versiones aplicadas y envía únicamente migraciones pendientes por stdin con `ON_ERROR_STOP=1`. En una instalación nueva ejecuta la migración histórica e inmutable `001_initial` como bootstrap, transfiere selectivamente al migrator los objetos funcionales no-extension de `leadflow` y ejecuta 002–023 como migrator restringido. En un volumen cuyo ledger ya contiene 001 no vuelve a ejecutarla. `001_initial` crea persistencia y reclamo; `002_n8n_core` añade `record_validation_failure`; `003_n8n_happy_path` añade la persistencia de `success`. El rol de aplicación conserva lectura y ejecución de funciones oficiales, sin DML directo.

Las migraciones vigentes de LF-008 son: `018_lead_interaction.sql`, soporte principal de interaction, checkpoint y recovery ampliado; `019_recovery_context_lookup.sql`, corrección del lookup de recovery; `020_recovery_interaction_validation.sql`, validación JSONB de interaction; y `021_crm_interaction_failure.sql`, fail-closed y persistencia de fallos en `crm_interaction`. No se editan ni se marcan manualmente como aplicadas.

LAB-LF-012 añade `022_dsr_hubspot_nondestructive.sql`, que coordina acciones HubSpot DSR no destructivas aun con ausencia local, y `023_dsr_delete_reconciliation.sql`, que permite cerrar exclusivamente `failed/contact_deletion_ambiguous` como `completed/reconciled_absent` tras una ausencia concluyente por lectura. Ambas están aplicadas y verificadas en el entorno de QA; no deben reaplicarse ni marcarse manualmente.

`sync_database_roles.ps1` crea o actualiza idempotentemente los roles y fuerza `NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION` tanto en migrator como app. El migrator recibe `CONNECT` y `USAGE, CREATE` solo sobre `leadflow`; app recibe `CONNECT` y `USAGE`, nunca `CREATE`. El bootstrap instala `pgcrypto` antes de las migraciones. La ejecución especial de 001 conserva intacto su contenido histórico sin conceder CREATE sobre la base ni CREATEROLE al migrator.

En un volumen anterior donde el migrator es el bootstrap histórico OID 10, definir una sola vez `POSTGRES_ROLE_SYNC_USER` con el nombre del migrator y ejecutar `apply_migrations.ps1`. La reparación aborta antes de renombrar roles si el bootstrap destino posee objetos, existen memberships inesperadas, el topology no coincide o hay objetos de usuario no soportados fuera de `leadflow`. Si las guardas pasan, usa tres sesiones: renombra temporalmente el bootstrap nuevo vacío, conserva el OID 10 renombrándolo al nombre bootstrap, crea un migrator restringido, transfiere selectivamente schema/tablas/secuencias/rutinas/tipos propios de `leadflow`, conserva extensiones con el OID 10 y elimina el rol transitorio solo tras demostrar que está vacío. Después se verifican roles/ownership/runtime y se retira `POSTGRES_ROLE_SYNC_USER`. No usa `REASSIGN OWNED` global. Los secretos siguen siendo configuración de ENVIRONMENT fuera de Git; la separación y los grants son controles SYSTEM.

En Linux esa misma reparación se ejecuta con `bash scripts/database/apply_migrations.sh`; en Windows, con `./scripts/database/apply_migrations.ps1`. Ambos reutilizan los mismos SQL validados y distinguen instalación nueva de volumen heredado.

No ejecutar con valores vacíos. La migración incorpora BEGIN/COMMIT y un ledger `leadflow.schema_migrations`. La inserción de versión ocurre antes del DDL de negocio; una repetición falla por PK y revierte la transacción, sin eliminar datos. Es **segura bajo este mecanismo, no un script de repetición silenciosa**. ON_ERROR_STOP y una conexión psql dedicada son obligatorios. No editar una migración aplicada ni marcar versiones manualmente.

Verificación posterior: consultar schema_migrations, inspeccionar `\d leadflow.executions` y `\d leadflow.execution_events`, probar una clave repetida y confirmar violación UNIQUE dentro de una transacción de prueba que termine en ROLLBACK. Antes de desplegar, comprobar también dos conexiones concurrentes. Estas pruebas requieren PostgreSQL y no se confunden con el validador estático.

## Validación disponible

Para instalación/configuración, validar como mínimo que Compose resuelva sin errores, que el ledger alcance la migration 023, que los healthchecks configurados respondan y que `git diff --check` no reporte defectos. Las suites funcionales y validadores históricos se ejecutan solo cuando el alcance del cambio los requiere; no forman parte de cada setup rutinario.

El webhook local es `POST http://127.0.0.1:5680/webhook/leadflow` y exige `X-LeadFlow-Key`. Clave ausente, incorrecta o configuración vacía se rechazan sin devolver ni registrar la clave. Un evento nuevo recorre el flujo vigente hasta `success`, fallo sanitizado o estado recuperable; un reenvío exacto queda `duplicate` sin repetir efectos externos.

Para detener sin borrar datos: `docker compose stop`. Para retirar contenedor y red conservando datos: `docker compose down`. `docker compose down -v` elimina deliberadamente la base local. Las pruebas crean una base temporal aislada y la eliminan al finalizar.
