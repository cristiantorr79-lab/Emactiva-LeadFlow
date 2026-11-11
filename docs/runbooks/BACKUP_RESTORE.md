# Backup y restore portable

## Contrato y límites

`config/backup-policy.json` exige una ejecución cada 24 horas, 30 días de retención, RPO objetivo de 24 h y RTO objetivo de 8 h. Los dos objetivos permanecen `NOT_VERIFIED` hasta una prueba real del entorno. El bucket y las identidades se entregan por entorno; no se fija proyecto, dominio ni credencial en Git.

Google Cloud aplica la retención de 30 días mediante la política de ciclo de vida del bucket: estos scripts no la duplican. Además, la eliminación no definitiva conserva el objeto 7 días adicionales. Por ello una copia puede seguir recuperable hasta 37 días y una solicitud DSR debe considerar esa ventana, mantener/reaplicar tombstones y no declarar destrucción física antes de que concluya.

## Dependencias y secretos

Host Linux: Bash, Docker con Compose, Python 3, Node.js 20 o posterior, GNU `sha256sum`, `curl` y Google Cloud CLI. El cifrado usa únicamente `node:crypto`, sin paquetes descargables. La VM usa la identidad `default` publicada por el servicio de metadata de Compute Engine. Los scripts comparan ese email con la identidad esperada y ejecutan gcloud con un `CLOUDSDK_CONFIG` temporal vacío; rechazan claves JSON, overrides de credenciales y overrides del endpoint de metadata. No se consultan ni registran access tokens.

La clave AES-256 se monta como archivo externo de 32 bytes (raw, hexadecimal o base64), con permisos `0600` o más restrictivos, y su ruta se entrega en `BACKUP_KEY_FILE`. Nunca imprimirla, copiarla al artefacto ni incluirla en el archivo de entorno. `BACKUP_GCP_IDENTITY` debe coincidir exactamente con la identidad `default` de metadata. El rol de backup solo crea objetos y no debe leerlos.

### Custodia y recuperación de credenciales

- Bitwarden es la custodia administrativa de recuperación: guarda copias controladas de claves y datos de recuperación, con acceso administrativo separado; no se usa como sustituto de la identidad runtime ni se copian secretos al repositorio, logs o artefactos.
- Desarrollo local usa archivos de secretos fuera de Git, separados del archivo de configuración, con directorios `0700` y archivos `0400`/`0600`. Solo se usan valores sintéticos.
- Producción obtiene secretos desde el gestor de secretos del entorno y los monta como archivos de mínimo privilegio. Backup, escritor DSR, administrador de evidencia y restore mantienen identidades independientes; no se usan claves JSON ni se amplían permisos de `leadflow-backup`.
- La configuración sigue siendo portable: entorno y rutas de archivos suministran bucket, identidades y secretos; ningún proyecto, dominio o valor secreto queda hardcodeado.
- Rotar inmediatamente tras exposición, pérdida de custodia o cambio de responsables, y de forma planificada según la política administrativa. Conservar en custodia las versiones necesarias para descifrar backups durante toda su ventana recuperable de 30+7 días y evidencia DSR aún vigente; retirar una versión solo después de probar recuperación y confirmar que ningún artefacto retenido depende de ella. La recuperación exige restaurar el archivo con permisos restrictivos, comprobar su correspondencia externa con el periodo del artefacto y registrar la prueba sin revelar el valor.

## Backup manual

Configurar `BACKUP_GCS_BUCKET=gs://<bucket>`, `BACKUP_GCP_IDENTITY`, `BACKUP_KEY_FILE`, `POSTGRES_DB`, `POSTGRES_BOOTSTRAP_USER`, `BACKUP_COMPOSE_PROJECT`, `SOURCE_COMPOSE_PROJECT` y `BACKUP_COMPOSE_OVERRIDE` absoluto. Los dos nombres de proyecto deben coincidir; no existe fallback a `leadflow`. El script exige el override y verifica que exactamente un PostgreSQL y un n8n pertenezcan mediante labels al proyecto autorizado, y que `/home/node/.n8n` sea un volumen etiquetado para ese mismo proyecto. Ejecutar `bash scripts/backup/backup.sh` desde Linux.

Las fases son independientes y fallan cerrado:

1. `generate`: pausa controlada de n8n antes de `pg_dump --format=custom`, mantiene la pausa hasta copiar el volumen y garantiza reanudación inmediata o desde el trap de cleanup.
2. `encrypt`: envelope AES-256-GCM autenticado con nonce aleatorio; SHA-256 del cifrado; eliminación de todo temporal en el trap.
3. `transfer`: `gcloud storage cp --no-clobber` del artefacto y checksum. Un nombre UTC más nonce evita colisión; nunca se sobrescribe una copia válida.

Los mensajes contienen solo fase, estado y nombre técnico. Un fallo de generación, cifrado, identidad, permisos, transferencia o cleanup produce salida distinta de cero y nunca `PASS` global.

La pausa impide que n8n escriba durante el dump lógico y la copia del volumen. `BACKUP_PAUSE_TIMEOUT_SECONDS` limita toda la ventana a 1800 segundos por defecto y como máximo 3600; timeout/fallo ejecuta el trap de reanudación. El conjunto es recuperable bajo el supuesto operativo de que n8n es el único escritor aplicativo y de que no existen otros procesos escribiendo su volumen. `pg_dump` conserva una instantánea consistente de PostgreSQL, pero PostgreSQL y el volumen no comparten una transacción ni un snapshot atómico: esto es una ventana de quiescencia coordinada, no consistencia integral demostrada. La prueba real debe cubrir escrituras concurrentes, duración de pausa y recuperación de workflows/credenciales.

## Programación no activada

