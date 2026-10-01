# LeadFlow — Client Intake

Este documento registra requisitos, no secretos. Usar datos sintéticos o sanitizados durante diagnóstico y pruebas siempre que sea razonable.

Antes de implementar deben quedar definidos como mínimo el proceso actual, fuente de leads, datos y campos obligatorios, sistema destino/CRM, definición de duplicado, reglas principales, responsable del cliente, entorno objetivo, alcance, restricciones conocidas y accesos disponibles o un plan concreto para obtenerlos.

## A. Entrega técnica

- Organización/proyecto:
- Fuente(s) de leads:
- CRM o sistema destino:
- Proveedores requeridos:
- Campos de entrada y destino necesarios:
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

## Privacidad y seguridad

- Nunca escribir aquí claves, tokens, passwords, webhooks secretos, connection strings ni credenciales.
- Documentar únicamente qué acceso se necesita, para qué, quién lo autoriza y cuándo debe revocarse.
- Los secretos se entregan mediante un mecanismo externo autorizado y se separan por entorno.
- Preferir cuentas técnicas, API keys o tokens con permisos mínimos, accesos temporales y credenciales revocables; evitar contraseñas personales cuando sea posible.
- Preferir ejemplos y datasets sintéticos/sanitizados; no pegar payloads reales si no son estrictamente necesarios y aprobados.
- No asumir que un proveedor, país o base jurídica está aprobado por aparecer en este intake.
