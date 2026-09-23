# Setup inicial

## Requisitos y estado

LF-001.B usa Docker 29.6.1, Docker Compose 5.1.4, PostgreSQL 17.6 (`postgres:17.6-bookworm`) y Python 3.14.3. n8n y servicios mock todavía no están instalados ni tienen versión fijada. PostgreSQL se publica únicamente en loopback para desarrollo local.

Desde la raíz del repositorio en PowerShell:

```powershell
Copy-Item .env.example .env
```

Completar `.env` con el usuario de aplicación y un password local. El contenedor inicializa el rol DDL fijo `leadflow_migrator`; la aplicación usa `POSTGRES_USER`, con privilegios mínimos. Ambos reciben la misma credencial solo en este entorno local aislado. No versionar ni imprimir el archivo. Cargar sus variables en PowerShell y ejecutar:

```powershell
Get-Content .env | Where-Object { $_ -match '^[A-Za-z_][A-Za-z0-9_]*=' } | ForEach-Object { $name, $value = $_ -split '=', 2; Set-Item "Env:$name" $value }
docker compose config --quiet
docker compose up -d postgres
./scripts/database/wait_postgres.ps1
./scripts/database/apply_migrations.ps1
python scripts/test/test_persistence.py
python scripts/validation/validate_lab_lf_001.py
python scripts/validation/validate_lab.py
git status --short
git diff --check
```

Compose carga `.env`, pero los scripts también requieren sus variables en la sesión. POSTGRES_USER identifica al rol de aplicación; `leadflow_migrator` es el rol DDL del contenedor. CRM, enrichment y Slack siguen vacíos. Nunca imprimir variables sensibles.

## Migración

`apply_migrations.ps1` envía SQL por stdin al cliente psql del contenedor con `ON_ERROR_STOP=1`; no expone passwords en argumentos. La migración configura el rol de aplicación y le concede lectura y ejecución de funciones oficiales, sin DML directo.

No ejecutar con valores vacíos. La migración incorpora BEGIN/COMMIT y un ledger `leadflow.schema_migrations`. La inserción de versión ocurre antes del DDL de negocio; una repetición falla por PK y revierte la transacción, sin eliminar datos. Es **segura bajo este mecanismo, no un script de repetición silenciosa**. ON_ERROR_STOP y una conexión psql dedicada son obligatorios. No editar una migración aplicada ni marcar versiones manualmente.

Verificación posterior: consultar schema_migrations, inspeccionar `\d leadflow.executions` y `\d leadflow.execution_events`, probar una clave repetida y confirmar violación UNIQUE dentro de una transacción de prueba que termine en ROLLBACK. Antes de desplegar, comprobar también dos conexiones concurrentes. Estas pruebas requieren PostgreSQL y no se confunden con el validador estático.

## Validación disponible

`validate_lab.py` comprueba estructura, configuración vacía para secretos, reglas Git, estados, casos de pruebas, campos y UNIQUE SQL, y secretos evidentes en archivos versionados y nuevos no ignorados. No muestra valores detectados. Incluye balance léxico básico del SQL y `git diff --no-index --check` por archivo nuevo para cubrir lo que `git diff --check` omite. No sustituye al parser/servidor PostgreSQL ni a una auditoría exhaustiva de secretos. El resultado exacto de cada check y el código de salida indican PASS/FAIL; cualquier FAIL impide el cierre.

El plan LF-T01–LF-T20 se ejecutará al existir runtime, mocks e infraestructura. En este LAB se valida su definición, no su comportamiento.

Para detener sin borrar datos: `docker compose stop`. Para retirar contenedor y red conservando datos: `docker compose down`. `docker compose down -v` elimina deliberadamente la base local. Las pruebas crean una base temporal aislada y la eliminan al finalizar.
