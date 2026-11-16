# LF-A01 — Anexos de implementación y aceptación

**Versión documental:** 1.0 · 16/11/2026. **Estado:** edición consolidada para aprobación del responsable. No autoriza exposición comercial.

Plantillas para completar por instalación: no son evidencia de ejecución ni autorización. No incorporar valores de secretos, datos personales ni payloads. Registrar únicamente referencias protegidas.

## A. Ficha de entrega

| Campo | Registro |
|---|---|
| Cliente / código de entorno | __________________ |
| Modalidad A/B y alcance contratado | __________________ |
| Responsable técnico y funcional | __________________ |
| Responsable de privacidad y aprobador DSR | __________________ |
| Versión y commit aprobados | __________________ |
| Fecha, ventana y autorización | __________________ |
| Proveedores, cuentas responsables y región | __________________ |
| Pipeline / etapa / campos HubSpot | __________________ |
| Dominio web y endpoint autorizado | __________________ |
| Soporte, canal y escalamiento | __________________ |
| Custodia y referencia de evidencia | __________________ |
| Responsable operativo y de backup | __________________ |

## B. Inventario de configuración externa

Registrar cada parámetro, origen, responsable y referencia; no copiar valores sensibles. Los manifiestos, el validador y `.env.example` de la versión entregada son la autoridad del conjunto completo. No cargar `.env` automáticamente en producción.

| Familia | Parámetros y controles |
|---|---|
| Core / proyectos | `APP_ENV`, `LEADFLOW_COMPOSE_PROJECT`; verificar nombre efectivo del Core y `COMPOSE_PROJECT_NAME` del bootstrap. |
| PostgreSQL | `POSTGRES_DB`, `POSTGRES_BOOTSTRAP_USER`, `POSTGRES_MIGRATOR_USER`, `POSTGRES_APP_USER`; roles distintos, migraciones y permisos. |
| Core / entradas | `LEADFLOW_ALLOWED_SOURCES`, `LEADFLOW_ALLOWED_INTERESTS`, `PUBLIC_WEBHOOK_HOST`. |
| Adapters | `CRM_PROVIDER`, `ENRICHMENT_PROVIDER`, `CRM_UPSTREAM_URL`, `ENRICHMENT_UPSTREAM_URL`, `RECOVERY_ADAPTER_URL`, `ADAPTER_ALLOWED_OPERATIONS`; capacidades CRM `CRM_CAP_*` según proveedor. |
| HubSpot | `HUBSPOT_PROPERTY_INDUSTRY`, `HUBSPOT_PROPERTY_COMPANY_SIZE`, `HUBSPOT_PROPERTY_WEBSITE`, `HUBSPOT_INTERACTION_KEY_PROPERTY`, `HUBSPOT_TICKET_MESSAGE_PROPERTY`, `HUBSPOT_TICKET_INTEREST_PROPERTY`, `HUBSPOT_TICKET_PIPELINE_ID`, `HUBSPOT_TICKET_STAGE_ID`. Verificar su materialización efectiva, no asumir por presencia en `.env.example`. |
| Recovery / retención | `RECOVERY_MAX_PROCESSING_AGE_SECONDS`, `RETENTION_SUCCESS_DAYS`, `RETENTION_FAILED_DAYS`, `RETENTION_PROCESSING_DAYS`, `RETENTION_PURGE_BATCH_SIZE`; reintentos `RETRY_*`, timeouts `ADAPTER_*_TIMEOUT_MS`. |
| Bridge | `WEB_BRIDGE_COMPOSE_PROJECT`, `WEB_BRIDGE_ENV=production`, `WEB_BRIDGE_PUBLIC_PATH`, `WEB_BRIDGE_UPSTREAM_URL`, `WEB_BRIDGE_SOURCE`, `WEB_BRIDGE_UPSTREAM_NETWORK`, `WEB_BRIDGE_ABUSE_CONTROL=external`, `WEB_BRIDGE_TURNSTILE_MODE=siteverify`. |
| Bridge / verificación | `WEB_BRIDGE_ALLOWED_ORIGINS`, `WEB_BRIDGE_TURNSTILE_HOSTNAMES`, acción, timeout, proxy opcional, límites y timeouts de Bridge según Compose. |
| Gateway | `WEB_GATEWAY_COMPOSE_PROJECT`, `WEB_GATEWAY_BIND_ADDRESS`, `WEB_GATEWAY_PUBLIC_IP`, `WEB_GATEWAY_PUBLIC_PATH=/lead`, `WEB_GATEWAY_UPSTREAM_URL=http://web-bridge:8080/lead`, `WEB_GATEWAY_ALLOWED_ORIGINS`. |
| Gateway / límites | `WEB_GATEWAY_MAX_BODY_BYTES`, `WEB_GATEWAY_REQUEST_TIMEOUT_SECONDS`, `WEB_GATEWAY_UPSTREAM_TIMEOUT_SECONDS`, `WEB_GATEWAY_RATE_REQUESTS`, `WEB_GATEWAY_RATE_WINDOW_SECONDS`, `WEB_GATEWAY_RATE_MAX_KEYS`. |
| Frontend | `VITE_LEADFLOW_FORM_ENABLED`, `VITE_LEADFLOW_BRIDGE_URL`, `VITE_TURNSTILE_SITE_KEY`. Solo valores públicos; habilitación explícita. |
| Backup y DSR | Buckets separados, identidades, claves independientes, variables y límites de M03 y runbook BACKUP_RESTORE. |

