# LF-M01 — Manual de instalación e implementación

**Versión documental:** 1.0 · 16/11/2026. **Estado:** edición consolidada para aprobación del responsable. No autoriza exposición comercial.

## 1. Propósito y alcance

Instalar LeadFlow en un entorno compatible, configurar proveedores, verificar seguridad y funcionalidad, y entregar el sistema al responsable operacional. Modalidad A: ejecuta el cliente. Modalidad B: ejecuta Emactiva dentro del alcance contratado. El cliente autoriza accesos, tratamiento de datos y puesta en servicio en ambas modalidades. Hosting, costos de terceros, operación permanente y nuevas integraciones no se incluyen automáticamente.

La referencia productiva es Linux/Debian, Docker Compose y Google Cloud. No se certifica aquí otro proveedor de infraestructura. El sitio web no es requisito universal del Core; este manual describe la captación web validada. Otras entradas requieren integración autorizada y validación independiente. El contrato vigente exige email; no inventar emails para entradas telefónicas.

## 2. Arquitectura y componentes

Formulario HTTPS → Caddy → Rate Gate → Web Bridge → n8n Core → PostgreSQL / Adapters → HubSpot, Hunter y Slack. Turnstile verifica la captación web. Los respaldos y la evidencia DSR tienen custodias independientes.

| Componente | Versión declarada en repositorio |
|---|---|
| PostgreSQL | 17.6 Bookworm |
| n8n | 2.28.6 |
| Adapters, Bridge y Rate Gate | Python 3.14.3 slim Bookworm |
| Caddy | 2.11.3 Alpine |

Las versiones de Docker y Compose se deben comprobar en el host; la configuración requiere soporte de `!reset` y `!override`. No confundir las versiones de desarrollo con requisitos mínimos certificados. El Gateway de referencia publica TCP 443; no publicar PostgreSQL, n8n ni los adaptadores. Los tres proyectos Compose deben ser distintos. El endpoint público actual utiliza IP; el origen del formulario puede ser un dominio HTTPS distinto.

## 3. Preparación y requisitos

Confirmar alcance, responsable técnico, responsable funcional, titularidad de infraestructura, tratamiento de datos, fuente de leads, interesados autorizados, permisos y ventana de implementación. Identificar versión entregada y verificar integridad de artefactos antes de ejecutar.

Host Linux: Bash, Docker Engine, Compose plugin, Python 3, utilidades GNU; para respaldo y recuperación también Node.js 20+, sha256sum, curl y Google Cloud CLI. Dimensionar CPU, RAM, almacenamiento, disco de respaldo y red según carga; el tamaño mínimo certificado queda pendiente. Comprobar cuotas, DNS, conectividad de salida autorizada, IP pública y firewall. El cliente debe disponer de una cuenta GCP con las APIs e identidades necesarias para esta referencia. No descargar claves JSON de cuentas de servicio.

## 4. Preparación de proveedores

| Proveedor | Acción previa |
|---|---|
| HubSpot | Autorizar lectura/escritura de contactos y tickets; confirmar propiedades y pipeline/stage reales. |
| Hunter | Obtener credencial autorizada y verificar capacidad contratada. |
| Slack | Crear webhook de canal autorizado; evitar datos personales en alertas. |
| Turnstile | Crear widget, autorizar hostnames del formulario y suministrar site key al frontend y secret key al Bridge. |
| GCP | Preparar VM, identidad administrada, Secret Manager, almacenamiento y permisos específicos. |

HubSpot: permisos documentados `crm.objects.contacts.read`, `crm.objects.contacts.write`, `crm.objects.tickets.read`, `crm.objects.tickets.write`. Verificar las propiedades de contacto para industry, company_size y website y las de ticket `leadflow_interaction_key`, `content`, `leadflow_interest` (defaults configurables). No ampliar scopes ni crear schema automáticamente. El pipeline y stage se obtienen del portal del cliente, no de constantes históricas.

## 5. Configuración y secretos

Mantener configuración externa, sin valores reales en Git, manuales, capturas o logs. Usar mapas de referencias a versiones numéricas, no `latest`. Separar identidades de runtime, administración PostgreSQL, DSR, backup y restore. Los permisos efectivos se verifican en el entorno.

