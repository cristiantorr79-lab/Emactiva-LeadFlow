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