Las dos allowlists de orígenes deben coincidir y los hostnames Turnstile deben cubrirlos. Usar HTTPS canónico, sin espacios, rutas, comodines ni `:443` explícito. El Site Key debe corresponder al widget autorizado. No confundir origen frontend con endpoint IP actual.

### B.1 Mapas de referencias a secretos

| Operación | Versión y aliases exactos |
|---|---|
| runtime-compose | `LF015-SECRET-MAP-2`: `POSTGRES_APP_PASSWORD`, `LEADFLOW_WEBHOOK_KEY`, `N8N_ENCRYPTION_KEY`, `RECOVERY_CONTEXT_KEY`, `ADAPTER_SERVICE_KEY`, `DSR_SUBJECT_KEY`, `SLACK_WEBHOOK_URL`, `CRM_API_KEY`, `ENRICHMENT_API_KEY`. |
| web-bridge-compose | `LF015-WEB-BRIDGE-SECRET-MAP-1`: `WEB_BRIDGE_TURNSTILE_SECRET_KEY`, `WEB_BRIDGE_ABUSE_TOKEN`, `LEADFLOW_WEBHOOK_KEY`, `WEB_BRIDGE_EVENT_ID_KEY`. |
| web-gateway-compose | `LF015-WEB-GATEWAY-SECRET-MAP-1`: `WEB_BRIDGE_ABUSE_TOKEN`. |
| Privilegiados separados | `POSTGRES_BOOTSTRAP_PASSWORD`, `POSTGRES_MIGRATOR_PASSWORD`, `DSR_ADAPTER_SERVICE_KEY`; nunca en mapa runtime. |

Ejemplo estructural completo del mapa Gateway (sustituir referencias de ejemplo por las autorizadas; no contiene valores secretos):

```json
{
  "version": "LF015-WEB-GATEWAY-SECRET-MAP-1",
  "provider": "gcp-secret-manager",
  "operation": "web-gateway-compose",
  "expected_identity": "runtime@example-project.iam.gserviceaccount.com",
  "secrets": {
    "WEB_BRIDGE_ABUSE_TOKEN": "projects/example-project/secrets/leadflow-web-bridge-abuse-token/versions/1"
  }
}
```

Usar las mismas cinco propiedades superiores para los otros mapas, con su versión, operación y conjunto exacto de aliases. Bridge fija los IDs `leadflow-turnstile-secret`, `leadflow-web-bridge-abuse-token`, `leadflow-webhook-key`, `leadflow-web-bridge-event-id-key`. Bridge y Gateway requieren referencias al proyecto de la identidad esperada; comprobar las referencias permitidas de Core con su cargador. Usar versiones numéricas y permisos `0600` o más restrictivos en archivos externos. No usar `latest`, valores en claro ni fallback a credenciales locales.

## C. Checklist técnico y de entorno

Marcar PASS, WARN, FAIL, NOT_VERIFIED o N/A justificado. Adjuntar evidencia técnica mínima y responsable a cada resultado. No asignar PASS por mera existencia de un script.

| Control | Clase | Resultado / evidencia |
|---|---|---|
| Checkout, digests, proyecto y manifiestos aprobados | HYBRID | ______ |
| Capacidad, reloj, red, DNS, firewall | ENVIRONMENT | ______ |
| IAM mínimo, mapas, custodia y ausencia de exposición de secretos | HYBRID | ______ |
| Bootstrap, ledger y roles PostgreSQL | HYBRID | ______ |
| Core saludable, redes correctas, sin puertos internos publicados | HYBRID | ______ |
| Aprovisionamiento n8n y estado de contenido | HYBRID | ______ |
| Publicación del workflow expresamente autorizada | HYBRID | ______ |
| Bridge, Gateway, allowlists, Site Key y preflights | HYBRID | ______ |
| TLS, SAN, vigencia y renovación | ENVIRONMENT | ______ |
| Backup, autoridad DSR y restore aislado | HYBRID | ______ |
| Rollback, monitoreo y responsables | HYBRID | ______ |
| Reproducción independiente M01 (EDPB-T09) | HYBRID | ______ |