`BACKUP_SERVICE_USER=... BACKUP_SERVICE_GROUP=... sudo -E bash scripts/backup/install_schedule.sh /ruta/absoluta/leadflow-backup.env` instala idempotentemente un timer systemd de 24 horas, pero no lo habilita. Usuario y grupo deben existir y poder leer la clave externa y acceder al socket Docker; este último acceso equivale materialmente a privilegios elevados y debe aprobarse en el entorno. El archivo de entorno debe ser modo `0400` o `0600`. La unidad fija PATH, umask y hardening básico de systemd. Activarla requiere una decisión externa. No añadir otra regla de retención.

## Restore aislado

La cuenta de restore/lectura debe ser distinta de `BACKUP_GCP_IDENTITY`; no se amplían permisos de `leadflow-backup`. Preparar un proyecto Compose aislado, sin frontera pública ni puertos publicados, con un override absoluto dedicado. `RESTORE_COMPOSE_PROJECT` debe diferir del proyecto origen. El script verifica labels Compose, servicios target y que `/home/node/.n8n` sea un volumen propio del proyecto aislado.

## Evidencia DSR independiente

La migración `024_dsr_restore_evidence.sql` reutiliza `dsr_tombstones`. `prepare_dsr_restore_evidence` garantiza un tombstone también para DELETE/RESTRICT `not_found` y devuelve únicamente `subject_token` HMAC, disposición y timestamp efectivo. DELETE es terminal frente a RESTRICT. No se exportan email, nombre, teléfono, operador, payload ni datos CRM.

La migración también crea `dsr_restore_evidence_outbox`. La preparación del tombstone y del registro mínimo pendiente ocurre dentro de la misma transacción PostgreSQL. `dsr_admin.py` cifra cada evento con una clave dedicada y lo deposita en `DSR_EVIDENCE_SPOOL_DIR`, que debe ser un volumen/directorio durable independiente de PostgreSQL, n8n y sus backups, modo `0700`. El nombre es SHA-256 del registro canónico y la creación es exclusiva; repetir el mismo evento verifica el cifrado existente y no crea duplicados. Cada intento actualiza el outbox sin almacenar PII. El resultado administrativo añade `restore_protection_status`:

- `failed`: el cifrado o la publicación no terminó; el registro transaccional permanece recuperable en PostgreSQL, pero todavía no protege frente a restaurar una copia anterior;
- `staged`: conservado localmente, aún no publicado;
- `pending_confirmation`: el escritor intentó la publicación inmutable, pero sin lectura/listado no puede confirmar preservación remota;
- no existe estado `protected` en este flujo: solo el proceso administrativo separado que lee, autentica y consolida eventos puede confirmar cobertura.

La publicación opcional usa `DSR_EVIDENCE_WRITER_IDENTITY`, `DSR_EVIDENCE_GCS_PREFIX` y `--no-clobber`; cada objeto es inmutable y content-addressed. El escritor no necesita ni presume lectura, listado o eliminación. Un fallo conserva el registro pendiente y produce `restore_protection_status=failed`; no altera silenciosamente el resultado DSR histórico. Para recuperarlo, enviar únicamente `{"request_id":"..."}` a `scripts/admin/retry_dsr_restore_protection.py` con la configuración administrativa normal. El comando lee `get_dsr_restore_evidence`, repite solo stage/publicación idempotentes y nunca invoca `execute_dsr_request` ni el adaptador CRM. Los consumidores deben evaluar este campo por separado de `status`.

Una identidad administrativa distinta, con lectura autorizada, debe obtener de la fuente autoritativa un manifiesto `LF015-DSR-AUTHORITY-1`: identificador técnico de exportación, secuencia alta completa, instante cubierto y lista/digest exactos de IDs de evidencia. Después descarga y autentica exactamente esos eventos, los coloca en un directorio `0700` y ejecuta `dsr_restore_evidence.py bundle --events-dir ... --output-dir ... --authority-manifest ...`. El bundle v2 se rechaza si falta un ID, sobra uno o divergen orden, conteo o digest. Bundle y checksum son content-addressed, cifrados con AES-256-GCM y no se sobrescriben.

Para QA sintético, `dsr_qa_authority.py` mantiene snapshots inmutables `LF015-DSR-QA-JOURNAL-1` fuera del checkout, del backup y del destino restaurado. El snapshot inicial fija `coverage_started_at_utc` y secuencia cero; cada transición incrementa `snapshot_sequence` y encadena el SHA-256 del snapshot anterior. Solo `record` incorpora un artefacto DELETE/RESTRICT ya cifrado, autenticado y confirmado desde la publicación real del escritor; no construye eventos. `checkpoint` exige cero publicaciones pendientes y cobertura posterior a todos los eventos. `export` entrega `LF015-DSR-ADMIN-EXPORT-1`, sin subject tokens ni PII.

El inicio no acredita historia anterior. Un backup anterior a `coverage_started_at_utc` queda bloqueado aunque el registro tenga cero eventos; primero se inicializa la autoridad y después se crea un backup nuevo. Generar el manifiesto exclusivamente mediante:

```bash
python3 scripts/backup/dsr_restore_evidence.py authority-manifest \
  --admin-export /ruta/administrativa/export.json \
  --backup-manifest /ruta/protegida/manifest.json \
  --output /ruta/protegida/authority.json
```

El comando admite cero eventos únicamente con high-water mark 0 y conjunto vacío; rechaza huecos, secuencia alta divergente, pendientes, IDs duplicados, orden no determinista, backup anterior al inicio o posterior al checkpoint y cobertura anterior a un evento. `bundle` vuelve a exigir correspondencia exacta entre manifiesto y evidencia cifrada. El preflight requiere también `DSR_BACKUP_MANIFEST`, fuera del repositorio, y compara el manifiesto byte-semánticamente con la exportación para ese backup. Esto demuestra coherencia del conjunto QA, no autenticidad/procedencia ni cobertura global productiva.

