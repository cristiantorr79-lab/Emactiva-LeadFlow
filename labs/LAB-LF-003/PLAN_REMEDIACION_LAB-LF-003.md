# LAB-LF-003 — Plan formal de remediación

Fecha: 2026-09-27. Baseline técnico: `91aea95c05467b9d006832cb4816887c06b40644`.

Estado: **DESARROLLO CERRADO — FASES R2 A R6 COMPLETADAS; DEPLOYMENT-READY, NO DEPLOYED**.

Este documento ordena las remediaciones demostradas por las Tareas 01, 02, 03A y 03B. No cambia estados, conteos, gates ni conclusiones de `MATRIZ_GAP_EPB_V1.md`; tampoco reabre LAB-LF-002. EPB v1.0 regula privacidad y protección de datos. EDPB v1.0 regula preparación para despliegue y portabilidad bajo el principio “Cambia el entorno, no el sistema”.

Fuentes: `INVENTARIO_TAREA_01.md`, `AUDITORIA_TERCEROS_TAREA_03A.md`, `EVIDENCIA_OPERATIVA_TAREA_03B.md`, `MATRIZ_GAP_EPB_V1.md`, `HANDOFF_LAB-LF-003.md`, `docs/architecture/ARCHITECTURE.md`, `docs/architecture/CONTRACTS.md`, `<EMACTIVA_ROOT>\00_CORPORATIVO\PRIVACIDAD_Y_DATOS\EPB_v1.0.md` y EDPB v1.0 corporativo.

## 1. Reglas de clasificación y prioridad

| Capa | Criterio |
|---|---|
| SYSTEM | Se resuelve y prueba durante desarrollo sin infraestructura real. |
| HYBRID | Tiene una parte implementable durante desarrollo y otra que debe verificarse en el entorno real. |
| ENVIRONMENT | Solo puede comprobarse con hosting, cuentas o infraestructura concreta. |
| DOCUMENTAL/OPERATIVA | Requiere decisiones, procedimientos, registros, responsabilidades o evidencia no codificable. |

| Prioridad | Criterio |
|---|---|
| P0 — BLOQUEANTE | Impide el cierre funcional/privacidad o deja un FAIL bloqueante de sistema. |
| P1 — ALTA | Debe resolverse antes de producción después de los P0. |
| P2 — MEDIA | Hardening o riesgo residual material. |
| P3 — POST-DEPLOYMENT | Solo se verifica con cuentas o infraestructura reales. |

Un `NOT_VERIFIED` puramente ambiental no se convierte en FAIL de desarrollo. Ninguna acción de este plan presume un PASS futuro.

## 2. Registro de acciones

La columna “Orden” es el orden secuencial recomendado. “Componentes” identifica superficies probablemente afectadas en una implementación futura; no autoriza su modificación en esta tarea.

