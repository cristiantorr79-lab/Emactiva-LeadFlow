# LAB-LF-003 — Fase R1: definiciones previas

Fecha: 2026-09-27. Baseline técnico: `91aea95c05467b9d006832cb4816887c06b40644`.

Estado: **APROBADA FUNCIONALMENTE — LISTA PARA IMPLEMENTACIÓN R2**.

R1 define las reglas que R2 y R3 deberán implementar posteriormente. No cambia estados, conteos, gates ni conclusiones de la auditoría; no implementa TTL, operaciones DSR, SQL, workflows, Adapter, Compose, scripts, logging, autenticación, credenciales ni pruebas funcionales. EPB v1.0 y EDPB v1.0 son baselines complementarios y se aplica el principio “Cambia el entorno, no el sistema”.

## 1. Decisiones R1 aprobadas

| ID | Decisión aprobable | Justificación y límite |
|---|---|---|
| R1-D01 | El alcance V1 se dirige a leads, prospectos y contactos comerciales. | Es el titular previsto por el flujo observado; cualquier categoría adicional exige evaluación previa. |
| R1-D02 | Menores, D2 y tratamientos D3/alto impacto no están autorizados por defecto. | V1 no los necesita; si el contexto, volumen o perfilado eleva el riesgo se reabre la evaluación y la decisión DPIA. |
| R1-D03 | Los identificadores, hashes, metadatos y datos de perfil vinculables se tratan como datos D1, no como datos anónimos. | La seudonimización determinista mantiene capacidad de correlación. |
| R1-D04 | Cada superficie tendrá plazo técnico por defecto, trigger, método, owner y evidencia; los plazos de esta R1 son **PROPUESTOS**. | Requieren aprobación funcional y, cuando corresponda, jurídica/comercial antes de implementarse. |
| R1-D05 | La retención del ledger comienza al alcanzar estado terminal; el contexto recovery comienza al crearse y se elimina al finalizar. | Separa trazabilidad terminal de información necesaria solo para recuperación. |
| R1-D06 | Un hold por disputa, incidente u obligación suspende una eliminación concreta, nunca de forma indefinida ni global. | Debe registrar motivo, alcance, owner, aprobación, inicio y fecha/condición de revisión. |
| R1-D07 | La retención de terceros se gobierna por contrato, configuración de cuenta y operación DSR; LeadFlow no puede prometer borrado directo fuera de su control. | La evidencia debe registrar solicitud, respuesta y excepción por proveedor. |
| R1-D08 | El email es necesario para lookup, alta, enrichment y recovery del alcance funcional actual. | Su uso por Hunter y cualquier uso secundario requieren finalidad/base aplicable por cliente. |
| R1-D09 | Nombre, apellido, teléfono, empresa y enrichment son opcionales o condicionales y deberán poder excluirse por configuración aprobada. | Existir en el contrato técnico no demuestra necesidad para todos los clientes. |
| R1-D10 | `event_id` y `source` serán identificadores técnicos, estructurados y sin PII ni payload libre. | La estrategia preferida es validación estricta y normalización; no almacenar el valor inválido. |
| R1-D11 | Un `event_id` o `source` inválido se rechaza antes de idempotencia/persistencia con error canónico. | No se corrige silenciosamente ni se conserva el input crudo en logs o eventos. |
| R1-D12 | DSR comprende LOCATE, EXPORT, CORRECT, DELETE y RESTRICT en todas las superficies aplicables. | La operación puede combinar automatización controlada y pasos de proveedor/entorno. |
| R1-D13 | DSR usa una interfaz administrativa separada del webhook público, con identidad verificada, mínimo privilegio y doble control para operaciones destructivas. | La prueba de identidad y el rol contractual se definen por caso real. |
| R1-D14 | Los registros históricos que deban preservar integridad se corrigen mediante anotación/supersesión; los datos operativos mutables se corrigen en origen. | Evita reescribir evidencia sin impedir rectificación. |
| R1-D15 | El rol legal de Emactiva se determina por contrato/caso; su responsabilidad técnica como desarrollador/operador sí incluye controles seguros, trazabilidad y herramientas. | No se declara Controller/Processor universal. |
| R1-D16 | Retención, campos opcionales, proveedores y parámetros operacionales se externalizan dentro de límites seguros; la configuración no puede desactivar controles obligatorios. | Aplica EDPB: cambiar entorno/configuración no debe reescribir el núcleo. |

Cantidad de decisiones R1 aprobadas como definición funcional de LeadFlow: **16**.

