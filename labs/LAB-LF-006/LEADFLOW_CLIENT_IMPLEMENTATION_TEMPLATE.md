# LeadFlow — Plantilla de Implementación en Cliente

**Documento reutilizable — No almacenar secretos**

## 1. Identificación

**Cliente / proyecto:**  
**Fecha:**  
**Responsable Emactiva:**  
**Responsable técnico cliente:**  
**Responsable funcional cliente:**  

**Modalidad:**

- [ ] LeadFlow — Entrega técnica
- [ ] LeadFlow — Implementado por Emactiva

**Clasificación:**

- [ ] STANDARD / CORE
- [ ] CONFIGURATION / INTEGRATION
- [ ] PRODUCT ADAPTATION
- [ ] CUSTOM / OTHER PRODUCT

## 2. Objetivo del cliente

**Problema actual:**

**Resultado esperado:**

**Criterio de aceptación funcional:**

## 3. Discovery

### Proceso actual

**Fuente(s) de leads:**  
**CRM / sistema destino:**  
**Volumen aproximado si es relevante:**  
**Proceso actual de duplicados:**  
**Proceso actual ante fallos:**  

### Datos

**Email disponible:** Sí / No  
**first_name requerido:** Sí / No  
**last_name requerido:** Sí / No  
**phone requerido:** Sí / No  

**Interaction aplica:** Sí / No
**interest requerido:** Sí / No
**message requerido:** Sí / No
**Finalidad de message:**
**Representación en CRM:**
**Provider / capability relevante:**

**Justificación de teléfono si aplica:**

**Otros campos necesarios:**

**Finalidad del tratamiento:**

### Integraciones

**CRM:**  
**Enrichment:**  
**Alertas:**  
**Otros sistemas incluidos:**  

### Entorno

**Development:**  
**Test/Staging:**  
**Production:**  

**Infraestructura:**  
**Sistema operativo:**  
**Docker / Compose:**  
**PostgreSQL:**  
**Dominio:**  
**DNS:**  
**TLS:**  
**Firewall:**  
**Monitoreo:**  
**Backup:**  

### Privacidad

**Jurisdicción:**  
**Rol cliente:**  
**Rol Emactiva:**  
**Terceros:**  
**Transferencias conocidas:**  
**Retención aplicable:**  
**Requisitos especiales:**  

## 4. Accesos

Nunca registrar passwords, tokens, API keys, connection strings ni secretos en esta plantilla.

| Recurso | Finalidad | Nivel mínimo requerido | Responsable | Recibido | Revocación requerida |
|---|---|---|---|---|---|
| Infraestructura | | | | Sí / No | Sí / No |
| PostgreSQL migrator | | | | Sí / No | Sí / No |
| PostgreSQL app | | | | Sí / No | Sí / No |
| CRM | | | | Sí / No | Sí / No |
| Enrichment | | | | Sí / No | Sí / No |
| Alertas | | | | Sí / No | Sí / No |
| DNS/TLS | | | | Sí / No | Sí / No |
| Otro | | | | Sí / No | Sí / No |

**Mecanismo autorizado para entrega de secretos:**

## 5. Configuración

No incluir valores secretos.

**APP_ENV:**  
**PUBLIC_WEBHOOK_HOST:**  
**LEADFLOW_ALLOWED_SOURCES:**  
**LEADFLOW_ALLOWED_INTERESTS:**
**CRM_PROVIDER:**  
**ENRICHMENT_PROVIDER:**  
**CRM_UPSTREAM_URL:**  
**ENRICHMENT_UPSTREAM_URL:**  
**Retención success/duplicate:**  
**Retención failed:**  
**Retención processing/recovery:**  
**RETRY_MAX_ATTEMPTS:**  
**Timeouts relevantes:**  
**Capabilities interaction aplicables:**
**ADAPTER_ALLOWED_OPERATIONS para interaction:**
**HUBSPOT_TICKET_PIPELINE_ID, si HubSpot aplica:**
**HUBSPOT_TICKET_STAGE_ID, si HubSpot aplica:**

Los valores de pipeline/stage dependen del entorno; no registrar secretos ni asumir como universales los valores validados en otro portal.

**Mappings del cliente:**

**Notas de configuración:**

## 6. Preflight

| Control | Estado | Evidencia / nota |
|---|---|---|
| Alcance confirmado | | |
| Responsables confirmados | | |
| Entorno autorizado | | |
| Configuración identificada | | |
| Secretos disponibles externamente | | |
| PostgreSQL disponible | | |
| Rol migrator disponible | | |
| Rol app disponible | | |
| Conectividad disponible | | |
| CRM preparado | | |
| Interaction aplica | | |
| Representación CRM de interaction definida | | |
| `interaction_write` | | |
| `interaction_idempotency` | | |
| `interaction_reconciliation` | | |
| Cleanup de interaction definido | | |
| Enrichment preparado | | |
| Alertas preparadas | | |
| Migraciones identificadas | | |
| Backup definido cuando aplica | | |
| Restore definido cuando aplica | | |
| Rollback definido | | |
| Datos sintéticos preparados | | |
| Cleanup definido | | |
| Ventana autorizada | | |

Estados permitidos:

`PASS / WARN / FAIL / N/A / NOT_VERIFIED`

**Resultado preflight:**

## 7. Deployment

**Fecha:**  
**Versión / commit LeadFlow:**  
**Entorno:**  

### Componentes

- [ ] PostgreSQL
- [ ] n8n
- [ ] Adapter
- [ ] CRM integration
- [ ] Enrichment integration
- [ ] Alert integration
- [ ] Otros:

