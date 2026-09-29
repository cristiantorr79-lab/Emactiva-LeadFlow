# LAB-LF-003 — Privacidad y protección de datos

Fecha de apertura: 2026-09-26.
Estado: **LAB-LF-003 DEVELOPMENT CLOSED / DEPLOYMENT-READY; NO DEPLOYED**.

Baseline auditado: `91aea95c05467b9d006832cb4816887c06b40644` (LAB-LF-002 CERRADO PASS), sin diferencias iniciales. No se reabre el laboratorio anterior ni se declara cumplimiento legal.

Evidencia: [Inventario y mapa end-to-end](INVENTARIO_TAREA_01.md). Incluye campos, finalidades técnicas, transformaciones, tablas, logs, respuestas, HubSpot/Hunter/Slack, recuperación, retención, configuración, diez hallazgos preliminares y diferencias documentales.

Conclusiones principales: allowlist normal de proveedores efectiva; email cifrado temporal para recovery; event_id/source pueden conservar PII clara; sin retención general implementada en SQL; límites de sanitización interna y errores de plataforma; archivo de aprovisionamiento con credencial sin cifrado previo. No se inspeccionaron datos o secretos reales ni se validó despliegue efectivo.

Validaciones de entrega realizadas el 2026-09-26:

- `git rev-parse HEAD`: coincide con el baseline completo indicado arriba.
- `git diff --check`: exit 0, sin errores.
- `git diff --name-only`: vacío; ningún archivo previamente versionado modificado.
- Revisión adicional de ambos Markdown nuevos con `git diff --no-index --check -- /dev/null <archivo>`: sin diagnósticos de whitespace; exit 1 por diferencias frente al archivo vacío y aviso de conversión futura LF→CRLF. Los archivos nuevos no forman parte del diff normal mientras sigan untracked.
- `git status --short`: únicamente `?? labs/LAB-LF-003/`.
- No se ejecutaron pruebas funcionales; no se reutilizan los PASS históricos como resultados de esta auditoría.

No hubo llamadas externas, ejecución de suites, cambios de runtime/productivo, SQL, configuración o .env; sin commit/push. EPB v1.0 no está entre las fuentes locales revisadas: próximo paso, incorporarlo a la revisión y crear matriz de controles/evidencias y evaluación formal de terceros antes de plantear remediaciones.

## Tarea 02 — Cruce formal EPB v1.0 y matriz GAP

Estado: **COMPLETADA DOCUMENTALMENTE** el 2026-09-26. Esta evaluación pertenece exclusivamente a LAB-LF-003 y no modifica retrospectivamente LAB-LF-000, LF-001 ni LF-002.

Baseline corporativo utilizado: `<EMACTIVA_ROOT>\00_CORPORATIVO\PRIVACIDAD_Y_DATOS\EPB_v1.0.md`, SHA-256 `A8552A5E1231AF11753CB883E537462E56E8349D91C980C8752DA1AAC30C6C6A`. `<EMACTIVA_ROOT>` representa el directorio raíz corporativo de Emactiva y se resuelve según el entorno. El archivo corporativo se leyó sin modificar ni copiar al repositorio.

Evidencia generada: [Matriz GAP EPB v1.0](MATRIZ_GAP_EPB_V1.md). Cubre principios, ciclo de vida, arquitectura, implementación, terceros, transferencias, retención/eliminación, incidentes, derechos, pruebas EPB, perfil de riesgo, pendientes externos y priorización.

Conteo de los **154 controles** de las tablas de matriz (gates informados por separado):

| PASS | WARN | FAIL | N/A | NOT_VERIFIED |
|---:|---:|---:|---:|---:|
| 14 | 40 | 19 | 6 | 75 |

Los NOT_VERIFIED concentran evidencia contractual, jurídica y operacional que no existe en el repositorio. No se convirtieron automáticamente en FAIL. Los FAIL se reservaron para capacidades aplicables ausentes o incompatibles con requisitos expresos: retención general, eliminación/exportación, autorización interna, revisión de transferencias y rutas de derechos.

### Gates

- **Gate PRIV-00: WARN.** El inventario técnico existe y es verificable. Faltan categorías exactas de titulares, sensibles/menores, rol, países, jurisdicción, base jurídica y retención aprobada.
- **Gate PRIV-ARCH: FAIL.** No existe una ruta integral razonable para localizar y eliminar datos en PostgreSQL, terceros, logs y backups. La evaluación no reabre los LAB anteriores.

### H01–H10