## 2. Matriz de retención propuesta

Todos los plazos son **PROPUESTOS**, no obligaciones legales. “Hold” significa suspensión específica y revisable por disputa, incidente, solicitud DSR en curso u obligación determinada; no autoriza retención indefinida. Las reglas de terceros expresan control lógico de LeadFlow, no control físico sobre el proveedor.

| Superficie | Dato/categoría y finalidad | Inicio del plazo | Plazo técnico propuesto | Eliminación propuesta | Excepción | Responsable lógico | Capa | Evidencia disponible | Evidencia futura necesaria |
|---|---|---|---|---|---|---|---|---|---|
| PostgreSQL `executions`: success/duplicate | IDs técnicos, hashes, estado, CRM ID y tiempos para idempotencia, soporte y auditoría | Estado terminal | **90 días** | Purga auditable por lotes preservando integridad referencial | Hold específico y revisable | Emactiva operador; cliente aprueba necesidad | SYSTEM | Esquema y estados inventariados | Aprobación del plazo; prueba PRIV-T05 y métricas de purga |
| PostgreSQL `executions`: failed | IDs, etapa y errores canónicos para diagnóstico/recovery | Estado terminal | **180 días** | Purga auditable por lotes | Hold específico; investigación activa | Emactiva operador | SYSTEM | Esquema/error canónico inventariado | Aprobación; análisis de volumen y necesidad real |
| PostgreSQL `executions`: processing | Contexto operativo de ejecución activa | Creación/última actividad | **7 días máximo sin progreso**, seguido de resolución terminal; luego regla del estado final | Reconciliar a estado terminal antes de purgar | Job activo demostrado o hold | Emactiva operador | SYSTEM | Riesgo H09 confirmado | Política de timeout y pruebas de interrupción |
| PostgreSQL `execution_events` | Historial de etapa/resultado para auditoría técnica | Estado terminal de la ejecución padre | Igual al plazo de la ejecución padre | Cascada o purga coordinada | Mismo hold del padre | Emactiva operador | SYSTEM | FK/eventos inventariados | Prueba de cascada/integridad y conteos |
| PostgreSQL recovery/contexto cifrado | Email cifrado y lease para continuar una ejecución | Creación del contexto | Mientras `processing`, **máximo 7 días**; eliminación inmediata al terminal | Trigger/cleanup idempotente y barrido de huérfanos | Hold solo si recovery activo y autorizado | Emactiva operador | SYSTEM | Cleanup terminal parcial existente | Pruebas de éxito, error, interrupción y huérfanos |
| Tablas auxiliares futuras de retención/DSR | Jobs, holds y evidencia operacional minimizada | Cierre de operación | **180 días** para evidencia sin PII directa | Purga programada | Hold del caso asociado | Emactiva operador | SYSTEM | No implementadas | Diseño SQL, minimización y aprobación |
| n8n execution data | Payload/memoria de ejecución; diagnóstico | Fin de ejecución | **No guardar success/error/manual**; metadata técnica máxima **24 horas** si la plataforma la requiere | Pruning n8n | Ventana temporal de diagnóstico habilitada por incidente, con aprobación | Emactiva operador | HYBRID | Config declarada save-none/pruning 24; runtime no verificado | Config y muestra sanitizada del deployment |
| n8n metadata/config operacional | IDs, timestamps y estado técnico | Generación | **30 días** si existe fuera del ledger | Pruning/rotación | Hold específico | Emactiva operador | HYBRID | Superficie identificada, persistencia efectiva no comprobada | Inventario runtime y prueba de borrado |
| Logs de aplicación/Adapter/recovery | Estado, etapa, código canónico, correlación técnica | Emisión | **30 días** | Rotación y expiración por destino | Hasta **90 días** para incidente abierto, con hold | Emactiva operador | HYBRID | Logging explícito inventariado; sanitización parcial | Formato/allowlist, canarios y destino real |
| Logs Docker | stdout/stderr sanitizado para operación | Emisión | Límite por tamaño y archivos equivalente a **máximo 30 días** | Rotación `max-size/max-file` o equivalente | Exportación a repositorio de incidente con hold | Operador de infraestructura | HYBRID | Ausencia de límites confirmada | Config efectiva y prueba de rotación |
| Logs PostgreSQL | Conexiones/errores SQL sin parámetros sensibles | Emisión | **14 días** | Rotación/expiración del motor o colector | Hasta **90 días** por incidente | Operador de infraestructura/DBA | ENVIRONMENT | Config runtime no disponible | Parámetros efectivos y muestra sanitizada |
| Logs host/reverse proxy | Acceso, errores, IP/headers mínimos para seguridad | Emisión | **30 días** | Rotación/colector | Hasta **90 días** por incidente | Operador de infraestructura | ENVIRONMENT | No existe despliegue | Diseño de campos, base aplicable y configuración real |
| HubSpot | Email, identidad, contacto y enrichment para CRM | Alta/actualización del contacto | Según finalidad del cliente y política de cuenta; **sin plazo universal R1** | Operación DSR/retención de HubSpot y baja contractual | Hold/obligación definida por cliente | Cliente como owner funcional; Emactiva coordina técnicamente | HYBRID | Datos, región y capacidades generales/account-specific parciales | Plazo aprobado, DPA y configuración de cuenta |
| Hunter Customer Personal Data | Email enviado para enrichment y logs del servicio | Solicitud al endpoint | El mínimo contractual/configurable; **pendiente evidencia del email enviado** | Solicitud/expiración según contrato | Excepción documentada del proveedor | Cliente/Emactiva según rol real; Hunter ejecuta | HYBRID | Retenciones por categorías y plan Free documentados | Términos/endpoint/cuenta y mecanismo DSR |
| Hunter Profile Data | Industry, tamaño y website obtenidos para CRM | Recepción/uso del resultado | En LeadFlow no se persiste fuera de CRM; en Hunter rige su política/rol independiente | Borrado/corrección en CRM y coordinación con Hunter cuando aplique | Fuente pública/obligación del proveedor documentada | Cliente define uso; Hunter como Controller independiente para Profile Data | HYBRID | Rol dual y política general documentados | Finalidad/base del cliente y procedimiento operativo |
| Slack cuando se configure | `execution_id`, etapa y código de error para alerta | Publicación | **30 días o el mínimo configurable del plan**, sujeto a aprobación | Retención/eliminación del workspace/canal | Incidente activo con hold | Owner del workspace/cliente; Emactiva limita payload | HYBRID | Slack LeadFlow no configurado | V01–V08, plan, canal, permisos, DPA y retención |
| Backups PostgreSQL/n8n/config permitida | Copia cifrada del estado persistente para recuperación | Creación de copia | **30 días rolling**; no incluir secretos exportables si existe alternativa | Expiración automática y destrucción verificable | Copia preservada por incidente/obligación con hold | Operador de infraestructura; Emactiva define contrato | ENVIRONMENT | No existe infraestructura/política | Alcance, frecuencia, RPO/RTO, restore y prueba de expiración |
| Backups de logs/terceros | Copias controladas por entorno/proveedor | Creación | Igual o menor al plazo de la fuente; contrato específico | Expiración y solicitud al proveedor | Hold documentado | Operador/proveedor correspondiente | ENVIRONMENT | Capacidades generales parciales | Evidencia de cuenta/entorno y reaparición tras restore |

