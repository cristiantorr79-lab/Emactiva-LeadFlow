# HANDOFF — LAB-LF-014

**Estado:** LF014-T01 y LF014-T02 cerrados en GitHub; LF014-T03 y el issue padre #3 abiertos. **LAB pendiente de QA documental final y cierre Git.** No se declara `COMMERCIAL READY`.

## Objetivo y alcance

Definir y documentar las dos modalidades comerciales de LeadFlow, sus costos internos, precios y condiciones; producir una ficha comercial para clientes y una plantilla editable de cotización. Sin cambios en core, adapters, workflows, SQL ni infraestructura. Se mantienen los baselines EWB, EPB, EDPB y EQAB y el principio «Cambia el entorno, no el sistema».

## Tickets y estado verificado

- [#12 — LF014-T01 — Modelo de esfuerzo, costos y alcance](https://github.com/cristiantorr79-lab/Emactiva-LeadFlow/issues/12): **CLOSED — completed**. Análisis económico realizado; evidencia pendiente de consolidación en Git.
- [#13 — LF014-T02 — Pricing, inclusiones, soporte y reglas comerciales](https://github.com/cristiantorr79-lab/Emactiva-LeadFlow/issues/13): **CLOSED — completed**. Decisiones aprobadas y materiales generados. La apertura del XLSX corregido en Microsoft Excel fue confirmada por el usuario.
- [#14 — LF014-T03 — Coherencia comercial, QA documental y HANDOFF](https://github.com/cristiantorr79-lab/Emactiva-LeadFlow/issues/14): **OPEN**, pendiente de depuración, revisión final, evidencia Git y autorización de cierre.
- [#3 — LAB-LF-014](https://github.com/cristiantorr79-lab/Emactiva-LeadFlow/issues/3): **OPEN**.

## Decisiones comerciales aprobadas

| Materia | A — Entrega técnica | B — Implementado por Emactiva |
|---|---|---|
| Responsable de implementación | Cliente | Emactiva, en entorno autorizado y alcance acordado |
| Horas internas de trabajo | 10 h | 36 h |
| Reserva interna de soporte | 2 h | 4 h |
| Total presupuestado | 12 h | 40 h |
| Plazo condicionado | 1 día hábil | 5 días hábiles |
| Soporte inicial | 5 días hábiles | 10 días hábiles |
| Precio inicial neto | $400.000 CLP | $1.200.000 CLP |
| Pago | 50 % anticipo / 50 % contra entrega | 50 % anticipo / 50 % contra entrega |

Los plazos comienzan cumplidos los requisitos contractuales/técnicos y, para B, el preflight. El cliente cuenta con tres días hábiles para observaciones concretas, sin aceptación automática por silencio ni renuncia a derechos aplicables. Los defectos atribuibles a Emactiva se corrigen sin cobro adicional. Las reservas de soporte son presupuestarias, no límites automáticos de responsabilidad. No se incluye soporte 24/7, mantenimiento recurrente, monitoreo permanente ni funcionalidades nuevas. Solo HubSpot está validado como CRM real, dentro del alcance demostrado; otros CRM requieren evaluación y validación. Los costos externos necesarios son del cliente por defecto. El derecho de uso está condicionado a verificación de titularidad y licencias.

## Entregables definitivos previstos en `labs/LAB-LF-014/`

1. [Ficha comercial PDF — una página](LEADFLOW_FICHA_COMERCIAL.pdf), para mostrar al cliente.
2. [Ficha comercial DOCX](LEADFLOW_FICHA_COMERCIAL.docx), fuente editable de la ficha.
3. [Plantilla de cotización XLSX](LEADFLOW_PLANTILLA_COTIZACION.xlsx), edición interna y exportación posterior a PDF.
4. [Comparativa interna de modalidades XLSX](LEADFLOW_MODALIDADES_COMERCIALES.xlsx), contiene costos internos: **no enviar a clientes**.
5. Este `HANDOFF_LAB-LF-014.md`.

**Limpieza documental pendiente de ejecutar/verificar:** retirar, una vez preservado el contenido necesario, `LEADFLOW_FICHA_TECNICA_COMERCIAL.md`, `LEADFLOW_MODELO_COTIZACION.md` y `LEADFLOW_MODELO_COSTOS.md`, redundantes frente a los entregables definitivos. Revisar también los scripts auxiliares generados y decidir su conservación según utilidad de reproducción, sin modificar cambios ajenos.

## Evidencia de QA y validaciones

**PASS reportados por Codex en sus ejecuciones focalizadas (sin repetición de suites técnicas):** consistencia de precios, anticipos, saldos, plazos, soporte, inclusiones/exclusiones; cálculos internos de A $154.350 y B $514.500; integridad de la comparativa XLSX; PDF de ficha de una página A4; estructura XML/ZIP de la plantilla de cotización corregida y fórmulas A/B con tasa de prueba 0 %; `git diff --check` en las ejecuciones reportadas. No constituyen todavía el resultado del QA Git final posterior a la limpieza.

**PASS verificado por usuario:** la plantilla `LEADFLOW_PLANTILLA_COTIZACION.xlsx` corregida abre en Microsoft Excel sin la advertencia de reparación anterior. El usuario acepta la versión actual para este LAB, dejando mejoras futuras fuera de alcance.

**Fallo real y corrección:** el primer cálculo de la comparativa referenciaba incorrectamente filas de soporte y fue corregido. Después, la plantilla de cotización mostró reparación de Excel por duplicación de `<pageMargins>` en `sheet1.xml`; se agregó corrección reproducible y el usuario confirmó la apertura satisfactoria de la versión corregida.

**WARN:** identidad visual provisional (logo/paleta/tipografía); DELETE de HubSpot Ticket por archivado no prueba eliminación física irreversible; costos internos provisionales e inversión histórica no cuantificada; material pendiente de consolidación Git.

**NOT_VERIFIED:** exportación de la cotización XLSX a PDF desde Microsoft Excel; fidelidad de DOCX al abrirlo en Word; validación visual independiente del PDF final; RESTRICT externo HubSpot; licencias de terceros y titularidad; tratamiento tributario y redacción jurídica final; rentabilidad/capacidad operacional reales; controles HYBRID/ENVIRONMENT de cada instalación.

## Condiciones de habilitación comercial

La aprobación documental de este LAB **no equivale a habilitación comercial**. Antes de contratar: verificar facultades/licencias, tratamiento tributario, capacidad de implementación/soporte, alcance/compatibilidad, y condiciones de infraestructura y acceso de cada cliente. Respetar el límite de evidencia DSR de HubSpot y los requisitos de privacidad y seguridad.

## Git y cierre pendiente

Al redactar este HANDOFF, los archivos de LF014 y scripts auxiliares se reportaron sin seguimiento en Git; no se ha aportado todavía el inventario Git posterior a limpieza ni un commit/push de cierre. **No declarar PASS Git final sin obtenerlo.** Issues #12 y #13 están cerrados en GitHub, pero #14 y #3 permanecen abiertos.

### Siguiente acción exacta

1. Sustituir este HANDOFF por la versión actualizada y comprobar su codificación UTF-8.
2. Verificar que los cinco entregables definitivos estén presentes, preservar información necesaria y retirar los tres Markdown redundantes ya identificados.
3. Inspeccionar `git status --short` y los auxiliares en `.local/` y `scripts/lab014/` antes de decidir qué incorporar; no agregar artefactos temporales indiscriminadamente.
4. Ejecutar QA final proporcional (`git diff --check` con cambios en seguimiento y comprobación de archivos nuevos), revisar inventario y referencias; sin suites funcionales ni Codex.
5. Solicitar autorización explícita para `git add`/commit/push y, solo después de verificar la evidencia de cierre, cerrar #14 y #3.