| ID | Estado | Severidad preliminar |
|---|---|---|
| H01 | CONFIRMADO | ALTA |
| H02 | CONFIRMADO | ALTA |
| H03 | CONFIRMADO | MEDIA |
| H04 | CONFIRMADO | ALTA |
| H05 | CONFIRMADO | MEDIA |
| H06 | CONFIRMADO | ALTA |
| H07 | CONFIRMADO | MEDIA |
| H08 | CONFIRMADO | MEDIA |
| H09 | CONFIRMADO | ALTA |
| H10 | CONFIRMADO | BAJA |

«Confirmado» acredita la condición de diseño/código del inventario, no exposición ni incidente. No hay severidad CRITICA: no se demostró secreto expuesto, acceso no autorizado efectivo, D2, gran volumen ni incidente real.

### Bloqueantes y pendientes

Bloqueantes EPB: política/Matriz de Retención ausente; eliminación/exportación integral no soportada; Gate PRIV-ARCH fallido; transferencias sin revisión; autorización del Adapter no implementada/demostrada; tratamiento pendiente de H01/H04/H06/H09 antes de producción.

Evidencia externa pendiente: DPA, rol, región, subprocesadores, seguridad, retención, eliminación, transferencias, uso secundario/IA y owner de HubSpot/Hunter/Slack; scopes HubSpot; fuentes Hunter; workspace/canal Slack; infraestructura real de TLS, n8n, PostgreSQL, IAM, backups, logs, volúmenes y archivos `.local`; finalidad, rol, base jurídica, titulares, volumen, jurisdicción y procedimiento de derechos/incidentes por cliente.

Perfil de riesgo: **ALTO preliminar para cierre/producción**, sin declarar incidente. EPB-P13/DPIA: **PENDIENTE_DE_INFORMACION** hasta conocer volumen, D2/D3, sujetos vulnerables, alcance del perfilado/enrichment, usos downstream, países y jurisdicción.

Próximo paso recomendado: obtener y revisar las evidencias operativas/contractuales listadas, asignar responsables y preparar una tarea separada de plan de remediación priorizado. No implementar correcciones ni ejecutar PRIV-T01–T12 hasta aprobar ese alcance.

### Validaciones finales de Tarea 02

- `git rev-parse HEAD`: `91aea95c05467b9d006832cb4816887c06b40644`.
- EPB corporativo después de la lectura: SHA-256 sin cambio, `A8552A5E1231AF11753CB883E537462E56E8349D91C980C8752DA1AAC30C6C6A`.
- `git diff --check`: PASS, exit 0.
- Whitespace de los Markdown untracked de LAB-LF-003: PASS.
- Recuento automatizado de filas de control: 14 PASS, 40 WARN, 19 FAIL, 6 N/A y 75 NOT_VERIFIED.
- `git diff --name-only`: vacío; ningún archivo previamente versionado fue modificado.
- `git status --short`: únicamente `?? labs/LAB-LF-003/`.
- No se iniciaron Docker, n8n ni PostgreSQL; no hubo llamadas externas, suites LF-002, secretos leídos/mostrados, commit ni push.

## Tarea 03A — Auditoría externa oficial de terceros

Estado: **COMPLETADA DOCUMENTALMENTE** el 2026-09-26 a partir exclusivamente de los hallazgos oficiales suministrados. No se volvió a investigar Internet.

Evidencia creada: [Auditoría de terceros Tarea 03A](AUDITORIA_TERCEROS_TAREA_03A.md), con roles, DPA, datos, subprocesadores, localización, transferencias, retención, eliminación, derechos, seguridad, IA/uso secundario y pendientes de cuenta para HubSpot, Hunter y Slack.

Conclusiones:

- **HubSpot:** para el CRM auditado, el rol técnicamente esperable es Processor respecto de Customer Personal Data. DPA, subprocesadores, regiones posibles, seguridad y capacidades de derechos/eliminación están documentados; región, scopes, mappings, funciones habilitadas y contrato/configuración de nuestra cuenta siguen pendientes.
- **Hunter:** mantiene un modelo dual directamente relevante. Puede ser Processor respecto de Customer Personal Data enviado y Controller independiente respecto de Profile Data; Emactiva/cliente es Controller independiente de su uso del Profile Data. Debe documentar finalidad, necesidad y base aplicable. No hay evidencia para afirmar que `combined/find` envía emails LeadFlow a OpenAI.
- **Slack:** actúa como Processor para Customer Data; documenta DPA/SCC, seguridad, eliminación y backups normalmente destruidos dentro de 14 días. Región, plan, retención, canal/permisos y configuración IA del workspace siguen pendientes. H03 se mantiene.

Cambios de matriz: 6 controles NOT_VERIFIED→PASS, 33 NOT_VERIFIED→WARN y EPB-XFER07 FAIL→WARN. Nuevos conteos sobre 154 controles: **20 PASS, 74 WARN, 18 FAIL, 6 N/A, 36 NOT_VERIFIED**. El detalle por ID y evidencia está al final de la matriz.