Reglas transversales:

- El plazo se calcula con tiempo UTC y queda versionado.
- Una reducción de plazo puede aplicarse sin ampliar datos; una ampliación exige aprobación, justificación y evaluación de impacto.
- El borrado se registra con identificadores de operación y conteos, sin copiar el dato eliminado.
- Un restore debe reaplicar tombstones/solicitudes DSR y evitar reintroducir datos vencidos.
- Los datos de terceros se consideran pendientes hasta recibir confirmación o agotar el procedimiento documentado; no se declaran eliminados por LeadFlow sin evidencia.

## 3. Titulares y categorías de datos

### Titulares previstos

- Lead, prospecto o contacto comercial vinculado a una organización o actividad profesional.
- Persona que solicita ejercer un derecho sobre información procesada por el flujo.
- Operador/worker únicamente respecto de identificadores operacionales como `recovery_owner`.

No están aprobados por defecto: menores; personas vulnerables; empleados para vigilancia; consumidores fuera de una finalidad comercial aprobada; datos de salud, biométricos, creencias, afiliación política/sindical, vida sexual, origen racial/étnico u otras categorías D2; perfiles D3 o decisiones de alto impacto. Su aparición exige detener el uso previsto, evaluar el caso y autorizarlo expresamente antes de procesar.

### Inventario y restricciones

