# LAB-LF-003 — Matriz GAP de LeadFlow contra EPB v1.0

Fecha: 2026-09-26. Alcance: auditoría documental y estática; no constituye dictamen jurídico ni prueba de la operación desplegada.

Baseline técnico: `91aea95c05467b9d006832cb4816887c06b40644`. Baseline corporativo: `<EMACTIVA_ROOT>\00_CORPORATIVO\PRIVACIDAD_Y_DATOS\EPB_v1.0.md`, SHA-256 `A8552A5E1231AF11753CB883E537462E56E8349D91C980C8752DA1AAC30C6C6A`. `<EMACTIVA_ROOT>` representa el directorio raíz corporativo de Emactiva y se resuelve según el entorno. Evidencia técnica primaria: `labs/LAB-LF-003/INVENTARIO_TAREA_01.md`, SHA-256 `2A3763FC9BB760169D47801D2317C5FDB32C23B4720D98D6FEE6DB5C00ADE64A` al iniciar esta tarea.

## Método y criterios

Se cruzó cada requisito con evidencia versionada. La implementación se consultó solo para confirmar puntos de la Tarea 01. No se consultó Internet, no se inspeccionaron secretos o datos reales, no se ejecutaron suites ni servicios y no se atribuyeron prácticas a terceros sin evidencia.

Estados exclusivos: **PASS** evidencia suficiente; **WARN** control parcial o riesgo residual concreto; **FAIL** requisito aplicable incumplido o condición incompatible con un requisito obligatorio; **N/A** no aplica con justificación; **NOT_VERIFIED** puede aplicar, pero falta evidencia jurídica, contractual, operacional o técnica. Un FAIL técnico no prueba exposición ni constituye por sí mismo un incidente.

Referencias abreviadas: `INV` = Inventario Tarea 01; `T03A` = `AUDITORIA_TERCEROS_TAREA_03A.md`; `T03B` = `EVIDENCIA_OPERATIVA_TAREA_03B.md`; `W` = `workflows/leadflow_core_initial.json`; `A` = `adapters/server.py`; `D1…D11` = migraciones del mismo número; `R` = scripts recovery; `C` = Compose/.env.example/.gitignore; `P` = provisioning/validación; `T` = pruebas existentes; `DOC` = arquitectura, contratos, setup y handoffs. Las anclas completas están en INV, las fuentes oficiales suministradas están en T03A y la evidencia account-level/infraestructura está en T03B. EPB y EDPB son baselines distintos y complementarios.

## A. Principios EPB

| ID EPB | Requisito | Aplicabilidad | Evidencia observada | Archivo/componente | Estado | Riesgo/brecha | Evidencia faltante | Acción futura sugerida | H |
|---|---|---|---|---|---|---|---|---|---|
| EPB-P01 | Licitud y legitimidad | Sí: datos de leads | No hay base jurídica, rol ni jurisdicción determinados | EPB §4; INV terceros | NOT_VERIFIED | Tratamiento sin justificación demostrable | Base jurídica por caso/cliente y rol real | Evaluación jurídica y registro por operación | — |
| EPB-P02 | Finalidad determinada | Sí | Finalidad técnica documentada: captación, CRM, enrichment, idempotencia y trazabilidad | README, DOC, INV | WARN | Falta finalidad aprobada y comunicada por cliente/caso | Finalidad comercial y compatibilidad de usos | Aprobar registro de finalidades | H01,H05 |
| EPB-P03 | Minimización | Sí | Proyección webhook→HubSpot y doble allowlist Hunter→CRM; event_id/source libres y email enviado a Hunter | W, A, INV H01/H10 | WARN | Metadatos pueden contener PII; necesidad de Hunter/campos no aprobada | Justificación campo por campo y prueba EPB | Revisar necesidad y ejecutar PRIV-T01 | H01,H05,H08,H10 |
| EPB-P04 | Protección desde diseño y defecto | Sí | Hashes, cifrado recovery, respuestas mínimas, errores canónicos y no-retención n8n declarada | W, A, D1,D9,C | WARN | Retención, derechos, secretos temporales y fallos terminales incompletos | Evidencia operativa y cierre de gaps | Mantener plan de remediación EPB | H02,H04,H06,H09 |
| EPB-P05 | Transparencia | Sí cuando se opere con titulares | No hay aviso, texto o mecanismo de información en repositorio | EPB §4; búsqueda documental | NOT_VERIFIED | El repositorio no permite conocer información entregada al titular | Avisos y responsabilidades cliente/Emactiva | Revisión jurídica/documental por despliegue | — |
| EPB-P06 | Exactitud y calidad | Sí para CRM/enrichment | Email se normaliza; updates parciales; Hunter puede aportar datos sin mecanismo de verificación/corrección | W, A | WARN | Perfil enriquecido puede ser inexacto o desactualizado | Fuente, frescura, corrección y owner | Definir controles de calidad y corrección | H05 |
| EPB-P07 | Retención limitada | Sí | Solo recovery terminal y n8n tienen controles parciales; ledger/tablas/terceros sin plazo | D1-D11,C,INV retención | FAIL | Ausencia total de política general de retención, criterio no negociable EPB §21 | Matriz aprobada y evidencia operativa | Definir matriz y controles, sin diseñarlos aquí | H02 |
| EPB-P08 | Seguridad proporcional | Sí | Autenticación webhook, HTTPS upstream de producción, roles DB, cifrado recovery y tests históricos | W,C,D1,D9,T | WARN | Riesgo/volumen no determinados; red interna, secretos temporales y autorización no verificados | Threat/risk assessment y despliegue real | Evaluación de riesgo y pruebas focalizadas | H03,H04,H06 |
| EPB-P09 | Confidencialidad | Sí | Secrets por entorno, grants mínimos y allowlists; Adapter interno no autentica y recovery expone secretos por argv SQL | A,D1,D9,R,C | WARN | Fronteras internas y operación pueden ampliar acceso | Permisos efectivos/red/usuarios/logs | Revisar autorización y secretos en operación | H03,H04,H06 |
| EPB-P10 | Derechos de titulares | Sí según jurisdicción | Sin funciones/operación integral para localizar, exportar, corregir, eliminar o restringir | D1-D11,A,R | FAIL | Imposibilidad actual demostrada para eliminación integral | Procedimiento, identidad, APIs y terceros | Diseñar capacidad y ejecutar PRIV-T02/06/07 | H02,H07 |
| EPB-P11 | Responsabilidad demostrable | Sí | Inventario y esta matriz; pruebas técnicas históricas | INV,T,este documento | WARN | Faltan terceros, retención, jurisdicción, tests EPB y evidencia operativa | Registro de proveedores, resultados y owners | Completar dossier de evidencias | — |
| EPB-P12 | Gestión basada en riesgos | Sí | H01-H10 y perfil inicial documentados | INV, esta matriz | WARN | No hay método/aceptación/owner ni riesgo residual aprobado | Registro corporativo y responsables | Formalizar evaluación y seguimiento | H01-H09 |
| EPB-P13 | Evaluación de impacto | Potencialmente | D1 estándar, terceros e internacionalización desconocida; volumen/contexto desconocidos | INV, perfil de riesgo | NOT_VERIFIED | No puede decidirse alto riesgo sin operación/mercado/volumen | Perfil cliente, volumen, finalidad, jurisdicción | Decidir DPIA antes de producción | — |
| EPB-P14 | Privacidad en IA | No en baseline actual | No hay IA/modelos ni decisiones automatizadas en el flujo | W,A,DOC | N/A | Reabrir si se incorpora IA | Confirmación de alcance en cambios futuros | Gate de cambio para IA | — |
| EPB-P15 | Datos de prueba | Sí | Tests usan example.com/.invalid y sintéticos; pruebas reales tienen opt-in y email configurado | scripts/test, SETUP | WARN | No hay política que impida datos reales ni cleanup automático HubSpot | Evidencia de datasets, owner y limpieza | Formalizar estándar y ejecutar PRIV-T15 equivalente | — |

## B. Ciclo de vida y arquitectura