### Operación agrupada de la autoridad QA en Cloud Shell

Ejecutar con identidad administrativa DSR explícitamente comprobada, nunca con `leadflow-backup`, el escritor ni el restaurador. `DSR_BUCKET` apunta al bucket DSR existente; los snapshots se conservan por secuencia y `--no-clobber`. Cloud Shell es solo el contexto administrativo temporal: la fuente durable es la cadena inmutable del bucket.

```bash
set -Eeuo pipefail
umask 077
export DSR_BUCKET='gs://<bucket-dsr-existente>/qa-authority'
export SOURCE_ID='lf015-qa-admin-journal'
export WORK_DIR="$(mktemp -d)"
chmod 700 "$WORK_DIR"
STARTED="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
python3 scripts/backup/dsr_qa_authority.py init --source-system-id "$SOURCE_ID" --coverage-started-at "$STARTED" --output "$WORK_DIR/journal-000000.json"
gcloud storage cp --no-clobber "$WORK_DIR/journal-000000.json" "$DSR_BUCKET/journals/journal-000000.json"
```

Solo después de ese PASS se crea un backup nuevo. Por cada DELETE/RESTRICT sintético posterior, el escritor publica el artefacto cifrado content-addressed con su identidad create-only. El administrador descarga por URI exacta ese artefacto confirmado, recupera el último snapshot, comprueba que sea la secuencia más alta esperada y ejecuta `record`; publica el siguiente snapshot con `--no-clobber`. Un conflicto, hueco, objeto ausente o fallo de autenticación detiene el flujo; no se reconstruye el evento manualmente.

```bash
python3 scripts/backup/dsr_qa_authority.py record --journal "$WORK_DIR/journal-000000.json" --artifact "$WORK_DIR/<evidence-id>.dsr.gcm" --key-file "$DSR_EVIDENCE_KEY_FILE" --output "$WORK_DIR/journal-000001.json"
gcloud storage cp --no-clobber "$WORK_DIR/journal-000001.json" "$DSR_BUCKET/journals/journal-000001.json"
# Repetir secuencialmente solo para publicaciones confirmadas reales.
python3 scripts/backup/dsr_qa_authority.py checkpoint --journal "$WORK_DIR/journal-<ultima>.json" --covered-through "$(date -u +%Y-%m-%dT%H:%M:%SZ)" --pending-count 0 --output "$WORK_DIR/journal-<siguiente>.json"
gcloud storage cp --no-clobber "$WORK_DIR/journal-<siguiente>.json" "$DSR_BUCKET/journals/journal-<siguiente>.json"
python3 scripts/backup/dsr_qa_authority.py export --journal "$WORK_DIR/journal-<siguiente>.json" --authority-export-id "lf015-qa-$(date -u +%Y%m%dT%H%M%SZ)" --output "$WORK_DIR/admin-export.json"
python3 scripts/backup/dsr_restore_evidence.py authority-manifest --admin-export "$WORK_DIR/admin-export.json" --backup-manifest "$BACKUP_MANIFEST" --output "$WORK_DIR/authority.json"
```

Antes del checkpoint, el administrador reconcilia con la fuente operativa que el outbox pendiente sea cero y que todos los objetos esperados estén publicados; `--pending-count 0` es una declaración operativa, no una consulta automática. Publicar exportación/manifiesto/bundle con la identidad administrativa y precondición de no sobrescritura. Restore usa identidad read-only separada. Al terminar, borrar solo `WORK_DIR`; no borrar snapshots ni evidencia del bucket. IAM efectivo, listado/reconciliación, lifecycle y autenticidad del origen permanecen ENVIRONMENT `NOT_VERIFIED` hasta la ejecución real.

Este control SYSTEM demuestra que bundle y manifiesto coinciden; una fecha, hash, secuencia o URI aportados manualmente no demuestran actualidad global. La producción íntegra del manifiesto desde una autoridad administrativa independiente y su custodia son HYBRID/ENVIRONMENT y permanecen `NOT_VERIFIED`. Sin ese manifiesto el bundle no se crea y restore falla cerrado.

Restore recibe por URI explícita el bundle administrativo más reciente, sin depender de listado. La cuenta de restore es distinta del escritor y del administrador. La clave DSR debe ser distinta de `BACKUP_KEY_FILE`. El bundle nunca se incluye como única fuente dentro del propio backup.

Además de `LEADFLOW_RESTORE_ISOLATED=true`, `RESTORE_GCS_URI`, `DSR_EVIDENCE_URI`, identidades, ambas claves y variables PostgreSQL, se requieren:

- `RESTORE_STATE_DIR`: directorio absoluto, escribible y modo `0700`, fuera de temporales;
- límites de artefacto, total extraído, miembro y entradas (`RESTORE_MAX_*`), con defaults conservadores y techos fail-closed;
- `DSR_EVIDENCE_MAX_BYTES`: límite del bundle administrativo cifrado;
- `SOURCE_COMPOSE_PROJECT` y un proyecto/override de restore independiente.

Si el bundle falta, fue alterado, no coincide exactamente con el manifiesto autoritativo, su cobertura es anterior al backup, contiene duplicados o un evento inválido, el restore se bloquea antes de modificar el destino. El replay usa `leadflow.replay_dsr_restore_evidence(jsonb)`, que aplica eventos idempotentemente y conserva DELETE como disposición más fuerte. En la misma sentencia, `verify_dsr_restore_enforcement` llama al punto real `claim_event` para cada token DELETE/RESTRICT y exige el rechazo `42501`; cualquier aceptación aborta y revierte la sentencia. Tokens y SQL viajan por archivos/stdin temporales `0600`, no por argv ni logs.