| ID | Pri. | Capa | Fase | Controles EPB/EDPB | H | Problema y remediación propuesta | Componentes probables | Dependencias | Criterio de aceptación | Pruebas necesarias | Riesgo de regresión | Orden |
|---|---|---|---|---|---|---|---|---|---|---|---|---:|
| REM-01 | P0 | DOCUMENTAL/OPERATIVA | R1 | EPB-P07, EPB-LC12, EPB-RET01–13, EDPB-05-02 | H02,H07 | No existe una matriz general de retención. Aprobar una matriz versionada por dato/superficie con trigger, plazo, excepción, método, owner y evidencia. | Documento nuevo de retención; referencias en arquitectura/operación | Ninguna | Todas las superficies tienen regla aprobada o justificación explícita; no se inventa base jurídica de un cliente | Revisión de cobertura y consistencia contra inventario | Un plazo incorrecto puede causar borrado prematuro o conservación excesiva | 1 |
| REM-02 | P0 | DOCUMENTAL/OPERATIVA | R1 | EPB-P02,P03, EPB-LC02,LC04,LC05,LC11,LC16 | H01,H05,H08,H10 | Faltan categorías de titulares, finalidad y necesidad campo a campo. Definirlas, incluidos usos y límites de `event_id`, `source`, enrichment y datos D2/D3. | Matriz de finalidad/necesidad; contratos y arquitectura | REM-01 en paralelo permitido | Cada campo y salida tiene finalidad técnica, necesidad, categoría, prohibiciones y owner; datos de cliente quedan como input preproducción | PRIV-T01 diseñada; revisión de campos y casos negativos | Una minimización mal definida puede romper idempotencia, CRM o trazabilidad | 2 |
| REM-03 | P0 | DOCUMENTAL/OPERATIVA | R1 | EPB-P10, EPB-ARCH06, EPB-IMP15, EPB-DSR*, Gate PRIV-ARCH | H02,H07,H08 | No hay definición integral de derechos. Definir localizar, exportar, corregir/anotar, eliminar y restringir en PostgreSQL, HubSpot, Hunter, Slack si se activa, logs y backups, con identidad, autorización y excepciones. | Especificación DSR y mapa de superficies | REM-01, REM-02 | Flujo, inputs, outputs, responsables, evidencias, excepciones y coordinación por superficie aprobados | Casos de prueba PRIV-T02,T03,T05,T06,T07 especificados | Borrado incompleto, sobreborrado o divulgación al solicitante equivocado | 3 |
| REM-04 | P1 | DOCUMENTAL/OPERATIVA | R1 | EPB-P01,P05,P13, EPB-LC07,LC09,LC10 | — | Rol, jurisdicción, base aplicable, avisos, volumen y DPIA dependen del cliente. Crear checklist obligatorio de entrada a producción sin fijar una respuesta para un cliente inexistente. | Checklist de onboarding y decisión DPIA | REM-02, REM-03 | Se distingue lo definido por producto de lo que debe entregar/aprobar cada cliente antes de operar | Revisión documental por escenario | Una plantilla incompleta puede permitir producción sin decisión jurídica | 4 |
| REM-05 | P0 | SYSTEM | R2 | EPB-IMP01, EPB-ARCH09; EDPB-03-01,03-02,03-05 | H06 | La credencial temporal puede persistir y hereda ACL amplia. Eliminar el archivo persistente si es razonable; si es transitorio, crear con ACL mínima, cleanup en éxito/error/interrupción y operación idempotente. | `scripts/n8n/provision_n8n.ps1`, mecanismo de credenciales, tests | R1 puede continuar en paralelo | Ninguna credencial temporal queda tras toda salida; creación y limpieza son idempotentes; permisos mínimos comprobados sin leer valores | Casos éxito, error, cancelación, repetición y ACL | Puede impedir el provisioning o borrar un artefacto aún requerido | 5 |
| REM-06 | P1 | HYBRID | R2 | EPB-IMP02,IMP06; EDPB-03-03,08-05 | H06 | Compose reutiliza un password para migrator y app. Separar identidades/secretos y conservar mínimo privilegio; verificar grants efectivos después del despliegue. | `compose*.yaml`, `.env.example`, scripts DB, documentación | REM-05; modelo de roles aprobado | Desarrollo usa variables distintas y roles mínimos; verificación runtime queda registrada como ENVIRONMENT | Pruebas de migración, conexión app y denegación de privilegios; revisión post-deployment | Puede romper migraciones o acceso legítimo del runtime | 6 |
| REM-07 | P0 | SYSTEM | R2 | EPB-P09, EPB-IMP08,IMP10,IMP11; EDPB-03-05 | H04,H06 | Recovery expone email/secretos mediante argv/comandos observables y puede propagar stderr. Sustituir el canal por entrada segura y sanitizar errores/trazas con mensajes canónicos. | `scripts/recovery/*.py`, invocación `psql`, manejo de excepciones | REM-05 | Ningún secreto, email, URL sensible o payload aparece en argv, stderr o excepción; errores siguen siendo diagnosticables | Canarios sintéticos en argv/stdout/stderr, fallo SQL/HTTP y stack traces | Puede ocultar diagnóstico útil o romper recovery | 7 |
| REM-08 | P0 | HYBRID | R2 | EPB-IMP04,IMP05,ARCH04,ARCH05; EDPB-06-01,06-05,08-05 | H03 | El Adapter interno no autentica ni autoriza clientes. Diseñar identidad service-to-service portable, autorización por operación y defensa de red; comprobar identidad/red efectivas al desplegar. | `adapters/server.py`, workflow, Compose/red, contratos | REM-06; contrato de identidad | Requests sin identidad o sin permiso se rechazan; core usa identidad mínima; configuración cambia por entorno sin cambiar el contrato funcional | PRIV-T02,T03; replay, credencial inválida, operación no autorizada, indisponibilidad | Puede bloquear llamadas legítimas o alterar contratos internos | 8 |
| REM-09 | P0 | SYSTEM | R2 | EPB-P03, EPB-IMP03,IMP08,IMP11,IMP14 | H01,H07 | `event_id` y `source` aceptan contenido que puede ser PII. Elegir y documentar validación, normalización o seudonimización compatible con idempotencia y migración. | Workflow, funciones SQL/migración, contratos, tests | REM-02 | Valores fuera de política no persisten en claro; duplicados e idempotencia conservan semántica; compatibilidad/migración definida | PRIV-T01,T04; límites, Unicode, email canario, duplicados y recovery | Alto: puede romper deduplicación, claves existentes y soporte operativo | 9 |
| REM-10 | P0 | SYSTEM | R2 | EPB-IMP10,IMP13,IMP14; EDPB-05-03,06-05 | H09,H02 | Interrupciones pueden dejar executions/recovery en `processing`. Definir estados terminales, lease/timeout, reconciliación idempotente y política segura de abandono/reintento. | Migraciones SQL, recovery, workflow, tests | REM-01 para plazo; REM-07 | Toda ruta llega a estado terminal o a una cola recuperable acotada; reejecución no duplica efectos | Fallos en cada etapa, kill/interrupción, lease vencido, doble worker y restart | Puede marcar fallos prematuros o repetir escrituras a terceros | 10 |
| REM-11 | P2 | SYSTEM | R2 | EPB-IMP03,IMP10,IMP11; EDPB-06-04,06-05 | H03,H05,H10 | Códigos/IDs/URLs y valores de enrichment no tienen control homogéneo. Aplicar allowlists, esquemas, límites y normalización en fronteras sin guardar respuestas completas. | `adapters/server.py`, workflow, contratos, tests | REM-08, REM-09 | `error_code`, IDs, website y enrichment solo aceptan formas previstas; errores desconocidos se vuelven canónicos | Fuzz/boundary tests y respuestas anómalas de proveedor | Puede rechazar datos válidos o cambiar clasificación de retries | 11 |
| REM-12 | P0 | SYSTEM | R3 | EPB-P07,LC12,ARCH06,IMP15,RET01–13; EDPB-05-02 | H02,H07,H09 | Ledger, eventos y recovery carecen de cleanup general. Implementar purga auditable y segura conforme a la matriz, incluyendo estados estancados y dependencias referenciales. | Nuevas migraciones/funciones, job operacional, documentación | REM-01, REM-09, REM-10 | Purga respeta triggers/plazos/excepciones, es idempotente, registra conteos no personales y no rompe integridad | PRIV-T05; límites temporales, cascadas, hold/excepción, retry y rollback | Borrado prematuro, locks, pérdida de auditoría o crecimiento persistente | 12 |
| REM-13 | P0 | SYSTEM | R3 | EPB-P10,ARCH06,IMP15,DSR*, Gate PRIV-ARCH | H02,H07 | No existe operación integral por titular. Implementar capacidad privilegiada y auditable para localizar, exportar, corregir/anotar, eliminar y restringir en superficies controlables de LeadFlow. | SQL/CLI o servicio administrativo, contratos, documentación | REM-03, REM-12, REM-08 | Identidad verificada; autorización separada; alcance y resultado por superficie; operación repetible y evidencia minimizada | PRIV-T02,T03,T06,T07; sujeto inexistente, ambiguo y repetición | Muy alto: divulgación, modificación o borrado no autorizado | 13 |
| REM-14 | P1 | HYBRID | R3 | EPB-P10, TP*, DSR*, PRIV-T08 | H02,H08 | Los derechos no se coordinan con terceros. Crear orquestación/runbook con adaptadores o pasos manuales verificables para HubSpot, Hunter y Slack cuando aplique. | Adaptadores/operaciones, Registro de Proveedores, runbook DSR | REM-03, REM-13, REM-19 | Cada tercero tiene mecanismo, owner, SLA, evidencia y manejo de respuesta parcial; Slack permanece no configurado hasta onboarding | PRIV-T06,T07,T08 con dobles/mocks; verificación de cuenta después | APIs de terceros, rate limits o roles pueden dejar una solicitud parcial | 14 |
| REM-15 | P2 | HYBRID | R3 | EPB-ARCH07,RET08; EDPB-08-03,08-04 | H02 | Backups, restore y eliminación en copias no tienen contrato. Documentar semántica portable, excepciones, reaparición tras restore y método de borrado/expiración; verificar en entorno. | Contrato de despliegue y runbooks | REM-01, REM-03 | Alcance, frecuencia, custodia, cifrado, retención, RPO/RTO, restore y tratamiento DSR están definidos sin imponer proveedor | Revisión de diseño; restore/expiry post-deployment | Copias pueden reintroducir datos borrados o ser irrecuperables | 15 |
| REM-16 | P1 | SYSTEM | R4 | EPB-ARCH08,IMP08,IMP10,IMP11; EDPB-03-05,08-01 | H01,H03,H04 | Logging no tiene configuración uniforme y stdout/stderr puede contener datos sensibles. Definir formato, nivel, destino, redacción y campos permitidos por entorno. | Adapter, recovery, n8n/PostgreSQL docs, config/overrides | REM-07, REM-09, REM-11 | Logs suficientes y configurables; sin email, nombre, teléfono, payload, headers, tokens, URLs secretas ni trazas sin sanear | PRIV-T04 y EDPB-T08 con canarios | Redacción excesiva reduce soporte; insuficiente expone datos | 16 |
| REM-17 | P1 | SYSTEM | R4 | EPB-P07,ARCH08; EDPB-08-01 | H02,H04 | Docker carece de límites/rotación declarados. Añadir opciones portables de tamaño/archivos o mecanismo equivalente configurable por entorno. | `compose*.yaml`, overrides y guía de operación | REM-16, REM-01 | Todos los servicios declarados tienen política de crecimiento y retención coherente; defaults seguros y sustituibles | Validación Compose/config y prueba controlada de rotación futura | Límites bajos pueden perder diagnóstico; configuración incompatible puede impedir arranque | 17 |
| REM-18 | P2 | HYBRID | R4 | EDPB-02-01,02-04,05-05,06-01,07*,08*,09-04,10-01 | H04,H06 | Falta contrato portable completo para logs, redes, volúmenes, backups y separación dev/test/prod. Documentarlo y aportar overrides/configuración sin acoplar proveedor. | Compose/overrides, arquitectura, setup/deployment docs | REM-06, REM-15, REM-16, REM-17 | Sustitución de entorno no cambia núcleo; responsabilidades y puntos ENVIRONMENT están explícitos | EDPB-T01,T03,T04,T05,T07,T08,T09 | Una guía incompleta puede crear despliegues divergentes o inseguros | 18 |
| REM-19 | P1 | DOCUMENTAL/OPERATIVA | R5 | EPB-LC08, TP*, XFER*, PRIV-T08,T09 | H05,H08 | Falta Registro de Proveedores y decisiones account-specific. Registrar owner, rol, datos, región, transferencias, retención, DPA y revisión: HubSpot enrichment activo; Hunter Free vs `combined/find`; Slack NOT_CONFIGURED con checklist V01–V08 al activarse. | Registro de Proveedores y checklist de onboarding | REM-02; REM-03 | Cada proveedor tiene decisión y pendientes; no se crea workspace Slack; scopes mínimos HubSpot; Hunter reconciliado antes de uso real | Revisión documental y PRIV-T08,T09 planificadas | Rol o términos incorrectos pueden invalidar la operación prevista | 19 |
| REM-20 | P1 | DOCUMENTAL/OPERATIVA | R5 | EPB-P01,P05,P11,P12,P13; PRIV-T10 | — | Faltan procedimiento de incidentes, DSR operacional, risk register, RACI, transferencias y decisión DPIA. Crear y asignar estos registros, distinguiendo producto y cliente. | Procedimientos y registros corporativos/LAB | REM-04, REM-19 | Owner, entrada, escalamiento, evidencia, revisión y criterio de activación definidos; DPIA queda decidible con datos reales | Tabletop de incidente/DSR y revisión de completitud | Responsabilidades ambiguas pueden retrasar respuesta o cierre | 20 |
| REM-21 | P3 | ENVIRONMENT | R5/R7 | EPB-TP*,XFER*,DSR*, EDPB-03-04 | H08 | Contratos y cuentas reales deben probar DPA, región, roles, permisos, retención, transferencias y operación DSR. Recoger evidencia sanitizada al existir cliente/cuentas. | Consolas y contratos de HubSpot/Hunter/Slack | REM-19, REM-20; cuentas reales | Cada cuenta activa tiene evidencia vigente y owner; Slack V01–V08 solo se reauditan al configurarlo | PRIV-T08,T09 y muestreo account-specific | Configuración puede divergir del diseño aprobado | 21 |
| REM-22 | P0 | SYSTEM | R6 | PRIV-T01–T10; controles EPB vinculados | H01–H10 | Los controles carecen de resultados posteriores a remediación. Implementar y ejecutar pruebas de minimización, acceso, autorización, logs, retención, eliminación, exportación, terceros, transferencias e incidentes. | `scripts/test/`, fixtures sintéticos, reportes | REM-05–REM-20 según prueba | Cada prueba aplicable tiene resultado y evidencia; ninguna se declara PASS antes de ejecutarse | PRIV-T01–T10; foco H01,H03,H04,H06,H09 | Tests incompletos pueden dar confianza falsa; fixtures reales pueden exponer PII | 22 |
| REM-23 | P0 | SYSTEM | R6 | EDPB-02*,03*,05*,06*,08*,09*,10-04 | H03,H04,H06,H09 | Falta evidencia EDPB y regresión completa después de cambios. Ejecutar configuración, secretos, hardcodes, dependencias, persistencia, clean start, sustitución de entorno, operación, documentación y regresión LeadFlow. | Validadores, Compose, docs y suites existentes | REM-05–REM-18, REM-22 | EDPB-T01–T09 aplicables y regresión completa pasan; cambiar configuración no exige modificar núcleo | EDPB-T01–T09 y suite LeadFlow completa | Cambios transversales pueden romper contratos, recovery o despliegue | 23 |
| REM-24 | P3 | ENVIRONMENT | R7 | EDPB-03-04,06-03,07*,08-01,08-03,08-04,08-05,09-03,10-05 | H02,H03,H04,H06 | Hosting, TLS, at-rest, firewall, IAM/MFA, backups/restore, logging runtime y permisos efectivos no pueden verificarse sin despliegue. Ejecutar checklist INFRA-V01–V15 y cerrar solo evidencia real. | Infraestructura, runtime, cuentas y reporte post-deployment | REM-15–REM-23; despliegue real | Cada control aplicable tiene evidencia y estado; lo no verificado nunca se presenta como PASS | Pruebas de TLS, acceso, backup/restore, rotación y muestras sanitizadas | Diferencias del entorno pueden invalidar supuestos de desarrollo | 24 |