| ID EPB | Requisito | Aplicabilidad | Evidencia observada | Archivo/componente | Estado | Riesgo/brecha | Evidencia faltante | Acción futura sugerida | H |
|---|---|---|---|---|---|---|---|---|---|
| EPB-LC01 | Inventario de datos | Sí | Campos, transformaciones, destinos, persistencia y logs inventariados | INV | PASS | Limitado al baseline estático | Confirmación operacional periódica | Mantenerlo ante cambios | H01-H10 |
| EPB-LC02 | Categorías de titulares | Sí | Se infiere leads/contactos; no hay definición aprobada | README, INV | WARN | Pueden existir prospectos, clientes, empleados o menores | Casos de uso y titular por cliente | Registrar categorías explícitas | — |
| EPB-LC03 | Categorías de datos | Sí | D1 identificadores/contacto/perfil y metadatos correlacionables identificados | INV | PASS | Clasificación puede aumentar por contexto | Validación cliente/jurídica | Mantener clasificación D0-D3 | H07 |
| EPB-LC04 | Datos sensibles D2 | Potencial | Contrato no los solicita, pero campos libres y enrichment no prueban ausencia | W,A,INV | NOT_VERIFIED | Entrada/website/company pueden contener información inesperada | Restricciones de uso y muestras operativas controladas | Definir prohibiciones/validaciones | H01,H05 |
| EPB-LC05 | Menores | Potencial | No hay edad, restricción ni caso de uso documentado | Repositorio | NOT_VERIFIED | No puede excluirse tratamiento de menores | Público objetivo y política cliente | Determinar antes de producción | — |
| EPB-LC06 | Fuentes | Sí | Webhook cliente, HubSpot y Hunter identificados | INV flujo | PASS | Origen último de datos Hunter pendiente | Evidencia contractual del proveedor | Completar registro de fuentes | H08 |
| EPB-LC07 | Rol probable de Emactiva | Sí | EPB exige función real; repo no determina controlador/procesador | EPB §16 | NOT_VERIFIED | Obligaciones no asignables | Contrato y modelo operativo | Determinar por despliegue/cliente | — |
| EPB-LC08 | Terceros | Sí | HubSpot, Hunter y Slack identificados técnicamente | A,C,INV | WARN | No existe Registro de Proveedores completo | Evidencia de sección D | Crear registro formal | H08 |
| EPB-LC09 | Países de procesamiento | Sí | Ningún país/región demostrado | Repositorio | NOT_VERIFIED | Transferencias indeterminadas | Regiones de cuentas y subprocesadores | Auditoría oficial posterior | — |
| EPB-LC10 | Jurisdicciones previstas | Sí | Timezone Chile y referencia corporativa no prueban jurisdicción aplicable | C,EPB §14 | NOT_VERIFIED | Perfil jurisdiccional no validado | Mercados, titulares, entidad y contratos | Abrir perfil real antes de producción | — |
| EPB-LC11 | Necesidad de cada campo | Sí | Finalidad técnica observada; no aprobación de necesidad para teléfono/company/enrichment/event metadata | INV inventario | WARN | Posible recopilación excesiva | Propietario de finalidad y justificación | Matriz necesidad-campo | H01,H05,H08 |
| EPB-LC12 | Retención | Sí | No existe matriz general | INV retención | FAIL | Incumple EPB §9 y criterio §21 | Plazos, inicio, eliminación y excepción | Crear Matriz de Retención | H02 |
| EPB-LC13 | IA | No actual | No componente IA | W,A,DOC | N/A | Cambio futuro debe reabrir control | Gestión de cambios | Registrar N/A y vigilar alcance | — |
| EPB-LC14 | Decisiones automatizadas | No en evidencia actual | Automatiza integración y retries, no decisiones con efecto sobre personas | W,A | N/A | Enrichment puede influir procesos posteriores no observados | Uso downstream | Revisar si cambia el uso | — |
| EPB-LC15 | Riesgo inicial | Sí | H01-H10 y perfil de este documento | INV | WARN | Falta aceptación y contexto operacional | Owners, volumen, probabilidad real | Formalizar risk register | H01-H09 |
| EPB-LC16 | Finalidad | Sí | Captación, sincronización CRM, enrichment, idempotencia y auditoría tienen finalidad técnica observada | DOC,INV | WARN | No equivale a finalidad jurídica/comercial aprobada por tratamiento | Registro por cliente/caso y compatibilidad de usos | Aprobar finalidades antes de operar | H01,H05 |
| EPB-ARCH01 | Origen/destino | Sí | Mapa exacto webhook→DB→HubSpot→Hunter→HubSpot→Slack→cliente | INV | PASS | Despliegue efectivo no comprobado | Diagrama/config real | Verificar antes de producción | — |
| EPB-ARCH02 | Almacenamiento | Sí | Tablas, n8n, volúmenes y persistencia de terceros distinguidos | INV,D1,D9,C | PASS | Backups y proveedores pendientes | Infraestructura efectiva | Inventario operativo | H02 |
| EPB-ARCH03 | Transmisión | Sí | Campos/headers/endpoints documentados; HTTPS externo exigido, HTTP/DB interno | INV,A,C,P | WARN | TLS efectivo e infraestructura interna no comprobados | Captura/configuración de despliegue | Verificación de transporte | H04,H08 |
| EPB-ARCH04 | APIs | Sí | Webhook, Adapter y APIs de proveedores identificados | W,A,INV | PASS | Adapter interno carece autenticación de aplicación | Topología y ACL reales | Revisar frontera interna | H03 |
| EPB-ARCH05 | Accesos | Sí | Rol app sin DML, funciones SECURITY DEFINER y scopes HubSpot mínimos observados | D1,D7,D9,T03B | WARN | Grants runtime, IAM host/n8n y acceso Adapter no verificados | IAM, red y DB del futuro despliegue | Revisar post-deployment | H03,H04 |
| EPB-ARCH06 | Eliminación | Sí | Solo cleanup del recovery terminal; no ruta integral | D9,INV | FAIL | No se puede eliminar a un titular en todas las superficies | Diseño y operación de borrado | Bloquear cierre hasta ruta razonable | H02 |
| EPB-ARCH07 | Backups | Sí si existe despliegue | No hay política ni evidencia de backup/WAL/restauración/eliminación | C,INV | NOT_VERIFIED | Copias pueden conservar datos fuera de plazos | Arquitectura operativa | Obtener política y prueba | H02 |
| EPB-ARCH08 | Logs | Sí | Ledger minimizado; n8n save-none/pruning 24; Adapter sin access log | D1,C,A,INV,T03B | WARN | event_id/source, stderr y falta de rotación/configurabilidad mantienen riesgo | Logs runtime post-deployment y remediación SYSTEM | Plan de logging portable | H01,H03,H04 |
| EPB-ARCH09 | Secretos | Sí | Fuera de Git; credencial temporal presente/persistente y secretos recovery en argv | C,P,R,T03B | WARN | ACL no exclusiva y ausencia de cleanup confirmadas | Remediación SYSTEM y controles de entorno | Priorizar H06 | H04,H06 |
| EPB-ARCH10 | Integraciones externas | Sí | HubSpot, Hunter, Slack y contratos técnicos localizados | A,C,INV | PASS | Contratos/ubicación siguen pendientes | Registro de proveedores | Completar sección D | H08 |

## C. Implementación