| Dato | Finalidad técnica | Necesidad | Req. | Destino | Persistencia | Clase | Restricciones |
|---|---|---|---|---|---|---|---|
| `email` | Lookup/alta CRM, enrichment e identificación recovery/DSR | Necesario para el flujo actual | Obligatorio | PostgreSQL cifrado temporal, HubSpot, Hunter | Recovery cifrado temporal; CRM/proveedor | D1 directo | Normalizar; no logs/argv; Hunter requiere finalidad aprobada |
| `first_name` | Completar contacto CRM | Útil si la finalidad requiere personalización | Opcional | HubSpot | CRM | D1 directo | Excluible por configuración; no enrichment/logs |
| `last_name` | Completar contacto CRM | Útil si la finalidad requiere identificación | Opcional | HubSpot | CRM | D1 directo | Excluible; evitar si no es necesario |
| `phone` | Contactabilidad autorizada | Depende del canal/finalidad del cliente | Opcional | HubSpot | CRM | D1 directo | Deshabilitado si no existe necesidad aprobada; formato validado |
| `company` | Contexto comercial y entrada canónica opcional | Condicional al caso B2B | Opcional | HubSpot; memoria Adapter | CRM | D1 potencial | No asumir que siempre es dato empresarial no personal |
| `industry` | Enrichment profesional/segmentación | Condicional a finalidad aprobada | Opcional | HubSpot | CRM | D1 perfil | Allowlist/tipo; excluible; sin decisiones de alto impacto |
| `company_size` | Enrichment/segmentación de empresa | Condicional | Opcional | HubSpot | CRM | D1 perfil potencial | Excluible; documentar uso downstream |
| `website` | Referencia pública de empresa | Condicional | Opcional | HubSpot | CRM | D1 potencial/URL | Validar esquema; quitar query/credenciales; excluible |
| `execution_id` y referencias | Correlación, respuesta y auditoría | Necesario | Técnico | PostgreSQL, respuesta; Slack condicionado | Ledger/logs | D1 correlacionable | No usar como identidad del titular; no exponer más de lo necesario |
| `event_id` | Idempotencia y trazabilidad de evento | Necesario si lo aporta integración | Técnico obligatorio | PostgreSQL | Ledger | D1 potencial hoy | Futuro contrato técnico sin PII; rechazo temprano |
| `source` | Identificar integración/origen | Necesario | Técnico obligatorio | PostgreSQL | Ledger | D1 potencial hoy | Slug/allowlist sin PII; rechazo temprano |
| `lead_identifier` | Correlación por email | Necesario para ledger/recovery | Derivado | PostgreSQL/logs permitidos | Ledger | D1 seudonimizado | SHA-256 determinista no es anonimización; acceso/retención |
| `idempotency_key` | Evitar duplicados | Necesario | Derivado | PostgreSQL/recovery | Ledger | D1 seudonimizado | No sustituye borrado de inputs; algoritmo versionado |
| ID CRM/contact ID | Actualizar y reconciliar contacto | Necesario tras alta/lookup | Derivado | PostgreSQL/HubSpot | Ledger/CRM | D1 indirecto | Validar forma; no exponer al cliente/logs innecesarios |
| Estado, etapa, retries y tiempos | Operación, recovery y auditoría | Necesario | Técnico | PostgreSQL/logs | Ledger/eventos/logs | D1 correlacionable | Enums/contadores; plazo y acceso limitados |
| `error_type/code/message` | Diagnóstico y alerta | Necesario en forma canónica | Técnico | PostgreSQL/logs/Slack condicionado | Ledger/eventos/logs | D1 correlacionable | Allowlist; sin payload, PII, URL, header, token ni traza cruda |

## 4. Matriz de finalidad y necesidad campo a campo

| Campo | Clasificación R1 | Finalidad aprobable | Condición/configuración futura |
|---|---|---|---|
| `email` | NECESARIO | Identificar contacto, sincronizar CRM, enrichment previsto y recovery | Obligatorio para el flujo V1; Hunter deshabilitable si no hay finalidad/base para enrichment |
| `first_name` | OPCIONAL_JUSTIFICADO | Completar contacto para una interacción comercial identificada | Campo deshabilitable; solo enviar si presente y habilitado |
| `last_name` | OPCIONAL_JUSTIFICADO | Distinguir/completar contacto cuando el caso lo exige | Campo deshabilitable; solo enviar si presente y habilitado |
| `phone` | REQUIERE_JUSTIFICACION_CLIENTE | Contactabilidad por canal telefónico | Deshabilitado por defecto hasta que cliente declare finalidad/canal |
| `company` | CONDICIONAL | Asociar el contacto a contexto B2B | Habilitable para casos B2B; no requerido en todos los flujos |
| `industry` | REQUIERE_JUSTIFICACION_CLIENTE | Segmentación/enrichment profesional | Enrichment y mapping deshabilitables; uso downstream documentado |
| `company_size` | REQUIERE_JUSTIFICACION_CLIENTE | Segmentación por tamaño organizacional | Igual que industry; no usar para alto impacto por defecto |
| `website` | CONDICIONAL | Referencia de entidad y enrichment | Habilitable con sanitización de URL y necesidad documentada |
| `event_id` | NECESARIO | Idempotencia y trazabilidad del evento | Obligatorio como ID técnico conforme al contrato futuro |
| `source` | NECESARIO | Seleccionar/atribuir integración de origen | Obligatorio desde allowlist/configuración del entorno |

