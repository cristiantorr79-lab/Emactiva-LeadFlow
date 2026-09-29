# LAB-LF-003 — Tarea 03B: evidencia operativa de cuentas e infraestructura

Fecha de consolidación: 2026-09-27. Estado: **COMPLETADA DOCUMENTALMENTE**.

## 1. Alcance

Inspección pasiva y read-only de configuración declarada, archivos locales por existencia/metadata/ACL, exclusiones Git, código de fronteras y disponibilidad del daemon Docker. No se abrió `.env` ni el archivo de credenciales, no se imprimieron valores, hashes de secretos, URLs reales, connection strings, tokens o IDs de cuenta. No se inició Docker ni se realizaron llamadas a proveedores.

Estados: `VERIFIED` = hecho local demostrado; `PARTIAL` = evidencia real pero incompleta; `REQUIRES_USER` = requiere revisión visual/operativa de Cristian; `NOT_VERIFIED` = no observable con las fuentes disponibles. Declaraciones de archivos no acreditan despliegue efectivo.

## 2. Evidencia automática Codex

### Configuración y aplicación

| ID | Sistema | Requisito | Método | Resultado sanitizado | Evidencia | Estado | Impacto en matriz |
|---|---|---|---|---|---|---|---|
| CFG-01 | HubSpot | Variables esperadas | Lectura de nombres en `.env.example`, Compose y Adapter | `CRM_PROVIDER`, `CRM_API_KEY`, `CRM_UPSTREAM_URL`; mappings industry/company_size/website declarados | `.env.example`; `compose*.yaml`; `adapters/server.py:24-52` | VERIFIED | Confirma diseño; no cambia estado de cuenta |
| CFG-02 | Hunter | Variables esperadas | Igual | `ENRICHMENT_PROVIDER`, `ENRICHMENT_API_KEY`, `ENRICHMENT_UPSTREAM_URL` declaradas | mismos archivos | VERIFIED | Sin cambio: existencia real/plan pendientes |
| CFG-03 | Slack | Variables esperadas | Igual | `SLACK_WEBHOOK_URL` se proyecta a `ALERT_UPSTREAM_URL` | `.env.example`; Compose; Adapter | VERIFIED | Sin cambio: workspace/webhook no verificados |
| CFG-04 | Proveedores | HTTPS producción | Revisión estática | Producción exige URLs presentes y Adapter rechaza upstream no HTTPS/local/mock | `compose.production.yaml:23-27`; `adapters/server.py:47-52`; validador deployment | VERIFIED | Sustenta WARN de transporte; no prueba TLS real |
| CFG-05 | HubSpot | Mappings por defecto | Revisión de Adapter + comprobación manual V04 | `industry→industry`, `company_size→leadflow_company_size`, `website→website` | `adapters/server.py:45-46`; HUBSPOT-V04 | VERIFIED | Mapping efectivo confirmado; no valida contenido de valores |
| CFG-06 | PostgreSQL | Roles declarados | Revisión Compose/migraciones | Migrator fijo y rol app declarados; REVOKE público y GRANT de funciones/SELECT | `compose.yaml:6-10`; D1-D11 | VERIFIED | Confirma diseño de mínimo privilegio; grants efectivos pendientes |
| CFG-07 | PostgreSQL | Separación app/migrations | Revisión estática | Roles nominalmente separados, pero `POSTGRES_PASSWORD` alimenta tanto migrator como `POSTGRES_APP_PASSWORD` | `compose.yaml:7-10` | PARTIAL | Mantiene EPB-IMP02 WARN |
| CFG-08 | PostgreSQL | SSL cliente n8n | Revisión provisioning | Credencial importada declara `ssl='disable'` | `scripts/n8n/provision_n8n.ps1:7` | VERIFIED | Mantiene cifrado/transporte WARN; estado real pendiente |
| CFG-09 | n8n | Retención de ejecuciones | Revisión Compose | Success/error `none`, manual `false`, pruning `true`, max age `24` | `compose.yaml:45-49` | VERIFIED | Control declarado, no ejecución efectiva; RET04 sigue WARN |
| CFG-10 | n8n | Encryption key por entorno | Revisión Compose/provision | `N8N_ENCRYPTION_KEY` requerida; valor no leído | `compose.yaml:31`; provisioning | VERIFIED | Confirma requisito configuracional, no key management real |
| CFG-11 | Infraestructura | Puertos declarados | Revisión Compose | Development publica seis servicios solo en loopback; production resetea todos los puertos publicados | `compose.yaml`; `compose.production.yaml` | VERIFIED | Diseño confirmado; exposición real pendiente |
| CFG-12 | Docker | Redes declaradas | Revisión Compose | No hay sección de redes personalizada; Compose usaría su red default | `compose*.yaml` | VERIFIED | Segmentación/ACL reales NOT_VERIFIED |
| CFG-13 | Docker | Volúmenes persistentes | Revisión Compose | Volúmenes nombrados para PostgreSQL y n8n | `compose.yaml:13-14,52-54,171-173` | VERIFIED | Mantiene RET06/RET07 FAIL; no hay retención/cleanup |
| CFG-14 | Servicios | Healthchecks | Revisión Compose | PostgreSQL, n8n, mocks y Adapter tienen healthchecks | `compose.yaml` | VERIFIED | Disponibilidad declarada; no equivale a monitoreo privacidad |
| CFG-15 | Logs | Configuración declarada | Búsqueda de `logging`, rotación y archivos | Sin driver/rotación explícitos en Compose; n8n no guarda executions | Compose; inventario de archivos | PARTIAL | Logs de runtime/host siguen NOT_VERIFIED |
| CFG-16 | Backup | Scripts/configuración | Inventario por nombres y contenido relevante | No se encontró script de backup/restore/rotación/retención | inventario `rg --files` | VERIFIED | Ausencia de artefacto local; ARCH07/RET08 siguen NOT_VERIFIED porque infraestructura externa puede existir |
| CFG-17 | Cleanup | Scripts/configuración | Revisión de scripts/migraciones | Cleanup automático solo para recovery terminal; no para ledger, volúmenes o credencial temporal | D9; provisioning | VERIFIED | Mantiene H02/H06 y gaps de retención |
| CFG-18 | Runtime | Estado Docker | `docker version` pasivo, sin iniciar servicio | CLI PRESENTE; daemon `NOT_RUNNING_OR_INACCESSIBLE` | inspección 2026-09-26 | NOT_VERIFIED | Runtime registrado como `NOT_CHECKED_RUNTIME`; no cambia matriz |