| Grupo | Variables o referencias |
|---|---|
| PostgreSQL | POSTGRES_DB, POSTGRES_BOOTSTRAP_USER, POSTGRES_MIGRATOR_USER, POSTGRES_APP_USER y sus contraseñas distintas |
| Runtime | POSTGRES_APP_PASSWORD, N8N_ENCRYPTION_KEY, LEADFLOW_WEBHOOK_KEY, RECOVERY_CONTEXT_KEY, ADAPTER_SERVICE_KEY, DSR_SUBJECT_KEY, CRM_API_KEY, ENRICHMENT_API_KEY, SLACK_WEBHOOK_URL |
| Administración | POSTGRES_BOOTSTRAP_PASSWORD, POSTGRES_MIGRATOR_PASSWORD, DSR_ADAPTER_SERVICE_KEY |
| Core no secreto | CRM_PROVIDER=hubspot, ENRICHMENT_PROVIDER=hunter, CRM_UPSTREAM_URL, ENRICHMENT_UPSTREAM_URL, RECOVERY_ADAPTER_URL, PUBLIC_WEBHOOK_HOST, ADAPTER_ALLOWED_OPERATIONS, LEADFLOW_ALLOWED_SOURCES, LEADFLOW_ALLOWED_INTERESTS |
| Bridge | WEB_BRIDGE_EVENT_ID_KEY, WEB_BRIDGE_ABUSE_TOKEN, LEADFLOW_WEBHOOK_KEY, WEB_BRIDGE_TURNSTILE_SECRET_KEY |
| Gateway | WEB_BRIDGE_ABUSE_TOKEN (misma referencia autorizada que Bridge) |

El inventario anterior identifica grupos críticos; A01 incluye la lista de parámetros de frontera y el esquema de mapas. Para el conjunto Core completo, usar `.env.example`, los manifiestos Compose y el validador de la revisión entregada, sin cargar automáticamente `.env` en producción. Las contraseñas y claves sujetas al validador deben tener al menos 32 caracteres y los tres roles PostgreSQL deben ser distintos. Custodiar claves de n8n, backup y DSR de modo que una futura restauración sea posible. Restringir acceso a mapas y archivos locales; no imprimir el Compose resuelto ni variables de entorno.

Mapas: `LF015-SECRET-MAP-2` / `runtime-compose`; `LF015-WEB-BRIDGE-SECRET-MAP-1` / `web-bridge-compose`; `LF015-WEB-GATEWAY-SECRET-MAP-1` / `web-gateway-compose`. Proveedor `gcp-secret-manager`, identidad esperada de la VM y referencias numéricas autorizadas. Los mapas productivos se preparan fuera del repositorio. No reutilizar mapas de Emactiva en un cliente.

## 6. Preflight e instalación del Core

Ejecutar desde la raíz de la versión entregada, en la VM autorizada. Los ejemplos suponen que un operador ha suministrado las variables requeridas mediante el mecanismo externo aprobado. No ejecutar bloques si faltan parámetros o autorizaciones. Validar recursos y propiedad de proyectos, ausencia de colisiones, espacio, dependencias e imágenes; los mocks no forman parte del runtime productivo.

### 6.1 Inicialización de PostgreSQL nuevo

Solo para volumen nuevo autorizado. El proyecto Compose del bootstrap debe corresponder exactamente al Core que utilizará el volumen persistente. En una sesión administrativa protegida, suministrar las tres credenciales PostgreSQL y los nombres exigidos. Revisar primero que no existe una instalación previa.

```bash
python3 scripts/validation/validate_deployment_config.py --context postgres-admin
LEADFLOW_POSTGRES_BOOTSTRAP_AUTHORIZED=true bash scripts/database/bootstrap_postgres.sh
```

Requiere `COMPOSE_PROJECT_NAME` externo explícito. Resultado esperado: `PostgreSQL bootstrap: PASS`, migraciones aplicadas y contenedor administrativo retirado, volumen conservado. Si el volumen está inicializado o es ambiguo, detenerse; no borrar, recrear ni repetir bootstrap. Las actualizaciones de instalaciones existentes requieren procedimiento de migración y respaldo específico. Eliminar la disponibilidad de credenciales privilegiadas en la sesión antes de iniciar runtime.