Gates sin cambio: **PRIV-00 WARN** y **PRIV-ARCH FAIL**. H01–H10 conservan clasificación y severidad. La evidencia general de terceros no crea una ruta integral de localización/eliminación ni sustituye la configuración real de las cuentas.

Pendientes prioritarios de cuenta: región y funciones HubSpot, scopes/mappings/permisos; términos y retención del email/endpoint Hunter, evaluación del uso de Profile Data; región/plan/retención/canal/permisos/IA Slack; aceptación contractual y owner de cada revisión. Infraestructura, finalidad, rol, base jurídica, jurisdicción y procedimientos LeadFlow permanecen según Tarea 02.

Próximo paso recomendado: Tarea 03B de recolección de evidencia operativa de cuentas e infraestructura, sin remediaciones, seguida de decisión de cierre de gaps documentales y plan técnico separado.

Validaciones Tarea 03A: HEAD `91aea95c05467b9d006832cb4816887c06b40644`; `git diff --check` PASS; whitespace de Markdown LF-003 PASS; recuento automatizado 20/74/18/6/36; SHA-256 del EPB sin cambio; `git diff --name-only` vacío; `git status --short` únicamente `?? labs/LAB-LF-003/`. Sin Internet, Docker, APIs, suites, secretos, commit ni push.

## Tarea 03B — Evidencia operativa

Estado: **PARTE AUTOMÁTICA COMPLETADA / EVIDENCIA MANUAL PENDIENTE** el 2026-09-26.

Evidencia creada: [Evidencia operativa Tarea 03B](EVIDENCIA_OPERATIVA_TAREA_03B.md). Se inspeccionaron pasivamente configuración declarada, metadata/ACL de archivos locales, Git, fronteras de proveedores y disponibilidad de Docker, sin leer secretos.

Resultados automáticos principales:

- `.env`, `.local` y `.local/n8n/postgres-credential.json`: PRESENTES; contenido no leído; ignorados por Git.
- El archivo temporal de credenciales persiste desde 2026-09-25, hereda ACL con Modify para grupos locales y el script no implementa cleanup. Esto refuerza H06, ya CONFIRMADO/ALTA.
- `.env` hereda ACL equivalente; validez de variables y necesidad de los grupos no se comprobaron.
- Escaneo de alta confianza de archivos tracked: cero Slack webhooks, AWS keys, GitHub tokens o cabeceras de private key. No es un detector universal.
- Producción exige HTTPS externo; red interna usa HTTP y provisioning declara PostgreSQL SSL deshabilitado.
- Roles migrator/app están declarados, pero Compose reutiliza `POSTGRES_PASSWORD` como app password.
- n8n declara no guardar ejecuciones success/error/manual, pruning activo y máximo 24; despliegue efectivo no comprobado.
- No se encontraron artefactos de backup/restore/rotación ni cleanup general. Hay volúmenes persistentes PostgreSQL/n8n.
- Docker CLI presente; daemon apagado o inaccesible. Runtime: `NOT_CHECKED_RUNTIME`; no se inició.
- HubSpot/Hunter/Slack: endpoints, parámetros, mappings y payloads normales confirmados por código; configuración real de cuenta permanece pendiente.

No cambió ningún estado de la matriz: la evidencia automática confirma condiciones ya calificadas, pero configuración declarada/metadata no acredita operación, cuenta o infraestructura desplegada. Conteos: **20 PASS, 74 WARN, 18 FAIL, 6 N/A, 36 NOT_VERIFIED**. Gates: **PRIV-00 WARN**, **PRIV-ARCH FAIL**.

Checklist manual generado: HubSpot 6, Hunter 6, Slack 8 e Infraestructura 15; total **35 ítems**. Cada ítem indica dónde revisar, qué copiar al chat y qué no mostrar.

Próximo paso: Cristian debe ejecutar el checklist por bloques, comenzando por HubSpot V01–V06, y devolver únicamente estados/datos sanitizados. Tarea 03B no se cierra hasta incorporar esa evidencia manual.

Validaciones automáticas 03B: HEAD esperado; `git diff --check` PASS; whitespace LF-003 PASS; matriz sin cambios de conteo (20/74/18/6/36); `git diff --name-only` vacío; `git status --short` únicamente `?? labs/LAB-LF-003/`. No se leyó ningún secreto, no se inició Docker y no hubo APIs, suites, commit ni push.

## Tarea 03B — Consolidación final

Estado final: **COMPLETADA DOCUMENTALMENTE** el 2026-09-27. Se consolidaron evidencia automática y manual de HubSpot, Hunter, Slack e infraestructura. No se ejecutó ninguna remediación.

