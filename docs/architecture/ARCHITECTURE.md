# Arquitectura V1

## Componentes y límites

n8n orquestará el webhook y el núcleo reutilizable: validar, normalizar, reclamar evento, gestionar estados, clasificar errores, aplicar retries, registrar y responder. PostgreSQL será autoridad para idempotencia y trazabilidad. Los adaptadores CRM, enriquecimiento y alerta Slack traducirán los contratos externos sin introducir reglas del proveedor en el núcleo. Configuración exclusivamente por entorno, según `.env.example`.

LF-002.1 materializa esa frontera mediante el servicio interno `adapters`: el Core consume contratos estables `/crm/process`, `/enrichment/enrich`, actualización de enrichment y `/alert`; solo el adaptador conoce los endpoints y formatos HTTP de los mocks. Retries, delays y timeout del proveedor se configuran por entorno y se validan al iniciar. Las API keys se reciben en la frontera pero no se envían hasta definir el esquema de autenticación del proveedor real.

LF-002.2 convierte esta frontera en un contrato ejecutable. Cada CRM Adapter declara capacidades de unicidad, lookup posterior a CREATE, idempotencia por operation key y reconciliación de conflictos. El Core no conoce formatos de proveedor. Un CREATE ambiguo solo se repite cuando el perfil demuestra una garantía segura; en otro caso termina como `ambiguous_create`. La suite de conformidad valida también updates parciales, whitelist de enrichment, clasificación de errores, Retry-After y sanitización antes de admitir un adaptador futuro.

LF-002.4 separa development y production mediante `APP_ENV` y un override Compose. Development conserva puertos loopback y mocks. Production exige upstreams HTTPS explícitos, rechaza destinos locales/mock, no publica puertos de PostgreSQL, Adapter, n8n ni auxiliares y deja los mocks fuera salvo activación deliberada del perfil development. La exposición pública requiere una frontera TLS externa conectada a la red interna; el webhook autenticado no convierte HTTP directo en un canal público seguro.

LF-002.5 selecciona HubSpot como CRM y Hunter Combined Enrichment como proveedor real, siempre detrás del servicio Adapter. `CRM_PROVIDER` y `ENRICHMENT_PROVIDER` eligen mock o real; el Core y recovery conservan únicamente contratos canónicos. HubSpot usa Service Key como Bearer y un perfil deliberadamente conservador: no se presume unicidad, consistencia posterior a CREATE ni idempotencia por operation key. Hunter usa `X-API-KEY`; su respuesta se reduce a industry, company_size y website antes de salir del Adapter. Las respuestas crudas y credenciales no se registran ni persisten.

LF-001.C ejecuta n8n 2.28.6 en Docker, persistente y publicado solo en loopback. El workflow `leadflow_core_initial.json` autentica `X-LeadFlow-Key`, valida sin propagar PII, calcula hashes y usa exclusivamente `claim_event` y `record_validation_failure` con el rol de aplicación. Un nuevo evento queda honestamente en processing; aún no hay success comercial.

LF-001 ya incorpora `workflows/` y `scripts/test/` con contenido ejecutable. `mocks/`, `database/seeds/` y `docs/handoff/` siguen diferidos hasta que tengan contenido real; el handoff canónico permanece en `labs/`.

## Flujo normal

1. Asignar `execution_id` único y registrar recepción con mínimos metadatos.
2. Validar entrada y normalizar email (trim, lowercase y formato). Rechazar antes de cualquier llamada externa si es inválida.
3. Validar `source` contra `LEADFLOW_ALLOWED_SOURCES`, normalizarlo a minúsculas, validar `event_id` como token técnico y calcular SHA-256 UTF-8 de `source + ":" + event_id`; reclamar el evento atómicamente sin persistir el `event_id` crudo.
4. Pasar a processing; consultar CRM por email normalizado. Crear si no existe o actualizar los campos presentes si existe.
5. Enriquecer mediante el adaptador; actualizar únicamente los campos de enriquecimiento permitidos en CRM.
6. Persistir success y finished_at antes de responder. Si el enriquecimiento falla definitivamente, el resultado global es failed aunque el contacto ya exista; no se intenta revertirlo.

## Idempotencia y concurrencia

La tabla `leadflow.executions` conserva una fila propietaria por evento válido, con `idempotency_key UNIQUE`. El reclamo usa una función transaccional corta: crea la recepción con clave NULL e intenta asignar la clave mediante UPDATE; la restricción UNIQUE decide el único propietario y una excepción controlada resuelve al ganador. Solo quien obtiene la clave puede procesar. Nunca usar SELECT seguido de INSERT/UPDATE sin protección de UNIQUE ni mantener una transacción abierta durante llamadas HTTP.

La retención opera en PostgreSQL mediante lotes acotados. Antes de borrar, terminaliza ejecuciones processing vencidas; excluye holds activos y propietarios aún referenciados por duplicados retenidos; elimina eventos/contextos dependientes y después la ejecución. Cada corrida conserva solo conteos técnicos durante 180 días. Los plazos se suministran por entorno dentro de límites validados, sin cambiar la lógica de negocio.

