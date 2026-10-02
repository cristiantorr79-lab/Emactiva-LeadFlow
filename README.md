# Emactiva LeadFlow

Automatización modular de captación y gestión de leads para PYMES. LeadFlow V1 está funcional y probado: reduce carga manual, contactos duplicados y fallos sin trazabilidad al integrar formularios con un CRM.

## Alcance V1

Webhook → validación y normalización → idempotencia en PostgreSQL → consulta y creación/actualización CRM → enriquecimiento → actualización CRM → logging persistente → respuesta. Los errores se clasifican, se reintentan solo cuando corresponde y generan alerta Slack al fallar definitivamente.

La solución usa n8n como orquestador y PostgreSQL como autoridad de persistencia e idempotencia. Existen CRM Adapter, Enrichment Adapter y Slack Adapter, configurables por entorno, además de controles de privacidad, retención, DSR y recuperación.

El núcleo contiene reglas reutilizables; los adaptadores traducen contratos y errores de cada proveedor. Production se configura mediante variables de entorno y validación fail-closed, sin almacenar secretos en Git.

## Estado actual

LAB-LF-005 está cerrado y dejó disponible la preparación comercial y el playbook de implementación. LAB-LF-006 prepara la implementación remota en entornos autorizados de clientes. Los controles de infraestructura real —red, DNS, TLS, firewall, IAM, backup/restore, monitoreo y rotación— permanecen `NOT_VERIFIED` hasta obtener evidencia de un deployment real.

- [Arquitectura](docs/architecture/ARCHITECTURE.md)
- [Contratos](docs/architecture/CONTRACTS.md)
- [Setup y validación](docs/setup/SETUP.md)
- [Backup y restore](docs/runbooks/BACKUP_RESTORE.md)
- [Playbook de implementación — LAB-LF-005](labs/LAB-LF-005/LEADFLOW_IMPLEMENTATION_PLAYBOOK.md)
- [Runbook de deployment remoto — LAB-LF-006](labs/LAB-LF-006/LEADFLOW_REMOTE_DEPLOYMENT_RUNBOOK.md)
- [Plantilla de implementación en cliente — LAB-LF-006](labs/LAB-LF-006/LEADFLOW_CLIENT_IMPLEMENTATION_TEMPLATE.md)
- [Handoff — LAB-LF-006](labs/LAB-LF-006/HANDOFF_LAB-LF-006.md)
