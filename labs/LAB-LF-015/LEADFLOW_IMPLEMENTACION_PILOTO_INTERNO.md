# LeadFlow — Ficha de implementación del piloto interno Emactiva

Documento específico de LF015-T02. No contiene secretos ni autoriza deployment.

## 1. Identificación y autoridad

| Campo | Valor |
|---|---|
| Cliente funcional | Emactiva |
| Responsable funcional | Emactiva, función de cliente interno |
| Responsable de implementación | Emactiva, función de proveedor/implementador |
| Modalidad | B — Implementado por Emactiva |
| Clasificación | STANDARD/CORE para EVENT/LEAD/INTERACTION; CONFIGURATION/INTEGRATION para formulario, HubSpot y entorno |
| CRM | HubSpot |
| Datos autorizados | Exclusivamente sintéticos |
| Entorno candidato | Google Cloud existente; deployment no autorizado |
| Producción pública | No autorizada |

Las aprobaciones funcionales y técnicas deben quedar separadas aunque las funciones recaigan en Emactiva.

## 2. Objetivo, alcance y aceptación

El piloto debe demostrar en un entorno autorizado el flujo EVENT → LEAD → INTERACTION con HubSpot, idempotencia ante duplicado exacto, persistencia recuperable y operación sin exponer datos o secretos. La landing pública pertenece a LAB-EWEB-000 y no forma parte de LF015.