## 3. Fases y entregables

### R1 — Definiciones previas

Acciones REM-01 a REM-04. Entregables: Matriz de Retención versionada; matriz de finalidad/necesidad y categorías; especificación DSR para PostgreSQL, HubSpot, Hunter, Slack condicionado, logs y backups; reparto LeadFlow/cliente/proveedor; checklist de información preproducción. R1 no fija una base jurídica para un cliente inexistente.

### R2 — Seguridad SYSTEM

Acciones REM-05 a REM-11. Primero se cierra el ciclo de secretos y recovery; después identidad/autorización, metadatos de idempotencia, terminación y validación de fronteras. H06, H04, H03, H01 y H09 quedan trazados explícitamente. La parte de red/IAM de REM-06 y REM-08 sigue siendo HYBRID.

### R3 — Retención y derechos

Acciones REM-12 a REM-15. La Matriz de Retención y la especificación DSR son gates de entrada. La implementación futura cubre ledger, `execution_events`, recovery, superficies controlables, terceros y backups. Se orienta al cierre de EPB-P07, EPB-P10, EPB-LC12, EPB-ARCH06, EPB-IMP15, RET01–13 aplicables, PRIV-T05/T06/T07 y Gate PRIV-ARCH.

### R4 — Logging y EDPB

Acciones REM-16 a REM-18. Logging, redacción y rotación se resuelven en configuración portable. Logs efectivos, volúmenes, red, backup y restore se documentan como contrato de despliegue y se verifican posteriormente. No se exige proveedor ni multi-cloud.