| ID EPB | Requisito | Aplicabilidad | Evidencia observada | Archivo/componente | Estado | Riesgo/brecha | Evidencia faltante | Acción futura sugerida | H |
|---|---|---|---|---|---|---|---|---|---|
| EPB-IMP01 | Secretos fuera del código | Sí | Variables de entorno y exclusión Git; credencial temporal verificada por metadata/ACL | C,A,W,T03B | WARN | Archivo persiste, ACL amplia y recovery usa secretos en argv | No requiere despliegue para corregir | Priorizar remediación SYSTEM | H04,H06 |
| EPB-IMP02 | Separación de credenciales | Sí | Variables separadas por sistema; mismo nombre POSTGRES_PASSWORD alimenta migrator y app password en Compose | C | WARN | Separación DB declarada se debilita al reutilizar secreto | Credenciales efectivas por ambiente/rol | Revisar segregación | H06 |
| EPB-IMP03 | Validación | Sí | Tipos/longitudes/email/source y mappings; valores enrichment/error incompletos | W,A,D2 | WARN | H01/H03/H05 permiten contenido no acotado | Tests negativos EPB | Endurecimiento futuro | H01,H03,H05 |
| EPB-IMP04 | Autenticación | Sí | Webhook timingSafeEqual; proveedores con headers | W,A | WARN | Adapter interno no autentica clientes; despliegue no verificado | Topología, ACL y autenticación efectiva | Revisar autenticación service-to-service | H03 |
| EPB-IMP05 | Autorización | Sí | DB limita DML; no hay autorización de Adapter ni control por titular/cliente | D1,A | FAIL | Cualquier actor con alcance de red al Adapter puede invocar operaciones | Segmentación e identidad reales | Diseñar autorización antes de producción | H03 |
| EPB-IMP06 | Mínimo privilegio | Sí | Rol app con funciones/SELECT; Service Key HubSpot limitada a Contacts read/write | D1-D11,SETUP,T03B | WARN | Grants PostgreSQL runtime e IAM administrativo no demostrados; password DB reutilizado | Verificación post-deployment | Mantener diseño y verificar entorno | H03 |
| EPB-IMP07 | Cifrado | Sí | pgcrypto AES-256 recovery; n8n encryption key; HTTPS externo requerido | D9,C | WARN | DB interno ssl=disable, cifrado de volumen/backups no demostrado | TLS/at-rest/key management real | Auditoría de infraestructura | H04,H06 |
| EPB-IMP08 | Logs minimizados | Sí | Mensajes constantes/allowlists; event_id/source y códigos libres | A,D1-D6 | WARN | PII puede entrar por campos técnicos y errores internos | PRIV-T04 operativo | Validar/redactar posteriormente | H01,H03,H04 |
| EPB-IMP09 | Separación lógica entre clientes | No: baseline no implementa multicliente | DOC excluye multiempresa completa; ninguna tenant key | DOC,W,D1 | N/A | Antes de multicliente deja de ser N/A | Diseño futuro | Gate de cambio | — |
| EPB-IMP10 | Tratamiento seguro de errores | Sí | Error canónico y respuestas mínimas; nodos/JSON/SQL sin cobertura total | A,W,D4,D5,R | WARN | Ejecuciones pueden quedar processing y trazas no verificadas | Tests de rutas H04/H09 | Pruebas/remediación futura | H04,H09 |
| EPB-IMP11 | Sanitización | Sí | Respuestas públicas y errores canónicos mínimos; allowlists de campos | A,W,D2-D6,T | WARN | Valores de error y metadatos no tienen control homogéneo | Canarios y pruebas de plataforma | Ejecutar PRIV-T04 futuro | H01,H03,H04,H10 |
| EPB-IMP12 | Seudonimización | Sí | SHA-256 determinista para lead_identifier e idempotency_key | W,D1 | WARN | Sigue siendo vinculable y no sustituye retención/acceso | Modelo de amenazas y necesidad | Tratar como D1 y revisar diseño | H07 |
| EPB-IMP13 | Recovery | Sí | Lease, email cifrado, reconciliación y cleanup terminal | D7-D11,R | WARN | Contexto estancado y rutas no terminales; secretos por comando | Tests focalizados y operación real | Revisar tras remediación futura | H02,H04,H09 |
| EPB-IMP14 | Trazabilidad | Sí | executions y execution_events conservan estados, etapas, errores y tiempos | D1-D11 | WARN | Ledger sin retención y metadatos potencialmente personales | Accesos, integridad, plazo y uso operativo | Alinear con retención/incidentes | H01,H02,H07 |
| EPB-IMP15 | Eliminación técnica | Sí | Cleanup recovery terminal y cascada limitada | D9 | FAIL | No existe borrado integral por titular ni propagación a terceros/copias | Diseño, autorización y evidencia operativa | Bloqueante previo a Gate PRIV-ARCH | H02 |

## D. Terceros — Registro preliminar

La presencia del proveedor, servicio, función y categorías de datos se demuestra por código; no equivale a proveedor aprobado. La ausencia contractual se marca NOT_VERIFIED, no FAIL.