Antes de ejecutar `bash scripts/backup/restore.sh`, exportar al proceso las variables requeridas del archivo externo protegido; que una variable exista en `.env` no garantiza que Bash la exporte a procesos hijos. Usar el mecanismo controlado del entorno (por ejemplo, `set -a; source /ruta/externa/restore.env; set +a`) y comprobar solo presencia, nunca imprimir valores. Antes de modificar el destino, el flujo verifica aislamiento, identidad administrada, tamaño remoto/local, SHA-256, autenticidad AES-GCM del backup y del bundle DSR, cobertura autoritativa posterior al backup, identidad del manifest, estructura n8n no vacía y catálogo legible de `pg_restore`. Solo acepta manifest, `postgres.dump` y `n8n/`; rechaza rutas peligrosas, enlaces, tipos especiales, duplicados, entradas inesperadas y límites excedidos.

Después crea un estado durable `PREPARED`, detiene n8n, restaura PostgreSQL y repone directamente el volumen verificado mediante un contenedor sin red y root filesystem read-only. Luego reaplica el bundle y exige que los conteos aplicado, verificado y bloqueado por `claim_event` coincidan con todos los eventos. Un fallo parcial mantiene n8n/tráfico deshabilitados y deja `RECOVERABLE_FAILURE`; nunca imprime PASS. Ante ese estado, conservar el recibo y los logs técnicos, mantener el tráfico deshabilitado e identificar la última fase completada. No repetir restore hasta verificar el estado durable y la integridad/ownership del destino; corregir la causa y reintentar controladamente solo cuando sea seguro hacerlo. El intento fallido y el reintento deben permanecer trazables por separado.

Incluso con `restore status=PASS`, el resultado conserva `traffic=DISABLED`. PASS solo indica que las fases técnicas y los recibos externos pasaron; no autoriza tráfico. Antes de habilitarlo, revisar el estado durable, migraciones, healthchecks, integridad sintética PostgreSQL/n8n, evidencia DSR y medición RPO/RTO. Si cualquier control falla, mantener el entorno bloqueado y seguir el estado recuperable; nunca promoverlo.

QA integrado LF015: PostgreSQL 17.6 confirmó replay real `2|2|2`, repetición idempotente `2|2|2` y rechazos DELETE/RESTRICT con SQLSTATE `42501`. La prueba detectó que CTE independientes podían evaluar enforcement antes del replay; `emit-sql` ahora materializa `replay` y hace que la verificación dependa de su resultado. El outbox pasó `pending|0` → `failed` → `staged` → `pending_confirmation|3`; todo se ejecutó en transacción y el control posterior a `ROLLBACK` devolvió `0|0|0`. Esto no valida restore integral, autoridad administrativa real ni GCP.

## Prueba integral controlada preparada

### Preflight agrupado no destructivo

El override reutilizable `labs/LAB-LF-015/restore-isolated.override.yaml` elimina puertos y conecta PostgreSQL/n8n únicamente a una red interna project-scoped. No contiene secretos ni rutas de VM. Usarlo con un `RESTORE_COMPOSE_PROJECT` nuevo y distinto de `SOURCE_COMPOSE_PROJECT`; Compose asigna nombres exclusivos a redes y volúmenes mediante el proyecto.

Antes de crear el destino, cargar desde archivos externos las variables de restore y definir `BACKUP_COMPOSE_OVERRIDE`, `RESTORE_COMPOSE_OVERRIDE` con rutas absolutas distintas, `RESTORE_STATE_DIR` existente modo `0700`, claves distintas modo restrictivo, cuatro identidades distintas, URIs exactas y `DSR_AUTHORITY_MANIFEST`. Ejecutar:

```bash
python3 scripts/backup/preflight_restore.py
```

El comando solo ejecuta `docker compose config`, inspecciona metadatos locales de archivos/directorios y valida estructura; no inicia/detiene contenedores, no descarga objetos, no consulta metadata/IAM, no crea recursos y no revela valores. `FAIL` retorna 1; cualquier dependencia `NOT_VERIFIED` retorna 2 y bloquea restore. Requiere `DSR_AUTHORITY_EXPORT` y `DSR_BACKUP_MANIFEST` fuera del repositorio, y comprueba que la exportación corresponda exactamente con `DSR_AUTHORITY_MANIFEST` y cubra ese backup. `LF015_DSR_AUTHORITY_MODE=synthetic_closed_set` identifica únicamente una prueba de conjunto sintético cerrado y produce WARN: nunca acredita cobertura administrativa global. Sin fuente administrativa definida, secuencia alta reconciliada y bundle independiente autenticado, la autoridad real permanece `NOT_VERIFIED` aunque PostgreSQL local tenga cero solicitudes.

Tras un preflight sin FAIL, un operador autorizado puede crear solo el proyecto destino y ejecutar posteriormente restore. El cleanup se limita al destino, después de capturar evidencia y comprobar exactamente `RESTORE_COMPOSE_PROJECT` y su override:

```bash
docker compose -p "$RESTORE_COMPOSE_PROJECT" -f compose.yaml -f "$RESTORE_COMPOSE_OVERRIDE" down -v --remove-orphans
```

Nunca ejecutar ese cleanup con `SOURCE_COMPOSE_PROJECT`, `lf015-qa` ni un override de origen.

En la preparación original esta prueba aún no se había ejecutado. La ejecución QA aislada del 2026-11-10 aplicó temporalmente la identidad de restore, mantuvo el tráfico deshabilitado y devolvió la VM a su identidad de backup; esta evidencia no aprueba el patrón para operación comercial. Los scripts exigen identidades runtime distintas y ninguna credencial JSON descargada.

