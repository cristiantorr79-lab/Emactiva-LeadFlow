# HANDOFF LAB-LF-015

## Alcance LF015-T02

Implementación portable de backup/restore para PostgreSQL y n8n, sin cambios en infraestructura real. Se aplicaron EWB, EPB, EDPB y EQAB: mínimo acceso, privacidad/DSR, portabilidad por entorno, evidencia y fallo cerrado.

## Evidencia por capa

| Estado | Capa | Evidencia |
|---|---|---|
| PASS | SYSTEM | `backup_crypto.mjs` implementa AES-256-GCM streaming autenticado con `node:crypto`, cleanup de salida parcial y no-overwrite verificado. |
| PASS | SYSTEM | `backup.sh` verifica identidad Compute Engine por metadata, aísla la configuración gcloud, pausa n8n antes de `pg_dump`, limita la pausa, genera manifest y limpia temporales con trap. |
| PASS | SYSTEM | `restore.sh` completa validaciones previas antes de mutar, limita/extrae el TAR de forma segura, verifica labels y volúmenes Compose, conserva estado recuperable y mantiene n8n/tráfico deshabilitados. |
| PASS | SYSTEM | Migración 024 captura tombstone y outbox mínimo en la misma transacción de la solicitud DELETE/RESTRICT, conserva pendientes/fallos y permite reintento sin volver a ejecutar la operación destructiva. |
| PASS | SYSTEM | `dsr_restore_evidence.py` exige que el bundle v2 coincida exactamente con un manifiesto de cobertura autoritativo; ausencia, exceso, digest o conjunto divergente fallan cerrado. |
| PASS | SYSTEM | Restore reaplica DELETE/RESTRICT idempotentemente y verifica enforcement mediante el `claim_event` real; cualquier aceptación aborta y revierte la sentencia. |
| PASS | SYSTEM | `dsr_admin.py` conserva el contrato histórico y añade `restore_protection_status`; nunca afirma protección completa sin confirmación administrativa separada. |
| PASS | SYSTEM | Los PASS históricos de AES-GCM, round-trip, tampering, cleanup y no-overwrite permanecen vigentes; `backup_crypto.mjs` no cambió en esta corrección. |
| PASS | SYSTEM | 4 pruebas focalizadas nuevas/cambiadas cubren traversal, links, duplicados, contenido inesperado, límites, recibos DSR y contrato GCP/orden de pausa. |
| PASS | SYSTEM | Timer systemd reproducible/idempotente preparado estáticamente con periodo de 24 h y deliberadamente no habilitado. |
| NOT_VERIFIED | HYBRID | Sintaxis/runtime Bash y systemd no se ejecutaron: este PC no dispone de `/bin/bash`; no se instaló WSL. |
| WARN | HYBRID | La política lifecycle de 30 días debe existir una sola vez en el bucket; el repositorio no la crea ni duplica. |
| NOT_VERIFIED | ENVIRONMENT | VM, permisos efectivos, escritura GCS, identidad separada de restore/lectura y ausencia de lectura en `leadflow-backup`. |
| NOT_VERIFIED | ENVIRONMENT | Metadata/gcloud con credenciales administradas, restore completo, ownership efectivo del volumen n8n, healthchecks, integridad PostgreSQL/n8n y medición real RPO/RTO. |
| NOT_VERIFIED | HYBRID | La fuente administrativa debe emitir el manifiesto completo con secuencia alta y conjunto exacto. El SYSTEM valida su vínculo con el bundle, pero fecha/hash/secuencia/URI por sí solos no prueban actualidad global. |
| NOT_VERIFIED | ENVIRONMENT | Publicación con Object Creator sin read/list, descarga administrativa completa, custodia independiente del spool, bundle confirmado y replay/enforcement real en PostgreSQL aislado. |
| WARN | ENVIRONMENT | Soft delete añade 7 días recuperables: una copia expirada a 30 días puede persistir hasta 37; DSR debe conservar tombstones y no afirmar destrucción definitiva antes. |
| WARN | HYBRID | La pausa coordinada produce un conjunto recuperable si n8n es el único escritor, pero no constituye snapshot atómico entre PostgreSQL y volumen. |
| FAIL | SYSTEM | Ninguno en la batería focalizada final. |

## Riesgos y bloqueos

- No se ejecutaron operaciones GCP, cambios IAM, encendido de VM ni activación del timer.
- RPO 24 h y RTO 8 h continúan como objetivos, no como resultados probados.
- La identidad escritora publica eventos inmutables, pero no puede confirmar existencia remota sin lectura. Una identidad administrativa separada debe producir el manifiesto autoritativo, descargar/autenticar su conjunto exacto y crear el bundle; restore usa una tercera identidad de lectura.
- El outbox PostgreSQL permite recuperar fallos locales con `retry_dsr_restore_protection.py` sin invocar `execute_dsr_request` ni CRM. No sustituye la copia cifrada independiente: hasta stage/publicación confirmada la protección ante un backup antiguo sigue incompleta.
- `restore_protection_status` es adicional al contrato DSR histórico. `failed`, `staged` y `pending_confirmation` no equivalen a protección confirmada; integrar un estado final en sistemas consumidores requiere decisión contractual externa.
- Bash syntax/runtime permanece `NOT_VERIFIED` en este PC porque no existe `/bin/bash`; no se instaló WSL.
- Node.js 20 o posterior debe estar disponible en el host operativo; no hay dependencia Python de cifrado.
- Una transferencia interrumpida entre artefacto y checksum puede dejar un objeto huérfano no restaurable; se conserva sin borrado automático por mínimo privilegio y expira mediante el único lifecycle del bucket.
- El archivo accidental `abc` fue identificado como la ruta temporal generada por la depuración LF015 anterior y retirado; no pertenecía al producto.
- El usuario systemd dedicado necesita acceso al socket Docker, capacidad equivalente a privilegio elevado; su concesión y evidencia pertenecen al entorno.

## Validación ejecutada

- QA PostgreSQL 17.6 integrado: PASS. Bundle v2 sintético validado; replay real `2|2|2`; segundo replay `2|2|2`; dos tombstones presentes durante la transacción; `claim_event` devolvió SQLSTATE `42501` para DELETE y RESTRICT.
- Outbox real: PASS. Trigger creó `pending|0` y las transiciones controladas terminaron en `pending_confirmation|3`, sin repetir la solicitud destructiva ni usar servicios externos.
- Cleanup de datos: PASS. Tras `ROLLBACK`, tombstones, solicitud y outbox sintéticos devolvieron `0|0|0`.
- Cleanup de entorno: PASS. Artefactos locales sintéticos eliminados y contenedor verificado como `/leadflow-lf015-qa-pg|postgres:17.6-bookworm|none` antes de `docker rm -f`; consulta posterior no devolvió el contenedor.
- Defecto encontrado y corregido: los CTE independientes permitían ejecutar enforcement antes del replay. `emit_sql` usa ahora `WITH replay AS MATERIALIZED` y evalúa `verify_dsr_restore_enforcement` desde su resultado.
- Restore integral, manifiesto emitido por autoridad administrativa real y Google Cloud: `NOT_VERIFIED`.

- `node --check scripts/backup/backup_crypto.mjs`: PASS.
- PASS histórico conservado: `python -m unittest scripts.test.test_lf015_backup -v`, 5/5 previo para criptografía/contrato.
- `python -m unittest scripts.test.test_lf015_backup.DsrRestoreEvidenceTests scripts.test.test_lf015_backup.ContractTests -v`: PASS 5/5; cubre copia antigua frente a DELETE/RESTRICT posteriores, idempotencia, ausencia, alteración, manifiesto incompleto/divergente, cobertura desactualizada, fallo de publicación, rechazo seguro de reintento inválido y contrato de outbox/reintento/enforcement, sin Docker ni Google Cloud.
- `python -m py_compile scripts/backup/dsr_restore_evidence.py scripts/admin/dsr_admin.py scripts/admin/retry_dsr_restore_protection.py scripts/test/test_lf015_backup.py`: PASS.
- Runtime de migración, trigger, replay y rechazo real de `claim_event`: `NOT_VERIFIED` por restricción de no usar PostgreSQL/Docker real en esta ejecución.
- `python scripts/validation/validate_backup_policy.py`: `BACKUP_POLICY=PASS`.
- `python -m py_compile ...`: PASS para validador de archivo, política y batería LF015.
- `git diff --check`: PASS; solo avisos informativos de conversión LF/CRLF en archivos versionados.
- `bash -n` y ejecución Bash/systemd: NOT_VERIFIED por ausencia de `/bin/bash`/WSL en este PC.

### Corrección focalizada del recorrido de migraciones

- Causa reproducida localmente: el `while read` obtenía rutas desde `stdin` y `docker compose exec -T` heredaba el mismo descriptor; un hijo que leyera una línea consumía la siguiente migración. La prueba reprodujo recorrido incompleto con exit 0 (`FAIL stdin_cannot_truncate_migration_walk`). Un `</dev/null` aislado no elimina el acoplamiento estructural.
- Corrección SYSTEM: `apply_migrations.sh` materializa primero el inventario ordenado con `mapfile`, recorre un array, usa `psql_query ... </dev/null` para consultas escalares y falla si `processed != expected` o no hay archivos.
- Regresión de portabilidad de la prueba: aunque los archivos llegaron a Debian 13 con SHA-256 idéntico, la VM obtuvo 11/13. Los dos checks restantes dependían de detalles del arnés (parseo/registro lateral del `docker` simulado y coincidencia literal de expresiones del fuente), no del comportamiento observable protegido.
- Corrección focalizada del QA: `stdin_cannot_truncate_migration_walk` comprueba ahora las cuatro migraciones mediante la salida real del script mientras el `docker` simulado intenta consumir `stdin`; `migration_walk_count_fails_closed` inyecta en una copia temporal una iteración no contabilizada y exige exit distinto de cero con `processed=2 expected=3`. No se relajó ninguna garantía productiva.
- QA local focalizada tras el ajuste: controles Linux `PASS 13/13`; la repetición en Debian 13 permanece `NOT_VERIFIED`.
- PostgreSQL QA de la VM: `NOT_VERIFIED`. No declarar 24/24 hasta trasladar los dos archivos cambiados a una copia aislada, ejecutar el script y comprobar ledger 001–024 y código 0.

## Siguiente paso exacto

### Preparación QA integral: selección del origen

- PASS SYSTEM: `backup.sh` ya no usa el fallback `COMPOSE_PROJECT_NAME:-leadflow`. Exige `BACKUP_COMPOSE_PROJECT`, coincidencia exacta con `SOURCE_COMPOSE_PROJECT` y un `BACKUP_COMPOSE_OVERRIDE` absoluto/legible.
- PASS SYSTEM: antes de pausar o copiar, exige exactamente un contenedor PostgreSQL y uno n8n del proyecto autorizado mediante labels Compose, y confirma que `/home/node/.n8n` sea un volumen etiquetado para el mismo proyecto. Un mismatch falla antes de `docker pause` y `pg_dump`.
- PASS SYSTEM: la prueba focalizada comprueba ausencia del fallback, configuración obligatoria, igualdad del proyecto y validaciones de labels/volumen. No se ejecutó Docker ni se imprimieron archivos de entorno.
- NOT_VERIFIED ENVIRONMENT: inicio de n8n QA, `docker compose config` del override presente en la VM, datos sintéticos, backup cifrado, evidencia DSR, restore integral, RPO/RTO y cleanup real.

### Datos sintéticos para restore integral

- PASS SYSTEM: `qa_restore_probe.sh` implementa `prepare`, `verify` y `cleanup` con un `RUN_ID` único. PostgreSQL reutiliza `leadflow.claim_event` y exige exactamente `1|2|2` (una ejecución propia, los dos eventos contractuales y dos eventos totales); n8n guarda solo JSON técnico canónico en su volumen real `.n8n`, sin tocar su base interna ni workflows.
- PASS SYSTEM: antes de leer o escribir valida proyecto autorizado explícito, override absoluto, ausencia de puertos, red interna compartida, labels de ambos contenedores y pertenencia de ambos volúmenes. Colisiones, ausencia, alteración, conteos incompletos o destino ambiguo fallan cerrado.
- PASS SYSTEM: cleanup exige el estado exacto, elimina únicamente los dos eventos y la ejecución inequívocamente pertenecientes al probe más el archivo del `RUN_ID`, y confirma PostgreSQL `0|0|0`; no contiene `down`, eliminación de volúmenes ni DDL.
- NOT_VERIFIED ENVIRONMENT: preparación/verificación/cleanup contra `lf015-qa`, preservación efectiva por backup/restore y comparación de hashes en el destino aislado.

