# LeadFlow — Ficha técnica

## Propósito

LeadFlow ayuda a recibir y gestionar leads de forma ordenada, evitando duplicados, reduciendo tareas manuales y manteniendo trazabilidad cuando algo falla. V1 usa email como identidad principal.

## Arquitectura y flujo

Arquitectura: webhook/n8n como core de orquestación, PostgreSQL como autoridad de idempotencia y trazabilidad, y adapters para CRM, enrichment y alertas. Configuración y secretos se externalizan por entorno.

`Recepción → Validación → Detección de duplicados → CRM → Enriquecimiento → Trazabilidad → Alertas`

## Controles principales

- Validación y normalización de entrada.
- Idempotencia atómica y duplicados sin repetir efectos externos.
- Retries acotados por operación y fallos sanitizados.
- Trazabilidad por `execution_id` y eventos técnicos.
- Separación core/adapters/environment y proveedores reales bloqueados por defecto en development.
- Secretos fuera de Git, mínimo privilegio y configuración fail-closed.

## Privacidad y retención

Se minimizan logs y persistencia; no se guardan payloads completos, email en claro ni `event_id` crudo en el ledger vigente. Datos de prueba sintéticos. La política inicial configurable conserva success/duplicate 90 días, failed 180 días y acota processing/recovery a 7 días; holds y operaciones DSR aplican según contratos vigentes. Finalidad, rol, jurisdicción, terceros y transferencias se confirman por cliente antes de producción.

## Entornos

- **Development:** construcción, mocks, datos sintéticos y QA; sin conexiones accidentales a producción.
- **Demo:** demostración comercial, CRM demo, servicios controlados, credenciales exclusivas y cleanup entre sesiones.
- **Production:** endpoints, credenciales, dominios, red, infraestructura, backups, monitoreo y operación reales. Principio: “Cambia el entorno, no el sistema.”

## Evidencia existente

Runtime con mocks, lead válido, duplicate, ausencia de efectos externos repetidos, persistencia/trazabilidad y cleanup manual: PASS. Demo Sender y CRM Demo View: QA focalizada PASS. Pantallas auxiliares y demo final v1.3: revisión humana PASS. LAB-LF-004 permanece cerrado.

## Demo, modalidades y límites

Demo final: `Emactiva_LeadFlow_Demo_v1.3_spot_clean.mp4` (WARN menor aceptado en audio `00:29–00:31`). Modalidades: **Entrega técnica** e **Implementado por Emactiva**.

No se incluyen por defecto hosting, licencias, costos de API, soporte 24/7, mantenimiento ilimitado, campañas, generación de leads, operación permanente del CRM ni integraciones no evaluadas. Pricing, modalidad administrada/recurrente, SLA y adaptación teléfono/WhatsApp están diferidos. TLS, IAM, red, backups, monitoreo, rotación, infraestructura productiva y post-deployment requieren evidencia del entorno real.