La operación habitual no debe reiniciar ni cambiar repetidamente la identidad de la VM comercial. Para desarrollo se aprobó que la VM tenga `leadflow-runtime` adjunta y que solo la ruta invocada explícitamente por `backup.sh`, con `BACKUP_GCP_AUTH_MODE=impersonation`, obtenga desde metadata el token inicial y solicite a IAM Credentials un token temporal de `leadflow-backup`. El modo histórico `attached` sigue siendo el predeterminado y exige que metadata coincida con `BACKUP_GCP_IDENTITY`; no existe fallback entre modos, a ADC local ni a claves JSON. Escritor DSR, administrador y restore conservan sus identidades y contratos separados.

En impersonación deben definirse `BACKUP_RUNTIME_GCP_IDENTITY` y `BACKUP_GCP_IDENTITY` como cuentas válidas y distintas. `backup.sh` exige que metadata coincida con la primera; el uploader llama `generateAccessToken` para la segunda y utiliza ese token solo en las sesiones GCS del artefacto cifrado y su checksum. Tokens y respuestas de autenticación no se guardan ni se imprimen. `ifGenerationMatch=0`, streaming y create-only permanecen sin cambios. IAM Credentials deshabilitada, metadata inválida, scope insuficiente, permiso ausente, timeout o respuesta malformada producen FAIL sin fallback.

### Arquitectura IAM y almacenamiento del piloto

Se reutilizan el proyecto `emactiva-leadflow-pilot`, la VM `leadflow-pilot-01`, el bucket `emactiva-leadflow-pilot-backups` exclusivamente para backups y `leadflow-backup@emactiva-leadflow-pilot.iam.gserviceaccount.com` exclusivamente como identidad de backup. No ampliar sus permisos ni reutilizarla para DSR o restore.

Faltan tres cuentas de servicio y un bucket DSR configurable:

| Identidad | Uso único | Permiso de datos mínimo |
|---|---|---|
| `leadflow-runtime@emactiva-leadflow-pilot.iam.gserviceaccount.com` | Identidad principal de la VM de desarrollo | Sin acceso al bucket de backups; `iam.serviceAccounts.getAccessToken` exclusivamente sobre `leadflow-backup`. |
| `leadflow-backup@emactiva-leadflow-pilot.iam.gserviceaccount.com` | Crear backup y checksum | `storage.objects.create` en el bucket de backups; sin get/list/update/delete. |
| `<leadflow-dsr-writer@...>` | Publicar eventos DSR cifrados | `storage.objects.create` limitado al prefijo de eventos del bucket DSR; sin get/list/update/delete. |
| `<leadflow-dsr-admin@...>` | Enumerar/autenticar eventos y publicar bundles | get/list de eventos y create en el prefijo de bundles del bucket DSR; sin update/delete. |
| `<leadflow-restore@...>` | Leer backup, checksums y bundle indicado | rol personalizado con `storage.objects.get` condicionado a los prefijos de backup y bundles; sin create/list/update/delete. |

Para este modo, IAM Service Account Credentials API (`iamcredentials.googleapis.com`) debe estar habilitada; la VM debe estar adjunta a `leadflow-runtime` con scope OAuth `cloud-platform`; y esa identidad debe recibir `iam.serviceAccounts.getAccessToken` sobre el recurso exacto `leadflow-backup`, no a nivel amplio. Si se usa `roles/iam.serviceAccountTokenCreator`, vincularlo únicamente sobre esa cuenta y aceptar explícitamente que contiene permisos adicionales; el mínimo estricto es un rol personalizado con solo `iam.serviceAccounts.getAccessToken`. `leadflow-backup` conserva en el bucket exclusivamente `storage.objects.create` —por ejemplo, `roles/storage.objectCreator` limitado al bucket— sin get/list/update/delete. No crear claves administradas por usuario.

Secuencia futura GCP, todavía `NOT_VERIFIED`: habilitar IAM Credentials API; confirmar scope `cloud-platform`; adjuntar `leadflow-runtime`; aplicar el binding estrecho sobre `leadflow-backup`; verificar IAM efectivo y ausencia de acceso GCS directo del runtime; configurar las tres variables anteriores fuera de Git; y ejecutar una prueba sintética observando solo estados sanitizados. Compartir VM y metadata no aporta aislamiento fuerte entre procesos: el usuario del servicio backup, permisos de ejecución/lectura, acceso al socket Docker, firewall local y acceso al metadata server requieren hardening y validación ENVIRONMENT. Nada de esta preparación autoriza deployment ni tráfico real.

La evidencia DSR debe residir en un bucket diferente. Compartir `emactiva-leadflow-pilot-backups` acoplaría lifecycle, fallo administrativo, listado y permisos de dos custodias; además debilitaría la independencia requerida frente al backup restaurado. El bucket DSR debe tener uniform bucket-level access, public access prevention, no-overwrite y sin permisos update/delete para las identidades runtime. Su lifecycle es propio y no duplica el lifecycle del bucket existente. Un retention lock irreversible queda `NOT_VERIFIED` hasta validar política y cleanup del piloto.

Hay dos clases de conservación distintas:

- Evidencia histórica/auditable: eventos y bundles ya sustituidos se conservan al menos durante toda la recuperabilidad del backup relacionado; 37 días es el mínimo técnico actual, no una garantía de bloqueo permanente.
- Estado vigente de supresión: el conjunto mínimo cifrado de `subject_token` HMAC + disposición DELETE/RESTRICT debe permanecer disponible mientras el bloqueo siga vigente. La autoridad administrativa emite snapshots/bundles inmutables sucesivos del conjunto activo; restore consume uno cuya cobertura sea posterior al backup. Al sustituir un snapshot, el anterior conserva la ventana mínima necesaria para restaurar cualquier backup aún recuperable.