### Cuentas

- **HubSpot:** cuenta alojada en Estados Unidos (Este); Service Key con solo Contacts read/write; mappings efectivos confirmados. Se observó enriquecimiento gratuito de nombres de empresas activo, por lo que HubSpot no se trata como CRM puro. La evidencia account-specific de aceptación del DPA permanece NOT_VERIFIED.
- **Hunter:** plan Free con 50 créditos mensuales; UI indica que Lead enrichment no está incluido, pendiente de reconciliar antes de operación real. DPA/controles visibles; retención diferenciada documentada; solo `/v2/combined/find` en la ruta auditada. Cookies Product & Analytics y Advertising están ON para sitio/cuenta, sin probar uso adicional de la API. No hay evidencia de envío del email a OpenAI.
- **Slack:** la evidencia inicial pertenecía a **Agrovista IA Rural** y fue excluida. En LeadFlow, `SLACK_WEBHOOK_URL` está vacía, `ALERT_UPSTREAM_URL` ausente y el wiring existe; conclusión: Slack real no configurado. V01–V08 quedan NOT_VERIFIED/no configurados.

### Infraestructura y EDPB

Se incorporó **EDPB v1.0 — Emactiva Deployment & Portability Baseline** como baseline complementario, separado de EPB v1.0, bajo “Cambia el entorno, no el sistema”.

- ENVIRONMENT/post-deployment: V01 N/A sin hosting; V02 pendiente TLS público; V04 cifrado at-rest NOT_VERIFIED.
- HYBRID: V03 WARN por PostgreSQL `ssl=disable`; V05–V08 sin capacidad/política suficiente de backups; V09 logs WARN; V11 roles WARN; V12 red WARN; V13 acceso administrativo WARN.
- SYSTEM/desarrollo: V10 rotación FAIL; V14 credencial temporal FAIL; V15 cleanup FAIL.
- H06 permanece **CONFIRMADO / ALTA**, reforzado por archivo presente, persistencia, ACL heredada y ausencia de cleanup. No existe evidencia de exposición real ni incidente.

### Matriz y gates

Cambios 03B: EPB-TP-HS01 PASS→WARN, EPB-TP-HS03 WARN→PASS, EPB-TP-HU06 WARN→PASS y EPB-TP-SL01 PASS→WARN. Conteo recalculado: **20 PASS, 74 WARN, 18 FAIL, 6 N/A y 36 NOT_VERIFIED**. Gates sin cambio: **PRIV-00 WARN**, **PRIV-ARCH FAIL**. H01–H10 mantienen estados/severidades de Tarea 02, con H06 reforzado.

Próximo paso: **PRIORIZACIÓN Y PLAN DE REMEDIACIÓN LAB-LF-003**, manteniendo separados cambios SYSTEM ejecutables en desarrollo, validaciones HYBRID y evidencia ENVIRONMENT post-deployment. No iniciar remediaciones hasta autorizar esa tarea.

## Tarea 04 — Plan de remediación

Estado: **COMPLETADA DOCUMENTALMENTE / IMPLEMENTACIÓN NO INICIADA**.

Evidencia creada: [Plan formal de remediación](PLAN_REMEDIACION_LAB-LF-003.md).

El plan contiene **24 acciones**: **12 P0, 7 P1, 3 P2 y 2 P3**; por capa, **11 SYSTEM, 5 HYBRID, 2 ENVIRONMENT y 6 DOCUMENTAL/OPERATIVA**.

Fases finales:

- **R1:** definiciones previas de retención, finalidad/necesidad, DSR y entradas de cliente.
- **R2:** seguridad SYSTEM para secretos, autorización, metadatos, terminación y fronteras.
- **R3:** retención y derechos en PostgreSQL, terceros y backups.
- **R4:** logging configurable, rotación y contratos EDPB portables.
- **R5:** terceros, Registro de Proveedores y operación.
- **R6:** pruebas PRIV/EDPB y regresión completa.
- **R7:** cierre de desarrollo y verificación post-deployment.

Primer bloque recomendado, después de aprobar R1: **REM-05, REM-07 y REM-10**, que cubren ciclo seguro de la credencial temporal, secretos/PII en argv o stderr y terminación consistente de recovery. Dependen de las definiciones R1 aplicables y no requieren infraestructura real.

Dependencias obligatorias: no implementar TTL/purga sin Matriz de Retención; no implementar ni probar DELETE/export integral sin especificación DSR; no ejecutar PRIV-T05/T06/T07 antes de crear sus capacidades; no evaluar firewall, IAM, TLS público, cifrado at-rest ni cuentas reales sin despliegue.