| ID EPB | Requisito | Aplicabilidad | Evidencia observada | Archivo/componente | Estado | Riesgo/brecha | Evidencia faltante | Acción futura sugerida | H |
|---|---|---|---|---|---|---|---|---|---|
| EPB-TP-HS01 | HubSpot: proveedor/servicio/función | Sí | CRM Contacts Search/Create/Update; enriquecimiento gratuito de nombres de empresas activo en cuenta | A crm_*; T03A,T03B | WARN | HubSpot no es CRM puro en la configuración observada; rol/procesamiento adicional requiere análisis | Alcance y efecto contractual del enrichment activo | Revisar en plan de remediación documental | — |
| EPB-TP-HS02 | HubSpot: categorías de datos | Sí | Email, nombre, apellido, teléfono, company, industry, size, website, ID | INV | PASS | Valores pueden variar por mapping | Config efectiva | Confirmar por ambiente | H05 |
| EPB-TP-HS03 | HubSpot: ubicación | Sí | Región real de la cuenta verificada: Estados Unidos (Este) | T03B HUBSPOT-V01 | PASS | Transferencias/base aplicable siguen evaluándose por separado | Conservación periódica de evidencia de región | Registrar cambio de cuenta | — |
| EPB-TP-HS04 | HubSpot: subprocesadores | Sí | Lista formal oficial disponible | T03A, página oficial de subprocesadores | PASS | Versión aplicable debe mantenerse | Lista/fecha asociada a cuenta | Incorporar a revisión periódica | — |
| EPB-TP-HS05 | HubSpot: seguridad | Sí | DPA documenta medidas; Service Key observada con solo Contacts read/write | T03A; T03B V02/V03 | PASS | Administración/rotación de la credencial no auditada | Ciclo de vida de la Service Key | Mantener revisión de mínimo privilegio | — |
| EPB-TP-HS06 | HubSpot: retención | Sí | DPA contempla devolución/eliminación al terminar y tratamiento de backups | T03A, DPA oficial | WARN | Retención durante servicio/configuración real no confirmada | Plazos y configuración de cuenta | Conservar evidencia contractual/operativa | H02 |
| EPB-TP-HS07 | HubSpot: eliminación | Sí | DPA contempla retrieve/correct/delete/restrict y eliminación/devolución al terminar | T03A, DPA oficial; A | WARN | LeadFlow no integra DELETE/DSR ni prueba operación real | Procedimiento/API/configuración de cuenta | Integrar en futura ruta DSR | H02 |
| EPB-TP-HS08 | HubSpot: entrenamiento IA | Potencial | No hay evidencia | Repositorio | NOT_VERIFIED | Uso secundario desconocido | DPA/términos/config | Auditoría oficial posterior | — |
| EPB-TP-HS09 | HubSpot: mecanismo contractual | Sí | DPA oficial vigente revisado; HubSpot Processor para Customer Personal Data del servicio normal | T03A, DPA oficial | WARN | Aceptación y funciones activas de cuenta pueden alterar análisis | Contrato/aceptación y configuración real | Archivar evidencia de cuenta | — |
| EPB-TP-HS10 | HubSpot: transferencias | Sí | Marco contractual general y regiones posibles documentados | T03A, DPA/hosting oficiales | WARN | Región/mecanismo aplicable a nuestra cuenta no confirmado | Región y evidencia contractual de cuenta | Revisión operativa/contractual | — |
| EPB-TP-HS11 | HubSpot: responsable de revisión | Sí | No asignado | Repositorio | NOT_VERIFIED | Sin accountability | Nombre/rol/fecha | Asignar owner | — |
| EPB-TP-HU01 | Hunter: proveedor/servicio/función | Sí | Combined Enrichment por email; Processor para datos enviados y Controller independiente para Profile Data | A provider_enrich; T03A | PASS | Emactiva/cliente es Controller independiente de su uso del Profile Data | Finalidad/base propia y owner | Incorporar al registro | H08 |
| EPB-TP-HU02 | Hunter: categorías de datos | Sí | Envía email; recibe perfil company y potencial respuesta adicional descartada | A,INV | PASS | Origen/alcance del enrichment pendiente | Esquema y fuentes oficiales | Confirmar documentalmente | H05,H08 |
| EPB-TP-HU03 | Hunter: ubicación | Sí | Servidores declarados en Bélgica; subprocesadores internacionales | T03A, fuentes Hunter | WARN | Ruta efectiva y países de subprocesamiento de la cuenta/endpoint pendientes | Configuración y lista aplicable | Conservar evidencia operativa | — |
| EPB-TP-HU04 | Hunter: subprocesadores | Sí | Lista oficial disponible | T03A, página oficial | PASS | Versión aplicable debe mantenerse | Lista/fecha asociada al servicio | Revisión periódica | — |
| EPB-TP-HU05 | Hunter: seguridad | Sí | HTTPS/X-API-KEY del cliente; proveedor no evaluado | A,C | NOT_VERIFIED | Medidas del proveedor desconocidas | Medidas/certificaciones | Auditoría oficial posterior | — |
| EPB-TP-HU06 | Hunter: retención | Sí | API usage/logs 3 meses; User Input según Privacy Policy; Profile Data bajo Controller; Data Enrichment Processor hasta eliminación de cuenta | T03A; T03B HUNTER-V05 | PASS | Categorías no deben mezclarse; eliminación operativa LeadFlow no integrada | Mantener evidencia vigente por categoría | Incorporar a matriz de retención | H08 |
| EPB-TP-HU07 | Hunter: eliminación | Sí | Derechos de acceso/rectificación/eliminación/restricción/portabilidad documentados para Profile Data | T03A, fuentes Hunter; A | WARN | LeadFlow no integra operación y tratamiento del email enviado sigue pendiente | Procedimiento concreto de cuenta | Integrar en futura ruta DSR | H02 |
| EPB-TP-HU08 | Hunter: entrenamiento/uso secundario | Potencial | Hunter declara IA/ML en distintas funciones/procesos | T03A, fuentes Hunter | WARN | No hay evidencia de que `combined/find` envíe email a OpenAI ni de configuración específica | Evaluación endpoint/cuenta | No inferir; confirmar si es necesario | — |
| EPB-TP-HU09 | Hunter: mecanismo contractual | Sí | DPA oficial disponible y estándar aplicable mediante términos; roles Processor/Controller independiente documentados | T03A, DPA/privacy oficiales | PASS | Emactiva/cliente debe justificar finalidad/base del Profile Data | Evidencia de términos/cuenta y análisis propio | Archivar contrato y evaluación | H05,H08 |
| EPB-TP-HU10 | Hunter: transferencias | Sí | SCC y mecanismos equivalentes documentados; subprocesadores internacionales | T03A, DPA/subprocesadores | WARN | Países/ruta efectiva de nuestra operación no confirmados | Lista y mecanismo aplicables a cuenta | Revisión operativa/contractual | — |
| EPB-TP-HU11 | Hunter: responsable de revisión | Sí | No asignado | Repositorio | NOT_VERIFIED | Sin accountability | Owner/fecha | Asignar owner | — |
| EPB-TP-SL01 | Slack: proveedor/servicio/función | Sí, como capacidad prevista | Wiring de alertas existe, pero variables locales muestran Slack real no configurado | A Handler /alert,W; T03A,T03B | WARN | No hay workspace/canal LeadFlow operativo; evidencia de Agrovista fue excluida | Reauditar V01–V08 al activar Slack | Mantener deshabilitado o completar onboarding | H03 |
| EPB-TP-SL02 | Slack: categorías de datos | Sí | execution_id, stage, error_code; correlacionables y valores no totalmente acotados | INV,A | PASS | Posible PII vía error_code si frontera abusada | Muestra/config y validación | Confirmar y restringir después | H03 |
| EPB-TP-SL03 | Slack: ubicación | Sí | AWS principal; default puede ser EE. UU.; data residency disponible en ciertas configuraciones | T03A, fuentes Slack | WARN | Región real y tratamiento de Other Information del workspace no confirmados | Región/data residency del workspace | Conservar evidencia operativa | — |
| EPB-TP-SL04 | Slack: subprocesadores | Sí | Lista oficial disponible | T03A, página oficial | PASS | Versión aplicable debe mantenerse | Lista/fecha del workspace | Revisión periódica | — |
| EPB-TP-SL05 | Slack: seguridad | Sí | Cifrado tránsito/reposo, acceso, incident management y backups documentados | T03A, security practices | PASS | Miembros, apps, permisos y canal reales pendientes | Configuración efectiva | Auditoría operativa workspace | — |
| EPB-TP-SL06 | Slack: retención | Sí | Retención depende del plan/configuración del workspace | T03A, data management | WARN | Configuración LeadFlow desconocida | Plan y política efectiva | Conservar captura/configuración | H02 |
| EPB-TP-SL07 | Slack: eliminación | Sí | Eliminación de producción documentada; backups normalmente destruidos en 14 días con excepciones | T03A, fuentes Slack; M,A | WARN | Solicitud/configuración y ejecución real no comprobadas | Operación/admin/plan | Integrar en futura ruta DSR | H02 |
| EPB-TP-SL08 | Slack: entrenamiento IA | Potencial | No entrena modelos generativos con Customer Data salvo opt-in; modelos predictivos/globales con opt-out | T03A, privacy principles | WARN | Opt-in/opt-out del workspace no confirmado | Configuración real | Revisar workspace | — |
| EPB-TP-SL09 | Slack: mecanismo contractual | Sí | DPA disponible; cliente Controller y Slack Processor | T03A, DPA oficial | WARN | Aceptación/contrato del workspace no archivado | Evidencia contractual de cuenta | Archivar y asignar owner | — |
| EPB-TP-SL10 | Slack: transferencias | Sí | SCC documentadas; localización depende de configuración | T03A, DPA oficial | WARN | Región/mecanismo efectivo del workspace no confirmado | Región y contrato real | Revisión operativa/contractual | — |
| EPB-TP-SL11 | Slack: responsable de revisión | Sí | No asignado | Repositorio | NOT_VERIFIED | Sin accountability | Owner/fecha | Asignar owner | — |

## E. Transferencias internacionales

| ID EPB | Requisito | Aplicabilidad | Evidencia observada | Archivo/componente | Estado | Riesgo/brecha | Evidencia faltante | Acción futura sugerida | H |
|---|---|---|---|---|---|---|---|---|---|
| EPB-XFER01 | País de origen | Sí | Cliente/titular/infraestructura no determinados; timezone Chile no prueba origen | C | NOT_VERIFIED | Origen jurídico desconocido | Perfil cliente y hosting | Determinar por despliegue | — |
| EPB-XFER02 | Destino/país | Sí | Regiones posibles oficiales: HubSpot multirregión, Hunter Bélgica/subprocesadores internacionales, Slack default posible EE. UU./residency | T03A | WARN | Regiones reales de las cuentas/workspace no confirmadas | Configuración efectiva | Auditoría operativa de cuentas | — |
| EPB-XFER03 | Proveedor | Sí | HubSpot, Hunter y Slack identificados | INV | PASS | Registro formal pendiente | Owner/fecha | Completar registro | — |
| EPB-XFER04 | Base/mecanismo contractual | Sí si hay transferencia | DPA generales; Hunter y Slack documentan SCC/mecanismos equivalentes | T03A | WARN | Aplicación a cuentas, países y rol concreto no archivada | Contratos y configuración de cuenta | Revisión jurídica/contractual | — |
| EPB-XFER05 | Garantías adicionales | Potencial | HTTPS y medidas oficiales; SCC Hunter/Slack documentadas | A,C,T03A | WARN | No existe evaluación por ruta/país real ni garantías de cuenta | TIA/medidas según caso | Evaluar tras confirmar países | H04 |
| EPB-XFER06 | Restricciones sectoriales | Potencial | Sector/cliente no determinados | Repositorio | NOT_VERIFIED | Podrían existir exigencias superiores | Contexto comercial/jurídico | Determinar por caso | — |
| EPB-XFER07 | Revisión de transferencias | Sí | T03A revisa evidencia general oficial de tres proveedores | EPB §8,T03A | WARN | Falta confirmar región, contrato y configuración de cuentas antes de producción | Países efectivos, evidencia contractual y owner | Completar revisión operativa | — |