### 6.2 Runtime Core

Preparar imágenes de la versión y configuración no secreta. Antes de cualquier bootstrap, verificar también los tres preflight de configuración, cuando todos sus requisitos estén preparados; estos no inician servicios. El mapa runtime únicamente incluye los nueve secretos autorizados. Comprobar que el proyecto real de Compose coincide con el usado en bootstrap; el wrapper Core no fija un nombre de proyecto mediante `-p` ni garantiza conservar `COMPOSE_PROJECT_NAME` del entorno. No asumir que exportarlo basta. Comprobar el nombre efectivo de Compose con el directorio de checkout y los manifiestos aprobados antes de bootstrap; usar ese mismo nombre para todos los pasos. Si no coincide con la instalación autorizada, detenerse sin crear volúmenes. Recargar la configuración externa de la sesión runtime y usar el mapa privado correspondiente.

```bash
python3 scripts/admin/compose_with_secrets.py preflight --map "$LEADFLOW_SECRET_MAP_FILE"
```

Con PASS y autorización de arranque:

```bash
python3 scripts/admin/compose_with_secrets.py start --map "$LEADFLOW_SECRET_MAP_FILE"
```

Esperar `status=PASS`; verificar PostgreSQL, Adapters y n8n healthy, proyecto correcto y ausencia de puertos internos publicados. El preflight valida configuración; no demuestra por sí solo salud de servicios ni permisos de proveedores.

### 6.3 Aprovisionamiento n8n en Linux — gate ambiental pendiente

El aprovisionador `scripts/n8n/provision_n8n.py` reutiliza el mapa runtime LF015-SECRET-MAP-2. Requiere n8n 2.28.6 iniciado, proyecto Core explícito y mapa externo protegido. La versión local reportada reconcilia contenido y actividad, evita reimportar elementos equivalentes y limita la exportación descifrada al ID `leadflow-postgres`. H04/H05 cuentan con QA focalizado reportado (8/8 y 9/9 respectivamente); ejecución real y detección de ausencia siguen NOT_VERIFIED.

```bash
export LEADFLOW_COMPOSE_PROJECT='<proyecto-core-aprobado>'
python3 scripts/n8n/provision_n8n.py preflight --map "$LEADFLOW_SECRET_MAP_FILE"
```

El primer gate se realiza exclusivamente en Linux aislado, sin flags de reemplazo ni publicación. Si falla, registrar el error_id sanitizado y detenerse. No ejecutar apply hasta comprobar el comportamiento real y obtener autorización independiente. Una vez superado ese gate, la ruta prevista de instalación nueva es:

```bash
python3 scripts/n8n/provision_n8n.py apply --map "$LEADFLOW_SECRET_MAP_FILE" --authorize-provision
```

Verificar equivalencia de credencial y workflow e inactividad cuando se trate de una instalación nueva sin publicación autorizada. Publicar únicamente mediante decisión explícita (`--authorize-publish` junto con `--authorize-provision`), después de validar la instalación. Las autorizaciones de reemplazo son independientes (`--authorize-replace-credential`, `--authorize-replace-workflow`, `--authorize-active-replacement`); una divergencia requiere revisión específica; no usar flags de reemplazo como solución automática. Consultar SETUP.md de la revisión aprobada para opciones y límites. No abrir tráfico público.

## 7. Captación web: Bridge y Gateway

Preparar red externa autorizada, conectividad efectiva hacia n8n y salida requerida para Siteverify; comprobar que no se publican puertos del Bridge. Configurar proyectos distintos para Core, Bridge y Gateway. Preparar imágenes fijadas, incluyendo Rate Gate, antes del preflight del Gateway. Verificar las imágenes fijadas y su procedencia/digest antes de mutar: postgres:17.6-bookworm, n8nio/n8n:2.28.6, leadflow-adapters:python-3.14.3, leadflow-web-bridge:python-3.14.3, leadflow-web-gateway-rate-gate:python-3.14.3 y caddy:2.11.3-alpine. Si falta una imagen o su procedencia no está aprobada, detenerse. La preparación por pull/build requiere ventana autorizada; seguir SETUP.md. Verificar labels de proyectos y propiedad de redes y volúmenes; no reutilizar recursos de otra instalación. Los digests y la receta efectiva en un destino nuevo siguen NOT_VERIFIED.

