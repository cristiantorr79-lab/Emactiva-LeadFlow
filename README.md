# Emactiva LeadFlow

Automatización modular de captación y gestión de leads para PYMES. Busca reducir la carga manual, los contactos duplicados y los fallos sin trazabilidad al integrar formularios con un CRM.

## Alcance V1

Webhook → validación y normalización → idempotencia en PostgreSQL → consulta y creación/actualización CRM → enriquecimiento → actualización CRM → logging persistente → respuesta. Los errores se clasifican, se reintentan solo cuando corresponde y generan alerta Slack al fallar definitivamente.

Tecnologías previstas: n8n como orquestador, PostgreSQL como persistencia, CRM y enriquecimiento simulados con contratos realistas, Slack mediante webhook configurable y variables de entorno. Python (biblioteca estándar) se usa únicamente para validar este repositorio.

El núcleo contiene reglas reutilizables; los adaptadores traducen contratos y errores de cada proveedor. La V1 no incluye CRM real, dashboard, WhatsApp, IA ni multiempresa completa.

## Estado actual

LAB-LF-001 en curso. LF-001.C incorpora un núcleo n8n local que autentica, valida, normaliza, reclama eventos en PostgreSQL y responde NEW/DUPLICATE. Es un workflow de desarrollo importable; **todavía no existe procesamiento comercial productivo**, CRM, enrichment ni Slack.

- [Arquitectura](docs/architecture/ARCHITECTURE.md)
- [Contratos](docs/architecture/CONTRACTS.md)
- [Setup y validación](docs/setup/SETUP.md)
- [Plan de pruebas V1](docs/testing/TEST_PLAN_LF_V1.md)
- [Handoff LAB-LF-000](labs/LAB-LF-000/HANDOFF_LAB-LF-000.md)

Siguiente: LAB-LF-001 — Implementación de infraestructura base y núcleo inicial.
