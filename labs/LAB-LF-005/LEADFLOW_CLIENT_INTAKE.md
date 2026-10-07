# LeadFlow — Client Intake

Este documento registra requisitos, no secretos. Usar datos sintéticos o sanitizados durante diagnóstico y pruebas siempre que sea razonable.

Antes de implementar deben quedar definidos como mínimo el proceso actual, fuente de leads, datos y campos obligatorios, sistema destino/CRM, definición de duplicado, reglas principales, responsable del cliente, entorno objetivo, alcance, restricciones conocidas y accesos disponibles o un plan concreto para obtenerlos.

## A. Entrega técnica

- Organización/proyecto:
- Fuente(s) de leads:
- CRM o sistema destino:
- Proveedores requeridos:
- Campos de entrada y destino necesarios:
- ¿Cada envío representa una nueva consulta?:
- Interaction aplica: Sí / No
- `interest` requerido: Sí / No
- `message` requerido: Sí / No
- Finalidad justificada de `message`, si aplica:
- Allowlist de `interest`:
- Representación esperada de interaction en CRM:
- Capabilities CRM disponibles: `interaction_write` / `interaction_idempotency` / `interaction_reconciliation`:
- Restricciones técnicas u operacionales conocidas:
- Responsable técnico del cliente:
- Modalidad prevista de deployment:
- Clasificación preliminar (`STANDARD / CORE`, `CONFIGURATION / INTEGRATION`, `PRODUCT ADAPTATION`, `CUSTOM / OTHER PRODUCT`):
- Criterio de aceptación de la entrega:

## B. Implementación por Emactiva

Completar lo anterior y además:

- Entorno autorizado (development/test/production y responsable):
- Accesos necesarios y mecanismo autorizado para entregarlos:
- Responsable funcional del cliente:
- Finalidad del tratamiento/proceso:
- Contexto de privacidad y jurisdicción, cuando aplique:
- Rol esperado de Emactiva y del cliente, sujeto a confirmación:
- Requisitos operacionales (ventanas, disponibilidad, logs, backup, monitoreo y soporte acordado):
- Criterios de aceptación funcional y técnica:
- Terceros, regiones, contratos o restricciones de transferencia conocidos:
- Requisitos de retención, eliminación y atención de derechos aplicables:
- Retención y DSR de interactions persistidas en el CRM externo:

## EVENT, LEAD e INTERACTION

- **Reenvío técnico:** mismo `source + event_id`; se clasifica como `duplicate` y no repite efectos externos.
- **Nueva consulta:** nuevo `event_id`, incluso con el mismo email; crea un EVENT nuevo, reutiliza el LEAD identificado por email normalizado y puede crear una nueva INTERACTION.
- V1 sin interaction continúa soportado y no crea una interaction ficticia.
- HubSpot dispone de soporte real validado mediante Ticket dentro del Adapter, con `leadflow_interaction_key` única, asociación al Contact, idempotencia y reconciliación. No se presume que otro CRM ofrezca las mismas capabilities.

## Privacidad y seguridad

- Nunca escribir aquí claves, tokens, passwords, webhooks secretos, connection strings ni credenciales.
- Documentar únicamente qué acceso se necesita, para qué, quién lo autoriza y cuándo debe revocarse.
- Los secretos se entregan mediante un mecanismo externo autorizado y se separan por entorno.
- Preferir cuentas técnicas, API keys o tokens con permisos mínimos, accesos temporales y credenciales revocables; evitar contraseñas personales cuando sea posible.
- Preferir ejemplos y datasets sintéticos/sanitizados; no pegar payloads reales si no son estrictamente necesarios y aprobados.
- Justificar todo texto libre, minimizar `message` y no recolectar datos innecesarios.
- No incluir `message` ni `interest` en logs, Slack o respuestas públicas.
- Si una interaction se persiste externamente, registrar su retención, cleanup y cobertura DSR del provider. En HubSpot la cobertura DSR permanece `PARTIAL / NON-BLOCKING`.
- No asumir que un proveedor, país o base jurídica está aprobado por aparecer en este intake.