La configuración futura debe permitir excluir `first_name`, `last_name`, `phone`, `company`, `industry`, `company_size`, `website` y el envío a Hunter. No puede deshabilitar autenticación, validación, idempotencia, sanitización, auditoría mínima ni reglas de retención.

## 5. Contrato futuro de event_id y source

### `event_id`

- Semántica: identificador opaco de un evento en el sistema fuente, estable para retries y único dentro de `source`.
- Forma propuesta: 1–128 caracteres ASCII; primer carácter alfanumérico; restantes `A-Z a-z 0-9 . _ : -`.
- Contenido prohibido: email, teléfono, nombre, texto libre, JSON, URL, query string, payload o dato de negocio.
- Productor: la integración debe generar UUID, ULID o token técnico equivalente.
- Inválido: responder error canónico de validación antes de calcular/persistir claves; no registrar el valor crudo.
- Persistencia: usar el valor recibido transitoriamente y derivar la identificación técnica necesaria para idempotencia. El diseño futuro no debe depender de almacenar permanentemente el `event_id` crudo cuando pueda evitarse.

### `source`

- Semántica: identificador estable de la integración/origen, no de una persona.
- Forma propuesta: slug en minúsculas `^[a-z][a-z0-9_-]{0,63}$`.
- Debe pertenecer a una allowlist configurable por entorno; no se acepta fallback libre.
- Contenido prohibido: dominio con usuario, email, nombre de persona, teléfono, tenant secreto o payload.
- Inválido/desconocido: rechazo canónico antes de persistencia, sin eco del valor.

### Estrategia preferida e impacto

Se prefiere **validación estricta + normalización controlada de `source`**, manteniendo `event_id` opaco durante el procesamiento y minimizando su persistencia. La pseudonimización del input inválido no es una alternativa al rechazo: conservaría la ingestión de PII indebida. LeadFlow aún no está en producción, por lo que REM-09 puede ajustar contrato, fixtures y pruebas sin mantener compatibilidad con una versión productiva anterior.

`idempotency_key = SHA-256(source + ":" + event_id)` puede conservarse si ambos valores ya son canónicos. El cambio exige pruebas de duplicados, retries, colisiones, recovery y auditoría. `source` sí puede persistirse en forma canónica porque proviene de una lista controlada. Nunca se registran valores rechazados.

## 6. Especificación funcional DSR

### Reglas comunes

- Entrada primaria propuesta: email normalizado aportado por una solicitud verificada; opcionalmente ID CRM u otro dato de apoyo, nunca como única prueba de identidad.
- Autenticación/autorización: canal administrativo separado, operador identificado, rol mínimo y aprobación adicional para DELETE/RESTRICT masivo. El método de verificación del titular depende del cliente, jurisdicción y rol contractual.
- Auditoría: ID de caso, actor/rol, timestamps, superficies consultadas, resultado/código y excepciones; sin duplicar los datos exportados o eliminados.
- Idempotencia: una misma operación/caso puede repetirse sin duplicar exportaciones, anotaciones o borrados; cada superficie informa `completed`, `not_found`, `pending_provider`, `held` o `failed`.
- Errores: no revelar existencia a un actor no autorizado; conservar error canónico; reintentar solo fallos transitorios; escalar resultados parciales.
- Holds: se aplican a registros/superficies concretos, con motivo, aprobador, revisión y alcance visible en el resultado.