Ejemplo sintético de origen, sin secretos:

```env
WEB_GATEWAY_ALLOWED_ORIGINS=https://empresa.example,https://www.empresa.example
WEB_BRIDGE_ALLOWED_ORIGINS=https://empresa.example,https://www.empresa.example
WEB_BRIDGE_TURNSTILE_HOSTNAMES=empresa.example,www.empresa.example
WEB_GATEWAY_PUBLIC_PATH=/lead
WEB_GATEWAY_UPSTREAM_URL=http://web-bridge:8080/lead
```

Usar orígenes HTTPS canónicos sin espacios, rutas, comodines ni puerto predeterminado explícito. H12 cuenta con PASS SYSTEM reportado; aplicación en entorno real pendiente. Comprobar igualdad de las dos allowlists operativamente y presencia de todos los hostnames requeridos en Turnstile; el Site Key debe pertenecer al widget autorizado. El dominio del formulario es independiente de la IP HTTPS del endpoint. El soporte de endpoint propio por DNS queda fuera del procedimiento comprobado (H11).

Con mapas externos, red e imágenes preparados:

```bash
python3 scripts/admin/web_bridge_with_secrets.py preflight --map "$WEB_BRIDGE_SECRET_MAP_FILE"
python3 scripts/admin/web_gateway_with_secrets.py preflight --map "$WEB_GATEWAY_SECRET_MAP_FILE"
```

Si cualquiera falla, detenerse. Tras autorización y habiendo restringido el acceso externo a la ventana de prueba:

```bash
python3 scripts/admin/web_bridge_with_secrets.py start --map "$WEB_BRIDGE_SECRET_MAP_FILE"
python3 scripts/admin/web_gateway_with_secrets.py start --map "$WEB_GATEWAY_SECRET_MAP_FILE"
```

Comprobar servicios, redes, solo Caddy publicado en 443, confianza TLS, SAN, issuer y expiración. No saltar validación TLS. La continuidad de renovación y firewall requiere evidencia propia. Conservar la configuración e imágenes previas para rollback.

## 8. QA y aceptación técnica

Usar datos sintéticos autorizados y comprobar previamente ausencia de registros coincidentes. No enviar tráfico de clientes. Detener ante el primer fallo real.

| Caso | Resultado esperado |
|---|---|
| Servicios Core | Tres healthy; Bridge, Rate Gate y Caddy running, con prueba funcional aparte |
| OPTIONS desde origen autorizado | 204 y cabeceras CORS correspondientes |
| Origen no permitido | Rechazo sin reflejar origen no autorizado |
| Solicitud sin autorización | Rechazo sin efectos externos |
| Entrada malformada / excedida | Rechazo 4xx conforme al contrato |
| Lead sintético válido | Aceptación 202; verificar resultado terminal y efectos en CRM, no inferir éxito del 202 |
| Repetición exacta | Sin nuevos efectos externos |
| Mismo email con nueva consulta | Contacto identificado y nueva interacción según contrato |
| Rate limit | 429 al superar límite autorizado |
| Cleanup | Reconciliación de registros sintéticos y preservación de datos ajenos |

Registrar versión, entorno, fecha, responsable, resultado, evidencia sanitizada y limitaciones. Aplicar la secuencia y los criterios de A01; no usar pruebas destructivas DSR como smoke test ordinario. La evidencia técnica existente LF015-T03 no certifica automáticamente la instalación de un cliente ni el cambio local D1.6.

## 9. Activación y rollback

Antes de activar tráfico real, confirmar aceptación técnica y funcional explícita, configuración privacidad, custodia, respaldo recuperable, soporte, riesgos y responsables. Si falla una actualización, restringir entrada y restituir configuración e imágenes aprobadas. No eliminar volúmenes productivos ni usar `down -v`. Si afecta datos, evaluar restauración aislada según M03 y autoridad DSR independiente; no restaurar directamente sobre producción. Registrar incidente, resultado y autorización de reanudación.

## 10. Entrega y responsabilidades