Las operaciones DSR usan una frontera administrativa independiente. El runtime deriva un token HMAC de sujeto y PostgreSQL consulta tombstones antes de aceptar un evento. La evidencia DSR y la coordinación de terceros contienen únicamente identificadores técnicos, estados y códigos canónicos. Un restore debe reaplicar tombstones y restricciones antes de admitir tráfico; la custodia, cifrado y ejecución del backup pertenecen al entorno.

La operación oficial `leadflow.claim_event` inserta el registro received con clave NULL y su evento de auditoría. En la misma transacción intenta asignar la clave mediante UPDATE sobre esa misma fila. Si UNIQUE detecta un propietario concurrente, la excepción controlada marca la recepción actual como duplicate, mantiene su clave NULL y establece `duplicate_of` al propietario encontrado por esa clave. No se elimina ni reemplaza ninguna ejecución y ambos historiales se conservan. En logs, la clave de la recepción duplicada se obtiene mediante JOIN con su propietario. Los inválidos mantienen clave NULL, pues puede faltar source/event_id; PostgreSQL permite varios NULL bajo UNIQUE.

El rol de aplicación no tiene escritura directa en estas tablas: ejecuta funciones transaccionales concedidas expresamente. Así, la operación oficial garantiza que `duplicate_of` apunta a una fila con la clave reclamada. La FK garantiza existencia y las pruebas negativas/concurrentes verifican la regla que no puede expresarse limpiamente mediante un CHECK entre filas.

Un duplicado nunca modifica el estado del propietario ni dispara efectos externos. Su respuesta identifica su propia recepción y la ejecución original. Una entrega repetida de un evento failed tampoco lo reejecuta: la recuperación futura será una operación explícita sobre la ejecución original, no un bypass de UNIQUE. La misma clave con contenido distinto sigue siendo duplicada; el emisor debe asignar un nuevo event_id a cada cambio.

`source` es un slug canónico en minúsculas tomado de una allowlist de entorno y no contiene `:`. `event_id` puede contener `:` dentro de su formato técnico, se usa transitoriamente y mantiene sensibilidad a mayúsculas. No se recortan ni corrigen silenciosamente valores inválidos.

Si un proceso muere en processing, la fila permanece reclamada. LAB-LF-001 deberá definir recuperación controlada de ejecuciones interrumpidas y reconciliar CRM antes de reanudarlas. No expirar ni borrar automáticamente claves para reejecutar. Un fallo de PostgreSQL bloquea efectos externos y devuelve error de infraestructura; si no puede escribirse el log, no se afirma que quedó persistido.

## CREATE con resultado ambiguo

Un timeout o corte después de enviar CREATE puede ocultar una creación exitosa. Antes de repetir CREATE, consultar de nuevo por email normalizado. Si existe, continuar con ese contacto. Si no existe y el CRM garantiza lectura consistente y unicidad atómica de email, puede repetirse CREATE dentro del presupuesto. Si no garantiza estas propiedades, solo es seguro repetir con una clave de operación idempotente soportada por el proveedor; de otro modo fallar como `ambiguous_create` sin otra creación ciega.

El contrato del mock exige unicidad de email, lookup consistente y clave idempotente en CREATE. Esto también protege dos eventos diferentes concurrentes para el mismo email. Ante HTTP 409 de CREATE, reconciliar con lookup y reutilizar el contacto solo si coincide; un 409 de otro origen se clasifica como conflicto determinista. No hay retry genérico de 409 ni bucles ilimitados de reconciliación.

## Errores y retries

No reintentar datos inválidos, HTTP 400/401/403, HTTP 404 técnico ni errores funcionales deterministas. La ausencia legítima en lookup es `not_found` del contrato, no un 404 técnico. Reintentar HTTP 408/429/500/502/503/504, timeout y errores temporales de red. Otros errores no clasificados fallan de forma conservadora. CREATE ambiguo aplica primero la reconciliación anterior.

El máximo inicial es **3 intentos totales por operación**, no tres retries: intento 1 → esperar 5 s; intento 2 → esperar 15 s; intento 3 → fallo definitivo. Las variables RETRY_MAX_ATTEMPTS, RETRY_DELAY_FIRST_SECONDS y RETRY_DELAY_SECOND_SECONDS centralizan esta política. V1 admite máximo de 1 a 3; para más intentos se deberá ampliar explícitamente el esquema de delays. Los delays deben ser positivos. Para 429 con Retry-After válido se espera el mayor entre ese valor y el delay configurado, sin aumentar intentos.

La unidad reintentada es la operación fallida, nunca todo el flujo. La reconciliación consume el mismo presupuesto de recuperación de CREATE; si lookup falla no se envía CREATE. retry_count suma los reintentos de todas las operaciones de la ejecución y puede superar 2; el contador local por operación decide su agotamiento. El estado retrying vuelve a processing al continuar. Un 409 solo permite reconciliación acotada, sin espera automática.