### HubSpot — automático

| ID | Sistema | Requisito | Método | Resultado sanitizado | Evidencia | Estado | Impacto en matriz |
|---|---|---|---|---|---|---|---|
| HUBSPOT-A01 | HubSpot | Endpoint/operaciones | Código Adapter | Search y Contacts Object API v3; lookup, create y PATCH | `adapters/server.py:110-131` | VERIFIED | Confirma función técnica; sin cambio de cuenta |
| HUBSPOT-A02 | HubSpot | Datos enviados | Flujo estático | Lookup: email; create: email/nombre/apellido/teléfono/company; update: opcionales presentes; enrichment: tres mappings | Adapter/INV | VERIFIED | Mantiene minimización normal y H05 |
| HUBSPOT-A03 | HubSpot | Datos recibidos | Flujo estático | Lookup consume `id` y `properties.email`; create consume `id`; cuerpos adicionales no se propagan normalmente | Adapter/INV | VERIFIED | Sin cambio |
| HUBSPOT-A04 | HubSpot | Autenticación | Código | Bearer construido desde variable; valor no leído | `hubspot_headers` | VERIFIED | Scope/permiso real REQUIRES_USER |
| HUBSPOT-A05 | HubSpot | Scopes documentados | Lectura SETUP | Lectura/escritura de contactos indicada como requisito | `docs/setup/SETUP.md` | PARTIAL | Documentación ≠ scopes reales |
| HUBSPOT-A06 | HubSpot | Región de cuenta | Búsqueda estática + comprobación manual V01 | Estados Unidos (Este) | archivos versionados; HUBSPOT-V01 | VERIFIED | Región real confirmada para la cuenta revisada |

### Hunter — automático

