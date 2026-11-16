# LF-M03 — Manual de respaldo y recuperación

**Versión documental:** 1.0 · 16/11/2026. **Estado:** edición consolidada para aprobación del responsable. No autoriza exposición comercial.

## 1. Alcance, política y responsabilidades

El manual se dirige al administrador de infraestructura autorizado. Cubre respaldo cifrado de PostgreSQL y del volumen n8n, custodia independiente, restauración aislada y protección DSR. No cubre recuperación integral de una cuenta cloud perdida ni autoriza exposición comercial.

Política: frecuencia objetivo 24 horas; retención de backups 30 días y 7 días adicionales de soft delete en GCS. RPO objetivo 24 horas y RTO objetivo 8 horas; no son SLA ni mediciones continuas demostradas. La recuperabilidad potencial de 37 días debe considerarse en privacidad. El bucket aplica el lifecycle; no duplicar políticas de borrado.

Responsables: el operador de backup ejecuta y registra; el administrador de privacidad reconcilia la autoridad DSR; el restaurador lee artefactos específicos; el responsable del servicio aprueba ventanas, recuperación y retorno a tráfico. El propietario de infraestructura valida IAM, red, capacidad y continuidad. Separar aprobador y operador para DELETE/RESTRICT.

Regla de seguridad: ante configuración incompleta, permisos erróneos, pérdida de integridad, cobertura DSR insuficiente o estado ambiguo, detenerse. Nunca borrar volúmenes de origen, ampliar permisos por conveniencia ni repetir una restauración a ciegas.

Fuente técnica: docs/runbooks/BACKUP_RESTORE.md, config/backup-policy.json, scripts/backup/ y HANDOFF LAB-LF-015, base 5813007. Los valores de ejemplo no corresponden a credenciales ni infraestructura de clientes.

## 2. Preparación del respaldo y custodia

Requisitos del host: Linux, Bash, Docker y Compose, Python 3, Node.js 20+, GNU sha256sum, curl y gcloud. Revisar espacio, reloj, DNS, acceso al socket Docker (privilegio elevado), versiones aprobadas y ventana de operación. Confirmar un PostgreSQL y un n8n en el proyecto fuente y ownership del volumen /home/node/.n8n. No mostrar entornos de contenedores.

Configuración externa requerida: BACKUP_GCS_BUCKET, BACKUP_GCP_IDENTITY, BACKUP_KEY_FILE, POSTGRES_DB, POSTGRES_BOOTSTRAP_USER, BACKUP_COMPOSE_PROJECT, SOURCE_COMPOSE_PROJECT y BACKUP_COMPOSE_OVERRIDE (ruta absoluta). Los proyectos de backup y origen deben coincidir. Los directorios privados deben tener modo 0700; claves y configuración sensible 0600 o más restrictivo.

Identidades: runtime separado; backup con create-only para artefacto y checksum; escritor DSR create-only; administrador DSR con lectura/listado y creación controlada; restore con lectura de objetos específicos. Bucket DSR distinto del bucket de backups. Sin claves JSON descargadas ni fallback a credenciales locales.

En modo attached, metadata debe coincidir con BACKUP_GCP_IDENTITY. En modo impersonation, configurar también BACKUP_GCP_AUTH_MODE=impersonation y BACKUP_RUNTIME_GCP_IDENTITY distinta; validar IAM Credentials API, scope y permiso getAccessToken sobre la cuenta backup exacta. No ampliar acceso directo GCS de runtime.

Custodia: clave AES-256 de 32 bytes, externa al backup. Mantener versiones recuperables en custodia administrativa independiente (referencia: Bitwarden). No imprimir claves, tokens ni copiarlos a Git. Verificar recuperación de versiones previas antes de retirarlas.

## 3. Respaldo manual y programación

Antes de ejecutar: identificar proyecto y override exactos, seleccionar identidad autorizada, cargar configuración protegida y verificar que no hay otros escritores del volumen. Aprobar ventana de quiescencia; la pausa de n8n puede afectar recepción de leads.

```bash
bash scripts/backup/backup.sh
```

El script pausa n8n durante pg_dump y copia del volumen, reanuda mediante cleanup, cifra con AES-256-GCM y genera SHA-256 del artefacto cifrado. Transfiere artefacto y checksum sin sobrescritura. El límite de pausa por defecto es 1800 segundos y máximo 3600. No existe snapshot transaccional conjunto entre PostgreSQL y n8n.

