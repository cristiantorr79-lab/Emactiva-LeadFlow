# HANDOFF LAB-LF-012

Documento final de HANDOFF. **LAB-LF-012: CERRADO FUNCIONALMENTE — PASS**.

## Objetivo y tickets

- Ticket padre: #1.
- Ticket interno: #6 — LF012-T01, contrato DSR HubSpot y operaciones no destructivas.
- Ticket interno: #7 — LF012-T02, DELETE/RESTRICT HubSpot con aprobación, idempotencia y reconciliación.
- Ticket #8 — LF012-T03, QA focalizada HubSpot DSR, cleanup y HANDOFF — **PASS**.
- Objetivo: cerrar técnicamente las acciones DSR HubSpot controlables de LOCATE, EXPORT, CORRECT y DELETE, y clasificar RESTRICT sin introducir semántica HubSpot en Core ni persistir payload DSR.

## Alcance y decisiones

- El Adapter incorpora `crm.dsr_locate`, `crm.dsr_export` y `crm.dsr_correct`, todas fail-closed por identidad y allowlist.
- LOCATE usa email verificado transitorio, lookup exacto, rechazo controlado de múltiples Contacts y conteo exclusivo de Tickets con `leadflow_interaction_key`.
- EXPORT se construye con lecturas dirigidas, sin Exports API ni archivos. Limita Contact a email, nombre, apellido, teléfono, empresa y enrichment configurado; limita INTERACTION LeadFlow a interest, message y referencia técnica.
- CORRECT solo admite `first_name`, `last_name`, `phone` y `company`; email, enrichment, propiedades arbitrarias y Tickets están prohibidos. Toda escritura se confirma por lectura posterior, incluso ante resultado de PATCH ambiguo.
- `verified_email` no se persiste ni se registra. El export solo transita en la respuesta administrativa y no entra en `dsr_provider_actions`, logs, errores ni evidencia.
- La coordinación reutiliza `record_dsr_provider_result`; no se creó persistencia paralela.
- ANNOTATE permanece como evidencia administrativa local. Replicarlo en HubSpot ampliaría innecesariamente el tratamiento: ejecución externa `N/A`, código `administrative_local_only`.
- DELETE externo se implementa en #7; RESTRICT HubSpot se clasifica NOT_VERIFIED/capability_not_available sin crear una capacidad ficticia.

## Evidencia y estado

| Control | Estado | Evidencia |
|---|---|---|
| Contrato y autorización de tres operaciones | PASS | prueba focalizada LF012 y regresión de auth |
| LOCATE existente/no encontrado/ambiguo | PASS | mocks HubSpot |
| Solo INTERACTION LeadFlow | PASS | Ticket sin key excluido |
| EXPORT minimizado y no persistido | PASS | allowlists y revisión de coordinación |
| CORRECT allowlist, email prohibido, idempotencia y reconciliación | PASS | mocks de PATCH y lectura posterior |
| Sanitización de logs y errores | PASS | captura focalizada sin email, payload ni secreto |
| Cierre de provider action pending | PASS | coordinación llama `record_dsr_provider_result` |
| CORRECT con ausencia local y Contact externo | PASS | PostgreSQL temporal + HubSpot simulado: acción pending creada, reconciliada y cerrada |
| ANNOTATE externo | N/A | local administrativo; `not_applicable` justificado |
| Prueba destructiva HubSpot real | PASS | runner opt-in E2E: preflight, setup sintético, DELETE, reconciliación, idempotencia, evidencia y cleanup |
| DELETE Contact HubSpot por `contactId` | PASS | GDPR delete real y ausencia concluyente posterior |
| Archive de Tickets LeadFlow | WARN | API soportada archiva a papelera; borrado permanente no demostrado |
| Identidad destructiva separada | PASS | llave normal, ausente e inválida rechazadas; llave DSR válida aceptada |
| DELETE local-not-found / external-present | PASS | provider action pending creada y coordinación habilitada |
| RESTRICT local | PASS | tombstone y bloqueo futuro verificados en PostgreSQL temporal |
| RESTRICT HubSpot | NOT_VERIFIED | capability unavailable; no se creó operación o propiedad ficticia |
| Runner DELETE real E2E | PASS | `REAL-DSR-DELETE: PASS; ticket_archive=warn` y `RESULT: PASS` |