Cierre de desarrollo: ningún FAIL bloqueante SYSTEM; P0 de desarrollo completados; pruebas PRIV/EDPB aplicables y regresión PASS; documentación actualizada; WARN residuales con tratamiento; ENVIRONMENT registrado para post-deployment. Producción exige además verificar infraestructura, cuentas, proveedores, jurisdicción, rol, base jurídica, contratos y DPIA aplicable. EDPB no exige multi-cloud ni despliegue real para cerrar SYSTEM.

Próximo paso: **FASE R1 — DEFINICIONES PREVIAS DEL PLAN DE REMEDIACIÓN**. No iniciar R1 en Tarea 04.

## Fase R1 — Definiciones previas

Estado: **APROBADA FUNCIONALMENTE — CERRADA**.

Evidencia creada: [Definiciones R1](DEFINICIONES_R1_LAB-LF-003.md).

Las **16 decisiones R1** quedan aprobadas como definición funcional de LeadFlow. Las decisiones O01–O12 tienen resolución formal; seis materias de cliente/entorno permanecen pendientes para onboarding, preproducción o post-deployment y no bloquean R2.

Se aprueban como base técnica los plazos de 90 días para success/duplicate, 180 días para failed y máximo 7 días sin progreso para processing/recovery. Los holds son específicos, documentados, temporales y revisables. No se fija base jurídica, jurisdicción ni rol universal para un cliente inexistente.

`event_id` se valida como identificador técnico sin PII y su persistencia cruda debe minimizarse; `source` puede persistir canónicamente desde una allowlist. DELETE podrá conservar un tombstone mínimo, no reversible y sin datos personales para impedir repetición o reaparición.

No se implementaron TTL, DELETE, EXPORT, restricciones, SQL, workflows, Adapter, Compose, cleanup, logging, autenticación, credenciales ni pruebas funcionales.

Próximo paso: **FASE R2 — SEGURIDAD SYSTEM**.

Primer bloque: **R2-A — REM-05 + REM-07 + REM-10**.

- **REM-05:** asegurar que la credencial temporal de n8n no permanezca almacenada después de usarse.
- **REM-07:** evitar que correos, contraseñas u otros datos sensibles aparezcan en comandos o errores.
- **REM-10:** evitar que recuperaciones interrumpidas permanezcan indefinidamente en `processing`.

## Fase R2 — Seguridad SYSTEM / bloque R2-A

Fecha: 2026-09-28.

Estados:

- **REM-05=PASS.** La credencial temporal n8n se crea inmediatamente antes de importar, restringe herencia ACL en Windows y se elimina siempre mediante `finally`. El cleanup directo pasó en éxito, error e idempotencia; se eliminó el artefacto residual sin leer su contenido.
- **REM-07=PASS.** Recovery ya no incluye password ni SQL con email/secreto en argv; usa stdin y convierte stderr/fallos de proceso en códigos sanitizados con etapa. Los canarios de email, password y token no aparecieron en salida/error.
- **REM-10=PASS.** La ejecución recovery invocada se terminaliza al superar siete días, las excepciones persistibles terminan `failed`, se preserva la idempotencia/reconciliación y la migración/transiciones fueron verificadas en PostgreSQL local.

Archivos de producto: helper/provisioning n8n, runtime y scripts recovery, migración 012, configuración de ejemplo y contratos de arquitectura. Pruebas añadidas: `test_n8n_credential_cleanup.ps1` y `test_r2a_recovery_security.py`.

Resultados: sintaxis Python/PowerShell PASS; REM-05 7/7 PASS; REM-07/REM-10 unitario 15/15 PASS; frontera Adapter recovery 11/11 PASS. El smoke `test_deployment_security.py` pasó 11 comprobaciones estáticas y se detuvo al requerir el webhook local con Docker apagado; no constituye fallo del cambio.

Riesgos residuales previos de runtime cerrados mediante la validación final descrita abajo. El barrido general de retención permanece fuera de R2-A y corresponde a REM-12/R3. Conteos EPB y gates permanecen sin cambios.

### Validación runtime final de REM-10

Infraestructura local: Docker Desktop 29.6.1, PostgreSQL 17.6, Adapter, n8n y mocks locales declarados en Compose. La migración 012 aplicó correctamente y quedó registrada una sola vez.

Resultados:

- runtime focalizado REM-10: **7/7 PASS**;
- recovery completion: **10/10 PASS**;
- reconciliación/idempotencia: **9/9 PASS**;
- smoke deployment/security: **14/14 PASS**;
- provisioning n8n local: **PASS**, sin credencial temporal residual.

