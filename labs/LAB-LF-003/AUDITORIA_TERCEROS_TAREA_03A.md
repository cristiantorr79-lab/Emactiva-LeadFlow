# LAB-LF-003 — Tarea 03A: auditoría externa oficial de terceros

Fecha de revisión: **2026-09-26**.

Alcance: incorporación documental de los hallazgos oficiales proporcionados por la auditoría externa realizada por ChatGPT. En esta tarea no se volvió a investigar Internet, no se validaron cuentas reales y no se infieren condiciones no incluidas en esa evidencia. La configuración de LeadFlow se toma de `INVENTARIO_TAREA_01.md` y la evaluación EPB de `MATRIZ_GAP_EPB_V1.md`.

## HubSpot

| Dimensión | Evidencia oficial incorporada | Aplicación a LeadFlow / pendiente |
|---|---|---|
| Rol | Para Customer Personal Data del servicio normal, HubSpot actúa como **Processor**. La relación Controller-to-Controller se aplica específicamente a productos de enriquecimiento HubSpot y determinadas funciones de tracking | LeadFlow usa HubSpot como CRM y Hunter como enrichment. El rol técnicamente esperable para el flujo auditado es Processor, sujeto a confirmar que la cuenta no habilite funciones adicionales |
| DPA | DPA oficial vigente revisado, última modificación 2026-09-16 | Debe conservarse evidencia de aceptación/aplicación a la cuenta real |
| Categorías relevantes | LeadFlow envía email, nombre, apellido, teléfono, empresa y propiedades de enrichment; recibe ID y email de lookup | Mappings efectivos y propiedades habilitadas siguen NOT_VERIFIED |
| Subprocesadores | Lista formal oficial disponible | Debe conservarse la versión aplicable y confirmar la cadena asociada a la región/cuenta |
| Localización | Infraestructura disponible en Estados Unidos Este, Estados Unidos Oeste, Canadá, Australia y Unión Europea/Alemania | Región real de la cuenta LeadFlow: **NOT_VERIFIED** |
| Transferencias | El mecanismo contractual general está documentado en el marco oficial revisado | Aplicación, región y configuración concreta de nuestra cuenta siguen pendientes |
| Retención | El DPA contempla eliminación/devolución tras terminación y tratamiento específico de backups | Plazos/configuración durante el servicio y evidencia operativa de la cuenta siguen pendientes |
| Eliminación y derechos | El DPA contempla controles para retrieve, correct, delete y restrict | LeadFlow no integra hoy una ruta DSR/eliminación; capacidad/configuración efectiva de cuenta pendiente |
| Seguridad | Medidas técnicas y organizativas y notificación de brechas documentadas | Scopes, usuarios, permisos, región y configuración efectiva siguen pendientes |
| IA/uso secundario | La evidencia suministrada no aporta una conclusión específica para este flujo | Mantener NOT_VERIFIED; no inferir uso o ausencia de uso |
| Evidencia de cuenta pendiente | — | Región real; DPA/aceptación aplicable; scopes; usuarios/permisos; mappings; propiedades; funciones de enrichment/tracking habilitadas; retención y borrado efectivos; responsable y fecha de revisión |

Fuentes oficiales revisadas en la auditoría externa:

- https://legal.hubspot.com/dpa
- https://legal.hubspot.com/sub-processors-page
- https://knowledge.hubspot.com/account-security/hubspot-cloud-infrastructure-and-data-hosting-frequently-asked-questions

## Hunter

| Dimensión | Evidencia oficial incorporada | Aplicación a LeadFlow / pendiente |
|---|---|---|
| Rol | Para Customer Personal Data enviado por el usuario para prestar el servicio, Hunter puede actuar como **Processor**. Para Profile Data, Hunter declara actuar como **Controller independiente**. Quien obtiene Profile Data actúa como Controller independiente respecto de su uso | LeadFlow envía email y recibe Profile Data mediante enrichment. Emactiva/cliente debe justificar su propia finalidad, necesidad y base aplicable; no se declara incumplimiento |
| DPA | DPA oficial disponible; Hunter indica que su DPA estándar aplica a través de sus términos | Conservar términos/versión y evidencia de la cuenta/relación aplicable |
| Categorías y fuentes | Email enviado; Profile Data obtenido de páginas web públicas e información profesional pública; generación de email profesional por patrones cuando corresponda; validación/confidence | Es directamente relevante al uso de `combined/find`; necesidad y uso downstream deben documentarse |
| Subprocesadores | Lista oficial disponible; incluye subprocesadores internacionales en múltiples países | Confirmar lista/versión aplicable al servicio y cuenta |
| Localización | Hunter declara servidores en Bélgica | Procesamiento adicional puede involucrar subprocesadores internacionales; ruta efectiva de cuenta/endpoint pendiente |
| Transferencias | Hunter documenta SCC y mecanismos equivalentes aplicables | Países concretos y aplicación a la cuenta/operación LeadFlow pendientes |
| Retención | Para Profile Data, se conserva mientras siga disponible en fuentes públicas o hasta solicitud de eliminación; Hunter declara eliminación dentro de su ciclo cuando desaparece de las fuentes | Retención del Customer Personal Data enviado y operación concreta de cuenta requieren evidencia adicional |
| Eliminación y derechos | Mecanismos de acceso, rectificación, eliminación, restricción y portabilidad para Profile Data | LeadFlow no integra una ruta de derechos con Hunter; procedimiento concreto pendiente |
| Seguridad | Existe DPA y marco oficial, pero la instrucción no aporta detalle suficiente para cerrar todas las medidas | Evidencia de medidas aplicables a cuenta/endpoint permanece pendiente |
| IA/uso secundario | Hunter utiliza IA/ML en distintas funcionalidades y procesos | No hay evidencia suficiente para afirmar que `combined/find` envía el email LeadFlow a OpenAI. Endpoint/configuración específica permanece pendiente |
| Evidencia de cuenta pendiente | — | DPA/términos aplicables; región/ruta efectiva; subprocesadores aplicables; retención del email enviado; endpoint/configuración; IA/ML específica; derechos operativos; finalidad/base de Emactiva/cliente; owner y fecha |