### Corrección SQL del probe QA

- FAIL observado en Debian/PostgreSQL: `psql -c` entregó literalmente `:'execution_id'` al servidor y PostgreSQL respondió `syntax error at or near ":"` durante la consulta inicial de colisión. Esa consulta era solo lectura, por lo que no alcanzó `claim_event` ni la escritura n8n; la ausencia efectiva de residuos se debe confirmar con `inspect` tras instalar la corrección.
- PASS SYSTEM: todas las sentencias parametrizadas se envían ahora por stdin a `psql -v`, contexto donde el cliente procesa `:'variable'`; no hay interpolación shell de valores SQL. Se corrigieron consulta, creación y eliminación en una sola pasada.
- PASS SYSTEM: un fallo posterior a `claim_event` ejecuta compensación limitada al execution ID y archivo del `RUN_ID`. Cleanup acepta `1|2|2` o `0|0|0`, permanece limitado y es idempotente. `inspect` informa de forma no destructiva los conteos y hash/ausencia.
- PASS local focalizado: prepare, verify, duplicado, RUN_ID/configuración inválidos, alteración, fallo SQL, fallo n8n con compensación, cleanup repetido e inspect. PostgreSQL real y la repetición en GCP permanecen `NOT_VERIFIED`.

### Compatibilidad definitiva con el esquema QA

- Causa confirmada: migración 013 elimina `executions.event_id`; migración 016 reemplaza `claim_event` por la firma de seis argumentos e incorpora `subject_token`. La implementación anterior consultaba/eliminaba por una columna inexistente, pasaba cinco argumentos y esperaba incorrectamente un evento.
- PASS SYSTEM: el probe deriva hashes técnicos deterministas y verifica pertenencia por `execution_id`, `source`, `idempotency_key`, `lead_identifier` y `subject_token`. Invoca la firma de seis argumentos y exige el resultado exacto `t|<execution_id>|`.
- PASS SYSTEM: el contrato SQL crea dos eventos (`received/validation` y `processing/idempotency`). Verify exige ambos y cleanup usa un CTE `owned` materializado; si campos o cardinalidad divergen no elimina nada.
- PASS focalizado 5/5 sobre ciclo, estados presente/ausente, duplicado, contrato de seis argumentos, ausencia de referencias a `executions.event_id`, errores/compensación, cleanup idempotente, aislamiento y alteración. PostgreSQL real aislado no estaba disponible localmente; VM continúa `NOT_VERIFIED`.

### Issue #16: representación de `claimed`

- FAIL confirmado en GCP: PostgreSQL concatena un booleano como `true`/`false`; el SQL devolvía `true|probe-...|`, mientras el control estricto esperaba `t|probe-...|`. El RUN_ID `lf015-20261109T162639Z-a28270c1` fue inspeccionado después como `0|0|0` y n8n `ABSENT`.
- Corrección SYSTEM: el SQL normaliza explícitamente con `CASE WHEN claimed THEN 't' ELSE 'f' END`; se conserva la comparación exacta de `t|<execution_id>|`. `false`, duplicado, salida malformada o error SQL siguen fallando y activando compensación.
- Prueba focalizada local: aceptación de `true` normalizado, rechazo de `false` y respuesta malformada, y ausencia de residuos tras compensación. La ejecución funcional `prepare` + `verify` en GCP permanece `NOT_VERIFIED`.

### Issue #16: subida GCS con scope write-only

- Evidencia ENVIRONMENT: identidad administrada y escritura directa mediante GCS JSON API obtuvieron PASS/HTTP 200; `gcloud storage cp` devolvió 403 con `devstorage.write_only`. Esto demuestra la incompatibilidad observada, no la causa interna exacta del CLI.
- Corrección SYSTEM: `gcs_json_upload.py` obtiene un token temporal desde metadata, crea una sesión resumable JSON API con `ifGenerationMatch=0` y transmite el archivo por bloques sin cargarlo completo. Solo acepta sesión HTTPS de `storage.googleapis.com`, aplica timeouts y trata 412, 403, autenticación ausente y respuestas inesperadas como FAIL sin imprimir token ni cuerpo remoto.
- Integración SYSTEM: `backup.sh` usa el uploader para cifrado y sidecar; `dsr_restore_evidence.py` lo usa para eventos, bundles y checksum. No se elimina ningún objeto ante fallo parcial y no se modificaron formatos, restore, IAM ni credenciales.
- PASS focalizado 4/4: binario/streaming y precondición, HTTP 403/412, timeout/token ausente sin secretos, sidecar fallido y ambos llamadores. Escritura real del backup y evidencia DSR mediante la nueva ruta permanecen `NOT_VERIFIED` hasta la VM QA.

### Preflight de restauración integral aislada

- PASS SYSTEM: `restore-isolated.override.yaml` define PostgreSQL/n8n sin puertos, red interna propia y volúmenes project-scoped; no contiene secretos ni rutas de VM. El proyecto restore debe ser distinto de `lf015-qa` y del origen.
- PASS SYSTEM: `preflight_restore.py` es no destructivo y valida herramientas, ambos `docker compose config`, separación de proyectos/redes/volúmenes, estado `0700`, claves distintas/restrictivas, cuatro identidades separadas, URIs y estructura `LF015-DSR-AUTHORITY-1`. No accede a GCP, metadata ni contenedores runtime.
- PASS focalizado 3/3: configuración aislada; rechazo de mismo proyecto, volumen/red compartidos y puertos; rechazo de identidad repetida, configuración incompleta y autoridad ausente.
- WARN HYBRID: `synthetic_closed_set` solo permite describir el conjunto cerrado de la prueba y no acredita ausencia global de DSR.
- NOT_VERIFIED HYBRID/ENVIRONMENT: fuente administrativa, high-water mark reconciliado, bundle/clave/checksum independientes, cuentas restore/DSR, permisos GCS efectivos y destino runtime aún no existen o no fueron comprobados. El preflight retorna 2 y bloquea restore mientras permanezcan pendientes.
- Cleanup autorizado únicamente para el proyecto restore exacto después de evidencia; queda prohibido ejecutarlo sobre `lf015-qa` o el origen.

### Autoridad DSR sintética del piloto QA

- PASS SYSTEM: `dsr_restore_evidence.py authority-manifest` consume una exportación externa `LF015-DSR-ADMIN-EXPORT-1` limitada a `synthetic_qa_closed_set` y genera el contrato existente `LF015-DSR-AUTHORITY-1`. No exporta subject tokens ni PII.
- PASS SYSTEM: exige secuencia contigua desde 1, high-water mark exacto, orden temporal determinista, cobertura UTC posterior a todos los eventos, IDs únicos y `publication_state=confirmed`. Cero eventos solo es válido con secuencia 0 y conjunto vacío.
- PASS SYSTEM: el preflight requiere `DSR_AUTHORITY_EXPORT` fuera del checkout y compara su resultado exacto con el manifiesto. Bundle conserva la segunda reconciliación contra los eventos cifrados; evento faltante, pendiente, secuencia incompleta o manifiesto alterado fallan cerrado antes de restore.
- PASS SYSTEM (2026-11-10): `dsr_qa_authority.py` inicializa una fuente QA sintética con cobertura explícita, snapshots encadenados e inmutables, secuencia continua, incorporación exclusiva de evidencia cifrada confirmada, checkpoint con pendientes cero y exportación `LF015-DSR-ADMIN-EXPORT-1`. No contiene subject tokens ni PII.
- PASS SYSTEM (2026-11-10): el manifiesto exige el manifest del backup y rechaza backups anteriores al inicio o posteriores al checkpoint de la autoridad. Regresión focalizada: `python -m unittest scripts.test.test_lf015_backup.DsrQaAuthorityTests` = 6/6 PASS, incluidos DELETE/RESTRICT cifrados, cero eventos, pendiente, secuencia alterada y backup antiguo.
- NOT_VERIFIED ENVIRONMENT: identidad administrativa efectiva, reconciliación real de outbox/objetos, publicación `--no-clobber`, IAM y lifecycle del bucket DSR no se ejecutaron. `--pending-count 0` debe provenir de esa reconciliación y no constituye por sí solo autoridad global.
- BLOQUEO: el backup ya creado antes de inicializar esta fuente no puede adquirir cobertura retroactiva. Primer paso: inicializar/publicar snapshot cero con la identidad administrativa DSR y, tras confirmarlo, producir un backup nuevo.
- PASS focalizado 4/4: cero eventos, DELETE/RESTRICT posteriores, export/manifiesto coherentes, evento faltante, hueco/high-water incompleto, pendiente, alteración y fuente ausente.
- NOT_VERIFIED HYBRID/ENVIRONMENT: no existe aún una fuente administrativa independiente desplegada/custodiada que pueda acreditar el high-water mark. El mecanismo valida lo recibido pero no inventa ni certifica procedencia global; producción permanece fuera del scope sintético.

Estado al finalizar la preparación: la restauración integral quedaba preparada a nivel SYSTEM/procedimiento y aún no se había ejecutado. La ejecución QA posterior y su alcance se consolidan en la sección de cierre del 2026-11-10. Los scripts cubren generación, cifrado, transferencia, validación, restore PostgreSQL/n8n, replay DSR, estado recuperable y cleanup local; no se añadió otra herramienta.

Diseño ajustado: el override QA usa una red Compose project-scoped con `internal: true`; PostgreSQL y n8n comparten esa red, no publican puertos ni se unen a redes de contenedores existentes. Sustituye el ejemplo incorrecto con `network_mode: none`. Compatibilidad mediante `docker compose config` y runtime permanecen `NOT_VERIFIED` hasta Linux.

El cambio secuencial de cuenta adjunta en `leadflow-pilot-01` queda solo como procedimiento QA excepcional, sujeto a ventana aprobada, metadata exacta y cleanup entre fases. No está aprobado para operación comercial. Para operación habitual se evaluarán workloads administrados separados con identidades adjuntas; Cloud Run Jobs, Batch, VM dedicada e impersonación/WIF son candidatos, no decisiones. Hay que verificar metadata, Docker/volúmenes, red, duración, región, permisos, logging y costo; impersonación/WIF no es compatible con los controles actuales sin cambio de código y nueva QA.

Faltan tres cuentas runtime: escritor DSR create-only, administrador DSR get/list de eventos + create de bundles, y restore con rol personalizado `storage.objects.get` sobre los objetos necesarios. `leadflow-backup` se reutiliza solo para create en backups y no recibe permisos nuevos. Ninguna cuenta usa claves JSON.

Se requiere un bucket DSR separado con acceso uniforme, prevención pública e identidades sin update/delete. Se distinguen evidencia histórica —mínimo técnico de 37 días— y snapshot cifrado/minimizado del conjunto de bloqueos vigentes, conservado mientras la autoridad lo marque activo y después durante la ventana de backups recuperables. Treinta y siete días no garantizan protección permanente. Base jurídica, duración/levantamiento de restricciones, lifecycle por clase, retention lock y fuente autoritativa permanecen `NOT_VERIFIED HYBRID/ENVIRONMENT`; no se aprueba retención indefinida por defecto.

Riesgos pendientes: QA secuencial exige detener la VM y mantiene al operador root como frontera privilegiada. La alternativa comercial puede requerir cambios de código o costo adicional todavía no medido. Eliminar un snapshot DSR vigente o aplicarle automáticamente el lifecycle histórico debe bloquear restore.

La rotación de `DSR_SUBJECT_KEY` también permanece bloqueada: sin dual-key/retokenización, los tokens nuevos no coincidirían con tombstones vigentes. Resolverlo exige decisión de privacidad, diseño y QA fuera de este ajuste; no se modificó el Core.