| Acción | Entrada y autorización | Superficies/resultado | Auditoría y errores | Terceros/backups | Automatización e intervención |
|---|---|---|---|---|---|
| LOCATE | Identificador verificado; operador DSR con permiso de lectura | PostgreSQL por `lead_identifier`/CRM ID; HubSpot; Hunter según mecanismo; Slack si existe; índices de logs y catálogo de backups. Devuelve mapa de presencia, no payload completo | Registrar superficies y estados; ambigüedad requiere revisión, sin revelar coincidencias al solicitante aún no verificado | Consultas/API o ticket documentado; backups se localizan por catálogo/tombstone, no por búsqueda indiscriminada del contenido | Automatizar PostgreSQL/HubSpot cuando exista API segura; operador resuelve identidad, Hunter/Slack y backups |
| EXPORT | LOCATE completado y autorización de divulgación | Paquete estructurado de datos del titular, fuentes, finalidades y metadatos pertinentes; excluye secretos, datos de terceros y diagnósticos internos no atribuibles | Manifest, hash del paquete, canal seguro y expiración; fallo parcial se declara | Obtener export del proveedor cuando aplique; backups no se restauran solo para export salvo obligación/decisión aprobada | Generación automatizable; revisión y entrega siempre controladas |
| CORRECT | Dato actual correcto + prueba/autoridad; permiso de escritura | HubSpot y datos operativos mutables; ledger histórico se anota/supersede, no se reescribe silenciosamente; Hunter se coordina según su rol | Antes/después minimizado, fuente de corrección y resultado; conflicto escala | Solicitud a proveedor y registro de respuesta; backups aplican corrección al restaurar mediante registro/tombstone | Cambios CRM automatizables; resolución de conflicto y Profile Data requieren operador |
| DELETE | LOCATE, identidad fuerte, base de procedencia y doble control | Contexto recovery, ledger/eventos según retención/hold, CRM, tercero, Slack/logs cuando identificables; devuelve estado por superficie | Evidencia de operación sin conservar el dato; `held` indica alcance/motivo; fallos parciales reintentables | Solicitudes a HubSpot/Hunter/Slack; tombstone para impedir reaparición desde backup; expiración de copias según contrato | LeadFlow controlable puede automatizarse; proveedores, logs no indexables y backups requieren operación |
| RESTRICT | Identidad verificada, alcance/motivo y aprobador | Marca que bloquea enrichment, envíos, actualización/uso y purga incompatible mientras se resuelve; conserva mínimo para aplicar restricción | Registrar inicio, alcance, revisión y levantamiento; no usar el dato restringido para nuevos fines | Propagar bloqueo/solicitud a CRM/proveedores cuando sea posible; restore reaplica restricción | Enforcement del sistema automatizable; decisión, revisión y terceros requieren operador |

No se presume que DELETE prevalezca sobre toda conservación. El resultado debe separar datos borrados, no encontrados, pendientes, sujetos a hold y controlados por terceros.

### Tombstone e idempotencia después de DELETE

Eliminar los datos de una persona no debe permitir que un evento antiguo vuelva a procesarse como nuevo. El diseño futuro puede conservar un **tombstone**, un registro técnico mínimo de eliminación que:

- no contiene email, nombre, teléfono, `lead_identifier` ni payload;
- no permite reconstruir los datos eliminados;
- conserva solo la señal técnica mínima para impedir repetición o reaparición;
- tiene plazo de conservación definido, acceso limitado y eliminación auditable.

La forma técnica, plazo y vínculo con idempotencia se diseñarán en R3 sin reintroducir datos personales.

## 7. Modelo preliminar de responsabilidades

| Actor | Responsabilidad técnica/operativa propuesta | Depende del contrato/caso | Debe resolverse antes de producción |
|---|---|---|---|
| Emactiva desarrollador | Diseñar minimización, validación, seguridad, retención configurable, DSR, pruebas, documentación y límites de adaptadores | Rol legal frente al titular | Capacidades SYSTEM cerradas, riesgos y documentación aprobados |
| Emactiva operador, si aplica | Operar runtime, accesos, purgas, casos DSR, incidentes, evidencias y coordinación | Si aloja/opera para el cliente; instrucciones y facultades | RACI, SLA, identidades, canales de soporte/DSR y procedimiento |
| Cliente LeadFlow | Definir finalidad comercial, necesidad de campos, categorías de titulares, base aplicable, avisos, canal de derechos y uso downstream | Controller/Processor y jurisdicción real | Checklist R1-D04, aprobación de campos/retención/proveedores y decisión DPIA |
| HubSpot | Ejecutar CRM, seguridad/retención/capacidades contractuales y solicitudes según cuenta | Rol puede cambiar por enrichment/funciones habilitadas | DPA aplicable, región, funciones, scopes, mappings, usuarios y DSR |
| Hunter | Procesar Customer Personal Data y actuar según su rol independiente sobre Profile Data | Finalidad/base de uso del Profile Data y términos de cuenta | Reconciliar plan/endpoint, retención email, DPA, transferencias y DSR |
| Slack | Procesar alertas si se activa; aplicar configuración de workspace, retención y eliminación | Workspace, plan, owner, canal y rol real | Permanece no configurado; ejecutar V01–V08 antes de activarlo |
| Operador de infraestructura | TLS, firewall, IAM/MFA, cifrado at-rest, volúmenes, backups/restore, logs, parches y evidencia runtime | Proveedor/topología y reparto con Emactiva/cliente | Contrato de despliegue, owners, RPO/RTO, acceso y checklist INFRA |