Entregar versión autorizada, manuales, plantillas sin secretos, inventario de configuración, checklist, evidencia de esa instalación y límites contractuales. Cliente valida finalidad, accesos, proveedores y operación posterior salvo acuerdo separado. Emactiva implementa solo en modalidad B y presta soporte según contrato. No distribuir HANDOFF internos ni datos de otras instalaciones. El acceso público exige aprobación independiente; un PASS técnico no implica habilitación comercial.

## 11. Preparación de infraestructura de referencia y límites de entrega

GCP: preparar un proyecto del cliente con facturación, Compute Engine, Secret Manager, Cloud Storage y, si se usa impersonación para backup, IAM Credentials API. Crear la VM Linux con identidad administrada y scope apropiado, disco persistente aprobado y acceso administrativo restringido. No descargar claves JSON. Crear almacenamiento de backups y otro de autoridad DSR, con prevención de acceso público y acceso uniforme IAM. Configurar lifecycle de backups según M03; no aplicar el mismo lifecycle al estado DSR vigente. Verificar permisos efectivos por identidad, DNS, reloj, egress y firewall; limitar TCP 443 a la ventana y origen autorizados hasta aprobar exposición pública. El certificado IP requiere comprobar renovación TLS-ALPN. No habilitar acceso público a n8n, PostgreSQL o adapters.

Antes del arranque, obtener las imágenes de terceros aprobadas y construir las imágenes propias desde el checkout autorizado. Las siguientes son rutas de construcción derivadas de los manifiestos y el Dockerfile de Rate Gate; la ejecución y los digests del destino deben comprobarse en preflight de suministro. No ejecutar en un entorno activo sin ventana de cambio.

```bash
docker pull postgres:17.6-bookworm
docker pull n8nio/n8n:2.28.6
docker pull caddy:2.11.3-alpine
docker build -t leadflow-adapters:python-3.14.3 adapters
docker build -t leadflow-web-bridge:python-3.14.3 bridge
docker build -f gateway/Dockerfile.rate-gate -t leadflow-web-gateway-rate-gate:python-3.14.3 gateway
```

Registrar IDs/digests, origen, versión y aprobación. Verificar que los cargadores usan los mismos tags; el start del Bridge puede ejecutar build y debe quedar dentro de la ventana autorizada. Tras iniciar Core, identificar su red real por labels y conexión del servicio n8n. Configurar `WEB_BRIDGE_UPSTREAM_NETWORK` con el nombre aprobado, no crear una red homónima a ciegas. Comprobar alias DNS y ruta webhook interna efectiva. Gateway y Bridge comparten esa red externa; Caddy conserva su red edge interna. La red compartida no constituye aislamiento completo frente a procesos del host.

## 12. Evidencia de referencia y controles de destino

| Control | Evidencia / estado |
|---|---|
| Recepción web y CRM real | PASS histórico LF015-T03: cuatro ejecuciones sintéticas, deduplicación y controles HTTP en alcance. |
| Seguridad y cleanup | PASS histórico acotado; no certifica ausencia de ataques. |
| Portabilidad de orígenes H08/H10/H12 | PASS SYSTEM reportado; nuevo dominio real NOT_VERIFIED. |
| Aprovisionador Linux H04/H05 | PASS SYSTEM reportado; CLI real, IAM y ausencia de credencial NOT_VERIFIED. |
| Capacidad e imágenes en destino | NOT_VERIFIED; dimensionar y validar en el entorno. |
| Renovación TLS y H11 | NOT_VERIFIED; endpoint DNS propio no acreditado. |
| Reproducibilidad por tercero EDPB-T09 | NOT_VERIFIED; requiere ejecución independiente autorizada. |

Este manual consolida la evidencia de la revisión base `5813007` y remediaciones locales reportadas D1.6/H12/H04/H05. No sustituye la identificación del commit final de entrega ni autoriza un apply no validado. El paquete técnico histórico fue aceptado con WARN; operación sostenida, resiliencia integral y habilitación comercial no están aceptadas. Fuentes: `docs/setup/SETUP.md`, `docs/architecture/CONTRACTS.md`, `docs/runbooks/BACKUP_RESTORE.md`, manifiestos Compose, scripts administrativos y evidencia LF015-T03/T04. Aplican EWB, EPB, EDPB y EQAB v1.0.
