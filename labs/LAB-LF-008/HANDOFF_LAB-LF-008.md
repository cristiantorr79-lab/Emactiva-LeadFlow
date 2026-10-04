# HANDOFF LAB-LF-008

## Estado final

**LAB-LF-008 — CLOSED — PASS WITH DOCUMENTED LIMITS**

La evolución funcional de LeadFlow separa EVENT, LEAD e INTERACTION sin alterar la identidad técnica histórica ni debilitar privacidad, recovery, DSR o retención. Los defectos descubiertos durante aceptación manual fueron corregidos y revalidados. No se realizó commit ni push.

## Modelo funcional y contrato

- **EVENT:** `source` + `event_id` representa un envío único. La identidad continúa siendo `SHA-256(source + ":" + event_id)`; el contenido no participa.
- **LEAD:** email normalizado y campos de contacto permitidos representan la identidad relativamente estable del prospecto.
- **INTERACTION:** `interest` y/o `message` representan exclusivamente el contexto opcional de ese contacto.

V1 sin `interaction` continúa soportado. Una interaction vacía equivale a omitida; strings vacíos tras trim se omiten; no se coercionan otros tipos y los campos desconocidos no se propagan. `interest` usa allowlist externalizable y admite hasta 100 caracteres. `message` admite hasta 2000 caracteres, recibe sólo trim exterior y conserva saltos de línea, Unicode y contenido interno.

El mismo `source + event_id` siempre es duplicate, aunque cambien `interest` o `message`. Un nuevo `event_id` para el mismo email reutiliza el contacto y registra una nueva interaction.

## Workflow n8n

El workflow principal continúa siendo uno solo; no se creó un workflow paralelo. Se incorporaron seis nodos:

- `Persist CRM Contact Checkpoint`
- `CRM Interaction`
- `Persist Interaction Outcome`
- `Interaction Succeeded`
- `Interaction Ambiguous`
- `Respond Interaction Recoverable`

Secuencia relevante:

`CRM → checkpoint crm_contact_id → interaction → persist interaction outcome → success/ambiguous decision → enrichment o respuesta recoverable`

El contacto CRM se confirma localmente antes de escribir la interaction. La interaction se procesa antes de enrichment y un duplicate no vuelve a producir efectos externos. El workflow fue ordenado visualmente con Tidy Up y publicado en n8n.

## Adapter, idempotencia y reconciliación

El adapter neutral expone escritura y reconciliación sin trasladar conceptos específicos del proveedor al core. Recibe sólo `contact_id`, la interaction validada y una operation key estable sin PII:

`<idempotency_key>:crm_interaction`

El mock CRM mantiene interactions separadas de contactos y garantiza unicidad por operation key, incluso bajo concurrencia. Las capabilities cubren escritura, idempotencia y reconciliación; si falta alguna, la operación falla cerrado.

Un resultado ambiguo permanece no terminal. Recovery conserva el último punto seguro, reconcilia antes de repetir y no recrea ciegamente ni el contacto ni la interaction.

## Correcciones realizadas durante LF-008

1. **Boundary V1 / Store Recovery Context**
   - Inicialmente enviaba JSONB `null` cuando no había interaction.
   - Se corrigió para enviar SQL `NULL` real.
   - La integración posterior pasó 11/11.

2. **Tests históricos de recovery**
   - Usaban la firma anterior de tres parámetros.
   - Se adaptaron al contrato LF-008 de cuatro parámetros.
   - Los fixtures V1 usan SQL `NULL` para interaction omitida.

3. **Recovery JSONB**
   - Se detectó un fallo en `get_recovery_crm_context`.
   - Migration 019 corrigió el lookup de recovery.
   - Migration 020 corrigió la validación JSONB explícita de interaction.
   - La reconciliación posterior pasó 9/9.

4. **Harness de retención**
   - El test histórico asumía que migrator podía ejecutar `CREATE DATABASE`.
   - Se adaptó a la separación vigente: bootstrap para CREATE/DROP y migration 001, transferencia de ownership y migrator para migrations posteriores.
   - Se corrigieron el encoding UTF-8 de SQL vía subprocess y la referencia histórica `email_ciphertext` a `context_ciphertext`.
   - Resultado final: PASS 12/12.

5. **Harness DSR / backup**
   - Se adaptó a la misma separación bootstrap/migrator y a encoding UTF-8 explícito.
   - Las aserciones funcionales no fueron debilitadas.
   - Resultado final: PASS 21/21.

