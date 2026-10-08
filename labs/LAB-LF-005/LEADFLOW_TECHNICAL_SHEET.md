# LeadFlow — Ficha técnica

## Propósito

LeadFlow ayuda a recibir y gestionar leads de forma ordenada, evitando duplicados, reduciendo tareas manuales y manteniendo trazabilidad cuando algo falla.

## Modelo funcional

- **EVENT:** envío técnico identificado por `source + event_id`.
- **LEAD:** contacto relativamente estable identificado para búsqueda por email normalizado.
- **INTERACTION:** consulta opcional con `interest` y/o `message`.

Un LEAD puede tener múltiples INTERACTION mediante EVENT nuevos. Un duplicate exacto no repite efectos externos. V1 sin interaction continúa soportado y no crea una interaction ficticia.

## Arquitectura y flujo

Arquitectura: webhook/n8n como core de orquestación, PostgreSQL como autoridad de idempotencia y trazabilidad, y adapters para CRM, enrichment y alertas. Configuración y secretos se externalizan por entorno.

`Recepción → Validación/normalización → EVENT/idempotencia → LEAD/CRM → INTERACTION opcional → Enrichment → Persistencia/trazabilidad → Respuesta/alertas`

## Controles principales

- Validación y normalización de entrada.
- Idempotencia atómica y duplicados sin repetir efectos externos.
- Operation key de interaction: `<idempotency_key>:crm_interaction`, sin PII.
- Recovery reconcilia antes de repetir una operación ambigua y no recrea contacto ni interaction a ciegas.
- Fail-closed cuando un Adapter carece de una capability crítica de escritura, idempotencia o reconciliación.
- Retries acotados por operación y fallos sanitizados.
- Trazabilidad por `execution_id` y eventos técnicos.
- Separación core/adapters/environment y proveedores reales bloqueados por defecto en development.
- Secretos fuera de Git, mínimo privilegio y configuración fail-closed.

## HubSpot validado

HubSpot es el primer CRM Adapter real validado. Solo dentro de ese Adapter, LEAD se traduce a Contact e INTERACTION a Ticket asociado al Contact. La propiedad única `leadflow_interaction_key` soporta idempotencia y reconciliación concluyente. Ticket no es un concepto del Core: LeadFlow permanece CRM-agnostic.

Evidencia LF-011: CREATE **PASS**, ASSOCIATION **PASS**, IDEMPOTENCY **PASS**, RECONCILIATION **PASS** y CLEANUP **PASS**.

## Privacidad y retención

Se minimizan logs y persistencia; no se guardan payloads completos, email en claro ni `event_id` crudo en el ledger vigente. `interest` y `message` permanecen fuera de logs, Slack y respuestas públicas. Recovery usa contexto mínimo, estructurado y cifrado; `lead_identifier` es seudonimizado y sigue siendo dato personal. Se usan datos de prueba sintéticos.

Retención inicial configurable: success 90 días, duplicate 90 días, failed 180 días y processing/recovery sin progreso máximo 7 días. Holds y operaciones DSR aplican según contratos vigentes.

DSR HubSpot según LAB-LF-012: LOCATE, EXPORT, CORRECT y DELETE validados dentro del alcance controlable. DELETE exige aprobación independiente y mantiene WARN por archivado de Tickets sin prueba de eliminación física permanente. RESTRICT permanece NOT_VERIFIED / capability_not_available. No se declara cobertura DSR universal.

## Entornos

- **Development:** construcción, mocks, datos sintéticos y QA; sin conexiones accidentales a producción.
- **Demo:** demostración comercial, CRM demo, servicios controlados, credenciales exclusivas y cleanup entre sesiones.
- **Production:** endpoints, credenciales, dominios, red, infraestructura, backups, monitoreo y operación reales. Principio: “Cambia el entorno, no el sistema.” Los controles HYBRID/ENVIRONMENT se validan para cada deployment concreto; evidencia previa no se generaliza automáticamente.

## Evidencia existente

LF-008 demostró EVENT + LEAD + INTERACTION, compatibilidad V1, idempotencia, recovery, privacidad, retención y DSR local. LF-009 aprobó Demo Sender, CRM Demo View y la demo audiovisual vigente. LF-011 validó interaction real HubSpot mediante Ticket, asociación, idempotencia, reconciliación y cleanup. LF-012 validó las operaciones DSR HubSpot controlables y documentó WARN para archivado de Tickets y NOT_VERIFIED para RESTRICT.

## Demo, modalidades y límites

Demo audiovisual oficial: `labs/LAB-LF-009/material_comercial/Emactiva_LeadFlow_Demo_LF009_FINAL_v2_audio_uniforme.mp4`. Modalidades: **Entrega técnica** e **Implementado por Emactiva**.

No se incluyen por defecto hosting, licencias, costos de API, soporte 24/7, mantenimiento ilimitado, campañas, generación de leads, operación permanente del CRM ni integraciones no evaluadas. Pricing, modalidad administrada/recurrente, SLA y adaptación teléfono/WhatsApp están diferidos. TLS, IAM, red, backups, monitoreo, rotación, infraestructura productiva y post-deployment requieren evidencia del deployment concreto cuando sean aplicables.