Emactiva no se declara universalmente Controller ni Processor. HubSpot, Hunter y Slack conservan los roles diferenciados ya documentados en Tarea 03A; la cuenta y el caso real determinan su aplicación.

## 8. Configuración futura

Los nombres son contratos conceptuales propuestos, no variables implementadas.

| Grupo | Decisiones configurables | Límites obligatorios |
|---|---|---|
| Retención | Días por estado de execution, eventos, logs y metadata; schedule/batch de purge | Rango aprobado; no `0` ambiguo ni infinito; reducción segura; ampliación exige aprobación |
| Campos | Habilitar nombre, apellido, teléfono, empresa, industry, company_size y website | Email/event/source permanecen según contrato V1; campos deshabilitados no se envían ni persisten |
| Enrichment | Hunter habilitado/deshabilitado; propiedades de salida habilitadas; mappings | Disabled por cliente sin finalidad/base; allowlist fija; sin payload completo |
| Proveedores/endpoints | URLs/base endpoints, timeouts, retries y adaptador seleccionado | HTTPS externo; validación al inicio; sin fallback peligroso ni dominio hardcodeado |
| Slack | Habilitado, canal lógico, payload permitido y timeout | Default deshabilitado; activación exige checklist V01–V08; nunca PII/secreto |
| DSR | Feature availability, límites de lote, modo dry-run, doble aprobación, retry | No deshabilitar auditoría/autorización; DELETE/RESTRICT nunca expuestos al webhook público |
| Logging | Nivel, formato, destino, correlación, rotación y retención | Allowlist/redacción obligatoria; debug no habilita payloads, headers, URLs secretas o tokens |
| Recovery | Lease, timeout, máximo de intentos y reconciliación | Límites seguros; sin secretos/PII en argv; estado terminal garantizado |
| Persistencia | Volúmenes/stores y parámetros de conexión | Sin rutas personales/absolutas funcionales; migraciones compatibles |
| Backups/restore | Alcance, frecuencia, retención, RPO/RTO y destino | Cifrado, custodia, prueba de restore y reaplicación de tombstones/holds |
| Entornos | Perfiles dev/test/prod y fuentes de secretos | Separación explícita; defaults seguros; producción falla si falta configuración obligatoria |

La configuración debe tener esquema, validación de arranque, fuente, rango, default seguro y documentación. Seguridad, sanitización, mínimo privilegio, auditoría y prohibición de D2/menores no son opciones desactivables.

## 9. Resolución de decisiones O01–O12