Se comprobaron success, failed, excepción persistible, expiración >7 días, CREATE ambiguo con reconciliación previa, ejecución original, claves de idempotencia intactas y ausencia de purga global. El primer fallo de infraestructura fue Docker daemon apagado; se inició conforme a la autorización. El primer intento de prueba carecía de `RECOVERY_ADAPTER_URL` en el entorno del host; se corrigió solo para la ejecución con endpoints loopback, sin modificar `.env`.

Cleanup: filas sintéticas eliminadas, mocks reiniciados, `postgres-credential.json` ausente y stack Compose detenido. No se utilizaron datos reales ni APIs externas.

Decisión: **REM-10 WARN → PASS**. REM-05 y REM-07 permanecen PASS. **PRIV-00 permanece WARN y PRIV-ARCH permanece FAIL.**

Próximo paso recomendado: seleccionar y autorizar el siguiente bloque R2 del plan; no iniciar R3 ni reevaluar otros controles por inferencia.

## Fase R2 — Seguridad / bloque R2-B REM-06

Fecha: 2026-09-28.

Estado: **REM-06=PASS**.

Compose, `.env.example`, provisioning, recovery y validadores usan credenciales separadas `POSTGRES_MIGRATOR_*` y `POSTGRES_APP_*`. La configuración local ignorada fue migrada sin mostrar valores; las identidades y contraseñas son distintas. Los scripts sincronizan ambos roles antes de aplicar migraciones y rechazan configuraciones compartidas.

La validación focalizada en PostgreSQL 17.6 confirmó:

- conexión con identidad migrator y operación DDL dentro de una transacción revertida;
- conexión con identidad app y lectura normal de `leadflow.executions`;
- denegación efectiva de `CREATE TABLE` al rol app;
- identidades y credenciales distintas, sin secretos en argumentos ni salida;
- sincronización correcta y las doce migraciones vigentes reconocidas como aplicadas.

No se ejecutó una regresión adicional: la prueba focalizada ya ejercita la conexión y operación normal del rol app. No se llamaron APIs reales ni se inició otro servicio. Cleanup: la operación DDL del migrator se revirtió, la operación denegada no creó tabla y PostgreSQL se detuvo al finalizar.

Decisión: **REM-06 WARN → PASS**. **PRIV-00 permanece WARN y PRIV-ARCH permanece FAIL.** No cambian conteos EPB ni otros estados.

Próximo paso recomendado: seleccionar y autorizar otro bloque; no iniciar R3 por inferencia.

## Fase R2 — Minimización / bloque R2-D REM-09

Fecha: 2026-09-28.

Estado: **REM-09=PASS**.

`source` se valida contra `LEADFLOW_ALLOWED_SOURCES`, se normaliza a slug minúsculo y solo entonces puede persistirse. `event_id` exige formato técnico estricto, rechaza formas evidentes de email, URL, teléfono numérico y texto libre simple, y se utiliza transitoriamente para derivar `idempotency_key = SHA-256(source:event_id)`. La migración 013 elimina la columna `event_id`; los rechazos no devuelven ni persisten el valor recibido.

La única prueba focalizada pasó **9/9**: source permitido y canónico, source rechazado, token técnico válido, email canario rechazado sin exposición, límites rechazados, no persistencia, duplicación estable, claves distintas y recovery sobre el original. Las migraciones 001–013 quedaron aplicadas; los fixtures se eliminaron y PostgreSQL se detuvo. No se ejecutó regresión adicional.

Primer fallo real: la consulta inicial de verificación de cleanup tuvo una cláusula `ESCAPE` mal escapada en PowerShell; se corrigió solo esa consulta y se confirmó ausencia de fixtures.

Riesgo residual: la allowlist debe coordinarse con cada integración y la clave SHA-256 sigue siendo seudonimizada, sujeta a controles de acceso y retención. **PRIV-00 permanece WARN y PRIV-ARCH permanece FAIL.** No cambian conteos EPB.

Próximo paso recomendado: seleccionar y autorizar otro bloque; no iniciar R3 por inferencia.

## Fase R2 — Seguridad / bloque R2-C REM-08

Fecha: 2026-09-28.

Estado: **REM-08=PASS para la parte SYSTEM**.

Se implementó una identidad service-to-service portable mediante `X-LeadFlow-Adapter-Key`, con secreto externo `ADAPTER_SERVICE_KEY`, comparación temporalmente segura y autorización por la allowlist `ADAPTER_ALLOWED_OPERATIONS`. Core y recovery incorporan la identidad en sus llamadas. El Adapter no inicia sin secreto o permisos válidos; no depende de IP, dominio ni proveedor.

La única prueba focalizada pasó **7/7**: ausencia de identidad `401`, identidad inválida `401`, operación autorizada funcional, operación no autorizada `403`, configuración sin secreto fail-closed, ausencia del secreto en salida/error y continuidad de una operación legítima existente. La sintaxis Python, el JSON del workflow y `docker compose config --quiet` pasaron. No se llamaron APIs reales ni se levantó el stack.