| ID | Sistema | Requisito | Método | Resultado sanitizado | Evidencia | Estado | Impacto en matriz |
|---|---|---|---|---|---|---|---|
| HUNTER-A01 | Hunter | Endpoint real | Código Adapter | GET `/v2/combined/find` | `adapters/server.py:150-164` | VERIFIED | Confirma servicio configurado en código |
| HUNTER-A02 | Hunter | Parámetros enviados | Código | Solo email URL-encoded; API key en header; company no se envía al Hunter real | `provider_enrich` | VERIFIED | Mantiene H08 por email en URL |
| HUNTER-A03 | Hunter | Respuesta proyectada | Código | De company: industry/category, size/employees/metrics, website/site/domain | `hunter_data` | VERIFIED | Confirma inventario |
| HUNTER-A04 | Hunter | Allowlist | Código y tests existentes leídos | Solo strings `industry`, `company_size`, `website` salen del Adapter | `filter_enrichment_fields`; Handler PATCH | VERIFIED | Mantiene H05/H10 |
| HUNTER-A05 | Hunter | Opciones adicionales | Revisión configuración | No se encontraron opciones de data usage, región, plan o IA configurables en repo | Adapter/Compose/.env.example | VERIFIED | Su existencia en cuenta sigue REQUIRES_USER |
| HUNTER-A06 | Hunter | Función configurada | Código + comprobación manual V06 | La ruta auditada usa únicamente `/v2/combined/find`; no se observaron funciones Hunter adicionales | Adapter; HUNTER-V06 | VERIFIED | Plan Free indica que Lead enrichment no está incluido; compatibilidad operativa debe reconciliarse antes de uso real |

### Slack — automático

| ID | Sistema | Requisito | Método | Resultado sanitizado | Evidencia | Estado | Impacto en matriz |
|---|---|---|---|---|---|---|---|
| SLACK-A01 | Slack | Payload normal | Código workflow/Adapter | Exactamente `execution_id`, `stage`, `error_code` | W nodos Alert; `Handler.do_POST` | VERIFIED | Confirma minimización nominal |
| SLACK-A02 | Slack | Rechazo de campos extra | Código | Adapter exige conjunto exacto de tres claves | `adapters/server.py:215-218` | VERIFIED | H03 se mantiene porque valores no están acotados completamente |
| SLACK-A03 | Slack | Rutas de envío | Trazado estático | Fallos CRM y enrichment del workflow; recovery continuation; reconcile CRM no alerta | W,R,INV | VERIFIED | Confirma cobertura parcial; sin cambio de estado |
| SLACK-A04 | Slack | Endpoint | Config declarada + comprobación local sanitizada | `SLACK_WEBHOOK_URL` presente vacía; `ALERT_UPSTREAM_URL` ausente; wiring sí; Slack real no configurado | Compose/Adapter; comprobación 03B | VERIFIED | No existe workspace/canal operativo LeadFlow que auditar |
| SLACK-A05 | Slack | Contenido adicional accidental | Revisión de ruta | No se observan payloads completos en ruta normal; error_code arbitrario sigue siendo posible | W,A,D6 | PARTIAL | H03 permanece CONFIRMADO |

## 3. Infraestructura local y host

| ID | Sistema | Requisito | Método | Resultado sanitizado | Evidencia | Estado | Impacto en matriz |
|---|---|---|---|---|---|---|---|
| INFRA-A01 | Host | Archivo `.env` | Existencia/metadata únicamente | PRESENTE; contenido NO LEÍDO | metadata local | VERIFIED | Confirma configuración local existente, no su validez |
| INFRA-A02 | Host | Directorio `.local` | Existencia/metadata/ACL | PRESENTE; ACL heredadas | metadata local | VERIFIED | Control de acceso parcial |
| INFRA-A03 | Host | Credencial temporal n8n | Existencia/metadata/ACL | PRESENTE, tamaño 318 bytes, modificado 2026-09-25; contenido NO LEÍDO | `.local/n8n/postgres-credential.json` metadata | VERIFIED | Refuerza H06; no cambia WARN/ALTA |
| INFRA-A04 | Host | Permisos de credencial | `Get-Acl` | Hereda Modify para `CodexSandboxUsers` y otro SID local; FullControl para usuario DELL, Administradores y SYSTEM | ACL local | PARTIAL | No es ACL exclusiva al owner; identidad/alcance del SID y necesidad de grupos requieren Cristian |
| INFRA-A05 | Host | Cleanup credencial | Revisión provisioning + metadata | Script escribe/importa y no elimina; archivo continúa presente | provisioning + INFRA-A03 | VERIFIED | Confirma persistencia descrita en H06 |
| INFRA-A06 | Host | `.env` permisos | `Get-Acl`, sin contenido | ACL heredada equivalente: grupos locales con Modify; DELL/Admin/SYSTEM FullControl | metadata local | PARTIAL | Acceso efectivo necesita revisión del host |
| INFRA-A07 | Runtime | Containers/red/volúmenes/health | Daemon pasivo | `NOT_CHECKED_RUNTIME`: daemon apagado o inaccesible; no se inició | docker version | NOT_VERIFIED | Checklist INFRA-V requerido |