No se aprueba retención indefinida por defecto. Privacidad debe definir base jurídica, duración y eventual levantamiento de RESTRICT/DELETE; infraestructura debe definir lifecycle por prefijo/clase, custodia de claves y continuidad del snapshot activo. Hasta esas decisiones, eliminar evidencia activa o aplicar un lifecycle único de 37 días falla cerrado y la restauración permanece bloqueada. El mecanismo reutiliza bundles cifrados y minimizados existentes; no añade email, teléfono, nombre ni payload ni modifica el Core.

Los `subject_token` dependen del namespace/clave HMAC administrativa. Rotar `DSR_SUBJECT_KEY` sin una migración de tokens haría que nuevos claims no coincidan con tombstones anteriores. El Core actual no implementa dual-key ni retokenización; por tanto esa rotación queda bloqueada hasta una decisión de privacidad, diseño de migración y QA específica. Esto no impide rotar las claves AES de backup/evidencia conservando sus versiones durante la ventana recuperable.

La completitud global del manifiesto sigue siendo HYBRID: el administrador debe reconciliar el listado autenticado de eventos con una fuente administrativa autoritativa y su high-water mark. El bucket, una fecha o un hash no sustituyen esa autoridad. Para la prueba sintética se acepta únicamente el conjunto cerrado de dos eventos identificado por el `RUN_ID`; esto no demuestra completitud productiva.

Compartir VM no autoriza compartir secretos: cada fase usa un usuario/directorio `0700`, monta solo sus secretos desde el gestor, desmonta y elimina temporales antes de detener la VM. Solo cruzan fases los artefactos cifrados, nombres técnicos, mediciones y volúmenes sintéticos expresamente requeridos. Antes de cada cambio se comprueba que no quedan tokens, `CLOUDSDK_CONFIG`, archivos de entorno o claves de la identidad anterior. El acceso root del operador y el impacto de detener `leadflow-pilot-01` son riesgos ENVIRONMENT y requieren ventana de mantenimiento aprobada.

Prerrequisitos exactos:

1. Host Linux con Bash, Docker Engine/Compose, Python 3, Node.js 20+, GNU coreutils, `curl`, `tar`, `timeout` y gcloud; checkout exacto de la rama aprobada.
2. Bucket de backups existente con su lifecycle único y un bucket DSR separado. Evidencia histórica: mínimo técnico de 37 días; snapshot de bloqueos vigentes: conservar mientras la autoridad lo marque activo y luego durante la ventana de backups todavía recuperables. La política final de privacidad/lifecycle está pendiente.
3. `BACKUP_KEY_FILE` y `DSR_EVIDENCE_KEY_FILE` diferentes, externos a Git y modo `0400`/`0600`; spool DSR y `RESTORE_STATE_DIR` independientes, modo `0700`.
4. Dos proyectos Compose únicos, por ejemplo `lf015-src-<run-id>` y `lf015-restore-<run-id>`, y un override absoluto externo a Git. El override elimina puertos, inicia solo `postgres`/`n8n`, reemplaza dependencias ajenas y conecta ambos a una red `internal` propia del proyecto. No reutilizar redes, volúmenes ni nombres de una instalación existente.
5. Variables PostgreSQL sintéticas con bootstrap/migrator/app distintos, secretos sintéticos de n8n y LeadFlow, `SOURCE_COMPOSE_PROJECT`, `RESTORE_COMPOSE_PROJECT`, `BACKUP_COMPOSE_OVERRIDE`, `RESTORE_COMPOSE_OVERRIDE`, límites de restore e identidades exactas. El host restore debe definir `LEADFLOW_RESTORE_ISOLATED=true`.
6. Manifiesto `LF015-DSR-AUTHORITY-1` emitido por la autoridad administrativa para el conjunto posterior al backup; para esta prueba sus eventos son sintéticos, pero su producción no se reemplaza por una fecha/hash/URI manual.

Override mínimo que el operador debe crear fuera del repositorio y revisar antes de iniciar:

```yaml
services:
  postgres:
    ports: !reset []
    networks: [lf015_internal]
  n8n:
    ports: !reset []
    networks: [lf015_internal]
    depends_on: !reset
      postgres:
        condition: service_healthy
networks:
  lf015_internal:
    internal: true
```

La red se crea con nombre project-scoped por Compose: PostgreSQL y n8n pueden resolver sus nombres y comunicarse entre sí, no publica puertos y no se conecta a redes de contenedores existentes. El patrón `!reset` ya se usa en `compose.production.yaml`; antes de crear recursos, `docker compose ... config` debe aceptar el override y mostrar únicamente la red interna en ambos servicios, cero puertos y solo la dependencia PostgreSQL. `backup.sh` y `restore.sh` reciben el mismo archivo mediante sus variables de override y son compatibles con esta topología; la validación runtime permanece `NOT_VERIFIED`.

Secuencia reproducible de ejecución posterior (`<...>` son valores externos, no comandos literales):