Fallo definitivo → persistir failed, error sanitizado y finished_at → intentar alerta Slack. Slack usa la misma clasificación y presupuesto, sin alertas recursivas. Su fallo se registra como evento de etapa alert sin reemplazar el error principal; no convierte failed en success. La tabla de eventos conserva la historia de etapas, intentos y fallos de alerta; la tabla executions es el resumen actual.

## Logging y seguridad

Resumen mínimo: execution_id, idempotency_key, source canónico, lead_identifier, status, stage, crm_action, crm_contact_id, enrichment_status, retry_count, error_type, error_code, error_message, started_at, finished_at. `event_id` no se conserva en el ledger. created_at/updated_at permiten auditoría. El cliente actualiza updated_at en cada mutación. Los cambios de resumen y su evento de auditoría deben confirmarse en la misma transacción.

lead_identifier será SHA-256 del email normalizado; reduce exposición pero sigue siendo dato seudonimizado. No guardar payloads completos, nombres, teléfono ni email en texto en logs. Permitir únicamente códigos y mensajes redactados; nunca cabeceras, tokens, URLs firmadas, webhook Slack o stack traces. Slack recibe solo execution_id, etapa y código sanitizado. Configurar retención y acceso restringido a logs al implementar infraestructura.

Credenciales fuera de Git; `.env.example` sin valores sensibles. PostgreSQL con usuario de aplicación de mínimo privilegio y rol de migraciones separado. LF-001.C añade autenticación por header configurable y falla cerrado si la clave configurada está vacía. Production valida configuración crítica antes de operar. TLS y una frontera pública deberán existir antes de salir de loopback.

El webhook local exige una clave de entorno y no se expone fuera de `127.0.0.1`. n8n guarda su configuración cifrada mediante N8N_ENCRYPTION_KEY. Las ejecuciones automáticas exitosas y fallidas no conservan datos de ejecución; esto minimiza la persistencia del payload recibido. El debugging local se apoya en respuestas sanitizadas, logs técnicos y las tablas LeadFlow, que no almacenan email, teléfono ni nombres.

R2-A limita la credencial de importación n8n al instante de uso: se crea con herencia ACL deshabilitada en Windows, se importa y se elimina en `finally`; el cleanup es idempotente. Recovery entrega password y SQL a `psql` por stdin, sin email, secreto o consulta en argv, y transforma stderr/fallos de proceso en códigos operacionales genéricos.

Una ejecución recovery invocada con más de `RECOVERY_MAX_PROCESSING_AGE_SECONDS` sin progreso, con máximo seguro de 604800 segundos, se terminaliza como `failed/recovery_expired` mediante una función transaccional. Solo afecta la ejecución original arrendada, conserva su clave de idempotencia y dispara el cleanup del contexto cifrado. El barrido general de retención sigue fuera de R2-A y pertenece a REM-12/R3.

## Extensibilidad

Futuros CRM y proveedores implementarán los mismos contratos y pruebas de conformidad. Un motor de política podrá ampliar delays o clasificación sin dispersar constantes. Multiempresa completa, IA, dashboard y WhatsApp quedan fuera de V1; no se implementan anticipadamente.
## Logging y portabilidad por entorno

LeadFlow emite eventos operacionales JSON con nivel y salida configurables. La allowlist conserva únicamente metadata técnica (`component`, `event`, `stage`, `error_type`, `error_code`, estado, códigos HTTP, reintentos e identificadores técnicos válidos); descarta payloads, datos de contacto, headers, tokens, URLs y valores externos arbitrarios. Compose aplica a todos sus servicios un driver y límites configurables con defaults seguros.

El core consume adaptadores por endpoints configurados, los secretos permanecen fuera de Git y producción usa un override sin puertos locales publicados. Los volúmenes persistentes son `leadflow_postgres_data` y `leadflow_n8n_data`; el contrato de backup está en `config/backup-policy.json` y exige reaplicar el estado DSR tras restore. Cambiar de entorno se resuelve mediante variables y overrides, sin modificar el core.

Permanecen **HYBRID/ENVIRONMENT** y no verificados hasta un despliegue real: red, DNS, dominio, TLS, firewall, IAM, almacenamiento y volúmenes efectivos, cifrado de host/storage, backup/restore ejecutados, monitoreo y separación dev/test/prod desplegada.
# LF-008: Event, Lead e Interaction

LeadFlow mantiene tres identidades separadas. `event_id` + `source` identifica el envío técnico y conserva la clave histórica `SHA-256(source + ":" + event_id)`; el email normalizado identifica el contacto; `interaction` contiene únicamente el contexto opcional del contacto actual. El contacto CRM se confirma localmente antes de escribir la interacción y esta usa `<idempotency_key>:crm_interaction`, sin PII.

La interacción se ejecuta antes de enrichment. El adapter expone capacidades independientes de escritura, idempotencia y reconciliación; si falta alguna, el core falla cerrado antes del primer efecto CRM. Un resultado ambiguo deja la ejecución no terminal, cifra el contexto JSON mínimo en `recovery_contexts` y obliga a reconciliar antes de repetir. El contenido temporal se elimina por el trigger terminal, DSR DELETE o expiración de recovery.