El runbook contiene la secuencia exacta para crear origen sintético, medir backup, generar DELETE/RESTRICT posteriores, consolidar bundle v2, crear destino vacío, medir restore, comprobar PostgreSQL/n8n/`42501`, mantener `traffic=DISABLED` y ejecutar `down -v`. Los objetos GCS deben eliminarlos una identidad administrativa o su lifecycle; no se amplían permisos de `leadflow-backup`.

Credenciales: Bitwarden queda aprobado como custodia administrativa de recuperación; desarrollo usa secretos sintéticos fuera de Git; producción usa gestor de secretos e identidades independientes. La rotación conserva claves antiguas mientras existan artefactos recuperables durante 30+7 días y exige prueba de recuperación antes de retirarlas.

Primer paso posterior histórico: aprobar con Privacidad la regla de vigencia/levantamiento del snapshot DSR y, en paralelo, validar en un host Linux únicamente `docker compose ... config` sobre el override de red interna. La ejecución QA posterior se registra en la sección de cierre siguiente.

## Cierre controlado LF015-T02 — evidencia operacional 2026-11-10

### PASS

- Respaldo cifrado `leadflow-20261110T152846Z-fad154b93261.tar.gcm` y checksum SHA-256 almacenados en el bucket de respaldos: PASS operacional informado.
- Autoridad administrativa DSR independiente para `synthetic_closed_set`: journals, checkpoint, export, manifiesto, bundle cifrado y checksum publicados; validación y descifrado del bundle: PASS. El conjunto contenía cero eventos.
- Lectura efectiva de ambos buckets con la identidad temporal `leadflow-restore`: PASS independiente. El resultado automatizado del preflight se conserva exactamente como 9 PASS, 1 WARN y 1 NOT_VERIFIED; esta lectura no reetiqueta el control automatizado IAM/GCS.
- Aislamiento: proyecto Compose `lf015-restore`, red interna y volúmenes exclusivos, sin puertos publicados (`HostConfig.PortBindings: {}`); los ocho contenedores originales y QA permanecieron saludables.
- Primer intento de restore: `RECOVERABLE_FAILURE` porque `POSTGRES_BOOTSTRAP_USER` y `POSTGRES_DB`, aunque presentes en `.env`, no estaban exportadas al proceso. Falló antes de `pg_restore`, se conservó su evidencia y el reintento controlado terminó `phase=complete`, `status=PASS`, `traffic=DISABLED`.
- PostgreSQL: restore ejecutado, esquema `leadflow` con 11 tablas y recuentos coincidentes en seis tablas: `execution_events 2/2`, `executions 1/1`, `recovery_contexts 0/0`, `dsr_requests 0/0`, `dsr_tombstones 0/0`, `dsr_restore_evidence_outbox 0/0`. Esto acredita recuentos, no igualdad completa de contenido.
- n8n 2.28.6: volumen con 11 archivos, servicio healthy y cero reinicios. PostgreSQL restaurado también healthy. El aviso DNS `EAI_AGAIN` hacia `api.n8n.io` no impidió el healthcheck; no se ejecutaron workflows de negocio.
- Cleanup de infraestructura temporal del destino: contenedores, dos volúmenes y red eliminados y verificados. La VM volvió a `leadflow-backup@emactiva-leadflow-pilot.iam.gserviceaccount.com`, scope `devstorage.write_only`, estado `TERMINATED`; `roles/iam.serviceAccountTokenCreator` temporal fue revocado y verificado. Se conservó evidencia durable de recuperación.
- Cleanup final confirmado: copias DSR y clave temporal eliminadas de Cloud Shell; archivos temporales y clave DSR eliminados de la VM; no quedan recursos `lf015-restore`. Se conservaron únicamente los dos registros durables de restauración. Los ocho contenedores originales/QA permanecieron saludables.

### WARN

- La autoridad DSR cubre exclusivamente el conjunto sintético cerrado de QA y no certifica cobertura global de producción.
- El aviso DNS externo de n8n no bloqueó salud, pero confirma que no se validó funcionalidad de workflows ni dependencia MCP externa.

### NOT_VERIFIED y riesgos residuales

- Cobertura DSR global y replay de DELETE/RESTRICT posteriores al backup: NOT_VERIFIED; cero eventos QA no demuestra enforcement de eventos posteriores en esta restauración.
- Igualdad completa de datos PostgreSQL/n8n y ejecución funcional de workflows: NOT_VERIFIED.
- RPO 24 h y RTO 8 h continúan como objetivos; no se aportaron mediciones.
- El control automatizado `iam_gcs_runtime` permanece NOT_VERIFIED aunque la lectura efectiva se comprobara por separado.
- Controles comerciales/producción HYBRID y ENVIRONMENT permanecen separados; esta evidencia no certifica restore de producción.

### Estado de cierre

- **LF015-T02: PASS técnico de restauración aislada QA**, con tráfico mantenido deshabilitado y las limitaciones anteriores expresamente excluidas.
- **LAB-LF-015: ABIERTO.** Los Issues #15 y #16 están `CLOSED`; los Issues #17 y #18 permanecen `OPEN`. Los `NOT_VERIFIED` técnicos residuales se mantienen como límites explícitos y no se convierten en PASS.

## Regularización de Issues #15, #16 y continuidad #17

Evaluación documental contra los criterios vigentes de GitHub Issues al 2026-11-10. `CUMPLIDO` significa que existe evidencia o una limitación aceptada por el propio criterio; no equivale a validación productiva.

### Issue #15 — LF015-T01

| Criterio de aceptación | Estado | Evidencia o bloqueo |
|---|---|---|
| Intake y discovery sin datos críticos improvisados | CUMPLIDO | GitHub #15 quedó CLOSED. La resolución aprobó piloto interno Emactiva, modalidad B, funciones diferenciadas, datos sintéticos, HubSpot candidato y límites de privacidad/acceso; los valores efectivos de deployment permanecen para #17. |
| Escenario representativo o cliente real autorizado y responsables definidos | CUMPLIDO | Piloto interno Emactiva autorizado; fase inicial controlada, no pública y sintética. Representante funcional y responsable de implementación diferenciados en la evidencia aunque los asuma la misma persona. |
| Alcance, clasificación, EVENT/LEAD/INTERACTION, criterios y exclusiones | CUMPLIDO | STANDARD/CORE para V1 y HubSpot; CONFIGURATION/INTEGRATION para formulario/puente. Landing, canales adicionales, automatizaciones nuevas y CRM propio quedan fuera. EVENT + LEAD + INTERACTION y duplicate exacto están definidos. |
| Riesgos, dependencias, privacidad y decisiones pendientes | CUMPLIDO | Seguridad del formulario, terceros, HubSpot, retención/DSR, backup, secretos, exposición y gates están identificados con NOT_VERIFIED explícitos. |
| Autorización del piloto antes de continuar | CUMPLIDO | Autorización expresa del piloto interno registrada el 2026-10-09; no autorizó por sí sola deployment, datos reales ni exposición pública. |
| Seguridad y privacidad del formulario/proceso identificadas | CUMPLIDO | Actores, datos, finalidad, terceros, capa segura, TLS/IAM/firewall, abuso, retención y DSR están delimitados como requisitos o riesgos. |
| Matriz inicial de aceptación multidominio | CUMPLIDO | Los Issues y este HANDOFF separan funcionalidad, seguridad, resiliencia, privacidad, operación, evidencia y bloqueos críticos/altos. |
| Estrategia controlado → remoto con aprobación; landing separada | CUMPLIDO | Primera fase sintética no pública; remoto sujeto a preflight/aprobación; LAB-EWEB-000 fuera de LF015. |
| Cliente interno y responsable diferenciados; HubSpot candidato | CUMPLIDO | Roles separados en autorizaciones/evidencia; HubSpot Emactiva quedó candidato sujeto a verificación. |
| Revisión humana y aviso email acordados | CUMPLIDO | Atención humana, horario/objetivo y aviso Google inicial/corporativo posterior quedaron definidos; viabilidad nativa permanece NOT_VERIFIED para #17. |
| Riesgos/configuración no demostrados permanecen NOT_VERIFIED | CUMPLIDO | No se forzó aceptación funcional ni producción para HubSpot, email, controles públicos o DSR externo. |

**Decisión #15: CERRADO en GitHub.** Se reutilizan sus decisiones autorizadas. El cierre de discovery no autoriza deployment público, datos reales ni convierte en PASS los controles efectivos de HubSpot, privacidad o infraestructura que corresponden a #17.

### Issue #16 — LF015-T02

| Criterio de aceptación | Estado | Evidencia o bloqueo |
|---|---|---|
| Oferta LF014 aplicada y responsabilidades explícitas | CUMPLIDO | `LEADFLOW_COTIZACION_PILOTO_INTERNO.xlsx` aplica modalidad B y referencia neta $1.200.000 CLP, conserva condiciones LF014, distingue costo real pendiente y declara facturación interna N/A. |
| Inventario de recursos, costos, accesos, preparación y ventanas | CUMPLIDO CON PENDIENTES | La ficha específica inventaría existentes/requeridos, responsables y accesos. Costos externos y ventana quedan marcados pendientes, sin inventarlos. |
| Preflight PASS o bloqueos explícitos; sin instalación ante crítico | CUMPLIDO CON LÍMITE | Restore QA: 9 PASS, 1 WARN y 1 NOT_VERIFIED, más lectura real independiente. No hubo exposición pública. TLS, HubSpot, formulario y controles productivos siguen bloqueando deployment de #17. |
| Datos de prueba, cleanup, backup/restore y rollback preparados | CUMPLIDO PARA QA | Datos sintéticos, backup cifrado, restore aislado, `RECOVERABLE_FAILURE` recuperado, rollback/estado durable y cleanup final están evidenciados. Producción y DSR global permanecen NOT_VERIFIED. |
| Tiempos y fricciones registrados | CUMPLIDO CON LÍMITE | Se separan estimaciones LF014 (36 h + 4 h, plazo 5 días) de tiempos reales no medidos. Se consolidaron siete fricciones técnicas/operativas; RPO/RTO siguen NOT_VERIFIED. |
| Superficies, TLS, puertos, firewall, IAM/MFA y red | CUMPLIDO COMO GATE | Aislamiento QA y ausencia de puertos: PASS. TLS, firewall/IAM/MFA y superficie pública no están verificados y permanecen bloqueantes antes de #17. |
| Secretos/roles segregados y rotación/revocación | CUMPLIDO COMO BLOQUEO | QA demostró identidades separadas, cleanup y revocación temporal; claves webhook/Adapter/DSR y segregación efectiva remota quedan CRITICAL NOT_VERIFIED para #17. |
| Abuso del formulario público evaluado | CUMPLIDO COMO BLOQUEO | Spam, rate limiting, payload y bots están identificados; falta seleccionar/verificar controles, clasificado CRITICAL para #17. |
| PII, terceros, retención/DSR, cifrado y sanitización | CUMPLIDO CON LÍMITE | Cifrado/backup QA y minimización DSR: PASS limitado. HubSpot, retención productiva, DSR global y sanitización desplegada siguen NOT_VERIFIED para #17. |
| Backup/restore, rollback, monitoreo e incidentes proporcionales | CUMPLIDO CON LÍMITE | Backup/restore/recuperación QA: PASS. Monitoreo, respuesta productiva y RPO/RTO medidos siguen NOT_VERIFIED. |
| Brechas críticas/altas bloquean deployment | CUMPLIDO | No se autorizó exposición; los controles externos pendientes permanecen explícitos y bloquean #17. |

**Entregables #16:** `LEADFLOW_COTIZACION_PILOTO_INTERNO.xlsx` y `LEADFLOW_IMPLEMENTACION_PILOTO_INTERNO.md`. La ficha contiene inventario, responsables, costos/tiempos diferenciados, matriz PASS/WARN/NOT_VERIFIED y severidades de deployment.

**Decisión #16: CLOSED.** Sus cinco criterios base y los criterios ampliados quedaron satisfechos mediante evidencia existente o bloqueos explícitos. El preflight termina `BLOCKED FOR DEPLOYMENT`: el cierre de #16 no autoriza #17 ni certifica producción.

### Continuidad Issue #17 — LF015-T03