## F. Retención y eliminación

No existe actualmente una política general ni Matriz de Retención LeadFlow. Los controles puntuales no satisfacen EPB §9 ni eliminan la brecha no negociable de §21.

| ID EPB | Requisito | Aplicabilidad | Evidencia observada | Archivo/componente | Estado | Riesgo/brecha | Evidencia faltante | Acción futura sugerida | H |
|---|---|---|---|---|---|---|---|---|---|
| EPB-RET01 | `executions` | Sí | Durable, sin TTL/purge por titular | D1-D11 | FAIL | Conservación indefinida de identificadores y metadatos | Plazo/trigger/operación/excepción | Matriz y control futuro | H02,H07 |
| EPB-RET02 | `execution_events` | Sí | Historial durable, sin TTL | D1-D11 | FAIL | Conservación indefinida correlacionable | Igual anterior | Matriz y control futuro | H02 |
| EPB-RET03 | Recovery context | Sí | Cifrado y cleanup al estado terminal/cascade | D9 | WARN | Processing estancado no expira | TTL/operación para no terminales | Definir control futuro | H02,H09 |
| EPB-RET04 | n8n | Sí | Save none y prune 24 declarados | C | WARN | Despliegue/restos/backups no verificados | Config efectiva y prueba | PRIV-T05/06 operativa | H02 |
| EPB-RET05 | Logs reales | Sí | Logs explícitos inventariados; runtime/host no observado | INV | NOT_VERIFIED | Plazos y contenido desconocidos | Config, muestras seguras y rotación | Auditoría operativa | H01,H04 |
| EPB-RET06 | PostgreSQL operativo | Sí | Volumen persistente; sin purge/at-rest/backups documentados | C,D1 | FAIL | Sin control general implementado | Política/operación desplegada | Definir matriz/control | H02 |
| EPB-RET07 | Docker volumes | Sí | Volúmenes nombrados, `down` conserva datos | C,SETUP | FAIL | Vida ligada a operación manual, no a finalidad | Inventario/cleanup/owner | Política operativa | H02 |
| EPB-RET08 | Backups/WAL/exportaciones | Potencial | Sin evidencia | Repositorio | NOT_VERIFIED | Copias fuera del borrado | Política y restore/delete test | Obtener evidencia | H02 |
| EPB-RET09 | HubSpot | Sí | DPA contempla eliminación/devolución al terminar y backups | A,SETUP,T03A | WARN | Plazo/configuración de cuenta y ruta LeadFlow desconocidos | Config/API/procedimiento real | Auditoría operativa | H02 |
| EPB-RET10 | Hunter | Sí | Retención/eliminación de Profile Data documentada; email enviado no persiste localmente | A,T03A | WARN | Retención de Customer Personal Data/endpoint no confirmada | DPA/configuración de cuenta | Auditoría operativa | H08 |
| EPB-RET11 | Slack | Sí | Retención depende de plan; producción elimina tras solicitud y backups normalmente en 14 días | A,M,T03A | WARN | Plan/configuración workspace desconocidos | Config/política/admin real | Auditoría operativa | H03 |
| EPB-RET12 | Mocks/pruebas | Sí en dev/test | Memoria se pierde al reiniciar; pruebas limpian fixtures; HubSpot real test sin cleanup automático | M,T,SETUP | WARN | Disciplina no es política verificable | Estándar y evidencia de cleanup | Formalizar operación | — |
| EPB-RET13 | Matriz/política general | Sí | Ausente | Repositorio, EPB §9 | FAIL | Bloqueante explícito EPB §21 | Dato/finalidad/plazo/inicio/método/excepción | Crear en tarea posterior | H02 |

## G. Incidentes

Retries, errores y alertas Slack son observabilidad operativa; no equivalen al procedimiento de privacidad exigido por EPB §10.

| ID EPB | Requisito | Aplicabilidad | Evidencia observada | Archivo/componente | Estado | Riesgo/brecha | Evidencia faltante | Acción futura sugerida | H |
|---|---|---|---|---|---|---|---|---|---|
| EPB-INC01 | Detección | Sí | Estados, eventos y alertas detectan fallos técnicos limitados | D1-D6,W | WARN | No detectan acceso/filtración/pérdida de privacidad | Monitoreo y casos de privacidad | Procedimiento y tests | H03,H04 |
| EPB-INC02 | Contención | Sí | Sin playbook ni acciones demostradas | Repositorio | NOT_VERIFIED | Respuesta ad hoc | Procedimiento/roles | Crear plan corporativo aplicable | — |
| EPB-INC03 | Preservación de evidencia | Sí | Ledger existe, sin cadena de custodia/protocolo | D1 | NOT_VERIFIED | Evidencia puede ser insuficiente o excesiva | Procedimiento/accesos/integridad | Definir operación | — |
| EPB-INC04 | Evaluación datos/titulares/riesgo | Sí | Sin mecanismo | Repositorio | NOT_VERIFIED | No se podría dimensionar evento | Plantilla/inventario operativo/roles | Definir proceso | — |
| EPB-INC05 | Escalamiento/notificación | Sí | Slack alerta fallo técnico; sin jurisdicción/plazos/roles | W,A | NOT_VERIFIED | Alerta técnica no decide obligaciones | Matriz RACI/contactos/criterios | Definir proceso | — |
| EPB-INC06 | Documentación/registro | Sí | execution_events no es registro de incidentes | D1 | NOT_VERIFIED | Incidentes de privacidad no quedarían gestionados | Registro dedicado/procedimiento | Definir proceso | — |
| EPB-INC07 | Corrección | Sí | Recovery corrige ejecuciones, no vulneraciones | R,D7-D11 | NOT_VERIFIED | Sin workflow de incidentes | Evidencia de proceso | Definir proceso | H09 |
| EPB-INC08 | Prevención de recurrencia | Sí | Tests técnicos, sin postmortem/cambio formal de incidente | T | NOT_VERIFIED | Aprendizaje no demostrable | RCA/postmortem/owner | Definir proceso | — |

## H. Derechos de titulares

Estados se evalúan por superficie. «Localizar» exige una ruta operacional por identidad; conocer que existen datos no basta. Hunter puede no conservar una cuenta del lead, pero se requiere evidencia del proveedor antes de N/A.

