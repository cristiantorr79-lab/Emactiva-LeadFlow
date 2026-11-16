# LF-M02 — Manual de operación y mantenimiento

**Versión documental:** 1.0 · 16/11/2026. **Estado:** edición consolidada para aprobación del responsable. No autoriza exposición comercial.

## 1. Alcance y responsabilidades

Este manual cubre la operación del sistema instalado, diagnóstico, recuperación funcional, privacidad y mantenimiento. Para instalación consultar M01; para restauración y custodia consultar M03; para usuarios de negocio consultar M04.

| Responsable | Función |
|---|---|
| Cliente / titular del entorno | Autorizar accesos, cambios, datos, ventanas, costos y decisiones de continuidad. |
| Administrador técnico | Verificar estado, ejecutar procedimientos autorizados y registrar evidencia sanitizada. |
| Responsable funcional | Confirmar procesamiento y resultados CRM sin reenviar eventos innecesariamente. |
| Responsable de privacidad y aprobador DSR | Verificar identidad, finalidad, alcance y aprobación independiente de acciones destructivas. |
| Emactiva | Soporte conforme al servicio contratado; escalar defectos SYSTEM y delimitar dependencias externas. |

## 2. Arquitectura operacional

Formulario HTTPS → Caddy → Rate Gate → Web Bridge → n8n Core → PostgreSQL y Adapters → HubSpot / Hunter / Slack. Turnstile protege la captación web. PostgreSQL es la autoridad de estados, idempotencia y recovery. No usar la recepción HTTP como prueba exclusiva del resultado en CRM.

| Proyecto Compose | Servicios de referencia | Estado esperado |
|---|---|---|
| Core | postgres, adapters, n8n | healthy (3) |
| Bridge | web-bridge | running; sin healthcheck en referencia |
| Gateway | rate gate, Caddy | running; sin healthcheck en referencia |

Los nombres efectivos son externos. Solo 443 se publica en la frontera de referencia. No publicar interfaces de administración, base de datos o adapters. Un estado running no prueba funcionalidad. Seis servicios es el inventario observado, no un requisito universal para futuras variantes.

## 3. Rutina de operación

| Frecuencia propuesta | Control | Evidencia mínima |
|---|---|---|
| Cada jornada operativa | Estado de servicios, reinicios, espacio, incidencias pendientes, antigüedad del respaldo | Fecha, conteos, estado y responsable |
| Semanal | Fallos/recovery, alertas, errores de proveedor, certificado y cuotas | Resumen de anomalías y acciones |
| Mensual | Accesos IAM, retención, capacidad, versiones y vigencia de custodia | Revisión autorizada y acciones asignadas |
| Después de cambio | Smoke test proporcional, comparación de servicios y rollback disponible | Resultado y versión desplegada |

Las frecuencias son recomendaciones operativas, no un SLA contratado ni evidencia de automatización existente. Si la VM está detenida por decisión autorizada, registrar estado y no interpretar ausencia de servicio como incidente imprevisto.

### Inspección de solo lectura (Linux)

Desde la raíz del repositorio aprobado, confirmar los tres proyectos reales mediante el inventario de Docker. No listar variables ni usar inspect completo. Ejecutar con permisos autorizados:

```bash
docker compose ls
docker ps -a --format '{{.Names}} {{.Status}} {{.Ports}}'
df -h
```

Comparar con el inventario de entrega. Confirmar pertenencia mediante labels selectivos y verificar reinicios por contenedor exacto:

```bash
docker inspect --format '{{.Name}} {{.RestartCount}} {{.State.Status}}' "$CONTAINER_ID"
```

La variable debe contener un ID verificado. Estos comandos son ejemplos operacionales de lectura; no constituyen una nueva ejecución sobre el entorno. No publicar salidas sin revisar identificadores y rutas sensibles.

## 4. Inicio y detención segura

Antes de iniciar: confirmar autorización, checkout aprobado, mapas externos protegidos, identidad runtime, red y disponibilidad de imágenes. Usar cargadores seguros de M01; no arrancar con credenciales bootstrap. Preflight no inicia servicios. Aplicar Core, después Bridge y finalmente Gateway. El aprovisionador n8n tiene H04/H05 PASS SYSTEM reportado y validación ambiental pendiente; no utilizarlo como procedimiento aprobado de modificación de instalaciones existentes.