Pruebas ejecutadas:

- `python -m py_compile adapters/server.py scripts/admin/dsr_admin.py scripts/test/test_lf012_hubspot_dsr.py` — PASS.
- `python scripts/test/test_lf012_hubspot_dsr.py` — PASS 21/21.
- `python scripts/test/test_lf012_correct_absent_coordination.py` — PASS 7/7.
- `python scripts/test/test_lf012_hubspot_delete.py` — PASS 19/19, incluida separación de identidades.
- `python scripts/test/test_lf012_delete_coordination.py` — PASS 11/11; base temporal eliminada.
- `python scripts/test/test_lf012_real_delete_preflight.py` — PASS 5/5, sin red ni escrituras.
- `python scripts/test/test_adapter_auth.py` — PASS 7/7.
- `python scripts/test/test_adapter_boundary_validation.py` — PASS 10/10.
- `python scripts/test/test_adapter_conformance.py` — PASS 26/26.

## Riesgos reales

- La asociación Contact → Tickets se rechaza como respuesta ambigua si HubSpot pagina más de 100 asociaciones; no se produce un conteo parcial silencioso.
- DELETE conserva el mismo límite: cualquier `paging` detiene el proceso antes de archivar Tickets o borrar el Contact.
- HubSpot documenta el endpoint de Ticket como archive hacia la papelera. La lectura normal posterior demuestra ausencia operativa, pero no borrado físico permanente; se conserva WARN hasta validación/provider capability posterior.
- Fuentes técnicas consultadas: [GDPR delete de Contact GA](https://developers.hubspot.com/changelog/new-v3-engagement-apis-in-beta-and-contacts-gdpr-delete-endpoint-moves-to-general-availability) y [archive de Ticket](https://br.developers.hubspot.com/docs/api-reference/crm-tickets-v3/basic/delete-crm-v3-objects-tickets-ticketId).
- La ejecución depende de aplicar la migración `022_dsr_hubspot_nondestructive.sql` y de autorizar las tres operaciones en `ADAPTER_ALLOWED_OPERATIONS`.
- Hunter conserva su calificación previa para LOCATE/EXPORT; este ticket cierra exclusivamente la acción HubSpot.

## Fallo detectado y corrección

Se confirmó que CORRECT con sujeto ausente localmente devolvía `local_status=not_found`, pero no creaba `hubspot/correct/pending`. La coordinación administrativa sí intentaba la corrección externa y luego `record_dsr_provider_result` fallaba con `provider action not found`.

La migración 022 ahora mantiene el estado global `partial` y crea las tres acciones técnicas también cuando CORRECT no encuentra sujeto local: HubSpot `pending`, Hunter `not_applicable/no_correction_contract` y Slack `not_applicable/no_subject_data`. La repetición del mismo `request_id` conserva una solicitud y tres acciones. La prueba integrada ejecutable confirmó el cierre posterior de HubSpot y que email, correcciones y payload no aparecen en evidencia persistente.

## Estado final y pendientes

- LF012-T01 (#6): **PASS**.
- LF012-T02 (#7): **PASS**.
- LF012-T03 (#8): **PASS**.
- LAB-LF-012: **CERRADO FUNCIONALMENTE — PASS**.
- No quedan pendientes `SYSTEM` dentro del alcance aprobado.
- Permanecen fuera de este cierre los pendientes `HYBRID/ENVIRONMENT` que requieran garantías o capacidades propias del proveedor.
- Ticket archive permanece **WARN**: ausencia operativa y visual demostrada, sin afirmar destrucción física irreversible interna del proveedor.
- HubSpot RESTRICT permanece **NOT_VERIFIED / capability_not_available**; no se declara una capacidad ficticia ni cobertura DSR externa completa.

## LF012-T02 — DELETE y clasificación RESTRICT

- DELETE conserva la aprobación independiente de PostgreSQL y verifica antes de la llamada que la solicitud persistida sea `delete`, que operador y aprobador sean distintos y que `hubspot/delete` esté `pending`.
- La ruta destructiva exige `DSR_ADAPTER_SERVICE_KEY`; `ADAPTER_SERVICE_KEY` es inválida para ella.
- La ausencia local también crea coordinación externa pending. La repetición por `request_id` no duplica solicitud ni acciones.
- Los Tickets se inventariarían antes de escribir; solo se archivan IDs cuya propiedad `leadflow_interaction_key` está presente. Tickets ajenos quedan intactos.
- Timeout o resultado ambiguo se reconcilian por lectura antes de cualquier repetición. El Contact se elimina mediante GDPR delete por ID, nunca por email.
- RESTRICT local permanece PASS. HubSpot queda `failed/capability_not_available`, equivalente técnico persistente de NOT_VERIFIED; no se expone endpoint externo.
- La prueba destructiva real se ejecutó posteriormente mediante el runner con opt-in explícito y terminó PASS; Ticket archive conserva WARN.

## LF012-T03 — QA destructiva real cerrada

- `scripts/test/test_lf012_real_hubspot_delete_opt_in.py` sale `NOT_RUN` si `RUN_REAL_DSR_DELETE_TESTS!=1` y `BLOCKED` si falta el segundo opt-in o cualquier configuración obligatoria.
- Solo opera sobre el email sintético/controlado exacto aportado en `REAL_DSR_DELETE_TEST_EMAIL`; no descubre ni selecciona Contacts existentes.
- Antes de cualquier escritura ejecuta `crm.dsr_locate` con un `request_id` técnico de preflight distinto y solo continúa ante ausencia concluyente (`found=false`, conteos cero). Contact preexistente, ambigüedad, fallo o respuesta no concluyente bloquean sin intentar cleanup.
- `ADAPTER_SERVICE_KEY` y `DSR_ADAPTER_SERVICE_KEY` deben ser diferentes; tanto el Adapter como el runner fallan cerrado si coinciden.
- Contact e INTERACTION se crean mediante los contratos normales del Adapter con identificadores UUID. El camino destructivo principal es `scripts/admin/dsr_admin.py`, con operador y aprobador técnicos distintos.
- La validación preparada exige una única INTERACTION LeadFlow en el inventario controlado, cierre de `hubspot/delete`, ausencia del Contact, ausencia operativa del Ticket, repetición idempotente y evidencia sin PII/payload/secretos.
- `finally` reutiliza el mismo `request_id` y el mismo flujo DSR aprobado cuando debe intentar cleanup. Si no puede demostrar ausencia final, el runner termina FAIL con código técnico sanitizado.
- Estado final: **PASS**. El runner real completó preflight, creación controlada, DELETE, reconciliación, idempotencia, evidencia minimizada y cleanup.
- Ticket archive mantiene **WARN**; RESTRICT local mantiene **PASS** y HubSpot RESTRICT continúa **NOT_VERIFIED / capability_not_available**.

### Diagnóstico del primer intento real

- El intento autorizado anterior superó preflight y creación del Contact, pero `/crm/record-interaction` devolvió un fallo funcional resumido por el runner como `synthetic_interaction_setup_failed`. Su cleanup posterior quedó **PASS**: Contact e INTERACTION ausentes, sin residuo real.
- `record_interaction` ahora añade exclusivamente `diagnostic_phase` a respuestas fallidas de HubSpot: `interaction_lookup`, `interaction_create`, `interaction_association` o `interaction_invalid_response`. Conserva status canónico, `http_status`, `retry_count` y `ambiguous`; no cambia retries, idempotencia ni reconciliación.
- El runner transforma el fallo en evidencia allowlisted de fase, HTTP status, código canónico, retry count y ambigüedad. No muestra IDs, operation key, payload, PII, headers ni secretos.
- `scripts/test/test_lf012_interaction_diagnostics.py` — **PASS 7/7** para lookup/create/association/invalid response, éxito sin cambios y sanitización.
- Este fallo intermedio quedó resuelto antes de la ejecución final PASS.

### Reconciliación de DELETE ambiguo atrapado

- Evidencia real observada: `lf012-cleanup-residual-20261008` quedó global `partial`, HubSpot `failed/contact_deletion_ambiguous`, Hunter `pending` y Slack `not_applicable`; una lectura posterior demostró Contact e INTERACTION ausentes. La repetición administrativa quedaba bloqueada por `destructive_state_invalid`. No se repitió DELETE.
- Causa: `dsr_admin.py` solo distinguía `pending` y `completed`; no existía transición segura desde un fallo ambiguo ya reconciliado como ausente.
- Corrección: únicamente `failed/contact_deletion_ambiguous`, con acción/provider exactos y aprobación persistida válida, ejecuta `crm.dsr_locate` con la identidad normal. Solo ausencia concluyente permite la función SQL compare-and-set `reconcile_dsr_delete_absent`, versionada en `023_dsr_delete_reconciliation.sql`, que registra `completed/reconciled_absent`. Ningún otro fallo puede completar.
- Contact presente, lookup fallido/no concluyente, código no allowlisted o aprobación inválida permanecen fail-closed. La rama ambigua no selecciona ni invoca `/crm/dsr-delete`.
- `scripts/test/test_lf012_delete_failed_reconciliation.py` — **PASS 9/9**; cubre cierre, bloqueo, aprobación, código no ambiguo, repetición y evidencia minimizada.
- La transición se validó posteriormente en el flujo real: `failed/contact_deletion_ambiguous → locate read-only → completed/reconciled_absent`, sin repetir DELETE.

### Criterio final del runner tras reconciliación

- El request real `lf012-real-delete-1b953e1a005f459590f60a98acc3b03d` terminó HubSpot `completed/reconciled_absent`; el post-check confirmó Contact e INTERACTION ausentes. El cleanup/post-check fue **PASS** y no se repitió DELETE.
- El `FAIL dsr_admin_delete_failed` posterior fue una expectativa desactualizada del runner: solo admitía `deleted`/`already_absent` y volvía a exigir una interacción después del cierre, aunque el inventario previo ya había demostrado exactamente una.
- El runner mantiene obligatoriamente `inventory.interaction_count==1` antes del DELETE y ahora acepta tres terminaciones: `deleted`, `already_absent` y `reconciled_absent`. Esta última exige `provider_status=completed`, `provider_result_code=reconciled_absent`, `reconciled=true`, `found=false` e `interaction_count=0`.
- El criterio terminal y la secuencia explícita se verificaron en la batería focalizada y en la ejecución real final.

### Secuencia explícita ante ambigüedad

- DELETE real y reconciliación real de ausencia ya fueron demostrados, pero el runner trataba la primera respuesta `failed/contact_deletion_ambiguous` como fallo definitivo y solo alcanzaba la reconciliación correcta indirectamente desde `finally`. Por eso conservaba `passed=false` y terminaba `dsr_admin_delete_failed` pese al estado persistido `completed/reconciled_absent`.
- `run_admin_to_safe_terminal` ejecuta una vez `dsr_admin`; acepta directamente cualquier terminal válido y permite exactamente una segunda llamada solo para el par exacto `provider_status=failed` y `provider_result_code=contact_deletion_ambiguous`. La segunda respuesta debe satisfacer el criterio terminal estricto.
- El flujo principal valida ahora la reconciliación antes de continuar. `finally` permanece reservado para cleanup de emergencia. La llamada posterior de idempotencia sigue activa como tercera llamada administrativa y debe observar el estado ya completed sin nueva operación destructiva.
- `scripts/test/test_lf012_real_runner_completion.py` — **PASS 20/20**.

### Evidencia final real

- Runner: `REAL-DSR-DELETE: PASS; ticket_archive=warn` y `RESULT: PASS`.
- Preflight de ausencia, creación de Contact e INTERACTION sintéticos e inventario previo exacto (`contact_count=1`, `interaction_count=1`): **PASS**.
- DELETE real, reconciliación segura del resultado ambiguo, ausencia de repetición ciega e idempotencia por `request_id`: **PASS**.
- Ausencia final (`found=false`, `contact_count=0`, `interaction_count=0`), cleanup y evidencia persistida sin PII ni secretos: **PASS**.
- Verificación visual manual: cero Contacts por el email autorizado, cero Tickets por `leadflow_interaction_key` y cero Tickets por asunto `LeadFlow interaction`: **PASS**.
- Migraciones `022_dsr_hubspot_nondestructive` y `023_dsr_delete_reconciliation`: aplicadas y verificadas.