| ID EPB | Requisito | Aplicabilidad | Evidencia observada | Archivo/componente | Estado | Riesgo/brecha | Evidencia faltante | Acción futura sugerida | H |
|---|---|---|---|---|---|---|---|---|---|
| EPB-DSR-PG01 | PostgreSQL: localizar | Sí | Hash email y contexto cifrado, sin función de búsqueda por titular | D1,D9 | WARN | Posible con clave/derivación, no operación soportada | Identidad, autorización y procedimiento | Diseñar capacidad | H07 |
| EPB-DSR-PG02 | PostgreSQL: exportar | Sí | SELECT técnico, sin export por titular | D1 | FAIL | No capacidad soportada | Formato, alcance y autorización | Diseñar PRIV-T07 | — |
| EPB-DSR-PG03 | PostgreSQL: corregir | Sí según dato | Sin función de corrección; ledger histórico puede requerir anotación | D1-D11 | FAIL | Datos vinculados no corregibles formalmente | Política por tipo de dato | Diseñar capacidad | — |
| EPB-DSR-PG04 | PostgreSQL: eliminar | Sí | Sin función; app no tiene DML | D1-D11 | FAIL | Imposibilidad técnica actual | Operación privilegiada/auditable | Diseñar PRIV-T06 | H02 |
| EPB-DSR-PG05 | PostgreSQL: restringir | Sí según jurisdicción | Sin estado/control | D1-D11 | FAIL | Procesamiento no restringible por titular | Reglas/estado/procedimiento | Diseñar capacidad | — |
| EPB-DSR-HS01 | HubSpot: localizar | Sí | Lookup por email existe para flujo, no DSR | A | WARN | Pieza técnica disponible, sin operación autorizada | Cuenta/procedimiento | Integrar en DSR futuro | — |
| EPB-DSR-HS02 | HubSpot: exportar | Sí | DPA contempla retrieve; LeadFlow no implementa proceso DSR | A,T03A | WARN | Capacidad/configuración y autorización de cuenta no probadas | API/proceso real | Diseñar operación futura | — |
| EPB-DSR-HS03 | HubSpot: corregir | Sí | PATCH parcial existe, no proceso DSR | A | WARN | Capacidad técnica limitada y sin autorización DSR | Procedimiento y campos | Diseñar operación | — |
| EPB-DSR-HS04 | HubSpot: eliminar | Sí | DPA contempla delete y eliminación/devolución; no DELETE en Adapter | A,T03A | WARN | Capacidad externa no integrada/probada | API/retención/proceso de cuenta | Auditoría y diseño | H02 |
| EPB-DSR-HS05 | HubSpot: restringir | Potencial | DPA contempla restrict; sin operación LeadFlow | T03A | WARN | Configuración y uso downstream desconocidos | Función/proceso real | Auditoría y diseño | — |
| EPB-DSR-HU01 | Hunter: localizar | Potencial | Hunter documenta acceso a Profile Data; roles duales definidos | A,T03A | WARN | Cuenta/procedimiento LeadFlow no integrados | Proceso aplicable | Diseñar operación futura | H08 |
| EPB-DSR-HU02 | Hunter: exportar | Potencial | Portabilidad documentada para Profile Data | T03A | WARN | Operación/cuenta no probadas | Procedimiento real | Auditoría operativa | — |
| EPB-DSR-HU03 | Hunter: corregir | Potencial | Rectificación y fuentes públicas documentadas | T03A | WARN | Perfil inexacto puede propagarse; LeadFlow no integra corrección | Proceso de cuenta | Diseñar operación futura | H05 |
| EPB-DSR-HU04 | Hunter: eliminar | Potencial | Eliminación de Profile Data documentada | T03A | WARN | Email enviado y operación LeadFlow requieren confirmación | Proceso aplicable | Diseñar operación futura | H08 |
| EPB-DSR-HU05 | Hunter: restringir | Potencial | Restricción documentada para Profile Data | T03A | WARN | Operación/cuenta no probadas | Procedimiento real | Auditoría operativa | — |
| EPB-DSR-SL01 | Slack: localizar | Sí para alertas correlacionables | No mecanismo local; workspace desconocido | A | NOT_VERIFIED | execution_id puede estar en mensajes | Admin/API/config | Auditoría operativa | H03 |
| EPB-DSR-SL02 | Slack: exportar | Potencial | Sin evidencia | Repositorio | NOT_VERIFIED | Capacidad depende de plan/rol | Config/contrato | Auditoría operativa | — |
| EPB-DSR-SL03 | Slack: corregir | Potencial | Sin evidencia | Repositorio | NOT_VERIFIED | Mensajes históricos | Config/proceso | Auditoría operativa | — |
| EPB-DSR-SL04 | Slack: eliminar | Sí si alerta contiene dato personal | Eliminación de producción y backup normalmente ≤14 días documentadas; solo mock integrado | M,T03A | WARN | Operación/configuración del workspace no demostrada | Admin/API/retención real | Auditoría operativa | H02 |
| EPB-DSR-SL05 | Slack: restringir | Potencial | Sin evidencia | Repositorio | NOT_VERIFIED | Acceso del canal desconocido | Membresía/permisos | Auditoría operativa | H03 |
| EPB-DSR-LB01 | Logs/backups: localizar | Sí si existen | No inventario operacional | INV | NOT_VERIFIED | Datos residuales no localizables | Catálogo de logs/copias | Auditoría infraestructura | H04 |
| EPB-DSR-LB02 | Logs/backups: exportar | Potencial | Sin evidencia | Repositorio | NOT_VERIFIED | Alcance jurídico/operativo desconocido | Política | Revisión jurídica/operativa | — |
| EPB-DSR-LB03 | Logs/backups: corregir | Potencial | Sin evidencia | Repositorio | NOT_VERIFIED | Inmutabilidad/excepciones no definidas | Política | Definir tratamiento | — |
| EPB-DSR-LB04 | Logs/backups: eliminar | Sí | Sin evidencia | Repositorio | NOT_VERIFIED | Borrado puede no alcanzar copias | Ciclo backup/rotación | Auditoría infraestructura | H02 |
| EPB-DSR-LB05 | Logs/backups: restringir | Sí | Sin evidencia | Repositorio | NOT_VERIFIED | Accesos no demostrados | IAM/proceso | Auditoría infraestructura | H03 |

## I. Pruebas mínimas EPB — estado preliminar

No se ejecutó ninguna prueba en esta tarea. Los resultados indican preparación/evidencia actual, y la columna faltante define el método necesario.

| ID EPB | Requisito | Aplicabilidad | Evidencia observada | Archivo/componente | Estado | Riesgo/brecha | Evidencia faltante | Acción futura sugerida | H |
|---|---|---|---|---|---|---|---|---|---|
| PRIV-T01 | Minimización | Sí | Validación estricta de source/event_id, allowlists de Adapter y regresión final sintética | test_event_identity_minimization, adapter_boundary, n8n_* | PASS | Necesidad jurídica por cliente sigue fuera del test SYSTEM | Decisión de cliente | Verificar en onboarding | H05,H10 |
| PRIV-T02 | Acceso | Sí | Roles DB separados, app sin DDL/admin y DSR administrativo separado | test_database_role_separation, test_r3_dsr_backup | PASS | IAM/red efectivos dependen del despliegue | Evidencia ENVIRONMENT | REM-24 | H03 |
| PRIV-T03 | Autorización | Sí | Webhook y Adapter autenticados; operaciones allowlist; DELETE/RESTRICT con aprobación independiente | test_adapter_auth, test_r3_dsr_backup | PASS | IAM humano real pendiente | Evidencia ENVIRONMENT | REM-21/24 | H03 |
| PRIV-T04 | Logs | Sí | Logger JSON allowlist, error canónico y canarios email/teléfono/token/header | test_r4_logging_portability | PASS | Muestras de host/plataforma reales pendientes | Evidencia ENVIRONMENT | REM-24 | H04 |
| PRIV-T05 | Retención | Sí | Política y purga por estado/plazo, holds, lotes, evidencia mínima e idempotencia | test_retention_purge | PASS | Scheduling, locks y volumen reales pendientes | Evidencia ENVIRONMENT | REM-24 | H02 |
| PRIV-T06 | Eliminación | Sí | DELETE local autorizado, idempotente, tombstone HMAC y coordinación de terceros | test_r3_dsr_backup | PASS | Ejecución real en proveedores/backups pendiente | Evidencia HYBRID/ENVIRONMENT | REM-21/24 | H02 |
| PRIV-T07 | Exportación | Sí | Export minimizado por titular con autorización y sujeto inexistente/ambiguo controlados | test_r3_dsr_backup | PASS | Entrega jurídica/identidad del cliente pendiente | Procedimiento cliente | Onboarding | — |
| PRIV-T08 | Terceros | Sí | Registro, owners lógicos, acciones DSR y dobles HubSpot/Hunter/Slack verificados | test_provider_adapters, test_r5_privacy_operations | WARN | Parte SYSTEM PASS; cuentas, contratos, permisos y SLA reales pendientes | Evidencia account-specific | REM-21 | H08 |
| PRIV-T09 | Transferencias | Sí | Regiones/mecanismos generales, registro y gate de onboarding documentados | registro R5, test_r5_privacy_operations | WARN | Parte SYSTEM documental PASS; rutas/países/mecanismos efectivos pendientes | Evidencia account-specific | REM-21 | — |
| PRIV-T10 | Incidentes | Sí | Procedimiento, RACI, risk register y tabletop sintético completados | registro R5, test_r5_privacy_operations | PASS | Notificación/plazos dependen de cliente y jurisdicción | Decisión de cliente | Onboarding | — |
| PRIV-T11 | Aislamiento multicliente | No actual | Multiempresa fuera de V1 | DOC | N/A | Reabrir antes de multicliente | Confirmación de arquitectura | Gate de cambio | — |
| PRIV-T12 | IA | No actual | Sin IA | W,A,DOC | N/A | Reabrir al incorporar IA | Inventario de componentes | Gate de cambio | — |

## Clasificación H01–H10 contra EPB

