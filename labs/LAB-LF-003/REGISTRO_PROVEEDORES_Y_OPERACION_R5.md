# LAB-LF-003 — Registro de proveedores y operación de privacidad R5

Fecha: 2026-09-28. Alcance: diseño de producto y operación previa a despliegue. No acredita contratos, cuentas ni configuración productiva.

## 1. Registro consolidado de proveedores

| Proveedor | Owner lógico | Finalidad y función | Datos de LeadFlow | Rol conocido | Región y transferencias | DPA, retención y DSR | Estado y pendientes |
|---|---|---|---|---|---|---|---|
| HubSpot | Operación CRM de Emactiva; cliente aprueba cuenta/configuración | Lookup, creación y actualización CRM. Enrichment adicional de HubSpot debe permanecer deshabilitado por defecto | Email, nombre, apellido, teléfono, empresa; `industry`, `company_size`, `website`; recibe ID técnico y email de lookup | Processor esperado para CRM normal; funciones adicionales pueden cambiar el análisis | Cuenta revisada: Estados Unidos (Este). Marco general de transferencias y subprocesadores documentado; aplicación account-specific pendiente | DPA general disponible. Aceptación, retención efectiva y operación DSR de la cuenta pendientes | Scopes mínimos observados: Contacts read/write. Confirmar usuarios, permisos, DPA aplicable, retención y que enrichment/tracking adicional esté deshabilitado antes de producción |
| Hunter | Operación de enrichment de Emactiva; cliente aprueba finalidad | `GET /v2/combined/find`; proyecta solo `industry`, `company_size`, `website` | Envía email; recibe Profile Data minimizado por allowlist | Processor para Customer Personal Data enviado; Controller independiente para Profile Data según evidencia consolidada | Servidores declarados en Bélgica; SCC/subprocesadores internacionales documentados. Ruta efectiva account-specific pendiente | DPA estándar disponible. API usage/logs observados por 3 meses; retención exacta del email y DSR operativo pendientes | Cuenta observada Free, 50 créditos/mes, con Lead enrichment indicado como no incluido. Reconciliar capacidad real, términos, endpoint, región y permisos antes de producción |
| Slack | Operación de alertas de Emactiva; cliente aprueba workspace/canal | Alerta técnica de fallos | Solo `execution_id`, `stage`, `error_code`; sin PII prevista | Slack Processor y cliente Controller para Customer Data | Región, data residency y SCC dependen del workspace real | DPA, plan, retención, eliminación y DSR dependen del workspace | **NOT_CONFIGURED**. No crear workspace ni credenciales durante LAB-LF-003. Activación sujeta al checklist V01–V08 |

### Checklist Slack V01–V08 para onboarding

1. **V01 — Workspace y owner:** identificar workspace dedicado, owner lógico y cliente responsable.
2. **V02 — DPA/contrato:** conservar versión y aceptación aplicables.
3. **V03 — Región:** registrar data residency y tratamiento de Other Information.
4. **V04 — Plan/retención:** registrar plan, retención, borrado y backups aplicables.
5. **V05 — Acceso:** revisar canal, miembros, apps, roles y mínimo privilegio.
6. **V06 — Payload:** verificar con canarios que solo salen `execution_id`, `stage`, `error_code` técnicos.
7. **V07 — Transferencias/IA:** registrar SCC, subprocesadores y opt-in/opt-out aplicable.
8. **V08 — DSR/incidente:** probar exportación/eliminación y ruta de escalamiento sin datos reales.

## 2. Procedimiento de incidentes