### R5 — Terceros y operación

Acciones REM-19 a REM-21. HubSpot requiere decisión por enrichment activo y evidencia DPA de cuenta; Hunter requiere reconciliar plan Free con `combined/find` y sus roles diferenciados; Slack permanece NOT_CONFIGURED y no se crea un workspace para la auditoría. Los registros operativos separan lo cerrable en desarrollo de lo exigible al cliente antes de producción.

### R6 — Pruebas

Acciones REM-22 y REM-23. Se ejecutan solo después de existir las capacidades. PRIV-T01–T10 y EDPB-T01–T09 aplicables producen evidencia nueva; luego se ejecuta la regresión completa de LeadFlow. Este plan no asume resultados.

### R7 — Cierre y verificación post-deployment

Acción REM-24 y consolidación de resultados. R7 aplica primero el criterio de cierre de desarrollo y, cuando exista infraestructura, completa los controles ENVIRONMENT. No convierte pendientes futuros en PASS ni obliga a desplegar para cerrar SYSTEM.

## 4. Dependencias, secuencia y paralelismo

Secuencia obligatoria:

1. Aprobar REM-01, REM-02 y REM-03 antes de implementar TTL, purga o DSR.
2. Resolver REM-05 y REM-07 antes de ampliar recovery o pruebas que manipulen credenciales.
3. Definir la política de `event_id/source` en REM-09 antes de migraciones de retención o localización.
4. Completar REM-10 antes de purgar estados `processing`.
5. Implementar REM-12 antes de ejecutar PRIV-T05.
6. Implementar REM-13 y REM-14 antes de ejecutar PRIV-T06/T07.
7. Completar REM-16 antes de REM-17 y de PRIV-T04.
8. Completar las remediaciones SYSTEM/HYBRID verificables antes de REM-22/REM-23.
9. Aplicar el cierre de desarrollo antes de iniciar REM-24.