Primer fallo: la prueba inicial heredó URLs upstream vacías del `.env` local y falló al importar la configuración; se corrigió únicamente su entorno sintético y la repetición pasó 7/7.

Riesgo residual: red, TLS interno, IAM, distribución y rotación efectiva de la identidad quedan pendientes HYBRID/ENVIRONMENT para el despliegue. **PRIV-00 permanece WARN y PRIV-ARCH permanece FAIL.** No cambian conteos EPB ni otros estados.

Próximo paso recomendado: seleccionar y autorizar otro bloque; no iniciar R3 por inferencia.

## Fase R2 — Fronteras / bloque R2-E REM-11

Fecha: 2026-09-28.

Estado: **REM-11=PASS**.

El Adapter centraliza códigos técnicos con formato y longitud controlados; IDs externos como strings opacos acotados; URLs website HTTP/HTTPS sin userinfo, query ni fragment; y los únicos campos enrichment permitidos (`industry`, `company_size`, `website`) con tipo y longitud definidos. Códigos desconocidos se convierten a códigos HTTP canónicos y los valores anómalos se rechazan o descartan sin propagar payload, headers, URL sensible o traza.

La única prueba focalizada pasó **10/10** con datos sintéticos: error code válido/anómalo, ID válido/inválido, website HTTPS/esquema peligroso, allowlist, campos extra, tipos/longitudes y no exposición del payload. No hubo regresión adicional, llamadas externas ni cambio en retries.

Riesgo residual: un proveedor puede introducir un ID o valor legítimo fuera de los límites actuales; cualquier ajuste requiere cambio explícito de contrato y prueba. **PRIV-00 permanece WARN y PRIV-ARCH permanece FAIL.** No cambian conteos EPB.

Próximo paso recomendado: cerrar documentalmente R2 o autorizar la fase siguiente; no iniciar R3 por inferencia.

## Cierre Fase R2 y Fase R3 — bloque R3-A REM-12

Fecha: 2026-09-28.

**FASE R2 — COMPLETADA EN SU ALCANCE DE DESARROLLO.** Estados PASS: REM-05, REM-06, REM-07, REM-08 parte SYSTEM, REM-09, REM-10 y REM-11. Permanecen pendientes HYBRID/ENVIRONMENT: red, TLS interno, IAM, rotación y verificaciones de infraestructura real.

Estado R3-A: **REM-12=PASS**.

Las migraciones 014–015 incorporan holds específicos, temporales y revisables; liberación auditable de holds vencidos; evidencia mínima de purga; y `purge_retained_data` por lotes. Aplica 90 días a success/duplicate, 180 días a failed y terminaliza processing/recovery con más de 7 días antes de iniciar su retención como failed. Respeta dependencias de duplicados, elimina eventos/contextos coordinadamente y conserva solo conteos técnicos durante 180 días.

La única prueba focalizada se ejecutó en una base PostgreSQL temporal y pasó **12/12**: seis límites terminales, dos casos processing/recovery, hold, hijos, idempotencia y evidencia minimizada. El primer intento falló por un fixture cuyo `finished_at` precedía al `started_at`; se corrigió solo el fixture. La base temporal fue eliminada y el stack quedó detenido. No se ejecutó PRIV-T05 final ni regresión adicional.

Riesgo residual: falta programar y observar el job en el entorno real, medir locks/volumen y confirmar plazos por cliente. **PRIV-00 permanece WARN y PRIV-ARCH permanece FAIL.** No cambian conteos EPB.

Paso ejecutado: REM-13, REM-14 y REM-15 se cerraron en su alcance desarrollable y se documentan a continuación.

## Fase R3 — cierre REM-13 + REM-14 + REM-15

Fecha: 2026-09-28.

- **REM-13=PASS (SYSTEM).** Existe interfaz administrativa separada para LOCATE, EXPORT minimizado, ANNOTATE, DELETE y RESTRICT. DELETE/RESTRICT requieren aprobador independiente, bloquean ambigüedad, son idempotentes y conservan un tombstone HMAC mínimo que impide reingreso sin almacenar PII eliminada.
- **REM-14=PASS (SYSTEM) / PENDIENTE (HYBRID).** HubSpot y Hunter generan acciones administrativas idempotentes con estado y referencia técnica; Slack queda N/A explícito cuando no existe dato del titular. Pendientes/fallos mantienen resultado parcial y los códigos externos se sanitizan. No se presume capacidad, SLA ni cuenta real.
- **REM-15=PASS (SYSTEM) / NOT_VERIFIED (ENVIRONMENT).** El contrato exige backup diario, 30 días, RPO ≤24 h, RTO ≤8 h, cifrado y custodia por entorno. Restore exige reaplicar tombstones/restricciones antes de habilitar tráfico. Ejecución, storage, cifrado y restore reales siguen sin evidencia.