## 4. Secretos

| ID | Sistema | Requisito | Método | Resultado sanitizado | Evidencia | Estado | Impacto en matriz |
|---|---|---|---|---|---|---|---|
| SEC-A01 | Git/local | `.env` ignorado | `git check-ignore -v` | PRESENTE e ignorado por regla `.env` | `.gitignore:2` | VERIFIED | Reduce riesgo de commit accidental; no protege ACL/backup |
| SEC-A02 | Git/local | `.local` y credencial ignorados | `git check-ignore -v` | PRESENTES e ignorados por `.local/` | `.gitignore:31` | VERIFIED | No resuelve persistencia H06 |
| SEC-A03 | Git | Logs/temp ignorados | `git check-ignore` con rutas testigo | `logs/` y `temp/` ignorados | `.gitignore:28-31` | VERIFIED | No prueba rotación ni contenido real |
| SEC-A04 | Git | Secretos versionados de alta confianza | Escaneo de archivos tracked; solo conteos/nombres | 0 Slack webhooks, 0 AWS keys, 0 GitHub tokens, 0 private-key headers | escaneo local; archivos secretos locales excluidos/no leídos | VERIFIED | Evidencia acotada, no detector universal |
| SEC-A05 | Recovery | Secretos en argv | Revisión código | `PGPASSWORD` y SQL con recovery secret/email pueden incorporarse a command line | `scripts/recovery/*.py` | VERIFIED | Mantiene H04 ALTA |
| SEC-A06 | Provisioning | Password en archivo temporal | Revisión script + metadata | JSON escrito con password y sin cleanup; archivo presente | provisioning; INFRA-A03 | VERIFIED | Mantiene H06 ALTA |
| SEC-A07 | Cuentas | Variables secretas reales | Política de no lectura | PRESENTE/AUSENTE por variable dentro de `.env`: NO_VERIFICABLE sin abrir archivo | `.env` no leído | NOT_VERIFIED | Requiere Cristian sin compartir valores |

## 5. Git

| ID | Sistema | Requisito | Método | Resultado | Evidencia | Estado | Impacto en matriz |
|---|---|---|---|---|---|---|---|
| GIT-A01 | Git | Archivos sensibles tracked | `git ls-files` por nombres | Solo `.env.example` coincide; `.env`/`.local` no tracked | índice Git | VERIFIED | Ningún secreto real demostrado en Git |
| GIT-A02 | Git | Patrones sensibles | Escaneo de alta confianza sin imprimir contenido | Cero coincidencias | archivos tracked | VERIFIED | Alcance limitado a patrones definidos |
| GIT-A03 | Git | Estado de auditoría | `git status --short` | Solo directorio documental LF-003 untracked | Git | VERIFIED | Ningún archivo productivo modificado |

## 6. Evidencia manual consolidada

### HubSpot

| ID | Resultado | Evidencia incorporada | Consecuencia |
|---|---|---|---|
| HUBSPOT-V01 | PASS | Data hosting real: Estados Unidos (Este) | Ubicación de cuenta verificada |
| HUBSPOT-V02 | PASS | Service Key `Emactiva LeadFlow`; scopes únicamente Contacts read/write | Señal favorable de mínimo privilegio; no se registró la clave |
| HUBSPOT-V03 | PASS | Permisos visibles limitados a Contacts read/write | Sin scopes adicionales observados |
| HUBSPOT-V04 | PASS | Mappings efectivos confirmados para industry, website y company_size | Coinciden con defaults auditados |
| HUBSPOT-V05 | FAIL / observación | La opción para dejar de usar enriquecimiento gratuito de nombres de empresas está OFF | Existe procesamiento adicional; HubSpot no debe modelarse como CRM puro. No se declara incumplimiento legal |
| HUBSPOT-V06 | NOT_VERIFIED | DPA general verificado en 03A; no se encontró aceptación/configuración account-specific | Mantener pendiente contractual específico de cuenta |

### Hunter