6. **Persistencia de fallos CRM Interaction**
   - La función histórica `record_crm_failure` sólo aceptaba etapas CRM anteriores a LF-008 y fallaba con `invalid CRM failure` para `crm_interaction`.
   - Migration 021 agregó la etapa y sus errores canónicos, rechazó `retry_count` nulo antes del loop y preservó `crm_action`/`crm_contact_id` previamente checkpointados cuando la salida de interaction entrega `NULL`.
   - La prueba SQL focalizada pasó 10/10.
   - La Prueba Manual 5 posterior confirmó persistencia funcional y error sanitizado.

7. **Rama ambigua explícita**
   - La primera implementación persistía correctamente `interaction_status=ambiguous`, pero después encaminaba la salida falsa de `Interaction Succeeded` a `Persist CRM Failure`.
   - El estado recuperable dependía accidentalmente del fallo posterior de ese nodo al no recibir el contexto esperado.
   - Se agregó una decisión explícita `Interaction Ambiguous`: la rama ambigua no invoca `record_crm_failure`, conserva checkpoint/contexto y responde HTTP 202 con información técnica sanitizada.
   - Recovery reconcilia por operation key antes de cualquier nueva escritura; la aceptación manual confirmó una sola interaction y finalización success.
   - La prueba estructural focalizada pasó 10/10 y el workflow corregido fue importado y publicado.

## Aceptación manual

- **Test 1 — V1 sin interaction:** PASS; no creó interaction ficticia.
- **Test 2 — lead nuevo + interaction:** PASS; contacto, interaction y enrichment correctos.
- **Test 3 — mismo email + nuevo event_id:** PASS; contacto reutilizado y nueva interaction.
- **Test 4 — mismo source + event_id:** PASS; duplicate sin nuevos efectos externos.
- **Test 5A — capability desactivada:** PASS; fail-closed, fallo sanitizado y persistencia correcta tras migration 021.
- **Test 5B — ambiguous interaction real:** PASS. La nueva rama explícita fue validada manualmente. El webhook devolvió HTTP 202 con respuesta pública sanitizada: `status=processing`, `recoverable=true` y `error.type=ambiguous_interaction`, sin PII ni contenido de interaction.

PostgreSQL conservó intencionalmente `status=processing`, `stage=crm_interaction`, `crm_action`, `crm_contact_id` e `interaction_status=ambiguous`. El recovery limpio, ejecutado con las credenciales actuales del host, terminó en `success` con `retry_count=0`; `reconcile_interaction` se incrementó y no se creó una segunda interaction.

La primera tentativa de recovery de esta validación queda invalidada como evidencia: la sesión PowerShell conservaba `ADAPTER_SERVICE_KEY` y `RECOVERY_CONTEXT_KEY` anteriores a la rotación. No representa un defecto de producto. La repetición posterior en una sesión limpia fue PASS.

## Configuración y credenciales

- `compose.yaml` propaga `LEADFLOW_ALLOWED_INTERESTS` a n8n y las tres capabilities de interaction al adapter.
- `ADAPTER_ALLOWED_OPERATIONS` incluye `crm.record_interaction` y `crm.reconcile_interaction`.
- Tras una exposición accidental en consola/chat se rotaron `LEADFLOW_WEBHOOK_KEY`, `ADAPTER_SERVICE_KEY`, `POSTGRES_APP_PASSWORD`, `RECOVERY_CONTEXT_KEY` y la clave CRM del entorno mock, sin registrar valores.
- La rotación de `RECOVERY_CONTEXT_KEY` se realizó con `recovery_contexts=0`; `leadflow_app` fue validado con su contraseña nueva.
- `.env.backup-lf008` fue eliminado y `.env` permanece ignorado por Git.
- La integración n8n + mocks posterior a la rotación pasó 11/11.

## Cleanup final

- Ejecuciones sintéticas eliminadas.
- Failure control eliminado.
- CRM mock recreado.
- Estado final del mock: `contacts=0`, `interactions=0` y contadores de llamadas en cero.

## Migraciones

- `018_lead_interaction.sql`: soporte principal de interaction, estados, checkpoint del contacto y recovery ampliado con JSON cifrado.
- `019_recovery_context_lookup.sql`: corrección del lookup de recovery con referencias explícitas.
- `020_recovery_interaction_validation.sql`: corrección de la validación JSONB mediante `(v_context->'interaction') - 'interest' - 'message'`.
- `021_crm_interaction_failure.sql`: soporte compatible y fail-closed de fallos `crm_interaction`, con preservación del checkpoint CRM.

Las migrations 018, 019, 020 y 021 fueron aplicadas correctamente mediante el mecanismo normal y quedaron registradas en `leadflow.schema_migrations`.

## Privacidad

