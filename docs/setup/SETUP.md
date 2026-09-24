# Setup inicial

## Requisitos y estado

LF-001.C usa Docker 29.6.1, Docker Compose 5.1.4, PostgreSQL 17.6 (`postgres:17.6-bookworm`), n8n 2.28.6 (`n8nio/n8n:2.28.6`) y Python 3.14.3. PostgreSQL se publica en `127.0.0.1:5432` y n8n en `127.0.0.1:5680`. El puerto 5678 pertenece a VetAtiende y no se modifica. Los mocks siguen fuera de esta etapa.

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
python scripts/validation/validate_lab_lf_001.py
git status --short
git diff --check
```

Compose carga `.env`, pero los scripts también requieren sus variables en la sesión. `provision_n8n.ps1` genera una credencial PostgreSQL cifrada en `.local/`, importa el workflow y lo publica mediante la CLI documentada de n8n. La carpeta `.local/` está ignorada. CRM, enrichment y Slack siguen vacíos.

## Migración

`apply_migrations.ps1` detecta versiones aplicadas y envía únicamente migraciones pendientes por stdin con `ON_ERROR_STOP=1`. `001_initial` crea persistencia y reclamo; `002_n8n_core` añade `record_validation_failure`. El rol de aplicación conserva lectura y ejecución de funciones oficiales, sin DML directo.

No ejecutar con valores vacíos. La migración incorpora BEGIN/COMMIT y un ledger `leadflow.schema_migrations`. La inserción de versión ocurre antes del DDL de negocio; una repetición falla por PK y revierte la transacción, sin eliminar datos. Es **segura bajo este mecanismo, no un script de repetición silenciosa**. ON_ERROR_STOP y una conexión psql dedicada son obligatorios. No editar una migración aplicada ni marcar versiones manualmente.

Verificación posterior: consultar schema_migrations, inspeccionar `\d leadflow.executions` y `\d leadflow.execution_events`, probar una clave repetida y confirmar violación UNIQUE dentro de una transacción de prueba que termine en ROLLBACK. Antes de desplegar, comprobar también dos conexiones concurrentes. Estas pruebas requieren PostgreSQL y no se confunden con el validador estático.

## Validación disponible

`validate_lab_lf_001.py` cubre infraestructura, migraciones, workflow, scripts, pruebas, documentación y secretos. Las pruebas funcionales se ejecutan por separado. El validador histórico `validate_lab.py` representa el contrato exacto de LF-000 y ya no es gate porque rechaza deliberadamente variables nuevas legítimas en `.env.example`.

El webhook local es `POST http://127.0.0.1:5680/webhook/leadflow` y exige `X-LeadFlow-Key`. Un evento nuevo queda en processing; un reenvío queda duplicate. LF-T01–LF-T20 completos esperan los mocks y etapas posteriores.

Para detener sin borrar datos: `docker compose stop`. Para retirar contenedor y red conservando datos: `docker compose down`. `docker compose down -v` elimina deliberadamente la base local. Las pruebas crean una base temporal aislada y la eliminan al finalizar.