| ID | Resultado | Evidencia incorporada | Consecuencia |
|---|---|---|---|
| HUNTER-V01 | PASS con observación | Plan Free, 50 créditos mensuales; UI indica que Lead enrichment no está incluido | Reconciliar capacidad del plan antes de operación real; no se declara fallo funcional sin prueba |
| HUNTER-V02 | PASS | Terms, DPA, Privacy, Cookies y Security Policy visibles | DPA aplicable disponible |
| HUNTER-V03 | PASS | Controles legales/privacidad y notificación de subprocesadores disponibles | Evidencia account-level favorable |
| HUNTER-V04 | WARN | Product & Analytics cookies ON; Advertising cookies ON | Afecta sitio/cuenta, no demuestra tratamiento adicional de la API LeadFlow |
| HUNTER-V05 | PASS con observaciones | API usage/logs 3 meses; User Input según Privacy Policy; Profile Data bajo Hunter Controller; Data Enrichment como Processor hasta eliminación de cuenta | Categorías se mantienen separadas; no se extrapola una a otra |
| HUNTER-V06 | PASS | Solo `/v2/combined/find` en la ruta auditada | No se observaron funciones Hunter adicionales |

Hunter usa AI/ML propio y OpenAI aparece para funciones opcionales. No hay evidencia de que la llamada LeadFlow `combined/find` envíe el email a OpenAI.

### Slack — corrección de atribución

Las capturas iniciales correspondían al workspace **Agrovista IA Rural**. Su plan, retención, canales, miembros, apps y configuración no son evidencia de LeadFlow y se excluyen de esta auditoría.

Comprobación local sanitizada: `SLACK_WEBHOOK_URL=PRESENTE_VACIA`, `ALERT_UPSTREAM_URL=AUSENTE`, `CONFIG_WIRED=SI`. Conclusión: Slack real **no configurado** para LeadFlow. SLACK-V01 a SLACK-V08 permanecen NOT_VERIFIED/no configurados; no existe workspace o canal LeadFlow operativo que permita atribuir evidencia account-level.

### Infraestructura — estados finales

| ID | Estado | Capa EDPB | Evidencia consolidada |
|---|---|---|---|
| INFRA-V01 | N/A / pendiente despliegue | ENVIRONMENT | No existe hosting productivo actual |
| INFRA-V02 | PENDIENTE DESPLIEGUE | ENVIRONMENT | TLS público se valida cuando exista exposición real |
| INFRA-V03 | WARN | HYBRID | PostgreSQL local/configuración inspeccionada usa `ssl=disable`; no implica exposición productiva |
| INFRA-V04 | NOT_VERIFIED | ENVIRONMENT | Cifrado host/volumen depende del futuro entorno |
| INFRA-V05–V08 | NOT_VERIFIED / capacidad insuficiente documentada | HYBRID | Sin política/configuración versionada suficiente de backup, retención, restore o eliminación; ejecución real dependerá del entorno |
| INFRA-V09 | WARN | HYBRID | Ledger estructurado y minimización parcial; event_id/source, stderr y configurabilidad mantienen riesgo |
| INFRA-V10 | FAIL | SYSTEM | Sin driver/opciones, max-size/max-file, logrotate, colector ni política de crecimiento |
| INFRA-V11 | WARN | HYBRID | Roles separados conceptualmente y grants mínimos; password reutilizado y runtime no verificado |
| INFRA-V12 | WARN | HYBRID | Loopback en desarrollo y puertos cerrados en producción; sin segmentación; firewall/proxy/TLS dependen del entorno |
| INFRA-V13 | WARN | HYBRID | Secretos fuera de Git y separación DB parcial; IAM/MFA/admin/break-glass pendientes |
| INFRA-V14 | FAIL | SYSTEM | Credencial temporal presente, ignorada por Git, no leída, persistente y con ACL heredada Modify para varios grupos/SID |
| INFRA-V15 | FAIL | SYSTEM | Sin cleanup en éxito/error/interrupción, sin finally ni mecanismo idempotente documentado |

H06 permanece **CONFIRMADO / ALTA** y queda reforzado por INFRA-V14/V15. No existe evidencia de exposición real ni se declara incidente.

## 7. Baseline EDPB v1.0

Durante 03B se incorporó como baseline complementario **EDPB v1.0 — Emactiva Deployment & Portability Baseline**, bajo el principio “Cambia el entorno, no el sistema”. EDPB no reemplaza EPB: EDPB regula preparación de despliegue y portabilidad; EPB regula privacidad y protección de datos.