Fuentes oficiales revisadas en la auditoría externa:

- https://hunter.io/data-processing-agreement
- https://hunter.io/privacy-policy
- https://hunter.io/subprocessors
- Documentación oficial Hunter GDPR/DPA citada por la auditoría externa

## Slack

| Dimensión | Evidencia oficial incorporada | Aplicación a LeadFlow / pendiente |
|---|---|---|
| Rol | Para Customer Data, cliente = **Controller** y Slack = **Processor** | LeadFlow envía en ruta normal execution_id, stage y error_code; H03 se mantiene por contenido insuficientemente acotado |
| DPA | Data Processing Addendum disponible | Debe conservarse evidencia aplicable al workspace/contrato real |
| Categorías relevantes | Customer Data limitado por el flujo normal a identificador de ejecución, etapa y código de error | Workspace/canal y validación efectiva de valores siguen pendientes |
| Subprocesadores | Lista oficial disponible; AWS es infraestructura principal | Confirmar versión aplicable al workspace/servicio |
| Localización | Ubicación por defecto puede ser Estados Unidos; data residency existe para ciertas configuraciones. Other Information puede procesarse en Estados Unidos aun con data residency | Región real del workspace LeadFlow: **NOT_VERIFIED** |
| Transferencias | Slack documenta SCC para transferencias internacionales | Aplicación/región/configuración del workspace pendientes |
| Retención | Depende del plan y configuración real del workspace | Configuración LeadFlow: **NOT_VERIFIED** |
| Eliminación y backups | Eliminación desde producción tras solicitud/configuración; backups normalmente destruidos dentro de 14 días, con excepciones limitadas documentadas | Operación, plan, configuración y prueba de eliminación del workspace pendientes |
| Derechos | La evidencia aportada acredita eliminación general, no cierra por sí sola localización/exportación/corrección/restricción en nuestro workspace | Procedimiento y capacidades reales pendientes |
| Seguridad | Cifrado en tránsito y reposo, controles de acceso, incident management y backups documentados | Miembros, apps, canal, permisos y configuración efectiva siguen pendientes |
| IA/uso secundario | Slack declara no entrenar modelos generativos con Customer Data salvo affirmative opt-in; documenta modelos predictivos/globales y opt-out | Estado de opt-in/opt-out y configuración concreta del workspace pendientes |
| Evidencia de cuenta pendiente | — | Región/data residency; DPA/contrato; plan; política de retención; canal/miembros/apps; permisos; eliminación; opt-in/opt-out IA; owner y fecha |

Fuentes oficiales revisadas en la auditoría externa:

- https://slack.com/trust/privacy/privacy-policy
- https://slack.com/terms-of-service/data-processing
- https://slack.com/trust/data-management
- https://slack.com/trust/data-management/privacy-principles
- https://slack.com/security-practices
- https://slack.com/slack-subprocessors

## Conclusiones transversales

- Los tres proveedores tienen marcos contractuales o de tratamiento documentados; eso reduce incertidumbre general, pero no acredita aceptación, región, plan, scopes, permisos o configuración de nuestras cuentas.
- HubSpot es esperablemente Processor en el CRM auditado, mientras no se activen funciones adicionales que cambien el rol.
- Hunter requiere una evaluación diferenciada: Processor para Customer Personal Data enviado y Controller independiente para Profile Data. Emactiva/cliente conserva responsabilidad propia sobre finalidad, necesidad y base de su uso del enrichment.
- Slack documenta seguridad, transferencias, eliminación y prácticas de IA generales, pero retención/región/IA reales dependen del workspace.
- La evidencia oficial no elimina H01-H10 ni la falta de una ruta integral de localización/eliminación. Gate PRIV-ARCH permanece FAIL.
