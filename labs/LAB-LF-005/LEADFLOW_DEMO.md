# LeadFlow — Guía de demo comercial

Demo audiovisual oficial aprobada: `labs/LAB-LF-009/material_comercial/Emactiva_LeadFlow_Demo_LF009_FINAL_v2_audio_uniforme.mp4`. Estado visual, audio y recorrido comercial: **PASS**.

Duración objetivo: 4–6 minutos. Usar exclusivamente datos sintéticos y un entorno development/demo con mocks. No mostrar `.env`, claves, tokens, headers, URLs sensibles, datos personales reales ni respuestas internas completas.

## Guion

1. **Problema (30–45 s).** “Cuando un lead llega, el trabajo manual, los duplicados y las integraciones frágiles generan retrasos y poca trazabilidad.”
2. **Primer contacto + interaction (45–60 s).** Abrir el Demo Sender, mantener datos sintéticos, seleccionar un interés permitido, escribir un mensaje sintético y enviar. Mostrar `success`, `execution_id`, `crm_action` y luego un contacto con una interaction en CRM Demo View.
3. **Contacto reutilizado (30–45 s).** Pulsar **Nuevo**, mantener el mismo email, cambiar la interaction y enviar. Explicar EVENT (envío), LEAD (identidad estable por email normalizado) e INTERACTION (contexto opcional); mostrar un contacto con dos interactions.
4. **Duplicado exacto (30–45 s).** Sin cambiar `source` ni `event_id` del paso anterior, reenviar. Mostrar `duplicate` y comprobar que no se crea otro contacto ni otra interaction.
5. **Fallo preparado (30–45 s).** Explicar con evidencia sanitizada que una escritura de interaction ambigua queda en estado recuperable y se reconcilia antes de repetirse. Es una fortaleza técnica/comercial, no un escenario principal en vivo.
6. **Trazabilidad (30–45 s).** Explicar que cada recepción tiene `execution_id`, estado y eventos técnicos, sin exhibir PII ni detalles internos innecesarios.
7. **Adaptabilidad (30–45 s).** Explicar la separación core/adapters/configuración/environment: un cliente nuevo no crea un fork del núcleo.
8. **Modalidades (30–45 s).** Presentar Entrega técnica e Implementado por Emactiva; aclarar que no existe todavía modalidad administrada recurrente.
9. **Cierre (15–30 s).** Preguntar: “¿Dónde se originan hoy sus leads, a qué sistema deben llegar y cuál es el principal punto de fricción o pérdida de trazabilidad?”

## Dos niveles de conversación

**Demo comercial:** problema, resultado, ausencia de duplicación, trazabilidad, adaptabilidad y modalidades. Exposición técnica mínima.

**Profundización técnica:** solo cuando corresponda, explicar n8n, contratos, adapters, PostgreSQL, idempotencia, retries y separación de environment. HubSpot es el primer CRM Adapter real validado; INTERACTION se representa como Ticket únicamente dentro de ese Adapter y LeadFlow sigue siendo CRM-agnostic. No convertir la demo inicial en una auditoría técnica ni en una prueba HubSpot real.

## Pantallas auxiliares

Las cuatro pantallas estáticas de `demo-assets/` apoyan el relato comercial y no forman parte del producto funcional LeadFlow:

1. **Apertura:** presenta Emactiva, LeadFlow, la propuesta general y el slogan antes de mostrar herramientas.
2. **El problema:** encuadra tareas manuales, duplicados, pérdida de seguimiento y herramientas desconectadas antes del caso práctico.
3. **Fallos y recuperación:** acompaña la explicación de fallo transitorio, retry controlado y fallo definitivo sin mostrar códigos, logs ni detalles sensibles.
4. **Cierre:** resume adaptabilidad, modalidades aprobadas y la pregunta de diagnóstico al prospecto.