Para detener: acordar ventana, impedir nuevas entradas por la frontera autorizada, reconciliar trabajo en curso, comprobar respaldos y detener Gateway, Bridge y Core en ese orden mediante procedimientos de proyecto específicos. No detener PostgreSQL mientras haya recuperación o respaldo activo. No improvisar una regla de firewall ni eliminar contenedores/volúmenes para detenerlos. `docker compose down -v` está prohibido en operación normal. Los cargadores solo ofrecen preflight/start. Para una parada controlada se pueden usar IDs exactos previamente verificados por labels, con `docker stop "$CONTAINER_ID"` por servicio, en el orden indicado; dentro de Core detener n8n, adapters y luego PostgreSQL tras comprobar quiescencia. No usar identificadores genéricos ni el comando con una lista no revisada. Esta secuencia queda como procedimiento de destino sujeto a validación HYBRID/ENVIRONMENT (D1-H07).

Al reanudar: comprobar inventario, health, reinicios, certificados y conectividad; ejecutar únicamente el smoke test acordado. Si falla un control crítico, mantener cerrada la frontera y escalar el primer fallo real.

## 5. Trazabilidad, estados y alertas

| Estado | Interpretación / acción |
|---|---|
| received | Recepción registrada; aún no acredita éxito. |
| processing | Ejecución en curso o pendiente de recovery. Revisar etapa y antigüedad. |
| retrying | Reintento transitorio; no iniciar otro manual sin reconciliar. |
| duplicate | Evento ya reclamado; consultar ejecución original. No equivale a success. |
| success | Procesamiento terminal exitoso según Core; contrastar CRM si corresponde. |
| failed | Fallo terminal; diagnosticar etapa y código antes de decidir recuperación. |

El HTTP 202 público indica aceptación genérica, no éxito comercial. Los estados del Core no deben exponerse al público con detalles internos. Registrar execution_id técnico, etapa, error_type/error_code sanitizados, timestamp UTC y responsable. No conservar payload, email, nombre, teléfono, tokens, cabeceras o stack traces en evidencias.

Slack directo Adapter→Slack fue comprobado en LF015. Alerta automática de fallo del Core y notificaciones nativas HubSpot permanecen NOT_VERIFIED. No depender exclusivamente de ellas; mantener revisión operacional manual hasta acreditarlas.

## 6. Diagnóstico y recuperación funcional

| Síntoma | Primera comprobación | Acción segura |
|---|---|---|
| 400 / 413 en frontera | Contrato, tipo y tamaño de entrada | Corregir origen de datos; no reintentar sin cambios. |
| 401 / 403 | Autorización, origen permitido, Turnstile | Verificar configuración y permisos; no desactivar controles. |
| 429 | Ventana y cuota; Retry-After si existe | Esperar ventana autorizada; considerar NAT. |
| 502 / 503 | Etapa, health, dependencia y conectividad | Distinguir fallo transitorio de definitivo. |
| Contacto / interacción ambiguos | Ejecución original y checkpoint CRM | Reconciliar antes de repetir CREATE. |
| PostgreSQL indisponible | Estado, disco, conectividad, roles | Fail-closed; no reenviar ni modificar tablas a mano. |
| Certificado vencido / inválido | Vigencia, confianza, firewall y TLS-ALPN | Mantener frontera cerrada; no omitir validación TLS. |

Recovery conserva la ejecución original y su idempotency_key. La interacción se reconcilia por la clave de interacción derivada. No volver a ejecutar todo el workflow ni generar otro event_id para el mismo intento. Los scripts `scripts/recovery/reconcile_crm.py` y `scripts/recovery/continue_recovery.py` son herramientas existentes; ambos reciben `execution_id` y `worker_id` de una ejecución original ya arrendada al worker autorizado. La reconciliación CRM precede a la continuación cuando lo exige el checkpoint. No inventar un lease ni invocar si no se ha comprobado su propiedad. Consultar los contratos y scripts de la versión instalada antes de ejecutar. La antigüedad máxima sin progreso es 604800 segundos (7 días); la expiración termina en failed/recovery_expired. No forzar terminalización mediante SQL directo.

## 7. Retención y privacidad

| Superficie | Política inicial |
|---|---|
| success / duplicate | 90 días desde finished_at |
| failed | 180 días desde finished_at |
| processing/recovery sin progreso | Máximo 7 días; terminalizar antes de aplicar retención failed |
| Evidencia mínima de purga | 180 días |
| Backups GCS | 30 días + 7 de soft delete según entorno de referencia |

`leadflow.purge_retained_data` ejecuta purga por lotes, coordinada con eventos y recovery. Un hold requiere motivo, owner, aprobador y revisión acotada; no hay hold global indefinido. Existe `scripts/database/purge_retention.ps1`; el procedimiento Linux seguro y programación efectiva deben verificarse antes de habilitar purga periódica. No ejecutar DELETE directo ni ampliar retención por conveniencia.

