# Arquitectura V1

## Componentes y límites

n8n orquestará el webhook y el núcleo reutilizable: validar, normalizar, reclamar evento, gestionar estados, clasificar errores, aplicar retries, registrar y responder. PostgreSQL será autoridad para idempotencia y trazabilidad. Los adaptadores CRM, enriquecimiento y alerta Slack traducirán los contratos externos sin introducir reglas del proveedor en el núcleo. Configuración exclusivamente por entorno, según `.env.example`.

En este LAB solo se define la arquitectura. Las carpetas `workflows/`, `mocks/`, `database/seeds/`, `scripts/test/` y `docs/handoff/` se crearán cuando tengan implementaciones o material propio. El handoff vive en `labs/` para evitar duplicarlo.

## Flujo normal

1. Asignar `execution_id` único y registrar recepción con mínimos metadatos.
2. Validar entrada y normalizar email (trim, lowercase y formato). Rechazar antes de cualquier llamada externa si es inválida.
3. Calcular SHA-256 UTF-8 de `source + ":" + event_id`, representado en hexadecimal minúsculo; reclamar el evento atómicamente en PostgreSQL.
4. Pasar a processing; consultar CRM por email normalizado. Crear si no existe o actualizar los campos presentes si existe.
5. Enriquecer mediante el adaptador; actualizar únicamente los campos de enriquecimiento permitidos en CRM.
6. Persistir success y finished_at antes de responder. Si el enriquecimiento falla definitivamente, el resultado global es failed aunque el contacto ya exista; no se intenta revertirlo.

## Idempotencia y concurrencia

La tabla `leadflow.executions` conserva una fila propietaria por evento válido, con `idempotency_key UNIQUE`. El reclamo usa una función transaccional corta: crea la recepción con clave NULL e intenta asignar la clave mediante UPDATE; la restricción UNIQUE decide el único propietario y una excepción controlada resuelve al ganador. Solo quien obtiene la clave puede procesar. Nunca usar SELECT seguido de INSERT/UPDATE sin protección de UNIQUE ni mantener una transacción abierta durante llamadas HTTP.

La operación oficial `leadflow.claim_event` inserta el registro received con clave NULL y su evento de auditoría. En la misma transacción intenta asignar la clave mediante UPDATE sobre esa misma fila. Si UNIQUE detecta un propietario concurrente, la excepción controlada marca la recepción actual como duplicate, mantiene su clave NULL y establece `duplicate_of` al propietario encontrado por esa clave. No se elimina ni reemplaza ninguna ejecución y ambos historiales se conservan. En logs, la clave de la recepción duplicada se obtiene mediante JOIN con su propietario. Los inválidos mantienen clave NULL, pues puede faltar source/event_id; PostgreSQL permite varios NULL bajo UNIQUE.

El rol de aplicación no tiene escritura directa en estas tablas: ejecuta funciones transaccionales concedidas expresamente. Así, la operación oficial garantiza que `duplicate_of` apunta a una fila con la clave reclamada. La FK garantiza existencia y las pruebas negativas/concurrentes verifican la regla que no puede expresarse limpiamente mediante un CHECK entre filas.

Un duplicado nunca modifica el estado del propietario ni dispara efectos externos. Su respuesta identifica su propia recepción y la ejecución original. Una entrega repetida de un evento failed tampoco lo reejecuta: la recuperación futura será una operación explícita sobre la ejecución original, no un bypass de UNIQUE. La misma clave con contenido distinto sigue siendo duplicada; el emisor debe asignar un nuevo event_id a cada cambio.

source es un identificador sin `:`; event_id puede contenerlo. Así se evita ambigüedad en la concatenación sin cambiar la fórmula definida. Ambos son sensibles a mayúsculas y no se recortan silenciosamente.

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

Resumen mínimo: execution_id, idempotency_key, event_id, source, lead_identifier, status, stage, crm_action, crm_contact_id, enrichment_status, retry_count, error_type, error_code, error_message, started_at, finished_at. created_at/updated_at permiten auditoría. El cliente actualiza updated_at en cada mutación. Los cambios de resumen y su evento de auditoría deben confirmarse en la misma transacción.

lead_identifier será SHA-256 del email normalizado; reduce exposición pero sigue siendo dato seudonimizado. No guardar payloads completos, nombres, teléfono ni email en texto en logs. Permitir únicamente códigos y mensajes redactados; nunca cabeceras, tokens, URLs firmadas, webhook Slack o stack traces. Slack recibe solo execution_id, etapa y código sanitizado. Configurar retención y acceso restringido a logs al implementar infraestructura.

Credenciales fuera de Git; `.env.example` sin valores sensibles. PostgreSQL con usuario de aplicación de mínimo privilegio y rol de migraciones separado. TLS y autenticación del webhook se definirán antes de exponer infraestructura; LAB-LF-000 no abre puertos ni utiliza secretos reales.

## Extensibilidad

Futuros CRM y proveedores implementarán los mismos contratos y pruebas de conformidad. Un motor de política podrá ampliar delays o clasificación sin dispersar constantes. Multiempresa completa, IA, dashboard y WhatsApp quedan fuera de V1; no se implementan anticipadamente.