El Demo Sender realiza el envío sintético y muestra success/duplicate; el CRM mock permite evidenciar deliberadamente el efecto controlado en el entorno de demo y no implica dependencia funcional del mock. n8n se muestra brevemente solo durante la profundización técnica y sin exponer secretos o datos internos innecesarios. Las pantallas auxiliares contextualizan esas vistas, pero no las sustituyen ni añaden capacidades al producto.

### CRM Demo View

`http://127.0.0.1:8095/crm` representa visualmente y en solo lectura el estado real en memoria del CRM mock. Muestra datos mínimos del contacto y sus interactions asociadas. No permite editar, borrar, buscar ni administrar; no forma parte de LeadFlow ni representa un CRM comercial específico. `Origen (Source)` se omite porque el CRM mock no almacena ese campo.

Orden recomendado de grabación:

1. Pantalla de apertura.
2. Pantalla del problema.
3. Demo Sender: contacto nuevo + interaction.
4. CRM mock: un contacto / una interaction.
5. Demo Sender: mismo email + nuevo `event_id` + nueva interaction.
6. CRM mock: un contacto / dos interactions.
7. Demo Sender: duplicado exacto del evento anterior.
8. Evidencia de trazabilidad sanitizada.
9. Pantalla de fallos y recuperación.
10. Vista breve de n8n, cuando corresponda.
11. Pantalla de cierre.

El cierre comercial aprobado es: “Antes de proponer una solución, queremos entender su proceso. ¿Cómo están gestionando hoy los leads que reciben?”

## Portfolio mínimo

El paquete inicial incluye el video demo final, un diagrama simple de arquitectura, 3–5 capturas, descripción comercial corta, explicación técnica breve, capacidades principales, evidencia de pruebas, modalidades de entrega y llamada a contacto. Capturas recomendadas: apertura; Demo Sender con lead válido; CRM Demo View con contacto; duplicate con trazabilidad; workflow n8n ordenado.

## Preparación y cierre

- Verificar que el entorno local controlado esté disponible y use mocks.
- Desde la raíz, ejecutar `labs/LAB-LF-005/demo-tools/demo.ps1 status` para comprobar mocks y PostgreSQL.
- Ejecutar `labs/LAB-LF-005/demo-tools/demo.ps1 prepare` para reiniciar exclusivamente crm-mock, enrichment-mock y slack-mock y verificar que quedaron limpios.
- Iniciar el Demo Sender según su README sin imprimir la clave.
- Configurar `DEMO_ALLOWED_INTERESTS` con la misma allowlist del runtime demo; el selector falla cerrado si no hay valores válidos.
- El Demo Sender genera `event_id` con namespace `demo-lf009-<YYYYMMDD-xxxxxx>-<n>`; **Nuevo** no cambia el email. Conservar el valor del segundo envío para demostrar el duplicado y anotar los `execution_id` de la sesión.
- Tener preparada la evidencia sanitizada de fallo/retry.
- Al terminar, cerrar el Sender. El Sender no guarda historial ni tiene base propia. Si se generaron datos temporales en el runtime, aplicar el procedimiento autorizado del entorno; no borrar datos indiscriminadamente durante la reunión.

El comando `cleanup` valida el namespace reservado, pero actualmente falla cerrado sin ejecutar SQL: LeadFlow no persiste `event_id`, por lo que la base no puede demostrar la relación entre sesión y `execution_id`. Hasta aprobar una trazabilidad local específica de demo, el cleanup PostgreSQL requiere selección manual por la lista explícita de `execution_id`; nunca usar email, fecha, últimas filas ni DELETE amplio. Los mocks sí se limpian mediante `prepare`. Este procedimiento corresponde solo al entorno demo; el cleanup de proveedores reales se ejecuta mediante su procedimiento autorizado y no se presume a partir de la limpieza de mocks.

La demo final se producirá por clips de pantalla y voz en off grabada por separado. Esto permite capturar cada lámina, Demo Sender, CRM Demo View y vista breve de n8n sin exponer comandos, secretos o esperas operacionales.