Paralelismo permitido:

- REM-01 y REM-02 pueden elaborarse en paralelo, con reconciliación previa a su aprobación.
- REM-04 puede avanzar junto con R2 después de REM-02/REM-03.
- REM-05 y el diseño de REM-08 pueden avanzar en paralelo; REM-06 debe respetar el mecanismo de secretos elegido.
- REM-12 y REM-13 pueden diseñarse en paralelo después de R1, pero la operación DSR debe consumir las reglas finales de retención.
- REM-19 y REM-20 pueden avanzar junto con R3/R4.
- Las pruebas de REM-22 y REM-23 pueden escribirse junto a cada cambio, pero su evidencia final se ejecuta después del conjunto integrado.

No se evalúan firewall, IAM, TLS público, cifrado at-rest ni cuentas reales durante desarrollo. No se implementa TTL sin Matriz de Retención ni DELETE integral sin modelo DSR.

## 5. Resumen cuantitativo

Total: **24 acciones**.

| P0 | P1 | P2 | P3 |
|---:|---:|---:|---:|
| 12 | 7 | 3 | 2 |

| SYSTEM | HYBRID | ENVIRONMENT | DOCUMENTAL/OPERATIVA |
|---:|---:|---:|---:|
| 11 | 5 | 2 | 6 |

## 6. Primer bloque recomendado

El primer bloque de implementación, después de aprobar R1, es **R2-A: REM-05, REM-07 y REM-10**: ciclo seguro de credencial temporal, eliminación de secretos/PII en argv y stderr, y terminación consistente de recovery. Estas acciones atacan H06, H04 y H09, todas de severidad ALTA, reducen riesgo inmediato y preparan pruebas focalizadas sin depender de infraestructura real. REM-09 debe seguir dentro del mismo R2 después de aprobar la política de metadatos de REM-02.