## D. Secuencia de aceptación funcional

Antes de probar, aprobar un conjunto sintético exclusivo, verificar que no colisiona con datos existentes, identificar responsables y cerrar la exposición a terceros. Usar M01 y M02; no ejecutar casos destructivos DSR sin aprobación separada.

| Caso | Resultado esperado | Evidencia |
|---|---|---|
| Consulta válida de contacto sintético nuevo | 202 público y CRM reconciliado; verificar ejecución terminal | ______ |
| Consulta legítima adicional con mismo correo y nuevo ID | Un contacto y nueva interacción cuando corresponda | ______ |
| Repetición del mismo ID y payload con token renovado | Sin efectos externos adicionales; mismo evento técnico | ______ |
| Solicitud inválida, origen prohibido o auth ausente | Rechazo y cero efectos externos | ______ |
| Turnstile inválido, tamaño excesivo, rate limit | Rechazo correspondiente dentro de límites acordados | ______ |
| Dependencia transitoria o resultado ambiguo, en QA controlado | Retry solo transitorio o reconciliación antes de CREATE | ______ |
| Alertas previstas y logs | Evidencia sanitizada, sin PII; distinguir directo de automático | ______ |
| Cleanup/post-check | Retirar solo elementos sintéticos autorizados; preservar servicio y datos ajenos | ______ |
| Entrega funcional y privacidad | Responsable conoce CRM, soporte, límites y derivación DSR | ______ |

## E. Acta de aceptación

Resultado por alcance: ACEPTADO / ACEPTADO CON WARN / NO ACEPTADO. ACEPTADO requiere controles aplicables demostrados. ACEPTADO CON WARN exige limitaciones explícitas, medidas compensatorias y aceptación del responsable, sin fallos bloqueantes. NO ACEPTADO corresponde a un fallo crítico o evidencia obligatoria insuficiente. NOT_VERIFIED nunca equivale a PASS.

| Alcance | Decisión / evidencia |
|---|---|
| Proceso funcional | __________________ |
| Gate técnico / GATE-PILOT de EQAB | __________________ |
| Seguridad y privacidad del entorno | __________________ |
| Resiliencia y operación sostenida | __________________ |
| Preparación comercial y licencias | __________________ |
| Exposición pública (autorización independiente) | __________________ |
| Riesgos, mitigaciones, propietario y revisión | __________________ |
| Aprobaciones verificables y fecha | __________________ |

El cliente autoriza infraestructura, finalidad, proveedores y accesos. Emactiva responde por el alcance contratado y los defectos atribuibles al producto. En A instala el cliente y en B Emactiva. El soporte inicial y las exclusiones se documentan en contrato; no se presume monitoreo permanente, mantenimiento ni soporte 24/7. Ningún PASS concede por sí solo derechos de propiedad intelectual, autorización de tratamiento de datos o exposición pública.

## F. Evidencia de referencia y límites de aplicación

| Control | Estado histórico de LeadFlow |
|---|---|
| Captación, HubSpot, deduplicación y cleanup | PASS acotado LF015-T03; datos sintéticos. |
| H08/H10/H12 portabilidad de orígenes | PASS SYSTEM reportado; otro dominio real NOT_VERIFIED. |
| H04/H05 reconciliación y minimización de credenciales | PASS SYSTEM reportado; Linux/n8n real NOT_VERIFIED. |
| Respaldo cifrado y restore aislado | PASS acotado; RPO/RTO continuos, pérdida completa y replay productivo no vacío NOT_VERIFIED. |
| Alertas Slack | Entrega directa PASS; automática ante fallo Core NOT_VERIFIED. |
| TLS, IAM, rotación, DSR externo | Pendientes según M01–M03; no certificar un nuevo destino. |
| Aceptación técnica histórica | ACEPTADO CON WARN; no implica aprobación comercial ni operativa. |

Base documental: `5813007` y remediaciones locales reportadas; asociar el paquete al commit final antes de su distribución. Fuentes: M01–M04, SETUP, CONTRACTS, BACKUP_RESTORE y evidencia LF015-T03/T04. Aplican EWB, EPB, EDPB y EQAB v1.0. Las plantillas se completan por instalación, sin trasladar resultados históricos como PASS de un nuevo cliente.