- Evidencia reutilizable: autorización del piloto controlado, clasificación EVENT/LEAD/INTERACTION, PASS históricos de idempotencia/migraciones, backup cifrado, restore aislado, recuperación ante interrupción, segregación temporal de identidades, cleanup final y límites DSR/producción.
- Dependencias: autorización separada de deployment; preflight remoto habilitante; secretos externos; HubSpot y notificación nativa verificados; controles de TLS/red/IAM, abuso, logs, monitoreo y cleanup acordados.
- Primer bloqueo real: no existe arquitectura aprobada para el endpoint/formulario ni controles verificados de exposición; por ello el preflight remoto conserva controles CRITICAL `NOT_VERIFIED`.
- Próxima acción concreta: seleccionar y documentar esa arquitectura y sus controles de TLS, red/firewall, IAM, secretos y rate limiting. Después completar el preflight remoto y solicitar autorización independiente para ejecutar #17.

## Registro documental posterior al cierre de LF015-T02

- **Issue #15:** CLOSED — discovery y autorización del piloto interno formalizados en GitHub.
- **Issue #16:** CLOSED — preparación comercial, documental y preflight finalizados dentro de su alcance. El despliegue permanece `BLOCKED FOR DEPLOYMENT`.
- **Issue #17:** OPEN — implementación y despliegue no autorizados mientras el preflight permanezca `BLOCKED FOR DEPLOYMENT`.
- **Issue #18:** OPEN — continuidad pendiente; no se declara completado en este LAB.
- **LAB-LF-015:** ABIERTO — continúa con #17 y #18; los cierres de #15/#16 no cierran el LAB.
- **Cotización:** `LEADFLOW_COTIZACION_PILOTO_INTERNO.xlsx`, aplicación interna de la modalidad B aprobada en LF014; no sustituye la plantilla comercial oficial.
- **Ficha técnica:** `LEADFLOW_IMPLEMENTACION_PILOTO_INTERNO.md`, documento específico del piloto.
- **Ficha editable:** `LEADFLOW_IMPLEMENTACION_PILOTO_INTERNO_EDITABLE.docx`, versión Word generada para edición y revisión.
- **Ubicación:** los entregables se mantienen en `labs/LAB-LF-015/`.
- **Validación:** existencia de los tres entregables originales y estructura básica XLSX PASS; `git diff --check` sin errores. No se declara una validación integral de fórmulas a partir del control ZIP.
- **Límites:** controles de despliegue CRITICAL/NOT_VERIFIED conservados para #17; sin autorización de exposición pública ni utilización de datos reales.
- **Git:** sin commit ni push. La consolidación Git queda para el cierre del LAB, previa revisión y autorización.

