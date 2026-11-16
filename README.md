# Emactiva LeadFlow

Automatización modular de captación y gestión de leads para PYMES. LeadFlow V1 está funcional y probado: reduce carga manual, contactos duplicados y fallos sin trazabilidad al integrar formularios con un CRM.

## Alcance V1

Webhook → validación / normalización → EVENT / idempotencia → LEAD / CRM → checkpoint de contacto → INTERACTION opcional → enrichment → persistencia / respuesta. Los errores se clasifican, se reintentan solo cuando corresponde y generan alerta Slack al fallar definitivamente.

EVENT identifica cada envío técnico mediante `source + event_id` y conserva una identidad SHA-256; un duplicado exacto no repite efectos externos. LEAD representa el contacto relativamente estable y usa el email normalizado como identidad principal de búsqueda. INTERACTION representa una consulta concreta con `interest` y/o `message`: es opcional, por lo que V1 sin interaction sigue soportado. El mismo email con un nuevo `event_id` reutiliza el contacto y puede registrar una nueva interaction.

La solución usa n8n como orquestador y PostgreSQL como autoridad de persistencia e idempotencia. Existen CRM Adapter, Enrichment Adapter y Slack Adapter, configurables por entorno, además de controles de privacidad, retención, DSR y recuperación.

El núcleo contiene reglas reutilizables; los adaptadores traducen contratos y errores de cada proveedor. Una interaction ambigua no se fuerza a fallo terminal: recovery conserva la ejecución original, reconcilia antes de repetir y no recrea contacto ni interaction a ciegas. HubSpot interaction real está validada mediante Tickets dentro del Adapter, con `leadflow_interaction_key` única para idempotencia y reconciliación; el Core sigue siendo CRM-agnostic. Production se configura mediante variables de entorno y validación fail-closed, sin almacenar secretos en Git.

LAB-LF-015 consolidó una implementación precomercial evaluada con Gateway/Bridge, secretos administrados, backup/restore y controles DSR. LF015-T04 mantiene aceptación técnica con advertencias y **no declara COMMERCIAL READY**: endpoint HTTPS por IP, renovación TLS, recuperación ante pérdida total, alerta automática del Core, rotación, límites DSR, aprovisionamiento Linux real, reproducibilidad documental independiente y capacidad/rentabilidad conservan gates explícitos. Los manuales definitivos aún no forman parte del repositorio.

## Estado actual

LAB-LF-007 cerró con evidencia real en una VM piloto: separación de roles PostgreSQL, portabilidad Linux, runtime saludable, rotación de credencial y smoke funcional. Esa evidencia no promueve controles ajenos al alcance del piloto ni sustituye la validación del deployment específico de cada cliente. LAB-LF-008 cerró el modelo EVENT + LEAD + INTERACTION, compatibilidad V1, idempotencia, recovery, privacidad, retención y DSR. LAB-LF-009 actualizó y aprobó la demo comercial. LAB-LF-010 está alineando la documentación y consolidación operativa/comercial, sin reabrir esos cierres.

- [Arquitectura](docs/architecture/ARCHITECTURE.md)
- [Contratos](docs/architecture/CONTRACTS.md)
- [Setup y validación](docs/setup/SETUP.md)
- [Backup y restore](docs/runbooks/BACKUP_RESTORE.md)
- [Handoff vigente — LAB-LF-015](labs/LAB-LF-015/HANDOFF_LAB-LF-015.md)
- [Ficha de implementación Emactiva — LAB-LF-015](labs/LAB-LF-015/LEADFLOW_IMPLEMENTACION_PILOTO_INTERNO.md)
- [Playbook de implementación — LAB-LF-005](labs/LAB-LF-005/LEADFLOW_IMPLEMENTATION_PLAYBOOK.md)
- [Runbook de deployment remoto — LAB-LF-006](labs/LAB-LF-006/LEADFLOW_REMOTE_DEPLOYMENT_RUNBOOK.md)
- [Plantilla de implementación en cliente — LAB-LF-006](labs/LAB-LF-006/LEADFLOW_CLIENT_IMPLEMENTATION_TEMPLATE.md)
- [Handoff — LAB-LF-006](labs/LAB-LF-006/HANDOFF_LAB-LF-006.md)
- [Handoff — LAB-LF-007](labs/LAB-LF-007/HANDOFF_LAB-LF-007.md)
- [Handoff — LAB-LF-008](labs/LAB-LF-008/HANDOFF_LAB-LF-008.md)
- [Handoff — LAB-LF-009](labs/LAB-LF-009/HANDOFF_LAB-LF-009.md)