1. **Detección:** registrar fuente, hora, componente y código técnico; no copiar payloads, credenciales ni PII a tickets o logs.
2. **Clasificación:** valorar confidencialidad, integridad, disponibilidad, categorías afectadas, volumen, duración y superficies propias/terceras.
3. **Contención:** revocar o rotar credenciales, restringir procesamiento, aislar el componente y preservar evidencia técnica mínima.
4. **Escalamiento:** Product Owner coordina; Security/Privacy Lead evalúa privacidad; cliente decide obligaciones propias; proveedor recibe escalamiento cuando su superficie esté implicada.
5. **Evidencia:** conservar cronología, decisiones, hashes/referencias técnicas, acciones y responsables lógicos bajo retención limitada.
6. **Cierre:** verificar contención, corrección, recuperación, terceros y riesgos residuales; registrar aprobador.
7. **Revisión:** documentar causa, controles preventivos y fecha de seguimiento. Plazos legales y notificaciones se determinan por cliente, jurisdicción y datos reales.

## 3. Procedimiento DSR operativo

1. El cliente recibe la solicitud y verifica identidad, alcance y autoridad conforme a su contexto jurídico.
2. El operador autorizado crea un `request_id` técnico y usa la interfaz administrativa REM-13; el email se usa transitoriamente y no se registra.
3. LOCATE/EXPORT/ANNOTATE se ejecutan con mínimo privilegio. DELETE/RESTRICT exigen aprobador independiente.
4. Ambigüedad o retention hold detienen la acción destructiva y requieren resolución humana.
5. REM-14 crea acciones idempotentes para HubSpot/Hunter; Slack queda `not_applicable` mientras no almacene datos del titular. Pendientes/fallos mantienen estado parcial.
6. El operador reúne evidencia minimizada por superficie, revisa el resultado y entrega únicamente el contenido autorizado al cliente.
7. La repetición usa el mismo `request_id`; tombstones/restricciones se reaplican tras restore antes de habilitar tráfico.

## 4. Risk register residual

| ID | Riesgo residual | Capa | Nivel | Tratamiento/owner lógico |
|---|---|---|---|---|
| R-01 | Configuración real de proveedor diverge del contrato de producto | HYBRID/ENVIRONMENT | ALTO | Onboarding account-specific; Operación + cliente |
| R-02 | Solicitud DSR parcial por permisos, rate limit o capacidad del proveedor | HYBRID | ALTO | Estado parcial, retry/escalamiento y evidencia; Privacy Lead |
| R-03 | Backup/restore real reintroduce datos eliminados o restringidos | ENVIRONMENT | ALTO | Validar restore y replay DSR; Infraestructura + Privacy Lead |
| R-04 | Red, TLS, IAM, cifrado o permisos reales insuficientes | ENVIRONMENT | ALTO | Checklist INFRA-V01–V15; Infraestructura + cliente |
| R-05 | Retención/rotación efectiva difiere de los defaults declarados | HYBRID/ENVIRONMENT | MEDIO | Verificación post-deployment; Operación |
| R-06 | Hunter Free no soporta la capacidad prevista | HYBRID | MEDIO | Reconciliar plan/endpoint antes de producción; Product Owner |
| R-07 | Jurisdicción, base jurídica o DPIA específica no decidida | CLIENTE | ALTO | Gate de onboarding; cliente + Privacy Lead |

## 5. RACI lógico

| Actividad | Emactiva Product Owner | Emactiva Security/Privacy | Emactiva Infra/Operación | Cliente Controller | Proveedor |
|---|---|---|---|---|---|
| Contrato y configuración del producto | A/R | C | C | C | I |
| Onboarding de cuenta y finalidad | C | C | R | A | I |
| Incidente técnico | A | C | R | I | C/R en su superficie |
| Evaluación/notificación de privacidad | C | R | C | A | C |
| Verificación de identidad DSR | I | C | I | A/R | I |
| Ejecución DSR en LeadFlow | A | C | R | C | I |
| Acción DSR en proveedor | A | C | R | C | R en su superficie |
| Backup, restore y replay DSR | C | C | A/R | I | C |
| Decisión DPIA/base jurídica | C | R | C | A | I |

`A` accountable, `R` responsible, `C` consulted, `I` informed. Son roles lógicos; las personas se asignan durante onboarding.

## 6. Transferencias y criterio DPIA