### Derechos de titulares (DSR)

1. Recibir por canal autorizado; verificar identidad y alcance fuera del webhook público.
2. Registrar request_id técnico y responsable. LOCATE, EXPORT y ANNOTATE se limitan a superficies autorizadas; no confundir anotación con corrección efectiva del dato en el proveedor.
3. DELETE y RESTRICT exigen aprobador independiente. No actuar ante hold o ambigüedad sin resolver.
4. Utilizar interfaz administrativa `scripts/admin/dsr_admin.py` según contrato vigente; entrada por stdin, credenciales administrativas separadas. No incorporar datos del titular en argumentos, tickets o logs.
5. Conciliar PostgreSQL y acciones externas; resultado partial no se comunica como completo. HubSpot archivado no implica eliminación física; enforcement externo RESTRICT no acreditado.
6. Confirmar protección frente a restore por autoridad DSR independiente. staged o pending_confirmation no equivalen a protected. Un fallo de publicación se recupera con `scripts/admin/retry_dsr_restore_protection.py` sobre el request_id autorizado, sin repetir DELETE/RESTRICT.

Custodiar evidencia mínima de decisión y alcance. No exponer subject_token o lead_identifier en reportes ordinarios. La duración legal del tombstone debe acordarse con el responsable de privacidad; conservar protección mientras exista riesgo de restauración o restricción vigente.

## 8. Respaldos, mantenimiento y cambios

Objetivos: backup cada 24 h, RPO 24 h y RTO 8 h. Son objetivos, no SLA demostrado. El timer systemd se instala con `scripts/backup/install_schedule.sh`, pero no se habilita automáticamente. Verificar activación autorizada, resultado, antigüedad e integridad mediante las identidades de M03. No ampliar permisos del escritor para comprobar una copia. Ante ausencia o fallo de respaldo, detener cambios de riesgo y escalar.

Antes de actualizar: fijar versión y digests aprobados, revisar impacto, snapshot/backup recuperable, ventana y rollback. No modificar Core para adaptar un dominio; configurar las tres allowlists externas, Site Key y ambos preflight según M01. Usar orígenes HTTPS canónicos sin puerto 443 explícito; preservar clave de evento web y clave de cifrado n8n. Rotar secretos según política y exposición, con transición coordinada y conservación de claves necesarias para restore. La rotación integral no está validada.

## 9. Escalamiento y registro de incidente

| Campo | Contenido |
|---|---|
| Incidente | ID técnico, UTC, versión, proyecto autorizado |
| Impacto | Servicios afectados, estado funcional, alcance de datos sin PII |
| Diagnóstico | Primer fallo real, etapa, código, evidencia mínima |
| Acción | Responsable, autorización, cambio, rollback y resultado |
| Cierre | PASS / WARN / FAIL / NOT_VERIFIED, pendientes y seguimiento |

Escalar al responsable de infraestructura los fallos ENVIRONMENT (IAM, red, disco, TLS, cuotas); a Emactiva los defectos SYSTEM; coordinar controles HYBRID. Si se sospecha exposición de secretos o datos, restringir acceso, preservar evidencia mínima y activar el procedimiento de incidentes del titular. No prometer plazos de soporte no contratados.

## 10. Gate operacional y pendientes

| Control | Estado de referencia |
|---|---|
| Seis servicios y cleanup LF015 | PASS histórico, no monitoreo sostenido |
| Backup cifrado y restore aislado | PASS histórico acotado; RPO/RTO sostenidos NOT_VERIFIED |
| TLS automático / renovación y recuperación ante pérdida total | NOT_VERIFIED |
| Purga programada y detención segura integral | NOT_VERIFIED en destino |
| Aprovisionamiento Linux n8n | H04/H05 PASS SYSTEM reportado; ejecución real NOT_VERIFIED |
| Alertas automáticas, enriquecimiento real y RESTRICT externo | NOT_VERIFIED |
| Prueba independiente de este manual | NOT_VERIFIED |

Fuentes de trabajo: docs/architecture/CONTRACTS.md, docs/setup/SETUP.md, docs/runbooks/BACKUP_RESTORE.md, LAB-LF-006/LEADFLOW_REMOTE_DEPLOYMENT_RUNBOOK.md y HANDOFF LAB-LF-015, cierre LF015-T03. Baselines EWB, EPB, EDPB y EQAB v1.0. La edición debe asociarse al commit autorizado de entrega. La reproducción independiente y los controles ambientales deben acreditarse antes de aceptar la operación en un destino nuevo.