## 7. Criterios de cierre

### Cierre de desarrollo de LAB-LF-003

- No queda ningún FAIL bloqueante SYSTEM ni la parte verificable de un HYBRID sin resolver.
- Las 12 acciones P0 están completadas en su alcance de desarrollo; los P0 con evidencia futura separan expresamente esa parte.
- Las pruebas PRIV y EDPB aplicables tienen resultado PASS; no se heredan resultados históricos.
- La regresión completa de LeadFlow pasa.
- Arquitectura, contratos, despliegue, retención, DSR, terceros y operación están actualizados.
- Todo WARN residual tiene riesgo, owner, tratamiento y condición de revisión.
- Los controles ENVIRONMENT quedan registrados para R7 como NOT_VERIFIED o estado sustentado.
- EDPB no exige multi-cloud ni un despliegue real para cerrar desarrollo.

### Preparación para producción real

Además del cierre de desarrollo, deben verificarse hosting/región, TLS público e interno aplicable, cifrado at-rest, firewall, IAM/MFA, backups/restore, logging runtime y rotación, permisos efectivos, cuentas/proveedores reales, jurisdicción, finalidad, base jurídica, rol, DPA/configuración contractual y decisión DPIA cuando corresponda. Ningún `NOT_VERIFIED` de entorno futuro puede presentarse como PASS.

## 8. Resultado documental de Tarea 04

El plan queda listo para revisión y ejecución futura. La siguiente tarea es **FASE R1 — DEFINICIONES PREVIAS DEL PLAN DE REMEDIACIÓN**. R1 no se inicia en Tarea 04.

## 9. Ejecución R2-A — REM-05 + REM-07 + REM-10

Fecha: 2026-09-28.

| Acción | Estado R2-A | Evidencia | Riesgo residual |
|---|---|---|---|
| REM-05 | PASS | Helper de credencial probado en creación, ACL, cleanup en éxito/error e idempotencia; provisioning local n8n completado; artefacto residual ausente | El archivo existe solo durante la importación y su contenido transita por memoria del proceso local |
| REM-07 | PASS | Password y SQL pasan por stdin; argv y errores canario no exponen password, token ni email; stderr se transforma en `recovery_database_error` con etapa | El contenido interno viaja transitoriamente por stdin y memoria del proceso, bajo el contrato esperado |
| REM-10 | PASS | Migración 012 aplicada en PostgreSQL 17.6; runtime 7/7, terminación recovery 10/10, reconciliación/idempotencia 9/9 y smoke deployment 14/14 | El barrido general de retención sigue fuera de R2-A y corresponde a REM-12/R3 |

Estos estados no cambian conteos EPB ni gates; R2-A no reevalúa otros controles por inferencia.

## 10. Ejecución R2-B — REM-06

Fecha: 2026-09-28.

| Acción | Estado R2-B | Evidencia | Riesgo residual |
|---|---|---|---|
| REM-06 | PASS | Compose, configuración y scripts usan variables distintas para migrator y app; PostgreSQL local confirmó ambas identidades, capacidad DDL del migrator, lectura normal de la app y denegación DDL de la app; no se imprimieron secretos | Los permisos y secretos deben volver a verificarse en cada entorno desplegado conforme al componente HYBRID de REM-06 |

La prueba focalizada `scripts/test/test_database_role_separation.py` cubrió conexión e identidad de ambos roles, operación de migración, operación normal de aplicación, denegación administrativa y ausencia de credenciales en argumentos o salida. La sincronización de roles y las doce migraciones vigentes finalizaron correctamente. No fue necesaria una regresión adicional porque la misma prueba ejercita la conexión y lectura que LeadFlow necesita con el rol app.

Este cierre no cambia conteos EPB ni gates: **PRIV-00 permanece WARN y PRIV-ARCH permanece FAIL**.

## 15. Cierre desarrollable de Fase R3 — REM-13 + REM-14 + REM-15

Fecha: 2026-09-28.

| Acción | Estado | Evidencia | Riesgo residual |
|---|---|---|---|
| REM-13 | PASS (SYSTEM) | Frontera administrativa separada para LOCATE, EXPORT, ANNOTATE, DELETE y RESTRICT; doble control destructivo; tombstone HMAC; bloqueo de reingreso; idempotencia y ambigüedad verificadas | Identidad humana efectiva, procedimiento de verificación y operación organizativa dependen del despliegue |
| REM-14 | PASS (SYSTEM) / PENDIENTE (HYBRID) | Acciones idempotentes HubSpot/Hunter, Slack N/A controlado, estados pending/completed/failed/not_applicable y resultados sanitizados | Capacidades, cuentas, SLA y ejecución real de proveedores siguen sin verificar |
| REM-15 | PASS (SYSTEM) / NOT_VERIFIED (ENVIRONMENT) | Política portable diaria/30 días, RPO ≤24 h, RTO ≤8 h, cifrado obligatorio y replay DSR tras restore | Backup, restore, cifrado, storage, custodia y métricas reales requieren infraestructura |