- `SYSTEM`: capacidades inherentes al producto/configuración versionada; pueden cerrarse durante desarrollo.
- `ENVIRONMENT`: evidencia que solo existe con un despliegue real; queda post-deployment sin penalizar desarrollo por ausencia de entorno.
- `HYBRID`: requiere diseño portable y comprobación posterior en el entorno.

Gaps SYSTEM confirmados: rotación de logs, archivo temporal y cleanup. Gaps ENVIRONMENT pendientes: hosting, TLS público, cifrado at-rest, firewall/IAM efectivos. Gaps HYBRID: TLS DB, backups, roles efectivos, red y acceso administrativo.

## 8. Evidencia pendiente

- Ninguna declaración de Compose, SETUP o `.env.example` confirma el entorno desplegado.
- El contenido de `.env` y del JSON de credencial no fue leído; presencia no equivale a configuración correcta.
- Docker runtime no fue inspeccionado porque el daemon estaba apagado o inaccesible.
- HubSpot: aceptación/configuración contractual account-specific y análisis del enriquecimiento gratuito activo.
- Hunter: reconciliar plan Free con disponibilidad real de Lead enrichment antes de operación; no requiere llamada real en esta consolidación.
- Slack: no configurado; cualquier futura activación exige completar V01–V08 con el workspace correcto.
- Hosting, TLS, cifrado at-rest, backups, logs, red/firewall, IAM y accesos administrativos no son observables desde el repositorio.
- La consolidación solo cambia estados de matriz con evidencia inequívoca; los conteos finales se registran tras el recálculo automatizado.

## 9. CHECKLIST MANUAL — CRISTIAN (registro histórico ejecutado)

Responder cada ítem con `PASS`, `FAIL` o `NO_ENCONTRADO` y solo el dato expresamente pedido. No enviar tokens, API keys, passwords, cookies, webhook completo, connection strings, IDs sensibles ni capturas con credenciales.

### A. HubSpot — 6 ítems

| ID | Qué revisar | Dónde revisar | Copiar al chat | NO mostrar |
|---|---|---|---|---|
| HUBSPOT-V01 | Región/data hosting real | HubSpot Settings → Account Management → Data Hosting | Estado + solo nombre de región | Account ID, usuarios, tokens |
| HUBSPOT-V02 | Scopes reales de Private App/credencial | Settings → Integrations → Private Apps → app usada | Estado + nombres de scopes, sin token | Token, client secret |
| HUBSPOT-V03 | Permisos efectivos sobre Contacts | Private App scopes y permisos del usuario/rol operador | Estado + lectura/escritura permitidas sí/no | Usuarios/IDs innecesarios |
| HUBSPOT-V04 | Mappings efectivos de industry/company_size/website | Properties y configuración desplegada del Adapter | Estado + tres nombres de propiedad | Valores de contactos, secretos |
| HUBSPOT-V05 | Enrichment HubSpot, tracking u otras funciones que alteren rol | Settings de Data Management/Tracking/Enrichment y productos activos | Estado + lista de funciones relevantes activas/inactivas | Datos de titulares, IDs |
| HUBSPOT-V06 | DPA/términos aplicables | Legal/contract records o portal de cuenta | Estado + nombre/fecha/versión aplicable | Contrato completo si contiene datos sensibles |

### B. Hunter — 6 ítems

| ID | Qué revisar | Dónde revisar | Copiar al chat | NO mostrar |
|---|---|---|---|---|
| HUNTER-V01 | Plan/cuenta usada | Hunter Account/Billing | Estado + nombre de plan | Email de login, billing IDs |
| HUNTER-V02 | DPA/términos aplicables | Legal/account records | Estado + nombre/fecha/versión | Credenciales/contrato con datos sensibles |
| HUNTER-V03 | Controles de privacidad disponibles | Account/Privacy/Settings | Estado + nombres de controles | API key |
| HUNTER-V04 | Configuración de data usage/IA si existe | Account/Privacy/AI/Data settings | Estado + opciones y estado on/off | Datos de consultas |
| HUNTER-V05 | Retención del email/query para la cuenta/servicio | Terms/DPA/support/account documentation | Estado + plazo o “no encontrado” | Emails consultados, tickets sensibles |
| HUNTER-V06 | Función realmente usada | Configuración desplegada/observabilidad sanitizada | Estado + `combined/find` sí/no y otras funciones activas | URL con query/email, API key |