Severidad preliminar pondera datos, exposición, probabilidad, impacto, alcance y controles. «CONFIRMADO» significa que la condición de diseño/código está demostrada, no que haya ocurrido una exposición.

| Hallazgo | Controles EPB relacionados | Clasificación | Severidad | Fundamento |
|---|---|---|---|---|
| H01 PII posible en event_id/source | P03,P07,P09; ARCH08; IMP03/08; PRIV-T01/04 | CONFIRMADO | ALTA | Ruta estática directa a tablas sin TTL; entrada válida/ inválida admite contenido personal. No hay evidencia de datos reales |
| H02 retención/eliminación incompleta | P07,P10; ARCH06/07; RET01-13; PRIV-T05/06 | CONFIRMADO | ALTA | Ausencia general demostrada y criterio EPB no negociable; email recovery tiene control parcial |
| H03 fronteras internas/error_code/ID | P08,P09; ARCH05; IMP04/05/08; PRIV-T02/03/04 | CONFIRMADO | MEDIA | Adapter no autentica y valores carecen de allowlist completa; requiere alcance de red/cliente interno, lo que reduce probabilidad |
| H04 trazas/argv/errores/transporte | P08,P09; ARCH03/08/09; IMP01/07/10 | CONFIRMADO | ALTA | Secret/email se incorporan a línea de comando SQL y stderr puede propagarse; exposición efectiva y entorno no verificados |
| H05 semántica enrichment/mapping | P02,P03,P06; LC04/11; IMP03 | CONFIRMADO | MEDIA | Filtro limita claves/tipo, no contenido/URL/colisiones; alcance normal acotado a tres propiedades |
| H06 credencial temporal en claro | P08,P09; ARCH09; IMP01/02/07 | CONFIRMADO | ALTA | T03B confirma archivo presente tras provisioning, sin cleanup y con ACL heredada Modify para varios grupos/SID; contenido no leído y sin evidencia de exposición real |
| H07 seudonimización vinculable | P03,P09,P10; LC03; DSR | CONFIRMADO | MEDIA | Hash determinista y referencias permiten vincular; es dato personal seudonimizado, con exposición limitada por roles |
| H08 email Hunter en URL | P03,P08; TP-HU; XFER; RET10 | CONFIRMADO | MEDIA | Código construye query; logging/retención del tercero no verificados. HTTPS protege contenido en tránsito frente a observadores intermedios |
| H09 rutas no terminales/incompatibilidades | P04,P08; RET03; IMP10; INC | CONFIRMADO | ALTA | Conexiones/nodos y límites SQL muestran rutas que pueden dejar processing; reproducción operativa no necesaria para confirmar diseño, pero impacto real pendiente |
| H10 minimización normal | P03,P04; IMP03/08; PRIV-T01/04 | CONFIRMADO | BAJA | Control favorable demostrado por código/tests existentes; permanece como hallazgo positivo. No descarta H01/H03-H05 |

Ningún H01-H10 se descarta. Todos tienen evidencia estática suficiente para confirmar la condición descrita; los efectos operativos o exposiciones reales permanecen fuera de lo afirmado. No se asigna severidad CRITICA porque no existe evidencia de secreto expuesto, datos sensibles, acceso efectivo no autorizado, gran volumen o incidente real.

## Gates EPB

| Gate | Estado | Evidencia y decisión |
|---|---|---|
| Gate PRIV-00 | WARN | El inventario, riesgos, proveedores y controles SYSTEM están cerrados. Categorías reales de titulares, menores/sensibles, rol, países, jurisdicción, finalidad/base jurídica y decisiones del cliente siguen HYBRID/ENVIRONMENT |
| Gate PRIV-ARCH | WARN | La arquitectura SYSTEM ya permite localizar, exportar, anotar, eliminar y restringir localmente; coordina terceros y reaplica tombstones tras restore. Cuentas, permisos, DSR de proveedores y backup/restore reales siguen sin verificar |

## Perfil de riesgo inicial

| Dimensión | Evaluación preliminar |
|---|---|
| Titulares | Leads/contactos; categorías comerciales exactas, relación previa y menores no verificados |
| D0/D1/D2/D3 | D0 configuración técnica; D1 email/nombre/teléfono/identificadores/perfil; D2 no solicitado pero no excluido; D3 posible por combinación/volumen/contexto, aún desconocido |
| Volumen | Desconocido; sin límites ni métricas de producción evidenciadas |
| Sensibilidad | Principalmente D1; enrichment profesional y correlación pueden elevar riesgo; no se confirma D2 |
| Terceros | HubSpot, Hunter y Slack; evaluación contractual pendiente |
| Internacionalización | Probable técnicamente por SaaS, pero países/regiones/mecanismos no verificados |
| IA | No en baseline actual |
| Decisiones automatizadas | No demostradas; automatización técnica sí, decisiones sobre personas no |
| Multicliente | No en V1; no existe tenant isolation |
| Impacto potencial | Pérdida de confidencialidad/contactabilidad, perfil incorrecto, persistencia y dificultad para derechos; aumenta con volumen y reutilización downstream |
| Riesgo general | **ALTO preliminar para cierre/producción**, por retención, derechos, transferencias/proveedores y secretos operativos incompletos; no equivale a incidente ni a riesgo crítico demostrado |
| EPB-P13/DPIA | **Pendiente de información**: decidir con volumen, categorías reales, sujetos vulnerables, alcance del enrichment, usos downstream, países y jurisdicción. Si aparecen D2/D3, gran escala, perfilado significativo o alto riesgo, será requerida antes de producción |

## Evidencias operativas/contractuales pendientes

| Área | Evidencia concreta requerida |
|---|---|
| HubSpot | Evidencia de aceptación del DPA y contrato aplicable; rol confirmado según funciones habilitadas; región real; subprocesadores/versión aplicable; transferencias de cuenta; retención/eliminación y operación DSR efectivas; términos IA/uso secundario no cubiertos por T03A; scopes, usuarios, permisos, mappings y propiedades reales; owner y fecha |
| Hunter | Evidencia de DPA/términos aplicables; finalidad/necesidad/base propia de Emactiva/cliente para Profile Data; retención del Customer Personal Data/email enviado; subprocesadores y rutas efectivas; configuración de `combined/find`; IA/ML específica del endpoint sin inferir OpenAI; medidas de seguridad no detalladas en la evidencia suministrada; derechos operativos, cuenta y owner |
| Slack | Evidencia de DPA/contrato aplicable; región/data residency real; plan y retención del workspace; subprocesadores/versión aplicable; canal, miembros, apps y permisos; operación de eliminación/exportación; opt-in generativo y opt-out predictivo/global; owner y fecha |
| Infraestructura | Diagrama desplegado; TLS público y upstream efectivo; cifrado interno/at-rest; PostgreSQL/n8n y versiones reales; grants/IAM/red/firewall; backups/WAL/restores/plazos/borrado; logs de n8n/containers/host/reverse proxy sin exponer datos; rotación; estado/permisos/cleanup de `.local/n8n/postgres-credential.json`; gestor/rotación de secretos; regiones de hosting |
| Producto/cliente | Finalidades aprobadas; necesidad campo a campo; categorías de titulares, menores y D2/D3; volumen; rol Emactiva/cliente; base jurídica; avisos; jurisdicciones/mercados; responsables de privacidad/seguridad/proveedores; uso downstream de enrichment; procedimiento DSR e incidentes; matriz de retención y excepciones |
| Validación | Ejecución controlada de PRIV-T01–T10 aplicables; evidencia de despliegue; pruebas de eliminación/exportación; muestras canario sin secretos reales; registro/aceptación de riesgos y decisión DPIA |

## Priorización

### BLOQUEANTES EPB

- Gate PRIV-ARCH FAIL: no existe ruta integral para localizar y eliminar datos.
- EPB-P07/RET13 FAIL: ausencia total de política general y Matriz de Retención.
- EPB-P10 y pruebas PRIV-T06/T07 FAIL: eliminación/exportación por titular no soportadas en PostgreSQL ni coordinadas con terceros.
- EPB-XFER07 FAIL: países y mecanismo de transferencias no revisados.
- EPB-IMP05 FAIL: autorización de la frontera interna Adapter no está implementada/demostrada.
- H01/H04/H06/H09 de severidad ALTA requieren tratamiento o aceptación formal antes de producción; no son incidentes confirmados.
- Perfil jurisdiccional, rol, base jurídica y proveedores deben verificarse antes de cualquier cierre de producción; su estado actual es NOT_VERIFIED, no un incumplimiento jurídico declarado.