### Migraciones

**Última migración aplicada:**  
**Resultado:**  

### Resultado deployment

`PASS / WARN / FAIL`

**Observaciones:**

## 8. Smoke test

| Prueba | Estado | Evidencia |
|---|---|---|
| PostgreSQL disponible | | |
| n8n disponible | | |
| Adapter disponible | | |
| Configuración válida | | |
| Autenticación funcional | | |
| Comunicación interna | | |
| Endpoint disponible | | |
| Logs disponibles | | |
| Sin error crítico inicial | | |

**Resultado smoke test:**

## 9. Primera ejecución controlada

**Identificador sintético de la prueba:**  
**Datos reales utilizados:** Sí / No  

Si Sí, justificar:

### Caso 1 — contacto nuevo

| Etapa | Estado | Evidencia |
|---|---|---|
| EVENT nuevo | | |
| LEAD creado | | |
| INTERACTION creada, si aplica | | |
| Enrichment | | |
| Persistencia | | |
| Respuesta | | |

### Caso 2 — mismo contacto + nueva consulta

| Evidencia | Estado | Nota |
|---|---|---|
| Nuevo `event_id` | | |
| Mismo email normalizado | | |
| Contacto reutilizado | | |
| Nueva interaction | | |
| No se creó segundo contacto | | |

### Caso 3 — duplicate exacto

**Mismo source:** Sí / No
**Mismo event_id:** Sí / No
**Detectado como duplicado:** Sí / No  
**Creó nueva interaction:** Sí / No
**Repitió efectos externos:** Sí / No  

Resultado esperado:

**No debe repetir efectos externos.**

Si interaction no aplica, documentar la ejecución V1 sin interaction y confirmar que no se creó una interaction ficticia.

## 10. Validaciones del entorno

| Control | Tipo | Estado | Evidencia / nota |
|---|---|---|---|
| Red | ENVIRONMENT | | |
| DNS | ENVIRONMENT | | |
| TLS | ENVIRONMENT | | |
| Firewall | ENVIRONMENT | | |
| IAM | ENVIRONMENT | | |
| Cifrado host/volumen | ENVIRONMENT | | |
| Backup real | ENVIRONMENT | | |
| Restore real | ENVIRONMENT | | |
| Monitoreo | ENVIRONMENT | | |
| Rotación | ENVIRONMENT | | |
| Logs | HYBRID | | |
| Secretos externos | HYBRID | | |
| Persistencia | HYBRID | | |

Estados:

`PASS / WARN / FAIL / N/A / NOT_VERIFIED`

## 11. Producción

**Preflight:**  
**Deployment:**  
**Smoke:**  
**Primera ejecución controlada:**  
**FAIL críticos pendientes:** Sí / No  

**Rollback disponible:** Sí / No  

**Riesgos residuales:**

### Autorización

**Responsable cliente que autoriza activación:**  
**Fecha:**  

**Producción activada:** Sí / No  

**Resultado:**

## 12. Rollback

**Versión anterior identificada:** Sí / No  
**Configuración anterior recuperable:** Sí / No  
**Estrategia DB:**  
**Estrategia integraciones:**  
**Procedimiento para detener tráfico:**  

**Rollback utilizado:** Sí / No  

Si fue utilizado:

**Motivo:**  
**Resultado:**  

## 13. Cleanup

| Elemento | Acción | Resultado |
|---|---|---|
| Leads sintéticos | eliminar / conservar justificado | |
| Contactos CRM de prueba | eliminar / conservar justificado | |
| Interactions CRM sintéticas | eliminar / conservar justificado / no controlable por provider | |
| Archivos temporales | eliminar | |
| Datos temporales | eliminar | |
| Accesos temporales | revocar | |
| Tokens temporales | revocar | |
| Configuración temporal | eliminar | |

**Post-check contactos, cuando sea controlable:**

**Post-check interactions, cuando sea controlable:**

## 14. Handoff

### Entregables

- [ ] Versión instalada registrada
- [ ] Arquitectura concreta registrada
- [ ] Configuración documentada sin secretos
- [ ] Migraciones registradas
- [ ] Responsabilidades registradas
- [ ] Backup/restore registrado
- [ ] Rollback registrado
- [ ] Retención registrada
- [ ] Riesgos registrados
- [ ] Pendientes registrados
- [ ] Soporte posterior delimitado

### Responsabilidades posteriores

**Emactiva:**

**Cliente:**

### Soporte incluido

### No incluido

### WARN

### NOT_VERIFIED

### Pendientes

## 15. Aceptación funcional

Cuando interaction aplique, confirmar:

- [ ] Contacto nuevo y primera interaction correctos
- [ ] Segunda consulta reutiliza el contacto y crea una nueva interaction
- [ ] Duplicate exacto no crea una tercera interaction
- [ ] Datos visibles únicamente donde corresponde
- [ ] `message` e `interest` ausentes de logs, Slack y respuestas públicas
- [ ] Retención, cleanup y límite DSR del provider registrados

**Responsable del cliente:**  
**Fecha:**  

**Resultado:**

- [ ] ACEPTADO
- [ ] ACEPTADO CON WARN
- [ ] NO ACEPTADO

**Observaciones:**

## 16. Resultado final de implementación

**Estado técnico:**

`PASS / WARN / FAIL`

**Estado controles del entorno:**

`PASS / WARN / FAIL / N/A / NOT_VERIFIED`

**Handoff completado:** Sí / No  
**Implementación cerrada:** Sí / No