La única batería focalizada R3 pasó **21/21** en PostgreSQL temporal. Primer fallo real: RESTRICT usó una referencia SQL `status` ambigua; se calificó la columna y la repetición pasó completa. No hubo APIs reales, suite completa ni repetición de pruebas R2. La base temporal se eliminó y el stack quedó detenido.

Riesgos residuales: verificación de identidad y roles humanos, operación de proveedores, cuentas/SLA, infraestructura de backup, custodia, cifrado, restore y métricas RPO/RTO. **PRIV-00 permanece WARN y PRIV-ARCH permanece FAIL.** No se reevalúan conteos EPB.

Paso ejecutado: R4 se cerró en su alcance desarrollable y se documenta a continuación.

## Fase R4 — cierre REM-16 + REM-17 + REM-18

Fecha: 2026-09-28.

- **REM-16=PASS (SYSTEM).** Adapter y recovery emiten eventos JSON mediante una política allowlist común. Nivel y salida se controlan por entorno; solo permanecen metadata y códigos técnicos válidos.
- **REM-17=PASS (SYSTEM).** Los seis servicios Compose comparten límites configurables de tamaño y archivos con defaults `json-file`, `10m` y `3`. La configuración Compose es válida.
- **REM-18=PASS (SYSTEM) / PENDIENTE (HYBRID/ENVIRONMENT).** Endpoints, secretos, logs y política Docker se externalizan; los volúmenes, backup policy y override de producción están declarados. El core no requiere cambios al sustituir el entorno.

La única prueba focalizada R4 pasó **12/12** en el primer intento. Los canarios de email, teléfono, token y header no aparecieron; el error externo se redujo a código canónico y se preservó la metadata técnica. Primer fallo real posterior: indentación incorrecta en la integración CLI de recovery, corregida antes del cierre; la validación de sintaxis pasó. No hubo PostgreSQL runtime, APIs reales, contenedores ni suite completa.

Riesgos residuales: falta comprobar red, DNS, dominio, TLS, firewall, IAM, almacenamiento/volúmenes, cifrado, backup/restore, monitoreo, retención efectiva del driver y despliegues dev/test/prod reales. **PRIV-00 permanece WARN y PRIV-ARCH permanece FAIL.** No se reevalúan conteos EPB.

Paso ejecutado: R5 y R6 se cerraron y la reevaluación final se documenta a continuación.

## Cierre de desarrollo R5 + R6

Fecha: 2026-09-29.

- **REM-19=PASS.** Registro único de HubSpot/Hunter/Slack completo; Slack permanece `NOT_CONFIGURED`; la evidencia account-specific se reserva para REM-21.
- **REM-20=PASS.** Incidentes, DSR operacional, riesgos, RACI, transferencias, DPIA y tabletop incidente/DSR quedaron verificables; prueba documental 12/12.
- **REM-21=NOT_VERIFIED / ENVIRONMENT.** Sin cuentas, consolas, contratos ni APIs reales nuevas.
- **REM-22=PASS SYSTEM.** PRIV-T01–T07 y T10 PASS; PRIV-T08/T09 SYSTEM cubiertos y globalmente WARN por cuentas/transferencias reales pendientes.
- **REM-23=PASS SYSTEM.** EDPB-T01–T09 aplicables, clean start, persistencia, idempotencia, n8n, adapters, recovery, retención, DSR, logging y portabilidad pasaron en la fase QA final.
- **REM-24=NOT_VERIFIED / ENVIRONMENT.** La infraestructura real sigue fuera del laboratorio.

La ejecución se reanudó desde el punto exacto de corte. No se repitieron migraciones, provisioning ni pruebas previamente confirmadas. Se forzaron proveedores y upstream a mocks locales y `RUN_REAL_PROVIDER_TESTS` permaneció deshabilitado. Los fallos aislados fueron del arnés/fixtures y se corrigieron con repetición exclusiva del archivo afectado. Las bases temporales quedaron en cero y Compose fue detenido.

Reevaluación: **PRIV-00=WARN** por contexto jurídico/cliente pendiente; **PRIV-ARCH=WARN** porque la arquitectura SYSTEM está resuelta pero proveedores, backup/restore e infraestructura efectivos requieren evidencia. No quedan FAIL bloqueantes SYSTEM.

Próximo paso recomendado: onboarding/deployment controlado para REM-21 y REM-24, seguido de evidencia post-deployment. Deployment-ready no significa deployed.
