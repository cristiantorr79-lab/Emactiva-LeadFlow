# LeadFlow — Portafolio técnico-comercial

**Emactiva · Ideas que avanzan contigo**
**Versión:** LF013 v0.1 · **Estado:** aprobado (no es certificación de comercialización ni despliegue productivo)

## 1. El problema que resuelve

Cuando los prospectos llegan por formularios o sistemas desconectados, su registro manual en un CRM puede introducir duplicados, demoras y errores difíciles de rastrear. LeadFlow organiza la recepción y gestión técnica de esos prospectos, de modo que cada envío tenga tratamiento controlado y trazable.

## 2. Qué hace LeadFlow

Recibe eventos desde una fuente integrable; valida y normaliza los datos; controla envíos duplicados; busca o registra el contacto en el CRM; agrega una consulta/interacción cuando corresponde; permite enriquecimiento acotado; registra estados técnicos, controla reintentos y recupera operaciones ambiguas sin repetir escrituras a ciegas.

**Propuesta comercial aprobada:** «LeadFlow ayuda a empresas a recibir y gestionar leads de forma más ordenada, evitando duplicados, reduciendo tareas manuales y manteniendo trazabilidad cuando algo falla».

## 3. Caso de uso: un contacto, dos consultas

1. **EVENT 1:** llega el primer formulario, con email válido y una consulta. LeadFlow identifica el envío, incorpora el LEAD al CRM y registra una INTERACTION cuando está habilitada.
2. **EVENT 2:** la misma persona envía una consulta nueva. Se reutiliza el LEAD existente y se registra una segunda INTERACTION.
3. **Duplicado exacto:** vuelve a recibirse el mismo `source + event_id`. Se identifica como duplicado, sin repetir efectos externos ni crear una tercera INTERACTION.

**EVENT** es el envío técnico; **LEAD**, la identidad relativamente estable del contacto mediante email normalizado; **INTERACTION**, una consulta opcional con `interest` y/o `message`. La compatibilidad V1 sin INTERACTION se mantiene.

## 4. Cómo está construido

`Origen integrable → webhook/n8n → validación → EVENT/idempotencia → LEAD/CRM → INTERACTION opcional → enrichment → persistencia/respuesta`.

- **Núcleo:** n8n orquesta; PostgreSQL controla idempotencia, estados y trazabilidad.
- **Adaptadores:** CRM, enriquecimiento y alertas traducen contratos y errores externos.
- **Entorno:** configuración, credenciales, endpoints, red y operación se definen por implementación, sin fijar proveedor en el núcleo.
- **Confiabilidad:** reintentos solo ante fallos transitorios; reconciliación de resultados ambiguos; fallos sanitizados; configuración crítica fail-closed.

La arquitectura no promete conexión automática con cualquier CRM. Cada adaptación se evalúa por capacidades requeridas y condiciones de entorno.

## 5. Integración real verificada: HubSpot

HubSpot es el primer **CRM Adapter real validado**. Dentro del adaptador, LEAD corresponde a Contact e INTERACTION a Ticket asociado; la propiedad única `leadflow_interaction_key` permite idempotencia y reconciliación. Ticket **no** es parte del concepto de INTERACTION en el núcleo.

La evidencia histórica de LAB-LF-011 demuestra creación de Ticket, asociación, idempotencia, reconciliación y cleanup con datos sintéticos. LAB-LF-012 cerró la funcionalidad controlable de DSR externo: LOCATE, EXPORT, CORRECT y DELETE con aprobación independiente y reconciliación segura. ANNOTATE se mantiene como anotación administrativa local.

**Límites que deben declararse cuando apliquen:** el archive de Ticket en HubSpot no demuestra borrado físico irreversible (**WARN**); RESTRICT externo de HubSpot **NOT_VERIFIED / capability_not_available**. La capacidad técnica demostrada no equivale a garantía de cumplimiento legal para todo cliente o jurisdicción.

## 6. Seguridad, privacidad y portabilidad

Se minimiza información persistida y evidencias; los logs no incorporan payload completo, email en claro, contenido de INTERACTION ni secretos. Los datos de demostración y prueba son sintéticos. Los identificadores hash siguen siendo información seudonimizada. La configuración y los secretos pertenecen al entorno; el núcleo permanece independiente de la infraestructura.

Los controles de red, TLS, IAM, backups, monitoreo, rotación, proveedor y operación deben verificarse por cada deployment concreto. Un piloto técnico o una demo no equivalen a validación automática de producción de otro cliente.

## 7. Evidencia y demostración

- **Demo comercial oficial, aceptada en LF009:** [Video de LeadFlow](../LAB-LF-009/material_comercial/Emactiva_LeadFlow_Demo_LF009_FINAL_v2_audio_uniforme.mp4).
- **Demo y aceptación visual:** [HANDOFF LF009](../LAB-LF-009/HANDOFF_LAB-LF-009.md).
- **EVENT + LEAD + INTERACTION:** [HANDOFF LF008](../LAB-LF-008/HANDOFF_LAB-LF-008.md).
- **Integración real HubSpot INTERACTION:** [HANDOFF LF011](../LAB-LF-011/HANDOFF_LAB-LF-011.md).
- **DSR HubSpot y límites:** [HANDOFF LF012](../LAB-LF-012/HANDOFF_LAB-LF-012.md).
- **Arquitectura vigente:** [ARCHITECTURE.md](../../docs/architecture/ARCHITECTURE.md).
- **Contratos vigentes:** [CONTRACTS.md](../../docs/architecture/CONTRACTS.md).
- **Ficha técnica:** [LEADFLOW_TECHNICAL_SHEET.md](../LAB-LF-005/LEADFLOW_TECHNICAL_SHEET.md).
- **Guía de demo:** [LEADFLOW_DEMO.md](../LAB-LF-005/LEADFLOW_DEMO.md).
- **Pantallas auxiliares de demo:** [demo-assets](../LAB-LF-005/demo-assets/).

Las referencias relativas están preparadas para ubicar este documento en `labs/LAB-LF-013/`; su incorporación y verificación real en Git quedan pendientes.

## 8. Modalidades de entrega

**Entrega técnica:** Emactiva entrega artefactos, documentación y handoff. El cliente realiza implementación, despliegue, operación y controles propios de su infraestructura.

**Implementado por Emactiva:** Emactiva configura, integra, despliega y valida el alcance expresamente acordado en un entorno autorizado. El cliente participa en la aceptación y asume la operación después del handoff, salvo acuerdo diferente.

No se incluyen automáticamente licencias, servicios de terceros, hosting, soporte 24/7, mantenimiento indefinido, desarrollo de nuevos proveedores ni operación continua. Precio, condiciones de soporte y alcance contractual son materias de **LAB-LF-014**.

## 9. Invitación a conversar

**Antes de proponer una solución, queremos entender tu proceso.**

¿Dónde se originan hoy los contactos de tu negocio, en qué CRM o sistema deben quedar registrados y cuál es la mayor dificultad en su gestión?

**Siguiente paso:** diagnóstico inicial de fuentes, sistema destino, volumen y necesidades para determinar si LeadFlow es compatible con el caso real y qué modalidad de implementación corresponde.

---

**Estado documental LF013:** ubicación y enlaces integrados; revisión comercial aprobada. Los PASS históricos citados no constituyen nuevas pruebas funcionales.