**Continuidad:** LF015-T03 (#17), comenzando por resolver la arquitectura segura de entrada y el preflight bloqueante, sin repetir evidencias QA cerradas.

## LF015-T03 — autenticación temporal de backups

- PASS SYSTEM: `backup.sh` conserva `attached` como modo predeterminado y añade `impersonation` opt-in. En este modo valida cuentas runtime/backup distintas, exige que metadata identifique a runtime y pasa la cuenta backup explícita al uploader; no hay fallback a runtime, ADC local ni claves JSON.
- PASS SYSTEM: `gcs_json_upload.py` conserva su contrato histórico y, solo cuando lo solicita `backup.sh`, intercambia el token de metadata mediante IAM Credentials `generateAccessToken`. El token temporal se usa en GCS con streaming e `ifGenerationMatch=0`; errores y respuestas de autenticación permanecen sanitizados.
- PASS QA focalizada: 6/6 casos sintéticos cubren modo histórico, impersonación, rechazo IAM, timeout, tokens malformados, identidad inválida, ausencia de secretos en errores, no-overwrite y uso compartido sin regresión DSR. Compilación Python y `bash -n`: PASS.
- WARN SYSTEM/ENVIRONMENT: procesos con acceso equivalente a metadata dentro de la misma VM no quedan fuertemente aislados. Deben restringirse usuario del servicio, ejecución/lectura de archivos, acceso Docker y metadata; la eficacia de esos controles no se valida localmente.
- NOT_VERIFIED ENVIRONMENT: IAM Credentials API, scope VM `cloud-platform`, binding de `iam.serviceAccounts.getAccessToken` limitado a `leadflow-backup`, permisos create-only del bucket e identidad efectiva no se probaron contra GCP. No se usaron credenciales reales ni se autorizó deployment o tráfico.
- Configuración futura: VM con `leadflow-runtime`; permiso mínimo `iam.serviceAccounts.getAccessToken` sobre la cuenta backup concreta; `leadflow-backup` mantiene solo `storage.objects.create` en el bucket; variables externas `BACKUP_GCP_AUTH_MODE=impersonation`, `BACKUP_RUNTIME_GCP_IDENTITY` y `BACKUP_GCP_IDENTITY`.

### LF015-T03 — carga portable de secretos productivos

- Archivos: `scripts/admin/compose_with_secrets.py`, `scripts/test/test_secret_runtime.py`, `.env.example` y este HANDOFF. No se modificaron Core, adapters, Compose, DSR ni backup/restore.
- Defecto corregido: `LF015-SECRET-MAP-1` exigía las doce variables de `SECRET_NAMES` a una única identidad y podía entregar credenciales administrativas al proceso Compose. Ese contrato queda sustituido por `LF015-SECRET-MAP-2`, que exige `operation=runtime-compose` y exactamente nueve secretos runtime con versiones numéricas: app PostgreSQL, n8n, webhook, adapter normal, recovery, clave de sujeto DSR, HubSpot, Hunter y Slack.
- PASS SYSTEM: `POSTGRES_BOOTSTRAP_PASSWORD` y `POSTGRES_MIGRATOR_PASSWORD` quedan clasificados como administración PostgreSQL; `DSR_ADAPTER_SERVICE_KEY`, como DSR privilegiado. Ninguno puede aparecer en el mapa runtime, resolverse mediante `leadflow-runtime` ni heredarse del entorno ambiente. La resolución autorizada conserva metadata administrada, memoria, sanitización, `COMPOSE_DISABLE_ENV_FILE=1` y ausencia de fallback.
- PASS SYSTEM: `compose.production.yaml` elimina `POSTGRES_PASSWORD`, las dos contraseñas administrativas y `DSR_ADAPTER_SERVICE_KEY` de los servicios runtime. El wrapper usa sentinelas no secretas de una sola posición exclusivamente para satisfacer la interpolación fail-closed del archivo base; el override las descarta antes de crear contenedores. El validador conserva `full` para operaciones históricas y añade `runtime`, que exige los nueve secretos operativos y rechaza cualquier valor privilegiado.
- PASS SYSTEM: `sync_database_roles.sh` y `apply_migrations.sh` conservan roles, ownership, orden y SQL, pero pasan las tres contraseñas solo por nombre a cada proceso administrativo `docker compose exec`; los valores permanecen en el entorno del operador y no en el servicio PostgreSQL persistente. No se regeneraron credenciales ni se ejecutaron migraciones.
- PASS SYSTEM: el adapter normal arranca sin clave destructiva. Un servicio `adapters-dsr-admin` bajo perfil explícito `administration`, sin restart automático, puerto loopback separado y guard de longitud conserva la autenticación `X-LeadFlow-DSR-Adapter-Key`/comparación constante para DELETE. `dsr_admin.py` conserva migrator, aprobación y claves normal/destructiva distintas; para usar esta ruta debe apuntar explícitamente al adapter administrativo y ejecutar cleanup al terminar.
- PASS QA focalizada: secretos/runtime 6/6; portabilidad Bash/migraciones 13/13; contratos de roles PostgreSQL 21/21. Se verificaron mapa V2, ausencia de credenciales privilegiadas reales en runtime, preflight sin `up`, resets de Compose, inyección administrativa por nombre, autorización DSR intacta, sintaxis Python/Bash y development/mocks. No se ejecutaron Docker, migraciones ni servicios.
- Identidades mínimas propuestas, no aprovisionadas: `leadflow-runtime` accede solo a los nueve secretos runtime; la operación PostgreSQL usa una identidad administrativa separada para bootstrap/migrator; la operación DSR usa una identidad privilegiada separada para `dsr-adapter-service-key`. El proceso DSR también necesita credenciales operativas de adapter/proveedor para ejecutar su función, por lo que la entrega combinada y su frontera IAM requieren un mecanismo administrativo explícito; no se asume aislamiento por compartir VM.
- Pendientes ENVIRONMENT: `enrichment-api-key` y `slack-webhook-url` continúan sin valor aprobado; HubSpot real, versiones/estado, bindings por secreto e identidad efectiva permanecen `NOT_VERIFIED`. `leadflow-runtime` no debe recibir acceso a `dsr-adapter-service-key` para superar artificialmente el bloqueo.
- WARN residual: Compose entrega estas credenciales como entorno de los contenedores. Operadores con acceso privilegiado a Docker/host pueden inspeccionarlas; `config -q`, captura de salidas y ausencia de archivos reducen exposición accidental, no proporcionan aislamiento frente a root/Docker.
- NOT_VERIFIED HYBRID/ENVIRONMENT: identidad efectiva de metadata, estado/versiones de Secret Manager, bindings por secreto y ejecución Linux de Docker Compose no se consultaron. Sin despliegue ni tráfico autorizado.
- WARN / NOT_VERIFIED ENVIRONMENT: compatibilidad efectiva de `!reset`/`!override` con la versión Compose de la VM, reinicio contra los volúmenes existentes, ausencia final de variables privilegiadas vía `docker inspect`, perfil DSR administrativo, metadata/Docker socket e IAM no se probaron. La misma VM y acceso Docker/root siguen siendo una frontera débil.
- Siguiente gate: en una copia aislada de la configuración y sin recrear el origen, ejecutar `preflight`, inspeccionar solo nombres —nunca valores— del modelo Compose y validar que runtime no contenga las tres variables privilegiadas. Después probar reinicio con volúmenes sintéticos equivalentes y la activación/cleanup separados del perfil DSR; solo esos PASS habilitan evaluar la VM real bajo autorización nueva.

### LF015-T03 — inicialización PostgreSQL separada

- Causa confirmada: el override productivo elimina `POSTGRES_PASSWORD`, `POSTGRES_BOOTSTRAP_PASSWORD` y `POSTGRES_MIGRATOR_PASSWORD` del servicio persistente, como exige la separación runtime, pero no había un procedimiento independiente que pudiera inicializar de forma segura un volumen vacío.
- Corrección SYSTEM: `compose.postgres-bootstrap.yaml` define únicamente `postgres-bootstrap`, sin puertos publicados ni restart automático, sobre el volumen PostgreSQL del proyecto indicado. `scripts/database/bootstrap_postgres.sh` exige autorización explícita, nombre de proyecto válido, configuración administrativa completa y validación `postgres-admin`; además deshabilita la lectura implícita de `.env`.
- PASS SYSTEM: antes de iniciar PostgreSQL, el script clasifica el volumen como vacío, inicializado o ambiguo. Solo acepta vacío; un volumen inicializado se reserva para el arranque runtime normal y un estado parcial/ambiguo falla cerrado. No usa `POSTGRES_HOST_AUTH_METHOD=trust`, no pasa valores secretos como argumentos y no imprime configuración sensible.
- PASS SYSTEM: `apply_migrations.sh` y `sync_database_roles.sh` mantienen su modo histórico por defecto y aceptan el modo interno `bootstrap`, limitado al servicio administrativo. Se conservan orden, ledger, ownership, roles y validaciones existentes. Tras la inicialización se detiene y elimina exclusivamente el contenedor bootstrap; el volumen persiste y el script no inicia servicios runtime con la identidad administrativa.
- PASS QA focalizada: `test_postgres_bootstrap.py` 6/6 (volumen vacío, inicializado, ambiguo, autorización/credencial ausente, credenciales fuertes/distintas, fallo de migración, cleanup y ausencia de secretos en salidas/argumentos); regresión de migraciones Linux 13/13; regresión de secretos runtime 6/6. Sintaxis Bash y Python: PASS. Todas las credenciales fueron sintéticas; no se ejecutó Docker.
- NOT_VERIFIED ENVIRONMENT: creación real del clúster PostgreSQL 17.6, healthcheck, ejecución 24/24 de migraciones, reinicio operativo posterior con el mismo volumen y compatibilidad de la versión Docker Compose de destino requieren una prueba Linux aislada. No se modificaron VM, GCP, IAM ni datos reales.
- Riesgo residual: el operador administrativo y procesos con acceso a Docker/root pueden observar el entorno del contenedor temporal; la separación de procesos reduce exposición runtime pero no constituye aislamiento fuerte dentro del mismo host.
- Siguiente gate: en Linux aislado y con un proyecto Compose sintético nuevo, suministrar las tres credenciales por el entorno del proceso autorizado, ejecutar una sola vez `LEADFLOW_POSTGRES_BOOTSTRAP_AUTHORIZED=true COMPOSE_PROJECT_NAME=<proyecto_sintetico> scripts/database/bootstrap_postgres.sh`, confirmar migraciones y luego arrancar el runtime mediante su wrapper sin credenciales administrativas. Repetir el bootstrap debe rechazarse como volumen ya inicializado.

### LF015-T03 — diagnóstico seguro del bootstrap PostgreSQL

- FAIL ENVIRONMENT: dos inicializaciones sintéticas independientes, proyectos `lf015t03isolated` y `lf015t03diag`, terminaron con código 2. Ambas crearon el volumen; la primera dejó `PG_VERSION`, `base`, `global` y `pg_wal`. Los contenedores administrativos temporales fueron eliminados. La captura externa filtró los mensajes originales, por lo que la causa funcional exacta continúa `NOT_VERIFIED`; esos resultados no acreditan fallo de una fase PostgreSQL concreta.
- Defecto diagnóstico SYSTEM corregido: `bootstrap_postgres.sh` descartaba salida crítica mediante `/dev/null` y dependía de `set -e`; `apply_migrations.sh` y `sync_database_roles.sh` usaban `mapfile < <(...)`, construcción que no permite comprobar de forma directa el estado del productor. Esto podía convertir el primer error en configuración vacía o en un código genérico.
- Implementación SYSTEM: cada fallo emite exclusivamente `phase`, `operation`, `status=FAIL`, `exit_code` real y un `error_id` estable `LF015-PG-*`. Se distinguen autorización, validación, clasificación del volumen, arranque, salud, configuración, sincronización/topología de roles, migración inicial, transferencia de ownership, migraciones posteriores, verificación y cleanup.
- Seguridad: stderr/stdout sin sanitizar de Docker, Compose y psql no se propaga. Los diagnósticos pertenecen a una lista cerrada; no incluyen argumentos, entorno, cadenas de conexión, SQL ni valores secretos. Los resultados estructurales necesarios se capturan, se comprueba primero el código del productor y solo después se procesan mediante `mapfile`.
- Cleanup: conserva el código del primer fallo, informa por separado fallos al detener o eliminar el contenedor y convierte un fallo de cleanup posterior a una ejecución exitosa en resultado no exitoso. No elimina volúmenes ni datos.
- PASS QA focalizada: diagnóstico bootstrap 7/7; portabilidad y propagación de errores de scripts PostgreSQL 14/14. Se probaron códigos de autorización/volumen/arranque/salud/migraciones/cleanup, productor fallido de configuración, sanitización con valor señuelo, cleanup tras fallo y caso exitoso. Sintaxis Bash/Python y `git diff --check`: PASS. No se ejecutaron Docker, GCP ni credenciales reales.
- NOT_VERIFIED ENVIRONMENT: la primera operación funcional que produjo código 2 en la VM sigue sin evidencia. La instrumentación no corrige ni atribuye una causa PostgreSQL; la próxima reproducción aislada debe aportar el primer `error_id` y su código.
- Siguiente gate Linux: usar un proyecto Compose sintético nuevo y secretos entregados al entorno por el mecanismo administrativo aprobado; habilitar `set -o pipefail`, ejecutar una sola vez `scripts/database/bootstrap_postgres.sh 2>&1 | tee <archivo_temporal_protegido>` y conservar `${PIPESTATUS[0]}` junto con las líneas `postgres_*`. No reutilizar los dos volúmenes fallidos ni filtrar nuevamente la salida. El archivo contiene solo diagnósticos sanitizados y debe eliminarse después de incorporar la evidencia al HANDOFF.

### LF015-T03 — puente seguro de recepción web

- Reutilización: el puente consume sin modificar el webhook interno existente `/webhook/leadflow`, su contrato `event_id/source/lead/interaction`, la allowlist de sources/interests y la autenticación `X-LeadFlow-Key`. No se modificaron Core, workflow, migraciones ni formulario Lovable.
- Implementación SYSTEM: `bridge/server.py` expone un contrato JSON estricto para `nombre`, `apellido`, `email`, `negocio`, `telefono`, `interes` y `mensaje`; email e interés son obligatorios y los demás opcionales. Rechaza tipos, longitudes, controles, claves duplicadas, campos inesperados, email inválido e intereses fuera de allowlist antes de cualquier llamada interna.
- Identidad corregida: el puente exige `X-LeadFlow-Submission-Id`, UUID v4 canónico en minúsculas generado por el cliente para cada consulta y conservado en sus reintentos. `event_id` deriva exclusivamente mediante HMAC-SHA-256 de ese UUID con el prefijo de propósito `LF015-WEB-EVENT-ID-V1 NUL` y la clave privada `WEB_BRIDGE_EVENT_ID_KEY`. El payload y la PII no forman parte del identificador.
- PASS SYSTEM: mismo UUID produce el mismo evento aunque el formulario sea reintentado; UUID distintos producen eventos distintos aun con contenido idéntico. Formato ausente, no UUID v4, mayúsculas o forma no canónica se rechazan antes del upstream. La clave HMAC es obligatoria, distinta de webhook/abuse y permanece solo en configuración del servidor.
- BLOCKED / WARN de binding: si se reutiliza un UUID con contenido distinto, ambos envíos conservan el mismo `event_id`, por lo que la deduplicación vigente evita un segundo efecto comercial. El puente no puede demostrar el cambio ni devolver conflicto sin estado durable. No se añadió una caché en memoria ni almacenamiento improvisado. El mínimo pendiente es un registro atómico de frontera, con `event_id`, fingerprint HMAC del contenido y retención/DSR aprobadas, operado con identidad separada; PostgreSQL dedicado o un servicio administrado requieren decisión de arquitectura y privacidad.
- Seguridad SYSTEM: `source` solo proviene de configuración y debe estar permitido; la clave del webhook nunca viene del cliente. Se aplican límites de cuerpo, timeouts de lectura/upstream, JSON único, respuestas públicas genéricas, logs por códigos permitidos y ausencia de payloads/headers/PII/secretos. El cliente HTTP no sigue redirects del upstream.
- Empaquetado: `compose.web-bridge.yaml` es opt-in mediante perfil, no publica puertos y configura filesystem read-only, usuario no-root desde la imagen, eliminación de capabilities y `no-new-privileges`. Endpoints, ruta, source, origins, límites y secretos permanecen externos.
- Antibot/rate limiting: production falla al iniciar si no se declaran origins HTTPS, modo `external` y token independiente de atestación. Cada POST exige ese token, previsto para ser eliminado del cliente e inyectado por una frontera confiable. Esto no implementa ni acredita por sí mismo rate limiting, WAF o CAPTCHA; CORS tampoco se considera autenticación.
- PASS QA previa no repetida: HTTP/validación/seguridad 9/9. QA focalizada de identidad 7/7: mismo UUID/misma consulta, UUID distintos/contenido idéntico, UUID inválido, UUID reutilizado/contenido distinto, preflight CORS limitado y clave criptográfica ausente. Compilación Python y `git diff --check`: PASS. Solo se usaron loopback, mocks y datos sintéticos con cleanup.
- WARN / NOT_VERIFIED HYBRID/ENVIRONMENT: integración del mapa de secretos, custodia/rotación de la nueva clave HMAC y token de atestación, reverse proxy que elimine headers aportados por el cliente e inyecte el token, rate limiting/antibot real, HTTPS/DNS, política de origins, red interna y observabilidad efectiva no se validaron. El componente no está desplegado ni expuesto.
- Siguiente gate: decidir si el piloto exige rechazo demostrable de UUID reutilizado con contenido distinto. Si se exige, aprobar primero el registro durable mínimo, su fingerprint con clave separada, identidad, concurrencia y retención; después integrar Lovable para generar/conservar el UUID v4. Sin esa decisión, solo puede validarse la deduplicación segura existente, no el conflicto de contenido.

#### Validación Turnstile SYSTEM

- Implementación: el puente recibe `X-Turnstile-Token` separado de los siete campos y lo valida por HTTPS contra Cloudflare Siteverify antes del webhook. Exige respuesta JSON acotada con `success=true`, hostname autorizado y action exacta cuando está configurada. Un resultado ausente, denegado, incompleto, malformado, inconsistente, con timeout o error de transporte falla cerrado y no llega a LeadFlow.
- Configuración: producción exige `WEB_BRIDGE_TURNSTILE_MODE=siteverify`, `WEB_BRIDGE_TURNSTILE_SECRET_KEY` externa, `WEB_BRIDGE_TURNSTILE_HOSTNAMES` explícito y, opcionalmente, `WEB_BRIDGE_TURNSTILE_ACTION`; `disabled` solo está permitido fuera de producción para aislamiento controlado. La Secret Key debe ser distinta de las claves webhook, event-id y atestación de abuso. No se incorporaron secretos al repositorio.
- Privacidad y reintentos: ni token, Secret Key ni respuesta Siteverify se propagan a EVENT/LEAD/INTERACTION, logs o errores públicos. El UUID y payload mantienen su identidad durante el reintento, mientras el cliente puede renovar exclusivamente el token Turnstile.
- PASS SYSTEM: compilación Python y batería focalizada del puente 20/20. Se cubrieron token válido, respuesta Siteverify autorizada, token ausente, formato inválido, rechazo Siteverify, hostname/action incorrectos, respuesta incompleta, timeout/error, configuración crítica ausente, no-forwarding y reintento con token renovado e identidad estable. Solo se usaron mocks, loopback y datos sintéticos; no hubo llamadas a Cloudflare ni GCP.
- WARN / NOT_VERIFIED ENVIRONMENT: widget real, hostname/action efectivos, conectividad saliente TLS, custodia/inyección de Secret Key, HTTPS público, reverse proxy, rate limiting y protección de abuso real siguen sin validación. Turnstile reduce abuso automatizado, pero no sustituye rate limiting ni autentica por sí solo al cliente.
- Siguiente gate: integrar el widget en un entorno aislado con hostname/action aprobados e inyectar la Secret Key desde el gestor autorizado; ejecutar una única solicitud sintética end-to-end y confirmar que un token válido llega al mock y uno inválido no lo alcanza, antes de habilitar tráfico público.

#### Carga independiente de secretos del Web Bridge

- Implementación SYSTEM: `scripts/admin/web_bridge_with_secrets.py` conserva el contrato versionado `LF015-WEB-BRIDGE-SECRET-MAP-1`, proveedor único `gcp-secret-manager` y operación `web-bridge-compose`. El mapa exige exactamente cuatro aliases: `WEB_BRIDGE_TURNSTILE_SECRET_KEY`, `WEB_BRIDGE_ABUSE_TOKEN`, `LEADFLOW_WEBHOOK_KEY` y `WEB_BRIDGE_EVENT_ID_KEY`. Cada alias queda ligado al ID de secreto autorizado y a una referencia con versión numérica; no admite sustitución por otro secreto, `latest`, duplicados ni valores heredados. Reutiliza el proveedor seguro de metadata/Secret Manager sin modificar `compose_with_secrets.py` ni su operación `runtime-compose`.
- Separación: exige `WEB_BRIDGE_COMPOSE_PROJECT` y `LEADFLOW_COMPOSE_PROJECT` válidos y distintos, usa únicamente `compose.web-bridge.yaml` y el perfil `web-bridge`, deshabilita la carga implícita de `.env` y entrega valores solo mediante el entorno del proceso hijo. `preflight` ejecuta exclusivamente `docker compose ... config -q`; no crea ni reinicia servicios. El futuro `start` apunta únicamente al servicio `web-bridge` del proyecto separado.
- Seguridad: rechaza mapas incompletos o con aliases adicionales, proveedor/operación incorrectos, IDs no autorizados, referencias no numéricas o duplicadas, identidad incorrecta, credenciales locales/metadata ambiguas, timeout, ausencia/denegación IAM y payload inválido. Los cuatro secretos se eliminan del entorno heredado y se reemplazan exclusivamente por los valores resueltos; no aparecen en argumentos, archivos, stdout, stderr ni errores. Las salidas de Compose se capturan y descartan.
- Configuración externa no sensible: antes de resolver secretos exige `WEB_BRIDGE_ENV`, `WEB_BRIDGE_PUBLIC_PATH`, `WEB_BRIDGE_UPSTREAM_URL`, `WEB_BRIDGE_SOURCE`, `WEB_BRIDGE_ALLOWED_ORIGINS`, `WEB_BRIDGE_ABUSE_CONTROL`, `WEB_BRIDGE_TURNSTILE_MODE`, `WEB_BRIDGE_TURNSTILE_HOSTNAMES`, `LEADFLOW_ALLOWED_SOURCES`, `LEADFLOW_ALLOWED_INTERESTS` y `WEB_BRIDGE_UPSTREAM_NETWORK`, además de los dos proyectos Compose distintos. Sus valores dependen del entorno y no se fijan en Git; action y límites/timeouts conservan su carácter opcional/default en Compose. El nombre de red se valida como identificador Docker y nunca se deriva ni se hardcodea.
- PASS SYSTEM: compilación Python y pruebas focalizadas del cargador 6/6. Se verificaron mapa exacto y resolución simulada de cuatro secretos, reemplazo de valores heredados, identidad/credenciales ambiguas, ID/referencia no autorizados, `latest`, duplicados, secreto ausente, permiso denegado, timeout, configuración/proyectos incompletos, no filtración, aislamiento de los Compose principales y preflight sin `start`. Se usaron proveedores simulados, temporales con cleanup y valores sintéticos; no se ejecutaron Docker, metadata ni Secret Manager reales.
- PASS reportado / NOT_VERIFIED ENVIRONMENT: se registra como evidencia externa proporcionada que Turnstile y Abuse Token versión 1 pudieron leerse en GCP y que los cuatro secretos versión 1 tienen bindings confirmados para `leadflow-runtime`. Esta ejecución no consultó GCP. La lectura agrupada real de los cuatro secretos, identidad efectiva, configuración completa, compatibilidad Compose, suministro al contenedor y Siteverify permanecen `NOT_VERIFIED` hasta el preflight supervisado.
- WARN residual: `leadflow-runtime` es identidad de toda la VM, no una frontera exclusiva del puente. Procesos con acceso a metadata, root o Docker pueden compartir esa capacidad; el cargador evita exposición accidental, pero no aporta aislamiento IAM entre procesos del mismo host.
- Siguiente gate VM: actualizar fuera de Git el mapa V1 con las cuatro referencias versión 1 e identidad `leadflow-runtime@emactiva-leadflow-pilot.iam.gserviceaccount.com`; exportar únicamente la configuración no sensible aprobada y proyectos principal/puente distintos; ejecutar solo `python3 scripts/admin/web_bridge_with_secrets.py preflight --map <ruta_protegida>`. No ejecutar `start`, mostrar `docker compose config` ni habilitar la landing durante este gate.

#### Red externa y preflight aislado del Web Bridge

- Corrección SYSTEM: `compose.web-bridge.yaml` dejó de crear/usar la red `default` del proyecto aislado y conecta exclusivamente el servicio `web-bridge` a una red Docker externa cuyo nombre procede de `WEB_BRIDGE_UPSTREAM_NETWORK`. El Compose no contiene el nombre real de la red, IP, dominio ni puerto publicado. El proyecto del Bridge continúa siendo distinto del proyecto principal.
- PASS SYSTEM nuevo: prueba focalizada de red 1/1 y compilación Python PASS. Se comprobó red externa parametrizada, rechazo de variable ausente o nombre inválido, ausencia del nombre real conocido en Git, ausencia de `ports` y fallo antes de resolver secretos. No se repitieron las seis pruebas cerradas del cargador ni las pruebas del puente.
- WARN HYBRID: compartir la red externa permite al Bridge alcanzar n8n, pero también puede darle visibilidad de otros contenedores conectados a esa red. Docker networking no sustituye autenticación `X-LeadFlow-Key`, políticas host/firewall ni una red dedicada; la segmentación efectiva requiere inspección y decisión de infraestructura.
- NOT_VERIFIED ENVIRONMENT: existencia y attachability de la red configurada, alias DNS efectivo de n8n, ruta webhook interna, conexión Bridge→n8n:5678, resolución Siteverify, preflight Compose en la VM y ausencia posterior de puertos publicados no se probaron en esta ejecución.
- Procedimiento supervisado: (1) transferir únicamente `compose.web-bridge.yaml` y `scripts/admin/web_bridge_with_secrets.py`, conservando el mapa privado ya preparado en la VM; (2) exportar los dos proyectos distintos y las once variables no sensibles requeridas con valores aprobados —incluida la red externa existente—, usando para upstream el alias/ruta internos verificados por el operador; (3) ejecutar `docker network inspect "$WEB_BRIDGE_UPSTREAM_NETWORK"` y confirmar que n8n está conectado, sin modificar la red; (4) ejecutar exclusivamente `python3 scripts/admin/web_bridge_with_secrets.py preflight --map <ruta_protegida>`; (5) si el preflight es PASS, obtener autorización separada antes de `start`; (6) después del arranque autorizado, verificar proyecto, red, health y ausencia de puertos publicados, y realizar solo una solicitud sintética interna. Ante cualquier fallo, retirar exclusivamente el servicio/proyecto del Bridge; nunca limpiar la red externa ni los ocho contenedores existentes.
- Siguiente paso exacto: transferir los dos archivos SYSTEM modificados, definir la configuración no sensible aprobada y ejecutar primero la inspección read-only de la red; solo si n8n pertenece a ella, ejecutar el preflight aislado. La landing permanece en demostración.

#### Bloque funcional y de seguridad Web Bridge — 13-11-2026

- Evidencia GCP reportada, no ejecutada por Codex: `web_bridge_secret_runtime phase=start status=PASS`; proyecto QA `lf015-t03-bridge-qa` iniciado sin puertos publicados sobre la red externa configurada; ocho contenedores operativos conservados; respuesta HTTP 200 en el healthcheck interno de n8n. Estos PASS no acreditan todavía Turnstile, el webhook funcional ni la landing extremo a extremo.
- Ajuste SYSTEM: PUT, PATCH y DELETE ahora reciben 405 sanitizado y no alcanzan el upstream, en vez de depender del 501 genérico de `BaseHTTPRequestHandler`. Se añadió cobertura directa de source fuera de allowlist y respuestas upstream 302/500, que permanecen fail-closed como 503 genérico.
- PASS SYSTEM nuevo: 2/2 pruebas focalizadas del contrato HTTP y 3/3 del procedimiento GCP; compilación Python PASS. Se verificaron métodos no permitidos, source, upstream inesperado, preflight read-only, red/puertos, gate funcional, paso de token solo por stdin y ausencia de `compose up/start`. Las pruebas históricas de validación, origen, Turnstile, timeout, upstream indisponible y sanitización se reutilizan como evidencia cerrada y no se repitieron.
- Procedimiento: `scripts/test/validate_web_bridge_gcp.py` localiza exactamente un contenedor por labels del proyecto/servicio, comprueba estado, red externa y ausencia de bindings publicados, y ejecuta desde el propio Bridge un healthcheck a la URL interna configurada. Por defecto termina con funcional `NOT_VERIFIED`. `--functional` exige `WEB_BRIDGE_QA_EXTERNAL_EFFECTS_DISABLED=true`, interés sintético permitido y un token Turnstile efímero leído de forma oculta; el token pasa por stdin y el abuse token se lee solo dentro del contenedor. No ejecuta `start`, `up`, cambios de red ni inspección completa del entorno del contenedor.
- Cleanup: el procedimiento no crea contenedores, redes, archivos ni volúmenes temporales. Una solicitud funcional puede crear evidencia sintética sujeta a la retención normal del sistema; no la elimina ni ejecuta DSR, por lo que reporta cleanup `NOT_APPLICABLE policy=retention` y debe usarse solo cuando el upstream QA esté confirmado sin efectos externos.
- WARN HYBRID: `WEB_BRIDGE_ABUSE_CONTROL=external` solo prueba que el Bridge exige una atestación. La eficacia de proxy/WAF/rate limiting, eliminación del header aportado por clientes y custodia en la frontera sigue siendo ENVIRONMENT. Compartir red Docker conserva visibilidad lateral y la identidad administrada sigue perteneciendo a toda la VM.
- NOT_VERIFIED ENVIRONMENT: solicitud real con token Turnstile, Siteverify, forwarding al webhook n8n, respuesta controlada y comportamiento landing→frontera pública permanecen pendientes. La landing sigue en demostración; no hay autorización de producción, DNS/TLS/firewall ni exposición pública.
- Siguiente paso exacto: transferir `bridge/server.py` y `scripts/test/validate_web_bridge_gcp.py` al source aislado; exportar `WEB_BRIDGE_COMPOSE_PROJECT`, `LEADFLOW_COMPOSE_PROJECT`, `WEB_BRIDGE_UPSTREAM_NETWORK`, `WEB_BRIDGE_N8N_HEALTH_URL`, `WEB_BRIDGE_PUBLIC_PATH` y `WEB_BRIDGE_ALLOWED_ORIGIN`; ejecutar primero `python3 scripts/test/validate_web_bridge_gcp.py`. Solo si termina preflight PASS, confirmar documentalmente que el workflow QA no produce efectos externos y entonces ejecutar una vez con `--functional`, ingresando el token efímero sin eco. Detenerse ante el primer FAIL y no reiniciar servicios.

#### Corrección de entorno QA del Web Bridge

- FAIL ENVIRONMENT reportado: el contenedor QA terminó con código 1 y entró en reinicios porque `WEB_BRIDGE_ENV=qa` era rechazado como `configuration_environment`; el operador lo detuvo después de 24 reinicios. No se atribuyen otros fallos funcionales a esa ejecución.
- Causa confirmada: `BridgeConfig.from_env()` admitía exclusivamente `development` y `production`, mientras la configuración aprobada del despliegue aislado usa `qa`.
- Corrección SYSTEM: `qa` se admite explícitamente y pertenece a `SECURE_ENVIRONMENTS` junto con `production`. Ambos exigen origins HTTPS explícitos, `WEB_BRIDGE_ABUSE_CONTROL=external` con token válido y Turnstile `siteverify` con Secret Key y hostnames autorizados. No se añadió bypass ni fallback a development.
- PASS SYSTEM: prueba focalizada 1/1 y compilación Python PASS. El caso cubre QA seguro válido, rechazo QA por origin HTTP/ausente, antiabuso ausente/deshabilitado, Turnstile deshabilitado o incompleto, entorno desconocido, compatibilidad production y contrato development vigente.
- Compatibilidad: `compose.web-bridge.yaml` ya transporta `WEB_BRIDGE_ENV` externamente; el cargador de cuatro secretos solo exige que esté presente y el procedimiento GCP no interpreta su valor. No requirieron cambios. La corrección no modifica Core, n8n, PostgreSQL, redes ni secretos.
- NOT_VERIFIED ENVIRONMENT: imagen reconstruida, arranque estable del contenedor con `WEB_BRIDGE_ENV=qa`, ausencia de nuevos reinicios y preflight/procedimiento GCP posteriores. El PASS operacional no se declara hasta validar la VM.
- Siguiente paso exacto: transferir únicamente `bridge/server.py`, reconstruir/recrear exclusivamente el servicio del proyecto `lf015-t03-bridge-qa` bajo autorización operativa y verificar primero estado estable/log sanitizado; después ejecutar `python3 scripts/test/validate_web_bridge_gcp.py` sin `--functional`. No intervenir los ocho contenedores principales.

#### Receptor QA aislado para Web Bridge

- Evidencia ENVIRONMENT reportada: Web Bridge QA reconstruido y operativo con cuatro secretos, cero reinicios, sin puertos publicados y preflight GCP PASS. Siteverify real continúa `NOT_VERIFIED` y la prueba funcional quedó bloqueada porque el webhook comercial activo no acredita ausencia de efectos externos.
- Diseño SYSTEM: `bridge/qa_receiver.py` implementa un receptor stateless con biblioteca estándar. Acepta únicamente POST JSON compatible con `event_id/source/lead/interaction` en una ruta configurable, exige `X-LeadFlow-Key` con comparación constante, limita cuerpo/lectura y devuelve exclusivamente `202 {"ok":true,"status":"received_qa"}`. No importa clientes HTTP, no escribe archivos, no persiste datos y no invoca servicios externos. Métodos mutantes no permitidos devuelven 405 y errores/logs contienen solo códigos estables.
- Contenedor: `compose.web-bridge-qa-receiver.yaml` es opt-in, usuario no-root, filesystem read-only, sin restart automático, capabilities eliminadas, `no-new-privileges`, sin `ports`, volúmenes ni archivos de secretos. Crea una red QA `internal` con nombre externo configurable y etiquetas de propiedad LAB; el receptor se conecta solo a esa red. El Bridge usa la misma red mediante su parámetro externo y deja de necesitar la red principal durante este gate.
- Secretos: el procedimiento reutiliza `web_bridge_with_secrets.py` y su mapa oficial de cuatro secretos. Para el proceso Compose del receptor filtra los otros tres y entrega exclusivamente `LEADFLOW_WEBHOOK_KEY`; no existe un segundo proveedor ni mapa genérico. Ruta, puerto, proyectos, red y upstream permanecen configuración externa.
- PASS SYSTEM: receptor 6/6 y procedimiento 5/5; compilación Python PASS. Se cubrieron POST sintético, respuesta controlada, autenticación ausente/incorrecta, métodos, JSON/contrato/tamaño inválidos, configuración fail-closed, ausencia estática de salida/persistencia, Compose endurecido, red interna, no puertos, secreto mínimo, upstream comercial rechazado, proyectos/red ambiguos, dry-run, autorización APPLY y comandos limitados a los dos proyectos QA. El primer fallo de prueba por cierre HTTP con cuerpo no consumido se corrigió añadiendo `Connection: close`; la repetición quedó PASS.
- Procedimiento GCP: `scripts/test/deploy_web_bridge_qa_receiver.py` ofrece `preflight`, `apply`, `verify` y `rollback`. Por defecto solo valida archivos/herramientas, ocho IDs principales, propiedad de recursos reanudados, ambos Compose mediante `config -q`, cuatro secretos y que el upstream sea exactamente `http://qa-receiver:<puerto><ruta_QA>` sobre una red distinta de la principal. APPLY exige `--authorize-apply`, inicia solo receptor/Bridge QA y confirma que los ocho IDs principales no cambiaron. VERIFY comprueba estado, red exclusiva, ausencia de puertos, upstream efectivo y health; `--functional` conserva Turnstile real y token efímero por stdin. ROLLBACK exige URL/red previas explícitas, restaura primero Bridge y elimina después solo el proyecto receptor.
- Cleanup/rollback: no existen volúmenes ni datos del receptor. `down --remove-orphans` se limita al proyecto receptor y su red etiquetada, después de restaurar Bridge. Nunca elimina la red principal. Si propiedad, estado previo o restauración son ambiguos, falla cerrado y requiere intervención.
- WARN: APPLY recrea exclusivamente el Bridge QA para cambiar su red/upstream; no es una operación sin impacto sobre ese contenedor. La red `internal` impide salida directa del receptor, pero el Bridge conserva salida necesaria para Siteverify. Acceso Docker/root e identidad VM siguen siendo fronteras compartidas.
- NOT_VERIFIED ENVIRONMENT: build/arranque del receptor, red QA real, cambio controlado del Bridge, health, rollback, token Turnstile válido y flujo Bridge→receptor. Landing, TLS/proxy/rate limiting públicos continúan fuera de este gate.
- Siguiente gate exacto: transferir `bridge/qa_receiver.py`, `bridge/Dockerfile.qa-receiver`, `compose.web-bridge-qa-receiver.yaml` y `scripts/test/deploy_web_bridge_qa_receiver.py`; configurar proyectos QA distintos, red QA nueva, ruta/puerto y upstream exacto al receptor; ejecutar `python3 scripts/test/deploy_web_bridge_qa_receiver.py preflight --map <ruta_privada>`. Solo con PASS, autorizar y ejecutar `apply`, luego `verify`; reservar `verify --functional` para un token efímero válido. La landing permanece en demostración.

#### Corrección del inventario principal del receptor QA

- FAIL ENVIRONMENT reportado: `preflight` terminó con `error_id=main_container_count` aunque el proyecto principal `emactiva-leadflow` conservaba sus seis servicios operativos saludables. La causa fue una validación SYSTEM que exigía de forma fija ocho contenedores.
- Corrección SYSTEM: `LEADFLOW_EXPECTED_MAIN_CONTAINERS` continúa siendo configuración externa obligatoria, sin valor por defecto, y ahora acepta cualquier entero positivo. El procedimiento conserva la comparación exacta entre el inventario real y el valor configurado; una divergencia sigue fallando cerrada con `main_container_count`.
- Protecciones conservadas: no cambiaron los gates de proyectos separados, red QA, propiedad de recursos ni la instantánea exacta de IDs principales antes y después de APPLY.
- PASS SYSTEM: compilación Python y tres pruebas focalizadas. Inventario 6 con `expected=6` fue aceptado; inventario 6 con `expected=8`, valor ausente, cero e inválido fueron rechazados; preflight siguió siendo no mutante y APPLY mantuvo la protección de identidades.
- NOT_VERIFIED ENVIRONMENT: el preflight corregido aún no se ejecutó en la VM. Siguiente paso exacto: transferir `scripts/test/deploy_web_bridge_qa_receiver.py`, configurar `LEADFLOW_EXPECTED_MAIN_CONTAINERS=6` y repetir exclusivamente `python3 scripts/test/deploy_web_bridge_qa_receiver.py preflight --map <ruta_privada>`; no ejecutar APPLY hasta obtener ese PASS.

#### Dependencia final de Siteverify real

- Revisión SYSTEM: `verify --functional` ya lee el token mediante prompt sin eco, lo conserva solo en memoria, lo entrega por stdin al proceso dentro del Bridge y no lo incorpora a argumentos, archivos ni salida. El Bridge lo valida con Siteverify y solo después reenvía al receptor QA; un rechazo impide el forwarding.
- Bloqueo ENVIRONMENT exacto: este repositorio no contiene página, frontend ni widget capaz de emitir un token Turnstile real para `emactivaspa.lovable.app`. Tampoco se pudo verificar desde este entorno la integración vigente de esa página. La prueba requiere la Site Key real asociada al hostname/action configurados y una sesión humana de navegador; una clave o token de prueba no acredita Siteverify real.
- No se requirió cambio de código. El token real es efímero y de un solo uso: debe obtenerse del callback del widget autorizado e introducirse inmediatamente en el prompt de una única ejecución `verify --functional`. PASS exige `qa_receiver phase=verify status=PASS` y la respuesta 202 del receptor; ante el primer FAIL se conserva el `error_id`, no se reutiliza el token y no se repite automáticamente.

#### Egress controlado para Siteverify QA

- Causa ENVIRONMENT confirmada: DNS de la VM PASS, DNS del Bridge FAIL y red QA `internal=true`; Siteverify terminó en `turnstile_unavailable`/HTTP 503. No se repitieron los PASS del formulario, Bridge, receptor, preflight, APPLY ni VERIFY.
- Solución SYSTEM: el Bridge permanece conectado exclusivamente a la red QA interna y usa `WEB_BRIDGE_TURNSTILE_PROXY_URL` para un túnel TLS CONNECT. `qa-egress` es la única frontera dual-homed; no publica puertos, no recibe secretos, no persiste datos y solo acepta la autoridad exacta `challenges.cloudflare.com:443`. Resuelve el nombre sin IP hardcodeada, rechaza toda respuesta DNS que no sea global —incluidos metadata, loopback, link-local y destinos privados— y limita solicitud, tiempo y bytes del túnel. El TLS continúa extremo a extremo entre Bridge y Cloudflare.
- Compose/procedimiento: la red del receptor conserva `internal=true`; la red de egress tiene nombre externo configurable y etiquetas de propiedad LAB. Preflight exige tres redes distintas, proxy exacto, proyectos separados, ownership de redes existentes y configuración Compose. APPLY inicia solo servicios QA y recrea el Bridge con el proxy. VERIFY comprueba redes, ausencia de puertos, upstream, proxy efectivo y handshake TLS a Siteverify antes de la opción funcional. La solicitud funcional conserva UUID v4 canónico con guiones, datos sintéticos y token por prompt oculto.
- Rollback/cleanup: restaura primero URL, red y modo de proxy anteriores del Bridge; después elimina exclusivamente `qa-egress` y su red etiquetada. Conserva receptor, red QA interna y proyecto principal. Una red de egress ya ausente se considera cleanup idempotente; ownership ambiguo/ajeno o cualquier comando fallido se detiene fail-closed.
- PASS SYSTEM focalizado: compilación Python; seis pruebas iniciales PASS y la única aserción defectuosa del test —confundía el nombre del archivo Compose con el servicio receptor— fue corregida y repetida PASS. Cobertura final afectada 7/7: CONNECT permitido/rechazado, IP privada/metadata, túnel Bridge, topología, preflight no mutante, APPLY acotado y rollback exclusivo de egress.
- WARN: la red de egress tiene NAT, pero solo el proxy endurecido se conecta a ella; Docker/root continúan siendo fronteras privilegiadas. El control de dominio es SYSTEM/aplicativo y no sustituye una política egress administrada del host.
- NOT_VERIFIED ENVIRONMENT: build, DNS del proxy, TLS real, Siteverify con token real, respuesta 202 del receptor y rollback en la VM apagada.
- Secuencia agrupada GCP: transferir los seis archivos operativos modificados de código/Compose, definir una red egress nueva y los valores previos explícitos, ejecutar `preflight`, `apply --authorize-apply`, `verify`, una sola vez `verify --functional` con token real, registrar las líneas `qa_receiver`, y finalizar con `rollback --authorize-apply`. Ante el primer FAIL no continuar; si APPLY ya ocurrió, ejecutar solo rollback y conservar su evidencia.

#### Consolidación del build del Bridge QA

- FAIL ENVIRONMENT confirmado: APPLY reutilizó una imagen Web Bridge anterior al fuente transferido. La recuperación supervisada reconstruyó el Bridge mediante el cargador de cuatro secretos existente.
- Evidencia GCP reportada y no repetida: proxy, aislamiento, DNS y TLS PASS; build mediante el cargador PASS; SHA-256 del fuente y contenido del contenedor coincidentes; Siteverify real y entrega al receptor QA PASS; rollback PASS; VM detenida.
- Corrección SYSTEM: `web_bridge_with_secrets.run_compose()` incorpora acciones explícitas. El inicio directo conserva `up --build`; APPLY ejecuta primero `build web-bridge` y solo tras su éxito inicia los servicios QA y usa `up --no-build`, evitando una segunda reconstrucción. Rollback también usa `--no-build`, porque restaura configuración con la imagen ya construida. Docker puede reutilizar su caché por contenido, pero una imagen stale ya no puede pasar APPLY sin invocar el build.
- Fail-closed: un fallo de build ocurre antes de cualquier `up`; APPLY no declara PASS ni inicia receptor, proxy o Bridge. No se imprimen salidas del builder ni secretos.
- PASS SYSTEM focalizado: compilación Python y cuatro controles afectados PASS —comandos build/cache, orden build→servicios, fallo de build sin arranque y rollback sin rebuild—. La primera ejecución encontró una aserción de test que confundía el nombre del archivo Compose con el proyecto; corregida a `--project-name`, quedó PASS sin cambio productivo.
- NOT_VERIFIED ENVIRONMENT: el APPLY modificado no se ha repetido en GCP. El próximo despliegue debe demostrar build previo, hash actualizado y arranque posterior antes de promover esta corrección a PASS ambiental.

#### Gateway HTTPS local con Caddy

- Implementación SYSTEM: `compose.web-gateway.local.yaml` crea un proyecto independiente con Caddy oficial fijado a versión, TLS mediante CA interna y publicación configurable cuyo default es loopback. Caddy solo acepta `/lead`, métodos POST/OPTIONS, limita cuerpo/cabeceras y tiempos, elimina headers internos aportados por el cliente y deriva una clave de rate por conexión. No comparte la red del Bridge.
- Frontera de política: `rate-gate` usa exclusivamente biblioteca estándar, no publica puertos y es el único enlace entre la red edge interna y la red externa ya usada por el Bridge. Valida allowlist HTTPS de Origin, ruta, método, cuerpo y configuración; reenvía solo headers públicos autorizados e inyecta `WEB_BRIDGE_ABUSE_TOKEN` desde el entorno protegido. Bridge, n8n y PostgreSQL no obtienen exposiciones nuevas.
- Rate limiting efectivo: ventana y cuota configurables por IP entregada por Caddy, respuesta 429 con `Retry-After`, recuperación tras la ventana, sincronización entre threads y cardinalidad total acotada con poda/rechazo fail-closed. Es deliberadamente local y en memoria; reiniciar el gate restablece contadores.
- Privacidad: no hay access log, payload/token/PII en diagnósticos ni persistencia del gate. Caddy registra solo nivel ERROR. Los volúmenes etiquetados contienen exclusivamente CA/certificados/configuración de Caddy y el cleanup autorizado es `docker compose ... down --volumes --remove-orphans` sobre su proyecto local.
- PASS SYSTEM focalizado: pruebas Python 4/4 cubrieron métodos/ruta, Origin, tamaño, suplantación de headers, inyección, rate limit/recuperación/cardinalidad, configuración ausente, aislamiento Compose y contrato TLS Caddy. Compilación Python PASS.
- NOT_VERIFIED local runtime: Docker daemon no estaba activo y Caddy no está instalado; no se ejecutaron `caddy adapt`, handshake TLS ni cleanup Compose real. No se instalaron dependencias. TLS público, DNS e infraestructura remota permanecen `NOT_VERIFIED ENVIRONMENT`.
- Riesgo residual: secretos en variables de entorno son visibles para operadores Docker/root; el rate limit por IP puede agrupar clientes detrás de NAT y no se comparte entre réplicas. Esta implementación solo autoriza QA local, no producción.
- Siguiente gate: iniciar Docker local, crear/conectar una red Bridge sintética, suministrar configuración y token sintéticos fuera de Git, ejecutar `config -q` y `up -d --build`, validar HTTPS con la CA local o `curl --insecure` exclusivamente en QA, repetir los negativos focalizados y finalizar con `down --volumes --remove-orphans` sobre el proyecto del gateway.

#### Corrección de publicación local del Gateway

- Causa confirmada: Caddy estaba conectado exclusivamente a `edge` con `internal=true`; el contenedor exponía `8443/tcp`, pero Docker no instalaba una publicación host efectiva. Se añadió `ingress`, red no interna y exclusiva de Caddy. `edge` conserva `internal=true`; `rate-gate` no pertenece a ingress y mantiene el único enlace hacia la red Bridge. La publicación continúa limitada por defecto a `127.0.0.1`.
- TLS: `skip_install_trust` desactiva la instalación automática de la CA sobre el contenedor read-only sin deshabilitar `tls internal`. La CA y certificados siguen en el volumen etiquetado de Caddy.
- PASS SYSTEM focalizado: prueba afectada 1/1; verificó CA interna sin auto-instalación, red ingress exclusiva, edge interna, ausencia de Caddy en la red Bridge y única declaración de `ports` con bind loopback.
- Evidencia Docker local nueva: ambos contenedores arrancaron; `rate-gate` informó startup PASS; Docker mostró `127.0.0.1:18443->8443/tcp`; la CA se extrajo explícitamente; los logs se capturaron antes del cleanup y no mostraron payloads, secretos ni el error previo de instalación de CA.
- Primer FAIL real posterior: `curl.exe`/Schannel rechazó la cadena con `CERT_TRUST_REVOCATION_STATUS_UNKNOWN` aun usando `--cacert`; ambas solicitudes devolvieron HTTP 000. Por instrucción no se repitió el ciclo. HTTPS 404/405 mediante CA explícita queda `NOT_VERIFIED`, no se atribuye a Caddy sin una prueba con otro validador TLS.
- Cleanup Docker local: PASS. Se eliminaron contenedores, redes ingress/edge, volúmenes Caddy, red Bridge sintética y copia temporal de CA; la comprobación final no encontró recursos del proyecto.
- Siguiente paso exacto: repetir una sola vez el mismo proyecto aislado y validar con Python `ssl.create_default_context(cafile=<root.crt>)`, sin desactivar verificación de certificado; exigir 404 y 405, capturar `ps/logs` y ejecutar el mismo cleanup.

#### Integración local Gateway → Bridge → receptor QA

- Evidencia previa reutilizada: HTTPS con CA explícita, 404/405, publicación loopback, aislamiento y cleanup del Gateway permanecen PASS; no se repitieron esos gates cerrados.
- Preparación SYSTEM: `compose.web-bridge-local-integration.yaml` añade un Siteverify sintético únicamente para QA local, sobre red interna, sin puertos ni bypass de `WEB_BRIDGE_TURNSTILE_MODE=siteverify`. El Bridge confía exclusivamente en la CA efímera montada y conserva hostname/action. El primer fallo comprobado fue un healthcheck por IP incompatible con el virtual host TLS; se corrigió para consultar `challenges.cloudflare.com` y el contenedor quedó healthy.
- PASS focalizado: contrato estático 1/1; Compose de receptor, Bridge y Gateway validó; receptor, mock, Bridge, rate-gate y Caddy arrancaron; el mock Siteverify quedó healthy; ningún servicio salvo Caddy publicó puerto. Se reutilizaron imágenes existentes.
- FAIL integración: no se acreditó el 202 extremo a extremo. La primera corrida fue bloqueada por Schannel al consultar revocación de la CA privada local. En la segunda, el envío válido devolvió un estado distinto de 202, pero un error del bloque diagnóstico PowerShell impidió conservar el código y logs sanitizados. Por tanto recepción QA, protección dinámica del header y rate limiting previo al Bridge quedan `NOT_VERIFIED`; no se atribuye causa al producto sin evidencia.
- Cleanup Docker local: PASS en ambas corridas. La comprobación final no encontró contenedores, redes ni volúmenes `lf015-int-*`; la CA temporal fue eliminada. No hubo servicios externos, GCP, HubSpot ni datos reales.
- Siguiente paso exacto: corregir únicamente el capturador de evidencia para conservar códigos HTTP y logs antes del cleanup, usar un cliente TLS que valide la CA local sin depender de revocación pública y ejecutar una sola corrida aislada; detenerse en el primer estado distinto de 403/202/429.

#### Integración SYSTEM aislada con núcleo LeadFlow

- Implementación: `compose.core-qa.yaml` endurece el proyecto exclusivo `lf015-core-qa`: red interna sin egress, volúmenes propios, ningún puerto salvo n8n en loopback, proveedores CRM/enrichment/alertas mock y ausencia de claves de proveedores reales. `run_lf015_core_qa.py` aplica preflight fail-closed, fija `COMPOSE_PROJECT_NAME`/`COMPOSE_FILE`, reutiliza imágenes y scripts de roles, migraciones y n8n, conecta Bridge solo al n8n QA, usa Siteverify TLS sintético y cliente Python con CA explícita, contrasta PostgreSQL/CRM mock y limpia tres proyectos aun ante fallo.
- Aislamiento de credencial n8n: `provision_n8n.ps1` admite `LEADFLOW_N8N_LOCAL_DIR`; el default histórico no cambia. El runner usa un directorio temporal exclusivo, eliminado durante cleanup.
- PASS SYSTEM: pruebas focalizadas 2/2, compilación Python y `git diff --check`. Se verificaron estáticamente red interna, mocks obligatorios, no uso de `compose.production.yaml`, preflight contra recursos previos, imágenes `--no-build`, CA explícita y snapshot del proyecto principal.
- Ejecución local: se lanzó una sola corrida con credenciales/datos sintéticos. El canal de ejecución no conservó la línea final ni un `error_id`; por ello HTTP, PostgreSQL, estadísticas CRM e idempotencia quedan `NOT_VERIFIED`, no PASS.
- Cleanup/entorno principal: PASS verificable. No quedaron contenedores `lf015-core-qa`, `lf015-core-qa-bridge` ni `lf015-core-qa-gateway`; los seis contenedores `emactiva-leadflow` continuaron saludables y no fueron recreados. No se contactó GCP ni proveedores reales.
- Siguiente paso: ejecutar una sola vez el runner con captura durable y sanitizada de stdout/primer `error_id`; exigir `http`, `db=2|1|2`, `crm=1|2`, `external_effects=0`, cleanup PASS y los mismos seis IDs principales antes de promover el gate.

#### Cierre de integración SYSTEM Gateway → núcleo QA

- Diagnóstico seguro: el runner informa fase, operación, exit code y `error_id` allowlisted; captura estados/health sin logs ni payloads antes del cleanup. Si detecta contenedores, redes o volúmenes QA preexistentes aborta antes de adquirir ownership y no ejecuta `down`.
- Fallos corregidos: la allowlist `ADAPTER_ALLOWED_OPERATIONS="*"` era inválida y fue sustituida por las siete operaciones operativas explícitas, sin DSR. n8n healthy no era alcanzable desde host por la red interna; el probe opt-in ahora se ejecuta dentro del contenedor y no publica puerto. El contraste inicial contaba tres ejecuciones técnicas; el contrato idempotente correcto cuenta dos `idempotency_key` distintas y conserva tres ejecuciones auditables.
- PASS integrado local: HTTPS Gateway → rate-gate → Bridge → n8n → PostgreSQL → adapters/mocks devolvió HTTP `202/202/202`; PostgreSQL `db=2|1|2`, `executions=3`; CRM mock `contacts=1`, `interactions=2`; duplicado exacto sin contacto/interacción adicional; `idempotency=PASS`; `external_effects=0` por red core interna y proveedores exclusivamente mock.
- PASS QA focalizado: 2/2, compilación Python y `git diff --check`. Cleanup eliminó contenedores, redes, volúmenes, CA y directorio de credencial temporal propios. Los seis IDs del proyecto principal permanecieron idénticos y saludables.
- Riesgo/alcance: resultado exclusivamente SYSTEM/local con datos sintéticos. No acredita producción, GCP ni proveedores reales y no autoriza deployment.

#### Cierre de integracion local Gateway - Bridge - receptor QA (2026-11-14)

Estado: CLOSED PASS - bloque de integracion local SYSTEM.

Correcciones validadas:
- Caddy: NET_BIND_SERVICE requerido por la imagen.
- Red ingress exclusiva de Caddy y publicacion loopback.
- TLS interno con CA explicita y skip_install_trust.
- Eliminacion del borrado redundante de X-LeadFlow-Rate-Key; asignacion autoritativa conservada.
- CA publica Siteverify en volumen independiente de solo lectura para Bridge.
- Claves privadas aisladas y Bridge no privilegiado UID 65534.

Evidencia:
- HTTPS con CA verificada y rutas 404/405: PASS.
- Siteverify sintetico HTTPS 200, hostname/action: PASS.
- Integracion completa: HTTP 403/202/429: PASS.
- Proteccion del token interno de abuso: PASS.
- Recepcion autenticada y validada por receptor QA: PASS.
- Publicacion exclusiva loopback: PASS.
- Regresion focalizada final: 2/2 PASS.
- Cleanup sin recursos remanentes: PASS.
- git diff --check: PASS sin errores reportados.

Limitaciones:
- Receptor QA stateless; no acredita persistencia ni CRM.
- TLS publico, DNS y despliegue Gateway remoto: NOT_VERIFIED.
- Rate limiting local en memoria; riesgo NAT y multirreplica.
- LAB-LF-015, LF015-T03 y ticket #17 permanecen abiertos.

Siguiente paso:
- Integracion controlada con el nucleo LeadFlow.
- Validar EVENT, LEAD, INTERACTION y CRM conforme al gate pendiente.
- Mantener GCP detenida durante preparacion local.
- No repetir PASS cerrados sin cambio o regresion.