```bash
set -Eeuo pipefail
umask 077
export RUN_ID='<utc-id>'
export BACKUP_COMPOSE_PROJECT="lf015-src-$RUN_ID"
export SOURCE_COMPOSE_PROJECT="$BACKUP_COMPOSE_PROJECT"
export BACKUP_COMPOSE_OVERRIDE='/ruta/absoluta/lf015-isolated.override.yaml'
set -a; source /ruta/externa/lf015-source.env; set +a

docker compose -p "$SOURCE_COMPOSE_PROJECT" -f compose.yaml -f "$BACKUP_COMPOSE_OVERRIDE" config >/dev/null
docker compose -p "$SOURCE_COMPOSE_PROJECT" -f compose.yaml -f "$BACKUP_COMPOSE_OVERRIDE" up -d postgres n8n
bash scripts/database/apply_migrations.sh
export LF015_QA_COMPOSE_PROJECT="$SOURCE_COMPOSE_PROJECT"
export LF015_QA_AUTHORIZED_PROJECT="$SOURCE_COMPOSE_PROJECT"
export LF015_QA_COMPOSE_OVERRIDE="$BACKUP_COMPOSE_OVERRIDE"
export RUN_ID="lf015-$(date -u +%Y%m%dT%H%M%SZ)-$(python3 -c 'import secrets; print(secrets.token_hex(4))')"
PROBE_RESULT="$(bash scripts/backup/qa_restore_probe.sh prepare "$RUN_ID")"
N8N_PROBE_SHA256="${PROBE_RESULT#*n8n_sha256=}"; N8N_PROBE_SHA256="${N8N_PROBE_SHA256%% *}"
BACKUP_STARTED="$(date +%s)"
BACKUP_RESULT="$(bash scripts/backup/backup.sh)"
BACKUP_SECONDS="$(( $(date +%s)-BACKUP_STARTED ))"
printf '%s\nbackup_seconds=%s\n' "$BACKUP_RESULT" "$BACKUP_SECONDS"
```

Registrar solo el nombre técnico devuelto por backup, `N8N_PROBE_SHA256` y construir `RESTORE_GCS_URI`; no registrar claves ni variables completas. Después del backup, crear en el origen dos solicitudes `not_found` con identificadores técnicos y tokens sintéticos, y cifrar sus registros directamente desde stdout; estos comandos no repiten ninguna operación destructiva externa:

```bash
for spec in "delete:d" "restrict:e"; do
  action="${spec%%:*}"; fill="${spec##*:}"; request_id="lf015-$action-$RUN_ID"
  docker compose -p "$SOURCE_COMPOSE_PROJECT" -f compose.yaml -f "$BACKUP_COMPOSE_OVERRIDE" exec -T postgres \
    psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_MIGRATOR_USER" -d "$POSTGRES_DB" -At \
    -c "SELECT * FROM leadflow.execute_dsr_request('$request_id','$action',repeat('0',64),repeat('$fill',64),'lf015-operator','lf015-approver',NULL);" >/dev/null
  docker compose -p "$SOURCE_COMPOSE_PROJECT" -f compose.yaml -f "$BACKUP_COMPOSE_OVERRIDE" exec -T postgres \
    psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_MIGRATOR_USER" -d "$POSTGRES_DB" -At \
    -c "SELECT json_build_object('subject_token',subject_token,'disposition',disposition,'effective_at_utc',effective_at_utc) FROM leadflow.prepare_dsr_restore_evidence('$request_id');" |
    python3 scripts/backup/dsr_restore_evidence.py stage --key-file "$DSR_EVIDENCE_KEY_FILE" --spool-dir "$DSR_EVIDENCE_SPOOL_DIR"
done
```

Transferir los dos artefactos cifrados por un canal administrativo protegido al contexto de escritor y publicar sus rutas exactas con `dsr_restore_evidence.py publish`; no transferir la clave ni el JSON descifrado. El administrador descarga/autentica el conjunto exacto, emite el manifiesto autoritativo y ejecuta:

```bash
python3 scripts/backup/dsr_restore_evidence.py bundle \
  --key-file "$DSR_EVIDENCE_KEY_FILE" \
  --events-dir /ruta/protegida/eventos \
  --output-dir /ruta/protegida/bundles \
  --authority-manifest /ruta/protegida/authority.json
python3 scripts/backup/dsr_restore_evidence.py publish \
  --artifact /ruta/protegida/bundles/<bundle-id>.dsr-bundle.gcm \
  --gcs-prefix "$DSR_EVIDENCE_GCS_PREFIX" \
  --writer-identity "$DSR_EVIDENCE_ADMIN_IDENTITY"
```

En el contexto restore, cargar exclusivamente su configuración y crear primero contenedores/volúmenes vacíos con el proyecto destino. Sin aplicar migraciones al destino, sincronizar únicamente los roles requeridos y ejecutar restore midiendo duración:

```bash
set -Eeuo pipefail
umask 077
export RESTORE_COMPOSE_PROJECT="lf015-restore-$RUN_ID"
export RESTORE_COMPOSE_OVERRIDE='/ruta/absoluta/lf015-isolated.override.yaml'
export LEADFLOW_RESTORE_ISOLATED=true
set -a; source /ruta/externa/lf015-restore.env; set +a

docker compose -p "$RESTORE_COMPOSE_PROJECT" -f compose.yaml -f "$RESTORE_COMPOSE_OVERRIDE" up -d postgres n8n
COMPOSE_PROJECT_NAME="$RESTORE_COMPOSE_PROJECT" bash scripts/database/sync_database_roles.sh
RESTORE_STARTED="$(date +%s)"
bash scripts/backup/restore.sh
RESTORE_SECONDS="$(( $(date +%s)-RESTORE_STARTED ))"
printf 'restore_seconds=%s\n' "$RESTORE_SECONDS"
```