### REMEDIACIONES TÉCNICAS

- Controles futuros para event_id/source, valores de error/enrichment, mapping HubSpot y autenticación/autorización Adapter.
- Ruta auditable de localización, exportación, corrección, eliminación/restricción y coordinación con proveedores.
- Implementación de retención/cleanup para ledger, eventos, recovery estancado, volúmenes y superficies operativas.
- Ciclo seguro de credencial temporal y secretos recovery; transporte/cifrado según arquitectura efectiva.
- Manejo terminal seguro de fallos y compatibilidad de retries/tipos; tests PRIV aplicables.

### REMEDIACIONES DOCUMENTALES/OPERATIVAS

- Registro de Proveedores y auditoría oficial/contractual de HubSpot, Hunter y Slack.
- Matriz de Retención, perfil jurisdiccional, rol/base jurídica, finalidades/necesidad y avisos.
- Registro de transferencias y mecanismos aplicables.
- Procedimientos de derechos e incidentes, RACI, evidencias y ejercicios.
- Risk register, decisión DPIA, política de datos de prueba y evidencia de infraestructura/backups/logs/IAM.

Estas listas priorizan trabajo futuro; esta tarea no diseña ni implementa soluciones.

## Cambios de estado incorporados en Tarea 03A

La reevaluación se limitó a controles afectados por la evidencia oficial suministrada. No cambiaron los gates ni H01-H10. El total pasó de 14 PASS / 40 WARN / 19 FAIL / 6 N/A / 75 NOT_VERIFIED a **20 PASS / 74 WARN / 18 FAIL / 6 N/A / 36 NOT_VERIFIED**.

| Estado anterior | Estado nuevo | Controles | Evidencia justificante |
|---|---|---|---|
| NOT_VERIFIED | PASS | EPB-TP-HS04, EPB-TP-HS05 | Lista formal de subprocesadores HubSpot; DPA con medidas técnicas/organizativas y notificación de brechas |
| NOT_VERIFIED | PASS | EPB-TP-HU04, EPB-TP-HU09 | Lista oficial Hunter; DPA/términos y roles Processor/Controller independiente documentados |
| NOT_VERIFIED | PASS | EPB-TP-SL04, EPB-TP-SL05 | Lista oficial Slack; cifrado, acceso, incident management y backups documentados |
| NOT_VERIFIED | WARN | EPB-TP-HS03, EPB-TP-HS06, EPB-TP-HS07, EPB-TP-HS09, EPB-TP-HS10 | Regiones posibles, DPA, capacidades de derechos/eliminación y marco general acreditados; cuenta real pendiente |
| NOT_VERIFIED | WARN | EPB-TP-HU03, EPB-TP-HU06, EPB-TP-HU07, EPB-TP-HU08, EPB-TP-HU10 | Bélgica, retención/derechos de Profile Data, IA/ML y SCC acreditados; email/endpoint/cuenta/ruta real pendientes |
| NOT_VERIFIED | WARN | EPB-TP-SL03, EPB-TP-SL06, EPB-TP-SL07, EPB-TP-SL08, EPB-TP-SL09, EPB-TP-SL10 | Localización posible, retención configurable, eliminación/backups, IA, DPA y SCC acreditados; workspace real pendiente |
| NOT_VERIFIED | WARN | EPB-XFER02, EPB-XFER04, EPB-XFER05 | Regiones posibles, DPA/SCC y medidas generales ahora documentados; aplicación efectiva pendiente |
| FAIL | WARN | EPB-XFER07 | Existe revisión oficial general T03A; aún falta cerrar regiones, mecanismos y contratos de cuentas antes de producción |
| NOT_VERIFIED | WARN | EPB-RET09, EPB-RET10, EPB-RET11 | Controles generales de retención/eliminación de los proveedores documentados; configuración real pendiente |
| NOT_VERIFIED | WARN | EPB-DSR-HS02, EPB-DSR-HS04, EPB-DSR-HS05 | DPA HubSpot contempla retrieve/delete/restrict; LeadFlow no integra la operación |
| NOT_VERIFIED | WARN | EPB-DSR-HU01, EPB-DSR-HU02, EPB-DSR-HU03, EPB-DSR-HU04, EPB-DSR-HU05 | Hunter documenta acceso, rectificación, eliminación, restricción y portabilidad de Profile Data; operación LeadFlow pendiente |
| NOT_VERIFIED | WARN | EPB-DSR-SL04 | Slack documenta eliminación de producción y destrucción normal de backups dentro de 14 días; workspace/operación pendientes |
| NOT_VERIFIED | WARN | PRIV-T08, PRIV-T09 | Auditoría oficial general ya disponible; pruebas contractuales/operativas de cuentas todavía pendientes |

## Cambios de estado incorporados en Tarea 03B

La consolidación distingue EPB (privacidad) de EDPB (deployment y portabilidad). No se añadió una matriz EDPB completa. Los gaps `SYSTEM` de rotación, credencial temporal y cleanup pueden cerrarse durante desarrollo; los controles `ENVIRONMENT` de hosting, TLS público, cifrado at-rest, firewall e IAM efectivo quedan para un despliegue real; los controles `HYBRID` requieren ambos.

| Estado anterior | Estado nuevo | Control | Evidencia |
|---|---|---|---|
| PASS | WARN | EPB-TP-HS01 | HUBSPOT-V05 confirma enriquecimiento gratuito de nombres de empresas activo; el rol no puede modelarse como CRM puro |
| WARN | PASS | EPB-TP-HS03 | HUBSPOT-V01 confirma data hosting real en Estados Unidos (Este) |
| WARN | PASS | EPB-TP-HU06 | HUNTER-V05 aporta retención diferenciada para API logs, User Input, Profile Data y Data Enrichment |
| PASS | WARN | EPB-TP-SL01 | Configuración local confirma wiring, pero Slack LeadFlow no está configurado; se excluyó evidencia del workspace Agrovista |

Los cambios se compensan en el conteo total: **20 PASS, 74 WARN, 18 FAIL, 6 N/A y 36 NOT_VERIFIED**. Gate PRIV-00 permanece WARN y Gate PRIV-ARCH permanece FAIL: la evidencia account-level no crea una ruta integral de localización/eliminación. H01–H10 conservan clasificación y severidad; H06 CONFIRMADO/ALTA queda reforzado por INFRA-V14/V15. No se declara incidente ni hallazgo CRITICA.

## Reevaluación final de desarrollo R5/R6

Fecha: 2026-09-29. Esta sección sustituye para el cierre de desarrollo los estados preliminares de PRIV-T01–T10 y gates indicados arriba; los conteos históricos de Tarea 03A/03B no se presentan como conteo final recalculado.

| Ámbito | Resultado final | Límite |
|---|---|---|
| PRIV-T01–T07, PRIV-T10 | PASS SYSTEM | Las decisiones jurídicas y de cliente no forman parte del test técnico |
| PRIV-T08, PRIV-T09 | PASS SYSTEM documental / WARN global | Cuentas, contratos, regiones, permisos, transferencias y operación real permanecen REM-21 |
| EDPB-T01–T09 aplicables | PASS SYSTEM | Infraestructura efectiva permanece REM-24 |
| Gate PRIV-00 | WARN | Perfil real de cliente, titulares, jurisdicción, rol y base jurídica pendiente |
| Gate PRIV-ARCH | WARN | No quedan FAIL bloqueantes SYSTEM; verificación de terceros, backup/restore e infraestructura real pendiente |

REM-19 y REM-20 quedan PASS; REM-21 queda NOT_VERIFIED/ENVIRONMENT; REM-22 y REM-23 quedan PASS SYSTEM; REM-24 queda NOT_VERIFIED/ENVIRONMENT. La regresión final utilizó únicamente datos sintéticos y mocks locales, con pruebas reales de proveedores deshabilitadas, y terminó PASS con cleanup de bases temporales y Compose.