La batería focalizada R3 pasó **21/21** en una base temporal: 11 controles DSR local, 6 de coordinación con terceros y 4 de backup/restore. No llamó APIs reales. La base temporal fue eliminada y PostgreSQL quedó detenido.

R3 queda completada solo en su alcance desarrollable. **PRIV-00 permanece WARN y PRIV-ARCH permanece FAIL** hasta una reevaluación formal futura; no cambian conteos EPB.

## 14. Cierre de Fase R2 y ejecución R3-A — REM-12

Fecha: 2026-09-28.

Fase R2 queda **COMPLETADA EN SU ALCANCE DE DESARROLLO** con REM-05, REM-06, REM-07, REM-08 parte SYSTEM, REM-09, REM-10 y REM-11 en PASS. Permanecen pendientes HYBRID/ENVIRONMENT la red, TLS interno, IAM, rotación y verificaciones de infraestructura real.

| Acción | Estado R3-A | Evidencia | Riesgo residual |
|---|---|---|---|
| REM-12 | PASS | Migraciones 014–015, holds específicos, purga por lotes, liberación auditable de holds vencidos, terminalización previa de processing, evidencia de conteos y prueba focalizada aislada 12/12 | La programación efectiva del job, volumen/locks y aprobación de plazos por cliente deben verificarse en cada entorno |

La prueba confirmó conservación y eliminación a 90/180 días, tratamiento de processing/recovery a 7 días, hold activo, eliminación coordinada de eventos, repetición idempotente y evidencia sin datos personales. Se ejecutó en una base temporal eliminada al finalizar; PostgreSQL quedó detenido. No se ejecutó PRIV-T05 como evidencia final de R6.

Este cierre no cambia conteos EPB ni gates: **PRIV-00 permanece WARN y PRIV-ARCH permanece FAIL**.

## 13. Ejecución R2-E — REM-11

Fecha: 2026-09-28.

| Acción | Estado R2-E | Evidencia | Riesgo residual |
|---|---|---|---|
| REM-11 | PASS | Validadores centralizados de códigos técnicos, IDs opacos, website y enrichment; códigos desconocidos canónicos; prueba focalizada 10/10 sin llamadas externas | Límites o formatos incompatibles con datos legítimos de un proveedor deberán ajustarse por contrato y con prueba, sin desactivar la validación |

La prueba focalizada confirmó código válido y canonicalización del anómalo; ID válido y rechazo controlado del inválido; HTTPS válido y rechazo de esquemas peligrosos; allowlist estricta de enrichment; descarte de campos adicionales, longitudes y tipos inválidos; y ausencia del payload anómalo en salida o errores. No cambió la política de retry ni se persistieron respuestas completas.

Este cierre no cambia conteos EPB ni gates: **PRIV-00 permanece WARN y PRIV-ARCH permanece FAIL**.

## 11. Ejecución R2-C — REM-08

Fecha: 2026-09-28.

| Acción | Estado R2-C | Evidencia | Riesgo residual |
|---|---|---|---|
| REM-08 | PASS (SYSTEM) | Identidad service-to-service por header y secreto externo; comparación temporalmente segura; allowlist por operación; fail-closed de configuración; prueba focalizada 7/7 | Red, TLS interno, IAM, distribución y rotación efectiva del secreto siguen pendientes HYBRID/ENVIRONMENT para cada despliegue |

Core y recovery transmiten `X-LeadFlow-Adapter-Key`; el Adapter exige `ADAPTER_SERVICE_KEY` y `ADAPTER_ALLOWED_OPERATIONS`. Requests sin identidad o con identidad inválida reciben `401`; una identidad válida sin permiso recibe `403`; una operación autorizada conserva el contrato funcional existente. La prueba focalizada confirmó además que el secreto no aparece en salida ni error y que la ausencia de configuración impide iniciar el Adapter.

Este cierre SYSTEM no cambia conteos EPB ni gates: **PRIV-00 permanece WARN y PRIV-ARCH permanece FAIL**.

## 12. Ejecución R2-D — REM-09

Fecha: 2026-09-28.

| Acción | Estado R2-D | Evidencia | Riesgo residual |
|---|---|---|---|
| REM-09 | PASS | Allowlist configurable y normalización canónica de `source`; formato técnico estricto de `event_id`; migración 013 elimina su persistencia; idempotencia, duplicados y recovery verificados 9/9 | Cambiar la allowlist exige coordinación con cada integración; SHA-256 determinista sigue siendo un identificador seudonimizado sujeto a acceso y retención |

La prueba focalizada confirmó source permitido/canónico y rechazo fuera de lista; aceptación de un event ID técnico; rechazo de email y límites sin divulgar el canario; ausencia de la columna persistente `event_id`; duplicación estable, claves distintas para eventos distintos y recovery sobre la ejecución original. Los fixtures fueron eliminados y PostgreSQL quedó detenido.