La aceptación funcional del deployment queda en LF015-T03 (#17). Requiere contacto nuevo/primera interacción, mismo contacto/nueva consulta, duplicate exacto sin efectos externos adicionales, visibilidad mínima de datos, logs sanitizados y cleanup/DSR del provider documentados.

Exclusiones: datos reales, exposición pública, desarrollo de Core, CRM propio, canales adicionales, automatizaciones comerciales nuevas, soporte 24/7, mantenimiento mensual y monitoreo permanente.

## 3. Datos, privacidad y operación

- Interfaz prevista: nombre, email, servicio de interés y mensaje obligatorios; apellido, empresa y teléfono/WhatsApp opcionales. La configuración end-to-end permanece pendiente de #17.
- Finalidad: responder consultas comerciales con revisión humana.
- Operación objetivo: lunes a viernes 09:00–18:00 America/Santiago, excluidos feriados; respuesta interna objetivo de cuatro horas hábiles.
- Aviso inicial: correo Google; correo corporativo posterior. Priorizar capacidad nativa de HubSpot, aún `NOT_VERIFIED`.
- HubSpot es tercero/proveedor candidato. Retención, DSR externo y eliminación física permanecen limitados por su capacidad y por las decisiones administrativas aplicables.
- No colocar claves webhook, tokens, credenciales ni PII en Git, logs, issues o esta ficha.

## 4. Inventario, propietarios y costos

| Recurso o dependencia | Situación | Propietario/responsable | Costo | Estado |
|---|---|---|---|---|
| LeadFlow Core, PostgreSQL y n8n | Componentes existentes; QA técnico disponible | Emactiva implementación | Incluido en referencia comercial | PASS para preparación |
| VM Google Cloud candidata | Existente, devuelta a identidad original y detenida | Emactiva infraestructura | Costo real del piloto no medido | PASS histórico / uso futuro no autorizado |
| Bucket de backups | Existente; backup cifrado y checksum verificados | Emactiva infraestructura | Pendiente de medición | PASS QA |
| Bucket DSR independiente | Existente para evidencia QA | Administración DSR de Emactiva | Pendiente de medición | PASS QA; producción NOT_VERIFIED |
| HubSpot Emactiva | Cuenta candidata; capacidad, permisos y limpieza del portal por verificar | Emactiva función cliente/CRM | Licencias/costos externos pendientes | NOT_VERIFIED |
| Formulario/puente seguro | Solución concreta pendiente; landing fuera de LF015 | Emactiva implementación + EWEB-000 | Pendiente | NOT_VERIFIED — HIGH |
| TLS, dominio y DNS | No definidos para este deployment | Emactiva infraestructura | Pendiente | NOT_VERIFIED — CRITICAL |
| Firewall/red pública y mitigación de abuso | No seleccionados/verificados | Emactiva infraestructura/seguridad | Pendiente | NOT_VERIFIED — CRITICAL |
| Secretos de runtime | Deben provenir de gestor externo y estar separados por entorno | Emactiva infraestructura/seguridad | Pendiente | NOT_VERIFIED — CRITICAL |
| Monitoreo, alertas e incidentes | No definidos para el piloto remoto | Emactiva operación | Pendiente | NOT_VERIFIED — HIGH |

Los costos externos, licencias y suscripciones corresponden al cliente salvo acuerdo específico. No se inventan importes ni se interpreta el precio comercial como costo real.

## 5. Accesos y responsabilidades

| Acceso | Finalidad mínima | Responsable | Situación | Revocación |
|---|---|---|---|---|
| Google Cloud | Preflight y deployment autorizado | Emactiva infraestructura | Pendiente para #17 | Obligatoria al finalizar |
| Identidad backup | Escritura create-only de backup | Emactiva infraestructura | Restaurada tras QA | Permanente según operación aprobada |
| Escritor DSR | Crear evidencia cifrada | Emactiva DSR | Diseño/QA existente | Según operación aprobada |
| Administrador DSR | Reconciliar evidencia y generar bundle | Emactiva DSR/privacidad | QA limitada | Temporal o administrada |
| Restaurador | Lectura de objetos exactos y restore aislado | Emactiva recuperación | Uso temporal QA finalizado | Revocada/retirada tras QA |
| HubSpot | Validar integración y cleanup sintético | Emactiva función cliente | Pendiente | Temporal y mínimo privilegio |
| DNS/TLS | Configuración de endpoint autorizado | Emactiva infraestructura | No entregado | Temporal cuando aplique |

Mecanismo de secretos: custodia administrativa en Bitwarden; desarrollo mediante archivos externos a Git; producción mediante gestor de secretos e identidades administradas. No se autorizan claves JSON descargadas.

## 6. Configuración pendiente

No se fijan aquí valores de `PUBLIC_WEBHOOK_HOST`, allowlists, pipeline/stage de HubSpot, URLs upstream, timeouts, retenciones ni límites de reintento. Deben obtenerse del entorno autorizado y validarse en #17. Los valores históricos de otro portal no son universales.

## 7. Preflight de LF015-T02

| Control | Capa | Estado | Severidad para #17 | Evidencia o bloqueo |
|---|---|---|---|---|
| Alcance, modalidad y responsables | HYBRID | PASS | — | Piloto interno, modalidad B y funciones diferenciadas documentadas. |
| Separación dev/test/restore/producción | HYBRID | PASS | — | QA y restore usaron proyectos, red y volúmenes exclusivos; producción no está creada. |
| Autorización de ventana de deployment | ENVIRONMENT | NOT_VERIFIED | CRITICAL | No existe autorización de deployment público ni ventana aprobada. |
| IAM de runtime remoto | ENVIRONMENT | NOT_VERIFIED | CRITICAL | QA verificó identidades temporales y revocación; permisos definitivos no están aprobados. |
| Red y firewall remotos | ENVIRONMENT | NOT_VERIFIED | CRITICAL | No se verificó exposición del piloto remoto. |
| TLS, dominio y DNS | ENVIRONMENT | NOT_VERIFIED | CRITICAL | No configurados ni validados. |
| Puertos del restore QA | ENVIRONMENT | PASS | — | Sin puertos publicados; red interna independiente. |
| Secretos externos y separación por entorno | HYBRID | NOT_VERIFIED | CRITICAL | Patrón definido; disponibilidad/configuración real pendiente. |
| Rotación y revocación | HYBRID | WARN | HIGH | IAM temporal QA fue revocado; rotación completa de secretos de #17 pendiente. |
| PostgreSQL y migraciones | SYSTEM/ENVIRONMENT | PASS | — | PostgreSQL 17.6 QA con 24/24 migraciones; restore aislado PASS. No repetir salvo cambio/riesgo. |
| n8n | SYSTEM/ENVIRONMENT | PASS | — | n8n 2.28.6 healthy en restore QA; workflows de negocio no ejecutados. |
| Adapters y operaciones permitidas | HYBRID | NOT_VERIFIED | HIGH | Configuración concreta de #17 pendiente. |
| HubSpot y permisos CRM | ENVIRONMENT | NOT_VERIFIED | CRITICAL | Portal candidato; permisos, capacidades, pipeline/stage y cleanup por validar. |
| EVENT/LEAD/INTERACTION e idempotencia | SYSTEM | PASS | — | PASS histórico reutilizable; validación funcional contra HubSpot queda en #17. |
| Aviso email nativo | ENVIRONMENT | NOT_VERIFIED | HIGH | Viabilidad/configuración HubSpot pendiente. |
| Formulario y puente seguro | HYBRID | NOT_VERIFIED | CRITICAL | Arquitectura concreta pendiente; no exponer webhook directamente. |
| Spam, bots y rate limiting | HYBRID | NOT_VERIFIED | CRITICAL | No hay control seleccionado/verificado para superficie pública. |
| Tamaño y validación de payload | SYSTEM/HYBRID | NOT_VERIFIED | HIGH | Debe probarse focalizadamente en GATE-PILOT. |
| Sanitización de logs/errores | SYSTEM/HYBRID | NOT_VERIFIED | HIGH | Requisitos definidos; ruta desplegada aún no validada. |
| Privacidad y minimización | HYBRID | WARN | HIGH | Datos sintéticos y minimización DSR QA; responsabilidades productivas/HubSpot requieren control continuo. |
| Retención y DSR global | HYBRID/ENVIRONMENT | NOT_VERIFIED | CRITICAL | Autoridad QA fue `synthetic_closed_set`; no certifica producción. |
| Backup cifrado y checksum | SYSTEM/ENVIRONMENT | PASS | — | Backup real QA cifrado en GCS y checksum verificado. |
| Restore aislado | SYSTEM/ENVIRONMENT | PASS | — | PostgreSQL/n8n restaurados; terminó `traffic=DISABLED`. No certifica producción. |
| Rollback/recuperación | SYSTEM/HYBRID | PASS | — | Estado durable y `RECOVERABLE_FAILURE` ejercitados; reintento controlado PASS. |
| Cleanup QA | HYBRID/ENVIRONMENT | PASS | — | Recursos restore, archivos/claves temporales e IAM temporal eliminados/revocados; registros durables conservados. |
| Monitoreo y alertas | ENVIRONMENT | NOT_VERIFIED | HIGH | No definidos para #17. |
| Respuesta a incidentes | HYBRID | NOT_VERIFIED | HIGH | Responsables y procedimiento operativo pendientes. |
| RPO/RTO medidos | HYBRID/ENVIRONMENT | NOT_VERIFIED | HIGH | 24 h/8 h permanecen objetivos, no mediciones. |

**Resultado:** `BLOCKED FOR DEPLOYMENT`. LF015-T02 documenta los bloqueos y no autoriza implementación. No existe FAIL técnico que invalide la preparación ya demostrada; los controles CRITICAL `NOT_VERIFIED` impiden iniciar #17.

## 8. Backup, restore, rollback y cleanup

- Backup lógico PostgreSQL y volumen n8n durante pausa controlada, cifrado AES-256-GCM y checksum: PASS QA.
- Restore PostgreSQL/n8n aislado: PASS QA. Primer intento `RECOVERABLE_FAILURE` por variables no exportadas antes de `pg_restore`; reintento controlado PASS.
- Estado final del restore: `phase=complete`, `status=PASS`, `traffic=DISABLED`.
- DSR: autoridad y bundle independientes para conjunto QA de cero eventos. Cobertura global y replay posterior al backup permanecen `NOT_VERIFIED`.
- Cleanup final: recursos `lf015-restore`, claves/temporales Cloud Shell/VM e IAM temporal eliminados; VM con identidad original y `TERMINATED`; dos registros durables de restore conservados.

## 9. Planificación, costos y tiempos

| Concepto | Valor | Naturaleza |
|---|---|---|
| Precio comercial modalidad B | $1.200.000 CLP netos | Referencia aprobada LF014; sin facturación interna |
| Costo real del piloto | Pendiente de medición | No inferido del precio comercial |
| Implementación | 36 horas | Estimación LF014, no tiempo real |
| Reserva interna de soporte | 4 horas | Estimación LF014, no límite de responsabilidad |
| Plazo comercial | 5 días hábiles | Condicionado a requisitos y preflight aprobado |
| Soporte inicial | 10 días hábiles | Condición comercial aprobada |
| Duraciones reales de T02 | No consolidadas | No inventar; RPO/RTO no medidos |
| Impuesto | Pendiente de verificación | No usar como valor tributario definitivo |
| Costos GCP/HubSpot/terceros | Pendientes de medición/verificación | Externos; a cargo del cliente salvo acuerdo |

Ventana de implementación: pendiente de autorización independiente para #17.

## 10. Fricciones y hallazgos de T02

1. El recorrido de migraciones podía truncarse por consumo de stdin; se corrigió y pasó la regresión focalizada.
2. Sustitución de variables `psql` mediante `-c` falló en Debian; se cambió a stdin seguro.
3. PostgreSQL concatenó booleano como `true` mientras el probe esperaba `t`; se normalizó explícitamente.
4. La identidad backup write-only no podía depender de operaciones de lectura; se implementó subida compatible con create-only.
5. La autoridad DSR requirió fuente independiente, secuencia y cobertura explícitas; producción global sigue fuera de evidencia.
6. El primer restore no recibió dos variables presentes en `.env` pero no exportadas; el fallo fue recuperable antes de `pg_restore` y el reintento fue exitoso.
7. La separación de identidades y la limpieza final añadieron coordinación operativa; no se midió su duración total.

## 11. Continuidad LF015-T03 (#17)

Antes de deployment se requiere: autorización y ventana; preflight remoto sin bloqueos CRITICAL; secretos externos; TLS/red/firewall/IAM; HubSpot y notificación; formulario/abuso/rate limiting; sanitización; monitoreo/incidentes; y plan de cleanup del CRM.

Primera acción: seleccionar y documentar la arquitectura del endpoint/formulario y sus controles de exposición. Después completar el preflight remoto y solicitar autorización independiente. No reutilizar el PASS QA como autorización productiva.