Producto: mantener endpoints y proveedores configurables, registrar región/rol por cuenta, limitar datos, exigir DPA/SCC cuando aplique y conservar evidencia de revisión. Cliente/entorno: decidir finalidad, base jurídica, jurisdicción, región, transferencias, excepciones y requisitos de notificación.

La DPIA se activa para decisión formal antes de producción cuando el contexto real indique alto riesgo, incluyendo tratamiento a gran escala, categorías sensibles, monitoreo sistemático, perfilado/decisiones significativas, combinación extensa de fuentes, titulares vulnerables, tecnología o usos novedosos, transferencias complejas o imposibilidad práctica de ejercer derechos. La decisión concreta queda **NOT_VERIFIED** hasta conocer cliente, datos, volumen, finalidad y jurisdicción.

## 7. Tabletop documental sintético

**Incidente:** un canario técnico indica posible exposición de un header de autorización en un log. Resultado: clasificar como posible confidencialidad; detener salida afectada; rotar la credencial sintética; preservar solo timestamp/componente/código; revisar sanitización y alcance; escalar a Security/Privacy; cliente decide notificación según datos reales; cerrar con causa, corrección y revisión. No se usó PII ni secreto real.

**DSR:** un titular sintético solicita acceso y eliminación. Resultado: cliente verifica identidad; operador ejecuta LOCATE/EXPORT; segundo rol aprueba DELETE; ambigüedad/hold bloquearían la acción; HubSpot/Hunter quedan como acciones trazables y Slack N/A; el mismo `request_id` evita duplicados; se conserva tombstone HMAC y evidencia no personal. No se llamó a proveedores reales.

## 8. REM-21 — evidencia exigida en onboarding/deployment

**REM-21=NOT_VERIFIED / ENVIRONMENT.** Por cada cuenta activa se debe recoger, sin secretos: owner y fecha; contrato/DPA y versión; rol; región/data residency; transferencias/SCC y subprocesadores; plan; scopes, usuarios y permisos; propiedades/funciones habilitadas; retención/borrado/backups; operación DSR; controles de IA/uso secundario; prueba sintética de mínimo payload. Para Slack deben completarse V01–V08. No se cierra con documentación general.

## 9. Mapa de evidencia final

| Control | Evidencia reutilizada / ejecución final |
|---|---|
| PRIV-T01 minimización | `test_event_identity_minimization.py`, `test_adapter_boundary_validation.py`, suite n8n |
| PRIV-T02 acceso | `test_database_role_separation.py`, `test_r3_dsr_backup.py` |
| PRIV-T03 autorización | `test_adapter_auth.py`, `test_r3_dsr_backup.py` |
| PRIV-T04 logs | `test_r4_logging_portability.py` |
| PRIV-T05 retención | `test_retention_purge.py` |
| PRIV-T06 eliminación | `test_r3_dsr_backup.py` |
| PRIV-T07 exportación | `test_r3_dsr_backup.py` |
| PRIV-T08 terceros | `test_provider_adapters.py`, registro R5; cuenta real pendiente |
| PRIV-T09 transferencias | registro R5 y checklist account-specific; evidencia real pendiente |
| PRIV-T10 incidentes | procedimiento y tabletop de este documento |
| EDPB-T01 configuración | `test_deployment_security.py`, Compose config |
| EDPB-T02 secretos | `test_r2a_recovery_security.py`, `test_n8n_credential_cleanup.ps1` |
| EDPB-T03 hardcodes | `test_r4_logging_portability.py`, validadores |
| EDPB-T04 dependencias | build/clean start y suite integrada |
| EDPB-T05 persistencia | `test_persistence.py`, recovery/retención |
| EDPB-T06 sustitución | `test_deployment_security.py`, overrides Compose |
| EDPB-T07 operación | recovery, DSR, runbooks y table tops |
| EDPB-T08 logging | `test_r4_logging_portability.py`, Compose config |
| EDPB-T09 documentación | validación R5/R6 y HANDOFF final |
