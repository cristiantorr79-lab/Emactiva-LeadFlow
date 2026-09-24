# Setup inicial

## Requisitos y estado

LF-001.D1 usa Docker 29.6.1, Docker Compose 5.1.4, PostgreSQL 17.6 (`postgres:17.6-bookworm`), n8n 2.28.6 (`n8nio/n8n:2.28.6`) y Python 3.14.3. PostgreSQL se publica en `127.0.0.1:5432`, n8n en `127.0.0.1:5680`, CRM mock en `127.0.0.1:5683` y enrichment mock en `127.0.0.1:5682`. El puerto 5678 pertenece a VetAtiende y no se modifica.

Desde la raíz del repositorio en PowerShell:

```powershell
Copy-Item .env.example .env
```

Completar `.env` con el usuario de aplicación, password local, `N8N_ENCRYPTION_KEY` y `LEADFLOW_WEBHOOK_KEY` aleatorias. El contenedor inicializa el rol DDL fijo `leadflow_migrator`; n8n usa `POSTGRES_USER`, con privilegios mínimos. No versionar ni imprimir el archivo. Cargar sus variables en PowerShell y ejecutar:

```powershell
Get-Content .env | Where-Object { $_ -match '^[A-Za-z_][A-Za-z0-9_]*=' } | ForEach-Object { $name, $value = $_ -split '=', 2; Set-Item "Env:$name" $value }
docker compose config --quiet
docker compose up -d postgres
./scripts/database/wait_postgres.ps1
./scripts/database/apply_migrations.ps1
./scripts/n8n/provision_n8n.ps1
python scripts/test/test_persistence.py
python scripts/test/test_n8n_core.py
docker compose up -d --build --wait crm-mock enrichment-mock
python scripts/test/test_mocks.py
python scripts/test/test_n8n_mocks_integration.py
python scripts/validation/validate_lab_lf_001.py
git status --short
git diff --check
```

Compose carga `.env`, pero los scripts también requieren sus variables en la sesión. `provision_n8n.ps1` genera una credencial PostgreSQL cifrada en `.local/`, importa el workflow y lo publica mediante la CLI documentada de n8n. La carpeta `.local/` está ignorada. Los mocks CRM y enrichment son servicios HTTP locales en memoria, configurados por entorno y todavía no integrados al workflow n8n. Reiniciar sus contenedores reinicia sus datos. Slack sigue fuera de esta etapa.

## Mocks LF-001.D1

CRM expone `POST /crm/lookup`, `POST /crm/contacts`, `GET /crm/contacts/{contact_id}`, `PATCH /crm/contacts/{contact_id}` y `PATCH /crm/contacts/{contact_id}/enrichment`. Enrichment expone `POST /enrich`. Ambos incluyen `GET /healthz`. Las URL base de las pruebas se configuran con `CRM_BASE_URL` y `ENRICHMENT_BASE_URL`; los puertos publicados admiten `CRM_MOCK_PORT` y `ENRICHMENT_MOCK_PORT`. Los valores de enrichment se configuran mediante `ENRICHMENT_INDUSTRY`, `ENRICHMENT_COMPANY_SIZE` y `ENRICHMENT_WEBSITE`.

`python scripts/test/test_mocks.py` ejecuta 12 comprobaciones HTTP reales: lookup, creación, idempotencia por `operation_key`, unicidad de email, updates parciales, enrichment y lista permitida de campos. `python scripts/test/test_n8n_mocks_integration.py` cubre el happy path integrado: creación, actualización, enrichment, persistencia success, duplicado sin nuevas llamadas y dos eventos para un único email. Las URL internas de n8n admiten `CRM_BASE_URL_N8N` y `ENRICHMENT_BASE_URL_N8N`. LF-001.D2 no añade simulación avanzada de errores, retries ni Slack.

## Migración

`apply_migrations.ps1` detecta versiones aplicadas y envía únicamente migraciones pendientes por stdin con `ON_ERROR_STOP=1`. `001_initial` crea persistencia y reclamo; `002_n8n_core` añade `record_validation_failure`; `003_n8n_happy_path` añade la operación oficial que persiste el resultado `success` después de CRM y enrichment. El rol de aplicación conserva lectura y ejecución de funciones oficiales, sin DML directo.

No ejecutar con valores vacíos. La migración incorpora BEGIN/COMMIT y un ledger `leadflow.schema_migrations`. La inserción de versión ocurre antes del DDL de negocio; una repetición falla por PK y revierte la transacción, sin eliminar datos. Es **segura bajo este mecanismo, no un script de repetición silenciosa**. ON_ERROR_STOP y una conexión psql dedicada son obligatorios. No editar una migración aplicada ni marcar versiones manualmente.

Verificación posterior: consultar schema_migrations, inspeccionar `\d leadflow.executions` y `\d leadflow.execution_events`, probar una clave repetida y confirmar violación UNIQUE dentro de una transacción de prueba que termine en ROLLBACK. Antes de desplegar, comprobar también dos conexiones concurrentes. Estas pruebas requieren PostgreSQL y no se confunden con el validador estático.

## Validación disponible

`validate_lab_lf_001.py` cubre infraestructura, migraciones, workflow, scripts, pruebas, documentación y secretos. Las pruebas funcionales se ejecutan por separado. El validador histórico `validate_lab.py` representa el contrato exacto de LF-000 y ya no es gate porque rechaza deliberadamente variables nuevas legítimas en `.env.example`.

El webhook local es `POST http://127.0.0.1:5680/webhook/leadflow` y exige `X-LeadFlow-Key`. Un evento nuevo queda en processing; un reenvío queda duplicate. LF-T01–LF-T20 completos esperan los mocks y etapas posteriores.

Para detener sin borrar datos: `docker compose stop`. Para retirar contenedor y red conservando datos: `docker compose down`. `docker compose down -v` elimina deliberadamente la base local. Las pruebas crean una base temporal aislada y la eliminan al finalizar.
