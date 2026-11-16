# LF-M04 — Manual de usuario funcional

**Versión documental:** 1.0 · 16/11/2026. **Estado:** edición consolidada para aprobación del responsable. No autoriza exposición comercial.

## 1. Qué hace LeadFlow

LeadFlow recibe consultas comerciales, valida la información, controla duplicados técnicos y coordina su registro en el CRM. Facilita el seguimiento de oportunidades; no sustituye al equipo comercial ni garantiza ventas.

| Concepto | Significado |
|---|---|
| EVENT | Recepción técnica identificada de forma estable. |
| LEAD | Contacto identificado mediante su correo normalizado. |
| INTERACTION | Consulta comercial asociada al contacto cuando corresponde. |

La solución de referencia integra un formulario web, HubSpot, Hunter y Slack. Otros canales, campañas, mensajería y scoring no están incluidos de forma automática. El Core no depende de un formulario web en particular, pero cada canal adicional requiere integración y validación.

## 2. Recepción de una consulta

El formulario Emactiva-Web solicita nombre, correo, interés y mensaje como campos obligatorios; apellido, negocio y teléfono son opcionales. El contrato del Bridge exige correo e interés, y el Core exige correo. Otros formularios autorizados pueden tener reglas distintas. Solicitar teléfono solo con finalidad aprobada; no constituye autorización para campañas. No ingresar contraseñas, documentos de identidad ni datos sensibles en el mensaje.

1. Abrir el formulario autorizado y elegir el interés correspondiente.
2. Completar los campos requeridos con información válida y pertinente.
3. Completar Turnstile y enviar una sola vez.
4. Si aparece confirmación de recepción, esperar la comprobación del CRM. HTTP 202 indica aceptación de la solicitud, no éxito de todas las operaciones.
5. Si hay un error, usar la función de reintento del mismo envío. Esta conserva el identificador y contenido originales y solicita una verificación renovada. No emplear “Nueva consulta” para repetir un envío incierto sin reconciliarlo.

**Modo demostración:** el botón «Probar envío (demostración)» permite probar la interfaz, pero la consulta no se transmite ni se almacena. En la landing de referencia esta modalidad fue restituida al terminar el piloto. No realizar una consulta real para comprobarla.

Ejemplo: una consulta sintética con `prospecto@example.test` y un interés autorizado. Si la misma persona hace una segunda consulta legítima, puede producir una nueva interacción asociada al contacto existente. Reenviar el mismo evento técnico no debe generar nuevos efectos externos.

## 3. Seguimiento en HubSpot

1. Acceder al portal autorizado con una cuenta personal y los permisos asignados.
2. Abrir la sección de contactos y buscar el correo de la consulta.
3. Revisar el contacto y las interacciones o tickets asociados; utilizar el pipeline y etapa definidos en la ficha A01.
4. Registrar la gestión comercial mediante los procedimientos de la organización. No editar identificadores de idempotencia.
5. Si falta un contacto o una interacción, informar al soporte antes de crear manualmente un duplicado para compensar un resultado desconocido.

| Resultado observable | Acción |
|---|---|
| Contacto nuevo | Revisar información y atender la consulta. |
| Contacto existente | Revisar la nueva interacción sin crear otro contacto. |
| Datos enriquecidos | Usarlos como referencia y verificar antes de decidir. |
| Sin registro visible | Escalar con hora y referencia técnica, si existe. |

Hunter puede aportar industria, tamaño de empresa y sitio web. No garantiza datos para todos los contactos. No puede sobrescribir correo, nombre o teléfono a través del enriquecimiento. La obtención de valores reales en el piloto sigue sin verificarse plenamente.

Los nombres de menús y campos visibles dependen de la cuenta, permisos y personalización de HubSpot. El implementador debe registrar las referencias específicas de cada cliente en A01. No se presupone un panel propio de LeadFlow.

## 4. Incidencias y estado del envío

| Situación visible | Acción recomendada |
|---|---|
| Datos inválidos | Corregir el campo señalado antes de enviar. |
| Verificación antiabuso rechazada | Renovar la verificación. |
| Límite de solicitudes | Esperar el intervalo indicado; no generar nuevos intentos continuos. |
| Timeout, error de red o respuesta incierta | Conservar la consulta y reintentar la misma cuando corresponda; escalar si persiste. |
| Confirmación de recepción | Revisar a través del operador autorizado; no equivale a éxito del CRM. |

Los estados internos son `received`, `processing`, `retrying`, `duplicate`, `success` y `failed`. No todos son visibles en el formulario. Un duplicado confirma que el evento ya fue reclamado, no que la ejecución original haya concluido con éxito. Un fallo terminal requiere diagnóstico; el usuario no debe intervenir en n8n, PostgreSQL ni credenciales.

Slack sirve como canal de alertas técnicas sin PII. La entrega directa Adapter→Slack fue comprobada; la alerta automática de fallo del Core sigue NOT_VERIFIED. Las notificaciones propias de HubSpot dependen de su configuración. Mantener el procedimiento de escalamiento acordado.

## 5. Privacidad y derechos de titulares

Utilizar únicamente cuentas autorizadas y los datos necesarios para el propósito acordado. No exportar contactos a dispositivos personales ni compartir capturas con datos identificables. El acceso comercial al CRM no habilita operaciones administrativas DSR.

Si una persona solicita acceso, exportación, corrección, eliminación o restricción, derivar al responsable de privacidad mediante el canal definido por el cliente. Este verifica identidad, finalidad y alcance. DELETE y RESTRICT exigen aprobación independiente; una anotación técnica no equivale a corregir el dato en el proveedor. No prometer eliminación física inmediata ni cumplimiento de todos los proveedores externos.

El historial técnico tiene plazos iniciales de 90 días en success/duplicate y 180 días en failed. Los estados processing/recovery sin progreso terminalizan al superar un máximo de 7 días conforme al contrato. Los plazos no sustituyen la política de CRM, backups ni obligaciones del titular. Consultar M02 y M03.

## 6. Soporte y entrega al usuario

Informar mediante el canal contratado: fecha y hora, entorno, pantalla o paso, mensaje genérico, referencia técnica si existe, impacto y si la consulta aparece en el CRM. Sanitizar capturas y no adjuntar payloads, tokens o credenciales.

Antes de entregar el sistema, el responsable funcional confirma acceso al CRM, campos y pipeline, recepción sintética, nueva consulta legítima, ausencia de efectos por duplicado técnico, canal de soporte y derivación de privacidad. Completar A01 y eliminar los registros sintéticos autorizados. La aceptación funcional no sustituye la aceptación técnica, ambiental ni la autorización independiente de exposición pública.

## 7. Referencias y alcance de evidencia

Referencias: M01, M02, M03, A01, contrato `docs/architecture/CONTRACTS.md` y evidencia LF015-T03. Base técnica `5813007` más remediaciones locales reportadas. Evidencia histórica: integración real HubSpot con datos sintéticos, recepción y deduplicación, interfaz validada, y modo demostración confirmado tras renombrado Emactiva-Web. Los nombres de campos del cliente y sus permisos deben comprobarse en su entrega. Aplican EWB, EPB, EDPB y EQAB v1.0.