Este cierre no cambia conteos EPB ni gates: **PRIV-00 permanece WARN y PRIV-ARCH permanece FAIL**.

### Validación runtime final de REM-10

Fecha: 2026-09-28. Infraestructura: Docker Desktop 29.6.1, PostgreSQL 17.6 y servicios locales/mocks declarados por Compose. No se llamaron APIs reales.

- `012_recovery_expiration.sql` aplicó sin error; el registro y la función quedaron presentes una sola vez. El mecanismo de migraciones la reconoce como ya aplicada.
- La prueba focalizada runtime pasó 7/7: ejecución vencida termina `failed/timeout/recovery_expired`, excepción persistible termina `failed/upstream_error/recovery_unexpected_error`, `idempotency_key` se conserva, una ejecución no objetivo permanece `processing` y no existe purga global.
- `test_recovery_completion.py` pasó 10/10: recovery success/failed, retries, cleanup de contexto, claves intactas, leases invalidados y segunda ejecución bloqueada.
- `test_recovery_crm_reconciliation.py` pasó 9/9: lookup antes de repetir, CREATE ambiguo reconciliado, worker exclusivo, lease recuperable, auditoría e idempotencia.
- `test_deployment_security.py` pasó 14/14 con endpoints loopback.
- El provisioning n8n local importó credencial/workflow, publicó, reinició y terminó sin `.local/n8n/postgres-credential.json`.
- Cleanup: cero filas sintéticas con los prefijos de prueba; mocks reiniciados para limpiar memoria; stack Compose detenido; credencial temporal ausente.

**REM-10 pasa de WARN a PASS.** REM-05 y REM-07 permanecen PASS. PRIV-00 permanece WARN y PRIV-ARCH permanece FAIL.
## 16. Cierre desarrollable R4 — REM-16, REM-17 y REM-18

Fecha: 2026-09-28.

- **REM-16=PASS (SYSTEM):** Adapter y recovery usan logging JSON uniforme, con nivel/salida configurables y allowlist de metadata técnica. Datos de contacto, payloads, headers, secretos, URLs y valores externos arbitrarios no se propagan.
- **REM-17=PASS (SYSTEM):** todos los servicios Compose declaran driver, `max-size` y `max-file`, configurables por entorno y con defaults seguros. `docker compose config --quiet` pasó.
- **REM-18=PASS (SYSTEM) / PENDIENTE (HYBRID/ENVIRONMENT):** endpoints y secretos están externalizados; logs, volúmenes, backup policy y override de producción quedan identificados. Red, DNS, TLS, firewall, IAM, storage/cifrado, backup/restore, monitoreo y despliegues reales siguen sin verificar.

La única prueba focalizada R4 pasó **12/12** en el primer intento. La validación estática posterior detectó indentación incorrecta en la integración CLI de recovery; se corrigió solo esa causa y la sintaxis pasó. No se ejecutaron APIs, PostgreSQL, contenedores, pruebas anteriores ni suite completa. **PRIV-00 permanece WARN y PRIV-ARCH permanece FAIL.** No se reevalúan conteos EPB.
## 17. Cierre R5/R6 — REM-19 a REM-24

Fecha: 2026-09-29.

- **REM-19=PASS:** registro consolidado de HubSpot, Hunter y Slack, con Slack `NOT_CONFIGURED` y pendientes account-specific explícitos.
- **REM-20=PASS:** procedimientos de incidente/DSR, risk register, RACI, transferencias, DPIA y dos tabletop sintéticos verificados 12/12.
- **REM-21=NOT_VERIFIED / ENVIRONMENT:** requiere cuentas, contratos, regiones, permisos, retención y operación real.
- **REM-22=PASS SYSTEM:** PRIV-T01–T07 y T10 PASS; T08/T09 PASS en diseño SYSTEM y WARN global por evidencia account-specific pendiente.
- **REM-23=PASS SYSTEM:** EDPB-T01–T09 aplicables y regresión LeadFlow completadas con mocks forzados.
- **REM-24=NOT_VERIFIED / ENVIRONMENT:** hosting, TLS, IAM, firewall, cifrado, backups/restores, logging runtime y permisos efectivos requieren despliegue real.

La fase final se reanudó desde el punto de corte y no repitió pasos PASS. Los fallos encontrados fueron de validador/fixtures/arnés: reglas obsoletas de `validate_lab`, import del helper al cargar el Adapter, variables de mocks/recovery y orden global de fixtures recovery; cada causa se corrigió y se repitió solo su prueba. No hubo APIs reales. Cleanup: PASS.

Resultado: **LAB-LF-003 DEVELOPMENT CLOSED / DEPLOYMENT-READY**. Deployment-ready no significa deployed. Gate PRIV-00 queda WARN y PRIV-ARCH queda WARN por dependencias HYBRID/ENVIRONMENT; no quedan FAIL bloqueantes SYSTEM.
