# Setup inicial

## Requisitos y estado

Git y Python 3 (sin dependencias externas) para validar este LAB. PostgreSQL y cliente psql serán necesarios para aplicar y comprobar la migración; n8n y servicios mock se integrarán en LAB-LF-001. No hay servicios que iniciar en LAB-LF-000 ni instalación automática. La versión concreta de PostgreSQL/n8n se fijará en infraestructura; el SQL utiliza identity, timestamptz, CHECK y UNIQUE.

Desde la raíz del repositorio en PowerShell:

```powershell
Copy-Item .env.example .env
python scripts/validation/validate_lab.py
git status --short
git diff --check
```

Copiar `.env` solo al configurar infraestructura; no hace falta para validar. Ninguna herramienta de este LAB carga `.env` automáticamente. APP_ENV identifica el entorno; POSTGRES_HOST/PORT/DB/USER/PASSWORD describen la conexión. CRM_BASE_URL/API_KEY y ENRICHMENT_BASE_URL/API_KEY apuntarán a los mocks. SLACK_WEBHOOK_URL será provisto por el operador. Los valores vacíos son intencionales, no credenciales operativas. RETRY_MAX_ATTEMPTS cuenta intentos totales; delays 5/15 segundos centralizados. Nunca imprimir variables sensibles.

## Migración

Con una base de desarrollo previamente provisionada y permisos DDL, cargar los valores de conexión mediante el mecanismo seguro del entorno. El cliente psql no interpreta variables POSTGRES_* automáticamente. Usar solicitud interactiva de contraseña; no incluirla en el comando:

```powershell
psql -X -W -h $env:POSTGRES_HOST -p $env:POSTGRES_PORT -U $env:POSTGRES_USER -d $env:POSTGRES_DB -v ON_ERROR_STOP=1 -f database/migrations/001_initial.sql
```

No ejecutar con valores vacíos. La migración incorpora BEGIN/COMMIT y un ledger `leadflow.schema_migrations`. La inserción de versión ocurre antes del DDL de negocio; una repetición falla por PK y revierte la transacción, sin eliminar datos. Es **segura bajo este mecanismo, no un script de repetición silenciosa**. ON_ERROR_STOP y una conexión psql dedicada son obligatorios. No editar una migración aplicada ni marcar versiones manualmente.

Verificación posterior: consultar schema_migrations, inspeccionar `\d leadflow.executions` y `\d leadflow.execution_events`, probar una clave repetida y confirmar violación UNIQUE dentro de una transacción de prueba que termine en ROLLBACK. Antes de desplegar, comprobar también dos conexiones concurrentes. Estas pruebas requieren PostgreSQL y no se confunden con el validador estático.

## Validación disponible

`validate_lab.py` comprueba estructura, configuración vacía para secretos, reglas Git, estados, casos de pruebas, campos y UNIQUE SQL, y secretos evidentes en archivos versionados y nuevos no ignorados. No muestra valores detectados. Incluye balance léxico básico del SQL y `git diff --no-index --check` por archivo nuevo para cubrir lo que `git diff --check` omite. No sustituye al parser/servidor PostgreSQL ni a una auditoría exhaustiva de secretos. El resultado exacto de cada check y el código de salida indican PASS/FAIL; cualquier FAIL impide el cierre.

El plan LF-T01–LF-T20 se ejecutará al existir runtime, mocks e infraestructura. En este LAB se valida su definición, no su comportamiento.