- `message` e `interest` no se exponen en logs, Slack, respuestas públicas ni evidencia QA.
- Slack conserva sólo `execution_id`, `stage` y `error_code`.
- No se persiste el payload completo.
- Las operation keys no contienen PII.
- Recovery conserva un contexto estructurado, cifrado y minimizado.
- Enrichment permanece limitado a `industry`, `company_size` y `website`; no sobrescribe email, nombre, teléfono ni interaction.
- `lead_identifier` continúa siendo dato seudonimizado.

## Retención y DSR

La política histórica se mantiene:

- success: 90 días;
- duplicate: 90 días;
- failed: 180 días;
- processing/recovery sin progreso: máximo 7 días.

Retention purge quedó confirmado PASS 12/12.

El soporte local DSR existente continúa cubriendo:

- LOCATE;
- EXPORT;
- CORRECT / ANNOTATE;
- DELETE;
- RESTRICT.

La batería focalizada DSR / backup quedó confirmada PASS 21/21. El trigger terminal, DSR DELETE y la expiración de recovery eliminan el contexto local ampliado. La eliminación local no implica borrar automáticamente una interaction ya persistida en un CRM externo; la retención y el DSR del CRM dependen del provider adapter y de la configuración del cliente.

## Evidencia final confirmada

| Evidencia | Resultado |
|---|---:|
| LF-008 interactions | **PASS 39/39** |
| Authenticate / validate / normalize | **PASS 8/8** |
| Adapter conformance | **PASS 26/26** |
| Provider adapters | **PASS 44/44** |
| n8n integration + mocks histórica | **PASS 11/11** |
| Persistencia focalizada de fallos CRM Interaction | **PASS 10/10** |
| LF-008 focalizada posterior a migration 021 | **PASS 39/39** |
| n8n integration + mocks posterior a migration 021 y rotación | **PASS 11/11**; el fallo D2-001 previo se debió al workflow desactivado |
| Rama ambigua explícita del workflow | **PASS 10/10** |
| Aceptación manual Tests 1–5 | **PASS** |
| Recovery encrypted context | **PASS 18/18** |
| Recovery CRM reconciliation | **PASS 9/9** |
| Recovery completion | **PASS 10/10** |
| Retention purge | **PASS 12/12** |
| DSR / backup focused battery | **PASS 21/21** |
| Python compilation | **PASS** |
| Workflow JSON validation | **PASS** |
| Migrations 018 / 019 / 020 / 021 | **PASS** |
| Cleanup de datos sintéticos | **PASS** |
| Validación manual de respuesta 202 y recovery ambiguo limpio | **PASS** |
| `git diff --check` final | **PASS**; warnings LF → CRLF de Windows no son errores |

## Archivos LF-008 modificados

- `.env.example`
- `compose.yaml`
- `workflows/leadflow_core_initial.json`
- `adapters/server.py`
- `mocks/server.py`
- `scripts/recovery/continue_recovery.py`
- `database/migrations/018_lead_interaction.sql`
- `database/migrations/019_recovery_context_lookup.sql`
- `database/migrations/020_recovery_interaction_validation.sql`
- `database/migrations/021_crm_interaction_failure.sql`
- `scripts/test/test_lf008_interactions.py`
- `scripts/test/test_crm_interaction_failure.py`
- `scripts/test/test_n8n_ambiguous_interaction_path.py`
- `scripts/test/test_n8n_mocks_integration.py`
- `scripts/test/test_recovery_encrypted_context.py`
- `scripts/test/test_recovery_crm_reconciliation.py`
- `scripts/test/test_recovery_completion.py`
- `scripts/test/test_retention_purge.py`
- `scripts/test/test_r3_dsr_backup.py`
- `docs/architecture/ARCHITECTURE.md`
- `docs/architecture/CONTRACTS.md`
- `labs/LAB-LF-006/LEADFLOW_CLIENT_IMPLEMENTATION_TEMPLATE.md`
- `labs/LAB-LF-008/HANDOFF_LAB-LF-008.md`

## Límites documentados

- **HubSpot interaction real: NOT_IMPLEMENTED / fail closed.** No se declara soporte hasta disponer de escritura idempotente y reconciliación concluyente. Este límite no bloquea el cierre funcional porque core, adapter y capabilities fallan cerrado.
- Los controles HYBRID/ENVIRONMENT no reevaluados no se promueven. Red, TLS interno, IAM, rotación, infraestructura real y post-deployment continúan sujetos a sus gates correspondientes.

## Cierre

La separación EVENT / LEAD / INTERACTION, compatibilidad V1, idempotencia, interaction externa, recuperación ambigua explícita, privacidad, retención, DSR, cleanup y regresión proporcional quedaron demostradas. LAB-LF-008 queda cerrado como **PASS WITH DOCUMENTED LIMITS**.