### C. Slack — 8 ítems

| ID | Qué revisar | Dónde revisar | Copiar al chat | NO mostrar |
|---|---|---|---|---|
| SLACK-V01 | Plan del workspace | Workspace Settings → Billing/Plan | Estado + plan | Billing/customer IDs |
| SLACK-V02 | Región/data residency | Organization/Workspace Settings → Data Residency | Estado + región o no disponible | Workspace ID innecesario |
| SLACK-V03 | Retención configurada | Settings → Message & File Retention | Estado + política/plazo | Mensajes reales |
| SLACK-V04 | Canal receptor | Configuración de incoming webhook/app | Estado + canal por alias no sensible | Webhook URL |
| SLACK-V05 | Miembros con acceso | Channel details → Members | Estado + conteo y categorías/roles | Nombres/emails si no son necesarios |
| SLACK-V06 | Apps/integraciones con acceso | Workspace Settings → Manage Apps | Estado + nombres de apps relevantes | Tokens, signing secrets |
| SLACK-V07 | Configuración IA/opt-in/opt-out | Admin/Organization Settings → AI/Privacy | Estado + opciones activas/inactivas | Contenido del workspace |
| SLACK-V08 | DPA/términos aplicables | Contract/legal/admin records | Estado + nombre/fecha/versión | Documento con firmas/datos sensibles |

### D. Infraestructura — 15 ítems

| ID | Estado inicial | Qué revisar | Dónde revisar | Copiar al chat | NO mostrar |
|---|---|---|---|---|---|
| INFRA-V01 | REQUIRES_USER | Hosting/región real | Consola/proveedor de hosting | Estado + proveedor y región | Account/project IDs |
| INFRA-V02 | REQUIRES_USER | TLS público efectivo | Reverse proxy/load balancer/DNS; inspección de certificado | Estado + protocolo/issuer/expiración | Private key, cookies |
| INFRA-V03 | REQUIRES_USER | TLS interno/DB efectivo | Config de red/PostgreSQL/n8n | Estado + sí/no por salto | Connection strings/passwords |
| INFRA-V04 | REQUIRES_USER | Cifrado at-rest host/volumen | Host/cloud disk settings | Estado + tecnología/servicio | Recovery keys |
| INFRA-V05 | REQUIRES_USER | Backups habilitados | Consola/backup jobs | Estado + sí/no y superficies | Backup contents/credentials |
| INFRA-V06 | REQUIRES_USER | Retención backups | Política/job | Estado + plazo | IDs/URLs firmadas |
| INFRA-V07 | REQUIRES_USER | Restore documentado/probado | Runbook/historial de pruebas | Estado + última fecha | Datos restaurados |
| INFRA-V08 | REQUIRES_USER | Eliminación backups | Política/operación | Estado + método/plazo | Credenciales |
| INFRA-V09 | REQUIRES_USER | Logs n8n/containers/host/proxy | Config de logging | Estado + superficies/destino | Contenido de logs |
| INFRA-V10 | REQUIRES_USER | Rotación de logs | Log driver/logrotate/SIEM | Estado + plazo/tamaño | Logs reales |
| INFRA-V11 | REQUIRES_USER | Usuarios/roles PostgreSQL efectivos | Administración DB | Estado + nombres de roles no sensibles y privilegios resumidos | Password hashes/secrets |
| INFRA-V12 | REQUIRES_USER | Firewall/red efectiva | Host/cloud firewall/Docker networks | Estado + puertos/orígenes resumidos | IPs privadas innecesarias |
| INFRA-V13 | REQUIRES_USER | Acceso administrativo | IAM/host/DB/n8n | Estado + roles y conteos | Nombres personales si no son necesarios |
| INFRA-V14 | PARTIAL | Permisos del archivo temporal | Propiedades/ACL del archivo local | Estado + si los grupos Modify observados son necesarios | Contenido del archivo |
| INFRA-V15 | PARTIAL | Cleanup posterior al provisioning | Runbook/automatización y archivo actual | Estado + política; confirmar si debe persistir | Password/JSON |

Resumen: checklist ejecutado/consolidado. Permanecen pendientes las evidencias expresamente clasificadas NOT_VERIFIED o post-deployment; no se reutilizó evidencia del workspace Agrovista para LeadFlow.