Aceptar: salida PASS global, artefacto y checksum confirmados por el rol autorizado, servicio reanudado, ausencia de temporales y diagnóstico sanitizado. Ante fallo, comprobar primero que n8n se reanudó, conservar fase/error técnico y reconciliar objetos existentes antes de volver a generar. No conceder permisos de lectura al escritor para comprobarlos.

Programación: instalar el timer systemd de 24 h solo tras aprobar usuario, grupo, archivo externo y permisos. El instalador no lo activa. Definir `USUARIO_BACKUP` y `GRUPO_BACKUP` con el usuario y grupo existentes aprobados, y usar la ruta real del archivo protegido.

```bash
BACKUP_SERVICE_USER="$USUARIO_BACKUP" BACKUP_SERVICE_GROUP="$GRUPO_BACKUP" \
sudo -E bash scripts/backup/install_schedule.sh \
/ruta/absoluta/leadflow-backup.env
```

La habilitación del timer exige decisión externa. Confirmar ejecución real, última copia utilizable y alertas por antigüedad/fallo. La operación sostenida permanece NOT_VERIFIED; instalar un timer no acredita que se ejecute ni que sus copias sean recuperables.

## 4. Autoridad DSR y preparación de recuperación

Una restauración antigua puede reintroducir datos borrados o restringidos. La autoridad DSR independiente debe cubrir el instante del backup y las operaciones posteriores requeridas para restaurar con seguridad. No usar el propio backup como única fuente de supresión.

Producción usa production_prospective: acta inicial LF015-DSR-PRODUCTION-BASELINE-1, journal productivo, exportación v2 y manifiesto v2. Iniciar únicamente bajo ventana administrativa, con nuevas operaciones DSR bloqueadas, cuatro conteos confirmados en cero (solicitudes, tombstones, outbox y acciones proveedor pendientes) y sin cadena previa. Si no aplica esa condición, no improvisar baseline.

Publicar acta y snapshot cero inmutables en bucket DSR independiente antes del nuevo backup. No existe cobertura retroactiva. Para cada DELETE/RESTRICT posterior, confirmar publicación cifrada y registrar el evento en la autoridad. Antes del checkpoint reconciliar secuencias, objetos y pendientes reales en cero. El administrador emite exportación y manifiesto, y genera bundle cifrado con clave distinta de la de backup.

```bash
python3 scripts/backup/dsr_restore_evidence.py authority-manifest \
--admin-export /ruta/protegida/export.json \
--backup-manifest /ruta/protegida/manifest.json \
--output /ruta/protegida/authority.json
```

Usar el procedimiento completo de journal, checkpoint y bundle del runbook `docs/runbooks/BACKUP_RESTORE.md`, que forma parte del paquete técnico versionado; no reemplazarlo por un archivo generado manualmente. Un hash o una fecha no prueban completitud global. Si restore_protection_status es failed, staged o pending_confirmation, no declarar protección remota confirmada. El retry administrativo repite solo stage/publicación, no DSR ni CRM.

Conservar estado vigente de supresión mientras corresponda; la duración jurídica y el levantamiento de restricciones siguen pendientes. No aplicar un lifecycle único de 37 días a evidencia vigente ni rotar DSR_SUBJECT_KEY sin transición y QA.

## 5. Preflight y restauración aislada

Seleccionar backup y checksum por URI exacta, bundle DSR vigente e identidad restore de lectura separada. Confirmar que backup y bundle estén autenticados, que la autoridad cubra el instante del backup y que no existan huecos o pendientes. Mantener tráfico deshabilitado.

Crear configuración externa con SOURCE_COMPOSE_PROJECT, RESTORE_COMPOSE_PROJECT distinto, BACKUP_COMPOSE_OVERRIDE y RESTORE_COMPOSE_OVERRIDE absolutos y distintos, RESTORE_STATE_DIR durable 0700, LEADFLOW_RESTORE_ISOLATED=true, RESTORE_GCS_URI, DSR_EVIDENCE_URI, claves separadas, identidades y variables PostgreSQL aprobadas. Incluir DSR_AUTHORITY_EXPORT, DSR_BACKUP_MANIFEST, DSR_AUTHORITY_MANIFEST y LF015_DSR_AUTHORITY_MODE=production_prospective. Respetar límites RESTORE_MAX_* y DSR_EVIDENCE_MAX_BYTES. Usar override aislado de referencia y verificar ausencia de puertos publicados.

```bash
# Cargar únicamente archivo externo confiable y aprobado.
set -a; source /ruta/externa/restore.env; set +a
python3 scripts/backup/preflight_restore.py
```

