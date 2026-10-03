# HANDOFF — LAB-LF-007

**Proyecto:** Emactiva LeadFlow
**LAB:** LAB-LF-007 — Piloto de Implementación Real de LeadFlow
**Estado:** CERRADO — PASS CON LÍMITES DOCUMENTADOS
**Fecha:** 2026-10-03

## Resultado

La implementación y la remediación PostgreSQL del volumen heredado fueron validadas en la VM piloto. LeadFlow quedó funcional, con separación efectiva entre bootstrap, migrator y app, ruta Linux sin PowerShell, salida `psql` sanitizada, credencial potencialmente expuesta rotada y smoke funcional posterior PASS 10/10. La VM fue detenida después de completar las validaciones para evitar costo innecesario.

## Causa y reparación PostgreSQL

El migrator había sido `POSTGRES_USER` durante el bootstrap histórico y correspondía al OID 10. PostgreSQL no permite despromover ese bootstrap original. La reparación protegida:

- conservó OID 10 como `leadflow_bootstrap`;
- creó un `leadflow_migrator` nuevo y restringido;
- mantuvo `leadflow_app` restringido;
- transfirió selectivamente ownership funcional del schema `leadflow`;
- conservó database y extensiones administrativas con bootstrap;
- evitó `REASSIGN OWNED` global;
- preservó datos y ledger 001–017;
- retiró `POSTGRES_ROLE_SYNC_USER` y recreó únicamente PostgreSQL para materializar el entorno definitivo.

## Estado final demostrado

### Roles — PASS

| Rol | OID | SUPERUSER | CREATEDB | CREATEROLE | REPLICATION |
|---|---:|---|---|---|---|
| `leadflow_app` | 24615 | false | false | false | false |
| `leadflow_bootstrap` | 10 | true | true | true | false |
| `leadflow_migrator` | 25302 | false | false | false | false |

### Ownership — PASS

- database `leadflow` → `leadflow_bootstrap`;
- extensión `pgcrypto` → `leadflow_bootstrap`;
- extensión `plpgsql` → `leadflow_bootstrap`;
- schema `leadflow` → `leadflow_migrator`.

### Configuración temporal — PASS

Cambiar `.env` o Compose no actualiza el entorno de un contenedor ya creado. Tras retirar `POSTGRES_ROLE_SYNC_USER` de `.env`, se recreó únicamente PostgreSQL y se verificó `POSTGRES_ROLE_SYNC_USER=UNSET` dentro del contenedor, sin borrar el volumen.

## Portabilidad Linux — PASS

- `bash -n scripts/database/apply_migrations.sh scripts/database/sync_database_roles.sh`: PASS en Debian;
- PowerShell no es dependencia del host Linux;
- `apply_migrations.sh` post-remediación reconoció 001–017 como aplicadas y terminó sin error.

## Sanitización y rotación — PASS

`SELECT set_config('leadflow.bootstrap_password', ...)` reflejaba el valor por stdout. Se eliminó el GUC secreto y los `set_config` no secretos dejaron de emitir filas. La prueba canario, legacy repair y portabilidad Linux pasaron localmente; la ejecución posterior en VM no imprimió secretos.

La credencial observada se trató como expuesta. Se generó criptográficamente una nueva contraseña dentro de la VM, se actualizó `.env` sin mostrarla, se recreó PostgreSQL sin borrar volumen, se aplicó mediante la ruta Bash sanitizada y se verificó autenticación TCP: `BOOTSTRAP_AUTH=PASS`. La contraseña anterior quedó reemplazada.

## Runtime y smoke posterior — PASS

- seis servicios healthy: adapters, crm-mock, enrichment-mock, n8n, postgres y slack-mock;
- `GET /healthz`: HTTP 200;
- `scripts/test/test_n8n_mocks_integration.py`: PASS 10/10;
- persistencia, contacto/enrichment, update, campos omitidos, duplicate sin llamadas externas, convergencia de contacto y respuesta pública sanitizada: PASS;
- `git diff --check` final en VM: PASS.

## Cleanup — PASS

El test eliminó sus filas PostgreSQL. `crm-mock` no posee volumen persistente; se reinició de forma controlada para eliminar el contacto sintético en memoria y volvió healthy. La VM se detuvo al concluir.

## Clasificación final

### PASS SYSTEM

- guardas y reparación multisesión;
- instalación nueva y volumen heredado;
- atributos y ownership objetivo;
- migraciones históricas intactas;
- sanitización de salida;
- ruta Bash portable.

### PASS HYBRID

- separación material de roles y ownership, demostrada localmente y en VM;
- configuración runtime materializada tras recreación controlada;
- aplicación de credenciales mediante flujo sanitizado;
- runtime y smoke funcional post-remediación.

### PASS ENVIRONMENT

- remediación sobre el volumen real;
- health de los seis servicios y n8n HTTP 200;
- rotación y autenticación TCP del bootstrap;
- cleanup sintético y detención de VM.

### NOT_VERIFIED

`scripts/test/test_database_role_separation.py` no se ejecutó directamente desde la shell Debian porque requiere exportar cinco variables PostgreSQL, incluidas dos contraseñas. No se forzó `source .env` ni exportación manual. Esto no constituye FAIL: atributos, ownership, migraciones, autenticación y runtime fueron demostrados mediante consultas directas y smokes independientes.

### WARN / límites

- Los OID registrados pertenecen al volumen piloto y no son invariantes portables, salvo la condición especial demostrada del bootstrap histórico OID 10.
- No se generaliza el sizing de la VM piloto como mínimo productivo.
- Controles no incluidos en la evidencia de este cierre no se promueven implícitamente a PASS.

## Conocimiento y promoción

El registro específico de LeadFlow está en `docs/knowledge/IMPLEMENTATION_ISSUES_AND_SOLUTIONS.md`.

Los patrones reutilizables y descontextualizados fueron promovidos a:

`00_CORPORATIVO/CONOCIMIENTO/EMACTIVA_Implementation_Issues_and_Solutions.md`

## Criterio de cierre

LAB-LF-007 queda **CERRADO — PASS CON LÍMITES DOCUMENTADOS**. No quedan remediaciones técnicas abiertas del hallazgo PostgreSQL. La única modalidad NOT_VERIFIED es el test específico de shell descrito; no invalida la evidencia material del control.