| ID | Estado | Resolución aprobada | Pendiente posterior |
|---|---|---|---|
| R1-O01 | APROBADA | Success/duplicate: 90 días. Failed: 180 días. Son plazos técnicos iniciales configurables, no obligaciones legales universales. | Ajuste por cliente solo dentro del proceso aprobado. |
| R1-O02 | APROBADA | Processing/recovery sin progreso: máximo 7 días; después debe reconciliarse o controlarse hasta un estado terminal. | Barrido general corresponde a REM-12/R3. |
| R1-O03 | APROBADA | Hold es una pausa temporal al borrado, específica, documentada y revisable; nunca global ni indefinida. | Asignar owner/aprobador operacional antes de producción. |
| R1-O04 | POLÍTICA APROBADA / CONFIGURACIÓN POR CLIENTE | Campos opcionales y enrichment se habilitan según necesidad real; phone requiere justificación. | Configuración concreta en onboarding/preproducción. |
| R1-O05 | APROBADA | LeadFlow no está en producción; REM-09 puede ajustar `event_id/source`, fixtures y pruebas sin compatibilidad productiva anterior. | Ninguno para iniciar REM-09. |
| R1-O06 | POLÍTICA APROBADA / MÉTODO DEPENDE DEL CLIENTE | La DSR llega previamente verificada y nunca se expone en el webhook público. | Método de identidad según cliente/jurisdicción antes de producción. |
| R1-O07 | APROBADA | `DSR_OPERATOR` prepara/ejecuta; `DSR_APPROVER` autoriza. DELETE y RESTRICT destructivos requieren aprobación separada. | Asignar identidades efectivas antes de operar. |
| R1-O08 | APROBADA | Datos mutables se corrigen en CRM/origen. El historial técnico no se reescribe silenciosamente; se anota o reemplaza de forma auditable. | Diseño técnico en REM-13. |
| R1-O09 | DEPENDENCIA EXTERNA PREPRODUCCIÓN | El sistema futuro debe representar una operación pendiente del proveedor. | Confirmar DSR/retención del email enviado a Hunter; no bloquea R2. |
| R1-O10 | APROBADA | El enriquecimiento gratuito automático de HubSpot queda deshabilitado por defecto; activación explícita y documentada. | Verificar configuración account-specific antes de producción. |
| R1-O11 | APROBADA | Slack permanece deshabilitado/no configurado; si se activa, ejecutar primero V01–V08. | Workspace/configuración futura; no bloquea R2. |
| R1-O12 | APROBADA COMO BASE TÉCNICA | Backup diario en despliegue persistente, 30 días, RPO ≤24 h y RTO ≤8 h; ajustable por cliente/infraestructura sin reescribir LeadFlow. | Evidencia de infraestructura real post-deployment. |

Las 12 decisiones tienen resolución funcional. Seis materias de cliente/entorno permanecen pendientes y **no bloquean R2**:

1. configuración concreta de campos de un futuro cliente;
2. mecanismo específico de verificación de identidad según cliente/jurisdicción;
3. evidencia operativa pendiente de Hunter;
4. configuración futura de Slack;
5. infraestructura real de backups;
6. jurisdicción, base jurídica y rol contractual de un cliente aún inexistente.

Estas materias deben cerrarse antes de producción cuando corresponda.

## 10. Dependencias para R2 y R3

| Trabajo futuro | Gate R1 |
|---|---|
| REM-05/07 secretos y recovery | Puede iniciar tras aprobar R1; debe respetar logging/retención y no crear nueva persistencia |
| REM-08 autorización Adapter | R1-D13 y R1-O07 aprobadas |
| REM-09 `event_id/source` | Habilitada: contrato de sección 5 y R1-O05 aprobados |
| REM-10 terminación recovery | Habilitada: R1-O02 aprobada |
| REM-12 purga/TTL | R1-O01/O02/O03 aprobadas; implementar en R3, no en R2 |
| REM-13 capacidades DSR | R1-O03/O06/O07/O08 aprobadas; implementar en R3 |
| REM-14 coordinación terceros | Política aprobada; R1-O09 permanece dependencia externa preproducción |
| REM-15 backups/restore | Base técnica R1-O12 aprobada; evidencia real posterior |
| PRIV-T05 | REM-12 implementada |
| PRIV-T06/T07 | REM-13/14 implementadas |

R2 no debe codificar plazos, roles o decisiones abiertas. R3 no debe implementar TTL/DELETE/EXPORT antes de aprobación funcional de esta R1.

## 11. Criterios de aceptación R1

R1 queda **aprobada funcionalmente y cerrada** porque:

- la Matriz de Retención propuesta cubre PostgreSQL, n8n, logs, terceros y backups;
- cada superficie distingue plazo técnico, trigger, eliminación, hold, owner, capa y evidencia;
- titulares, categorías no autorizadas y clasificación D1/D2/D3 están explícitos;
- existe matriz de necesidad campo a campo y lista de campos configurables;
- `event_id/source` tienen contrato futuro, estrategia e impacto de compatibilidad;
- LOCATE, EXPORT, CORRECT, DELETE y RESTRICT están definidos para todas las superficies;
- responsabilidades de Emactiva, cliente, proveedores e infraestructura están separadas;
- SYSTEM, HYBRID y ENVIRONMENT no se confunden;
- ninguna base jurídica, jurisdicción o rol de cliente inexistente se da por resuelto;
- las 12 decisiones O01–O12 tienen resolución funcional y los pendientes de cliente/entorno están separados;
- no se implementó código ni se ejecutaron remediaciones.

Resultado: **R1 APROBADA FUNCIONALMENTE — LISTA PARA IMPLEMENTACIÓN R2**. Próximo paso: **FASE R2 — SEGURIDAD SYSTEM; bloque R2-A — REM-05 + REM-07 + REM-10**.