RC 1: detener. RC 2: dependencia sin verificar; no avanzar mientras siga abierta. En la ejecución histórica solo se continuó después de acreditar independientemente el control IAM/GCS pendiente. El preflight no consulta IAM real ni inicia servicios. Verificar identidad/lectura y crear exclusivamente el destino autorizado conforme al runbook.

```bash
bash scripts/backup/restore.sh
```

El script valida tamaños, SHA-256, AES-GCM, estructura, manifest y evidencia DSR antes de modificar destino. Restaura PostgreSQL y volumen n8n; reaplica supresiones y verifica rechazo en claim_event. En fallo parcial deja RECOVERABLE_FAILURE y tráfico deshabilitado. Mantener estado durable, identificar última fase y reconciliar destino antes de cualquier reintento.

## 6. Validación, retorno y cleanup

Gate de restauración: exigir complete/PASS y traffic=DISABLED; comprobar migraciones y tablas esperadas para la versión entregada, integridad PostgreSQL, volumen y base interna n8n, workflow y credenciales recuperables, coincidencia de conteos DSR aplicado/verificado/bloqueado, red aislada y ausencia de efectos comerciales. No ejecutar workflow real como smoke test.

Revisar RPO observado (antigüedad de copia utilizable al incidente), tiempo de restauración técnica y tiempo total hasta servicio recuperado. Incluir detección, autorización, aprovisionamiento y validación al evaluar RTO integral. Un PASS técnico no autoriza activar tráfico; el responsable debe aprobar promoción, red, TLS, identidad y pruebas funcionales de destino por separado. Si falla un control, mantener aislamiento.

Cleanup de ensayo exclusivamente: capturar evidencia y verificar labels, proyecto destino y override exactos. Confirmar que no comparte volúmenes ni redes del origen. Solo con autorización de eliminación del destino de prueba:

```bash
docker compose -p "$RESTORE_COMPOSE_PROJECT" -f compose.yaml \
-f "$RESTORE_COMPOSE_OVERRIDE" down -v --remove-orphans
```

Nunca ejecutar con SOURCE_COMPOSE_PROJECT ni sobre el destino que se quiere conservar para recuperación. Revocar permisos temporales, eliminar archivos/credenciales locales autorizados, conservar artefactos cifrados y autoridad DSR. Verificar origen intacto, estado operacional y ausencia de recursos de ensayo residuales. No borrar buckets ni snapshots como parte de cleanup normal.

Registro: fecha UTC, versión, proyecto técnico, identificador de artefacto y hash, fase/estado, duración, resultado de verificación DSR, aprobación y cleanup. Sin emails, payloads, tokens o claves.

## 7. Evidencia y límites de aceptación

Evidencia histórica LF015: respaldo cifrado productivo controlado y restauración aislada el 15/11/2026; antigüedad de copia 1 h 35 min, restauración técnica 19 s, ventana de mantenimiento 17 min 20 s. 24 migraciones, 11 tablas, diez archivos n8n, un workflow y SQLite íntegro; replay DSR productivo vacío, estado complete/PASS y tráfico deshabilitado. Cleanup y restitución de identidad acreditados en el entorno observado.

PASS acotado: la ejecución demuestra recuperación técnica de ese artefacto con autoridad prospectiva y custodia separada. QA sintético anterior acredita replay DELETE/RESTRICT no vacío e idempotente; no equivale a replay productivo no vacío.

WARN / NOT_VERIFIED: operación automática sostenida, RPO/RTO integrales continuos, pérdida total de infraestructura, consistencia integral bajo escrituras concurrentes, cobertura histórica anterior al baseline, replay productivo no vacío, autenticidad/completitud sostenida de autoridad DSR, rotación de claves HMAC y condiciones IAM de un cliente nuevo. No promover a PASS por extrapolación.

Checklist antes de aceptación de un cliente:

- Identidades y custodia independiente verificadas.
- Backup reciente, cifrado y recuperable, checksum confirmado.
- Autoridad DSR independiente y vigente; evidencia sin pendientes.
- Restore aislado sin FAIL; tráfico deshabilitado hasta aprobación.
- RPO y RTO medidos con alcance documentado.
- Cleanup, revocación y salud del origen comprobados.
- Responsables, alertas y seguimiento de pendientes definidos.

Clasificación: SYSTEM para validaciones y scripts; HYBRID para reconciliación, cobertura y recuperación coordinada; ENVIRONMENT para IAM, capacidad, red, lifecycle y ejecución sostenida. Esta edición no acredita una instalación nueva.