`restore.sh` debe terminar con `traffic=DISABLED`; n8n queda detenido. Para verificar el destino, definir las tres variables `LF015_QA_*` con el proyecto/override de restore autorizado y ejecutar `qa_restore_probe.sh verify "$RUN_ID"`; exigir el mismo `n8n_sha256` registrado antes del backup. La utilidad comprueba exactamente una ejecución y un evento sintéticos y el archivo canónico persistido bajo `.n8n/lf015-probes`, sin modificar la base interna de n8n ni crear/activar workflows. Validar además 24 migraciones, conteo DSR `N|N|N` y rechazo `42501` de ambos tokens. Para healthcheck n8n, arrancarlo solo dentro del proyecto aislado sin puertos ni red externa, consultar `/healthz` desde el propio contenedor y detenerlo de nuevo:

```bash
docker compose -p "$RESTORE_COMPOSE_PROJECT" -f compose.yaml -f "$RESTORE_COMPOSE_OVERRIDE" exec -T postgres \
  psql -X -q -v ON_ERROR_STOP=1 -U "$POSTGRES_BOOTSTRAP_USER" -d "$POSTGRES_DB" -At \
  -c "SELECT count(*) FROM leadflow.schema_migrations; SELECT subject_token||'|'||disposition FROM leadflow.dsr_tombstones WHERE subject_token IN (repeat('d',64),repeat('e',64)) ORDER BY subject_token;"
docker compose -p "$RESTORE_COMPOSE_PROJECT" -f compose.yaml -f "$RESTORE_COMPOSE_OVERRIDE" start n8n
RESTORED_PROBE_RESULT="$(bash scripts/backup/qa_restore_probe.sh verify "$RUN_ID")"
RESTORED_N8N_SHA256="${RESTORED_PROBE_RESULT#*n8n_sha256=}"; RESTORED_N8N_SHA256="${RESTORED_N8N_SHA256%% *}"
test "$RESTORED_N8N_SHA256" = "$N8N_PROBE_SHA256"
docker compose -p "$RESTORE_COMPOSE_PROJECT" -f compose.yaml -f "$RESTORE_COMPOSE_OVERRIDE" exec -T n8n wget -q --spider http://127.0.0.1:5678/healthz
docker compose -p "$RESTORE_COMPOSE_PROJECT" -f compose.yaml -f "$RESTORE_COMPOSE_OVERRIDE" stop n8n
```

Repetir las dos llamadas sintéticas a `claim_event` usadas en QA y exigir SQLSTATE `42501`; no insertar un contacto real. Calcular RPO observado desde el timestamp UTC del nombre `leadflow-YYYYMMDDTHHMMSSZ-...` hasta el inicio de restore, y RTO observado con `RESTORE_SECONDS`. No habilitar tráfico.

Cleanup del probe es explícito y limitado al `RUN_ID`: ejecutar `qa_restore_probe.sh cleanup "$RUN_ID"` primero en el destino y luego en el origen, cambiando las variables `LF015_QA_*` al proyecto autorizado en cada caso. El comando se bloquea si no encuentra exactamente una ejecución y un evento, elimina solo esas dos filas y el archivo exacto del probe, y verifica `0|0`; no elimina bases, tablas, volúmenes ni otros archivos. Conservar fuera del entorno únicamente `RUN_ID`, hashes, tiempos y estados técnicos.

Cleanup posterior obligatorio, solo tras capturar resultados técnicos y comprobar los nombres exactos:

```bash
docker compose -p "$RESTORE_COMPOSE_PROJECT" -f compose.yaml -f "$RESTORE_COMPOSE_OVERRIDE" down -v --remove-orphans
docker compose -p "$SOURCE_COMPOSE_PROJECT" -f compose.yaml -f "$BACKUP_COMPOSE_OVERRIDE" down -v --remove-orphans
```

Eliminar directorios temporales sintéticos y archivos de secretos locales según su custodia. Los objetos cloud permanecen inmutables y expiran por el lifecycle aprobado; no conceder delete a las identidades runtime ni read/list/delete a `leadflow-backup` para acelerar cleanup. Registrar duración, resultado, estado final deshabilitado y cleanup. RPO 24 h y RTO 8 h continúan como objetivos hasta completar esta ejecución.

Secuencia de aprovisionamiento y validación posterior, sin ejecutarla desde este runbook:

1. Resolver privacidad/lifecycle del snapshot DSR activo y evaluar costo/requisitos de los runtimes administrados candidatos. Estos son gates; no declarar arquitectura comercial aprobada antes.
2. Crear las tres cuentas faltantes y el bucket DSR; aplicar IAM condicional/prefijos y las dos clases de conservación. Criterio PASS: análisis IAM muestra exactamente backup create-only, writer create-only, admin get/list+create y restore get-only; ninguna cuenta tiene claves administradas por usuario.
3. Validar estáticamente el override con `docker compose config`. PASS: cero puertos, una red project-scoped `internal`, PostgreSQL y n8n en esa red y ninguna dependencia hacia servicios existentes.
4. Para QA excepcional aprobada, usar el cambio secuencial de identidad: backup → escritor → administrador → restore, verificando metadata y limpiando secretos en cada transición. Cada mismatch o residuo produce FAIL y detiene la prueba.
5. Criterio integral: `traffic=DISABLED`, PostgreSQL/n8n íntegros, replay posterior al backup cuando existan eventos, snapshot vigente cubierto, RPO/RTO medidos y cleanup completo. La ejecución QA del 2026-11-10 obtuvo PASS técnico con cero eventos DSR; el cleanup de copias DSR y clave temporal en Cloud Shell, y de temporales y clave DSR en la VM, quedó confirmado en el HANDOFF. El replay posterior, RPO/RTO e igualdad completa permanecen `NOT_VERIFIED`; los dos registros de restauración se conservaron como evidencia.
6. Detener la VM y devolverla a su identidad operativa aprobada. Los objetos históricos expiran por su lifecycle; el snapshot activo no se elimina hasta decisión autoritativa y ventana de recuperación cumplida. No modificar IAM de `leadflow-backup`.
