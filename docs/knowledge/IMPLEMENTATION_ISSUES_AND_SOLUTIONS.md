# LeadFlow — Implementation Issues and Solutions

Registro acumulativo de problemas reales de implementación. Cada entrada debe conservar evidencia, distinguir validación SYSTEM de validación en entorno y actualizar su estado sin borrar el aprendizaje histórico.

Estados: `ACTIVE`, `OBSOLETE`, `REPLACED`.

## LF-ISS-001 — Migrator usado como bootstrap PostgreSQL

- **Fecha:** 2026-10-03
- **LAB / contexto:** LAB-LF-007, volumen PostgreSQL heredado del piloto.
- **Componente:** PostgreSQL / bootstrap de contenedor.
- **Síntoma:** `leadflow_migrator` conservaba SUPERUSER, CREATEDB, CREATEROLE y REPLICATION.
- **Causa raíz:** fue configurado históricamente como `POSTGRES_USER` durante `initdb`.
- **Impacto / riesgo:** incumplimiento de mínimo privilegio sin pérdida funcional observable.
- **Cómo se diagnosticó:** consulta de atributos de `pg_roles` y revisión de Compose/bootstrap.
- **Evidencia relevante:** migrator `t|t|t|t`; app `f|f|f|f`.
- **Solución aplicada:** separación bootstrap/migrator/app y reparación protegida para volumen heredado.
- **Qué no funcionó o debe evitarse:** asumir que un usuario bootstrap es apto como rol operativo.
- **Validación:** PASS local y en volumen heredado real; atributos y ownership finales verificados en VM.
- **Prevención:** verificar atributos efectivos después de inicializar o sincronizar roles.
- **Aplicabilidad / reutilización:** despliegues PostgreSQL basados en imágenes con bootstrap por variables.
- **Estado:** ACTIVE

## LF-ISS-002 — El bootstrap OID 10 no puede despromoverse

- **Fecha:** 2026-10-03
- **LAB / contexto:** LAB-LF-007, reparación del volumen heredado.
- **Componente:** PostgreSQL / catálogo de roles.
- **Síntoma:** `ALTER ROLE ... NOSUPERUSER` fue rechazado.
- **Causa raíz:** el migrator histórico era el bootstrap original OID 10, que debe conservar SUPERUSER.
- **Impacto / riesgo:** la despromoción directa no es una ruta válida.
- **Cómo se diagnosticó:** consulta de OID y error explícito de PostgreSQL.
- **Evidencia relevante:** `leadflow_migrator` OID 10; error `The bootstrap superuser must have the SUPERUSER attribute`.
- **Solución aplicada:** conservar OID 10 como bootstrap mediante rename y crear un migrator restringido nuevo.
- **Qué no funcionó o debe evitarse:** volver a intentar despromover o eliminar OID 10.
- **Validación:** transición multisesión PASS en PostgreSQL 17 efímero y en volumen real de VM.
- **Prevención:** identificar OID y origen del rol antes de alterar atributos administrativos.
- **Aplicabilidad / reutilización:** clústeres PostgreSQL heredados cuyo usuario operativo fue el bootstrap.
- **Estado:** ACTIVE

## LF-ISS-003 — Usernames distintos no prueban mínimo privilegio

- **Fecha:** 2026-10-03
- **LAB / contexto:** LAB-LF-007.
- **Componente:** PostgreSQL / autorización.
- **Síntoma:** existían roles distintos, pero migrator seguía siendo administrador del clúster.
- **Causa raíz:** la verificación inicial comprobaba separación nominal, no atributos y grants efectivos.
- **Impacto / riesgo:** falso PASS de seguridad.
- **Cómo se diagnosticó:** `pg_roles` y `has_schema_privilege`.
- **Evidencia relevante:** roles separados con atributos administrativos en migrator.
- **Solución aplicada:** pruebas explícitas de atributos, CONNECT, USAGE y CREATE.
- **Qué no funcionó o debe evitarse:** validar separación solo por nombres.
- **Validación:** pruebas focalizadas SYSTEM PASS.
- **Prevención:** incluir atributos y privilegios efectivos en todo checklist.
- **Aplicabilidad / reutilización:** cualquier diseño de roles PostgreSQL.
- **Estado:** ACTIVE

## LF-ISS-004 — Cambiar POSTGRES_USER no reemplaza el bootstrap heredado

- **Fecha:** 2026-10-03
- **LAB / contexto:** LAB-LF-007, volumen persistente existente.
- **Componente:** Imagen oficial PostgreSQL / volumen.
- **Síntoma:** apareció un bootstrap nuevo, pero el migrator histórico mantuvo OID 10 y privilegios.
- **Causa raíz:** variables de inicialización no reinicializan un directorio de datos existente.
- **Impacto / riesgo:** configuración declarada y estado real divergen.
- **Cómo se diagnosticó:** comparación de variables, roles, OID y ownership del volumen.
- **Evidencia relevante:** bootstrap nuevo con OID distinto; migrator histórico OID 10.
- **Solución aplicada:** ruta específica de reparación heredada, separada del flujo de instalación nueva.
- **Qué no funcionó o debe evitarse:** tratar un cambio de variable como migración del catálogo.
- **Validación:** PASS SYSTEM y PASS sobre volumen heredado real.
- **Prevención:** clasificar siempre instalación nueva versus volumen heredado.
- **Aplicabilidad / reutilización:** contenedores con inicialización de primer arranque y volúmenes persistentes.
- **Estado:** ACTIVE

## LF-ISS-005 — La configuración debe verificarse dentro del runtime

- **Fecha:** 2026-10-03
- **LAB / contexto:** LAB-LF-007, patch v2.
- **Componente:** Docker Compose / PostgreSQL.
- **Síntoma:** variables bootstrap estaban en `.env`, pero faltaban dentro del contenedor.
- **Causa raíz:** Compose las usaba para mapear `POSTGRES_USER/PASSWORD` sin exponer sus nombres originales.
- **Impacto / riesgo:** `sync_database_roles.sql` no podía leerlas con `\getenv`.
- **Cómo se diagnosticó:** comparación de presencia en host y entorno del contenedor.
- **Evidencia relevante:** bootstrap variables PRESENT fuera y MISSING dentro.
- **Solución aplicada:** exposición explícita y prueba estática de las variables runtime.
- **Qué no funcionó o debe evitarse:** inferir propagación por el uso en interpolación Compose.
- **Validación:** prueba estática y `docker compose config` sintético PASS.
- **Prevención:** comprobar configuración en el límite donde será consumida.
- **Aplicabilidad / reutilización:** variables renombradas o derivadas en contenedores.
- **Estado:** ACTIVE

## LF-ISS-006 — Inventariar ownership antes de reparar roles

- **Fecha:** 2026-10-03
- **LAB / contexto:** LAB-LF-007.
- **Componente:** PostgreSQL / ownership.
- **Síntoma:** database, schema, tablas, secuencias, funciones y extensiones pertenecían al migrator histórico.
- **Causa raíz:** todos se crearon bajo el bootstrap original.
- **Impacto / riesgo:** renombrar o reemplazar roles sin inventario puede romper migraciones o mover objetos incorrectos.
- **Cómo se diagnosticó:** consultas a `pg_database`, `pg_namespace`, `pg_class`, `pg_proc` y `pg_extension`.
- **Evidencia relevante:** objetos funcionales `leadflow` y extensiones tenían el mismo owner histórico.
- **Solución aplicada:** preflight fail-closed y transferencia limitada al schema funcional.
- **Qué no funcionó o debe evitarse:** reparar atributos antes de conocer dependencias y ownership.
- **Validación:** casos sintéticos PASS y ownership/datos preservados verificados en el volumen real de VM.
- **Prevención:** inventario por tipo y namespace antes de cambios de roles.
- **Aplicabilidad / reutilización:** migraciones de ownership y mínimo privilegio.
- **Estado:** ACTIVE

## LF-ISS-007 — REASSIGN OWNED puede mover demasiado

- **Fecha:** 2026-10-03
- **LAB / contexto:** LAB-LF-007.
- **Componente:** PostgreSQL / reparación de ownership.
- **Síntoma:** el owner histórico también poseía `pgcrypto`, `plpgsql` y objetos administrativos.
- **Causa raíz:** bootstrap y migrator habían sido la misma identidad.
- **Impacto / riesgo:** `REASSIGN OWNED` global trasladaría extensiones al migrator restringido.
- **Cómo se diagnosticó:** inventario de extensiones, funciones y objetos del catálogo.
- **Evidencia relevante:** `pgcrypto` y `plpgsql` bajo el OID 10 histórico.
- **Solución aplicada:** transferencia selectiva de schema, relaciones, rutinas y tipos no-extension de `leadflow`.
- **Qué no funcionó o debe evitarse:** `REASSIGN OWNED` indiscriminado.
- **Validación:** extensiones permanecen con bootstrap en pruebas PostgreSQL 17.
- **Prevención:** excluir dependencias de extensión y limitar por namespace/tipo.
- **Aplicabilidad / reutilización:** separación de propietarios en bases heredadas.
- **Estado:** ACTIVE

## LF-ISS-008 — No editar migraciones históricas aplicadas

- **Fecha:** 2026-10-03
- **LAB / contexto:** LAB-LF-007, revisión previa al transporte.
- **Componente:** Migraciones PostgreSQL.
- **Síntoma:** una propuesta modificó temporalmente `001_initial.sql` para retirar acciones bootstrap.
- **Causa raíz:** se intentó ejecutar toda 001 con un migrator restringido.
- **Impacto / riesgo:** drift histórico indetectable porque el ledger no guarda checksums.
- **Cómo se diagnosticó:** comparación contra HEAD y revisión de `schema_migrations`.
- **Evidencia relevante:** el ledger contiene versión/fecha, no hash; 001 fue restaurada al blob `eb6d27e1c77fc8176e6f8e1c58ce4125715bac71`.
- **Solución aplicada:** 001 original se ejecuta como bootstrap solo en instalación nueva, luego ownership selectivo; 002–017 usan migrator.
- **Qué no funcionó o debe evitarse:** editar una migración ya aplicada para resolver bootstrap.
- **Validación:** 001 idéntica a HEAD e instalación nueva 001–017 PASS.
- **Prevención:** diseñar fases bootstrap en el runner, preservando archivos históricos.
- **Aplicabilidad / reutilización:** cualquier repositorio sin checksum de migraciones.
- **Estado:** ACTIVE

## LF-ISS-009 — Un contenedor unhealthy no prueba caída funcional

- **Fecha:** 2026-10-03
- **LAB / contexto:** LAB-LF-007, piloto en VM.
- **Componente:** Docker / healthchecks.
- **Síntoma:** estado `unhealthy` durante diagnóstico aunque PostgreSQL seguía disponible.
- **Causa raíz:** el healthcheck y el estado funcional observaban condiciones distintas.
- **Impacto / riesgo:** diagnóstico incorrecto y acciones de recuperación innecesarias.
- **Cómo se diagnosticó:** contraste entre health status, disponibilidad y estado de roles.
- **Evidencia relevante:** PostgreSQL permaneció healthy/operativo durante la incidencia de variables y roles; el aprendizaje aplica a estados unhealthy observados en el piloto.
- **Solución aplicada:** corroborar disponibilidad y primer fallo real antes de atribuir caída.
- **Qué no funcionó o debe evitarse:** equiparar automáticamente `unhealthy` con aplicación caída.
- **Validación:** aprendizaje operativo del piloto; no constituye garantía universal.
- **Prevención:** healthchecks observables y verificación funcional mínima separada.
- **Aplicabilidad / reutilización:** stacks Docker con múltiples dependencias.
- **Estado:** ACTIVE

## LF-ISS-010 — Healthchecks proporcionales a recursos

- **Fecha:** 2026-10-03
- **LAB / contexto:** LAB-LF-007, VM piloto.
- **Componente:** Docker / capacidad de cómputo.
- **Síntoma:** checks sensibles bajo presión de recursos.
- **Causa raíz:** tiempos y frecuencia no pueden evaluarse aislados de la capacidad disponible.
- **Impacto / riesgo:** falsos negativos y reinicios o diagnósticos innecesarios.
- **Cómo se diagnosticó:** observación correlacionada de recursos y healthchecks en el piloto.
- **Evidencia relevante:** el comportamiento cambió al disponer de capacidad adecuada.
- **Solución aplicada:** dimensionar intervalos/timeouts de forma proporcional al entorno observado.
- **Qué no funcionó o debe evitarse:** usar umbrales agresivos sin considerar la VM.
- **Validación:** evidencia del piloto; valores productivos permanecen dependientes del entorno.
- **Prevención:** medir latencia real antes de fijar umbrales.
- **Aplicabilidad / reutilización:** servicios contenedorizados en VMs pequeñas.
- **Estado:** ACTIVE

## LF-ISS-011 — e2-micro fue insuficiente para el piloto

- **Fecha:** 2026-10-03
- **LAB / contexto:** LAB-LF-007, Google Cloud.
- **Componente:** Capacidad de VM.
- **Síntoma:** recursos insuficientes para el stack piloto completo.
- **Causa raíz:** capacidad de e2-micro inferior a la demanda observada del stack.
- **Impacto / riesgo:** degradación, healthchecks inestables y diagnóstico contaminado.
- **Cómo se diagnosticó:** ejecución real del stack y comparación tras ajustar capacidad.
- **Evidencia relevante:** e2-micro no sostuvo adecuadamente este piloto.
- **Solución aplicada:** usar capacidad superior para continuar el piloto.
- **Qué no funcionó o debe evitarse:** generalizar que e2-micro basta para este stack.
- **Validación:** demostrada solo para el piloto.
- **Prevención:** sizing basado en medición y carga objetivo.
- **Aplicabilidad / reutilización:** planificación inicial de despliegues LeadFlow.
- **Estado:** ACTIVE

Nota: este resultado no convierte e2-medium en mínimo universal de producción.

## LF-ISS-012 — Canal SSH operativo alternativo

- **Fecha:** 2026-10-03
- **LAB / contexto:** LAB-LF-007, acceso a VM piloto.
- **Componente:** Operación remota.
- **Síntoma:** Browser SSH fue inestable durante el piloto.
- **Causa raíz:** no determinada; no se generaliza fuera del caso observado.
- **Impacto / riesgo:** sesiones interrumpidas y menor confiabilidad operativa.
- **Cómo se diagnosticó:** comparación práctica entre canales de acceso.
- **Evidencia relevante:** Cloud Shell con `gcloud compute ssh` resultó más fiable en este piloto.
- **Solución aplicada:** usar el canal más estable para las operaciones controladas.
- **Qué no funcionó o debe evitarse:** depender de un único canal sin alternativa.
- **Validación:** evidencia limitada al piloto.
- **Prevención:** preparar una vía de acceso autorizada alternativa.
- **Aplicabilidad / reutilización:** operaciones remotas en Google Cloud, sujetas al entorno.
- **Estado:** ACTIVE

## LF-ISS-013 — SSH abierto globalmente no es estándar final

- **Fecha:** 2026-10-03
- **LAB / contexto:** LAB-LF-007, acceso temporal al piloto.
- **Componente:** Red / SSH.
- **Síntoma:** una regla `0.0.0.0/0` puede facilitar acceso temporal pero amplía exposición.
- **Causa raíz:** conveniencia operativa sin restricción de origen.
- **Impacto / riesgo:** superficie de ataque innecesaria.
- **Cómo se diagnosticó:** revisión del alcance efectivo de la regla.
- **Evidencia relevante:** el patrón fue identificado durante el piloto; no se aprueba como baseline.
- **Solución aplicada:** exigir justificación y cierre/restricción posterior según el entorno.
- **Qué no funcionó o debe evitarse:** normalizar `0.0.0.0/0` como configuración final.
- **Validación:** regla de seguridad derivada del alcance observado; estado final depende del entorno.
- **Prevención:** limitar origen, tiempo y propósito del acceso.
- **Aplicabilidad / reutilización:** cualquier VM con administración SSH.
- **Estado:** ACTIVE

## LF-ISS-014 — Detener diagnóstico cuando la evidencia basta

- **Fecha:** 2026-10-03
- **LAB / contexto:** LAB-LF-007.
- **Componente:** Proceso de diagnóstico.
- **Síntoma:** riesgo de ampliar investigación después de identificar el primer fallo real.
- **Causa raíz:** confundir exhaustividad con progreso seguro.
- **Impacto / riesgo:** cambios innecesarios, ruido y mayor superficie de error.
- **Cómo se diagnosticó:** la evidencia de variables runtime, OID y ownership explicó los fallos sucesivos.
- **Evidencia relevante:** cada corrección se guio por el primer error reproducible.
- **Solución aplicada:** detener exploración general y validar hipótesis focalizadas.
- **Qué no funcionó o debe evitarse:** repetir controles ya PASS o investigar componentes no implicados.
- **Validación:** proceso aplicado durante LAB-LF-007.
- **Prevención:** registrar evidencia suficiente y criterio de parada.
- **Aplicabilidad / reutilización:** incidentes técnicos y pilotos de implementación.
- **Estado:** ACTIVE

## LF-ISS-015 — Los volúmenes heredados requieren pruebas propias

- **Fecha:** 2026-10-03
- **LAB / contexto:** LAB-LF-007.
- **Componente:** Estrategia de pruebas/deployment.
- **Síntoma:** pruebas estáticas y de instalación nueva no detectaron la identidad bootstrap histórica del volumen.
- **Causa raíz:** el estado persistido conserva decisiones anteriores que las variables actuales no reemplazan.
- **Impacto / riesgo:** una corrección válida para fresh install puede fallar sobre datos reales heredados.
- **Cómo se diagnosticó:** validación real en VM seguida de reproducción PostgreSQL 17 aislada.
- **Evidencia relevante:** OID 10, ownership y extensiones del volumen difirieron del modelo nuevo.
- **Solución aplicada:** escenarios separados de new install y legacy repair, ambos con pruebas focalizadas.
- **Qué no funcionó o debe evitarse:** asumir equivalencia entre configuración declarada y volumen existente.
- **Validación:** ambos escenarios PASS local y reparación del volumen heredado PASS en VM.
- **Prevención:** incluir fixtures o pruebas de upgrade desde estados persistidos reales.
- **Aplicabilidad / reutilización:** bases, colas y servicios con estado durable.
- **Estado:** ACTIVE

## Promoción corporativa pendiente

Al cierre de LAB-LF-007 deberán promoverse únicamente los patrones reutilizables y descontextualizados a:

`00_CORPORATIVO/CONOCIMIENTO/EMACTIVA_Implementation_Issues_and_Solutions.md`

Ese archivo corporativo no se crea ni modifica desde este repositorio. La promoción no debe copiar nombres internos de scripts, VM, rutas locales o tablas salvo una referencia mínima al proyecto origen.

## LF-ISS-016 — Dependencia de herramienta del host no declarada

- **Fecha:** 2026-10-03
- **LAB / contexto:** LAB-LF-007, preparación de remediación en Debian.
- **Componente:** Deployment / portabilidad del host.
- **Síntoma:** el comando documentado de migraciones no podía ejecutarse porque `pwsh` no existía en la VM.
- **Causa raíz:** el flujo soportado dependía implícitamente de scripts PowerShell sin declarar PowerShell como prerequisito Linux.
- **Impacto / riesgo:** bloqueo operativo de migraciones y reparación aunque Docker/PostgreSQL estuvieran disponibles.
- **Cómo se diagnosticó:** comprobación directa del comando requerido en la VM Debian.
- **Evidencia relevante:** `pwsh` ausente; la remediación real no llegó a ejecutarse.
- **Solución aplicada:** ruta Bash explícita que usa Docker Compose y `psql` del contenedor, reutilizando los SQL existentes; PowerShell queda como opción Windows.
- **Qué no funcionó o debe evitarse:** asumir que una herramienta del equipo de desarrollo existe en el host objetivo.
- **Validación:** PASS local y ejecución de la ruta Bash PASS en Debian real.
- **Prevención:** declarar prerequisitos reales y probar comandos desde el sistema operativo objetivo.
- **Aplicabilidad / reutilización:** cualquier deployment multiplataforma o automatización operativa remota.
- **Estado:** ACTIVE

## LF-ISS-017 — SELECT set_config puede reflejar secretos

- **Fecha:** 2026-10-03
- **LAB / contexto:** LAB-LF-007, remediación real PostgreSQL en VM Debian.
- **Componente:** PostgreSQL / psql / sanitización de salida.
- **Síntoma:** la salida normal de `psql` mostró el valor correspondiente a `bootstrap_password`.
- **Causa raíz:** `SELECT set_config('leadflow.bootstrap_password', ..., false)` devuelve el valor configurado y `psql` imprime el resultado del SELECT.
- **Impacto / riesgo:** exposición de credenciales en terminal, captura de sesión o logs operativos.
- **Cómo se diagnosticó:** correlación de la cadena impresa con la sentencia `SELECT set_config` del preflight heredado.
- **Evidencia relevante:** el password solo se configuraba como GUC de sesión; el bloque posterior utilizaba directamente la variable segura de `psql` y no necesitaba ese GUC.
- **Solución aplicada:** eliminar el `set_config` del password y enviar los `set_config` no secretos a `\gset`, que conserva su efecto sin imprimir filas.
- **Qué no funcionó o debe evitarse:** ejecutar `SELECT set_config()` directamente con secretos o asumir que `psql -q` oculta resultados de consultas.
- **Validación:** canario local PASS; ejecución posterior en VM sin exposición; credencial observada rotada y autenticación nueva PASS.
- **Prevención:** no almacenar secretos en GUC cuando no sea imprescindible; si se requiere un resultado auxiliar no secreto, consumirlo con `\gset` o una construcción que no emita filas.
- **Aplicabilidad / reutilización:** scripts `psql` automatizados, pipelines y tareas operativas con variables sensibles.
- **Estado:** ACTIVE

## LF-ISS-018 — Configuración declarada no actualiza procesos existentes

- **Fecha:** 2026-10-03
- **LAB / contexto:** LAB-LF-007, cleanup posterior a reparación.
- **Componente:** Docker Compose / entorno de contenedor.
- **Síntoma:** una variable transitoria retirada de `.env` seguía presente dentro del contenedor PostgreSQL.
- **Causa raíz:** editar `.env` o Compose no modifica el environment de un contenedor ya creado.
- **Impacto / riesgo:** estado runtime divergente y reutilización accidental de configuración temporal.
- **Cómo se diagnosticó:** inspección de presencia de la variable dentro del contenedor después de editar configuración.
- **Evidencia relevante:** variable todavía configurada como migrator hasta recrear PostgreSQL.
- **Solución aplicada:** retirar la variable, recrear únicamente el contenedor afectado sin borrar volumen y verificarla como `UNSET`.
- **Qué no funcionó o debe evitarse:** asumir que reiniciar o editar archivos rematerializa el environment.
- **Validación:** PASS en VM; PostgreSQL volvió healthy y conservó el volumen.
- **Prevención:** verificar configuración en runtime y documentar cuándo se requiere recreación controlada.
- **Aplicabilidad / reutilización:** contenedores y procesos cuyo entorno se fija al crearse.
- **Estado:** ACTIVE

## LF-ISS-019 — Tests operacionales y exposición innecesaria de secretos

- **Fecha:** 2026-10-03
- **LAB / contexto:** LAB-LF-007, validación directa de separación de roles.
- **Componente:** QA operacional / manejo de credenciales.
- **Síntoma:** un test requería exportar cinco variables PostgreSQL, incluidas contraseñas, en la shell del operador.
- **Causa raíz:** interfaz del test diseñada para un entorno de proceso preconfigurado, no para ejecución manual segura.
- **Impacto / riesgo:** ampliar innecesariamente la presencia de secretos en el host o historial operativo.
- **Cómo se diagnosticó:** revisión de precondiciones al intentar ejecutarlo directamente en Debian.
- **Evidencia relevante:** la modalidad directa quedó NOT_VERIFIED; el control material fue demostrado con consultas y smokes independientes.
- **Solución aplicada:** no forzar `source .env` ni exportación manual; usar evidencia alternativa suficiente.
- **Qué no funcionó o debe evitarse:** debilitar manejo de secretos solo para obtener un PASS nominal.
- **Validación:** atributos, ownership, autenticación, migraciones y runtime PASS por vías independientes.
- **Prevención:** diseñar tests operacionales que consuman secretos en el límite más estrecho posible.
- **Aplicabilidad / reutilización:** scripts de QA ejecutados manualmente en hosts productivos o pilotos.
- **Estado:** ACTIVE

## LF-ISS-020 — Cleanup de estado efímero en mocks

- **Fecha:** 2026-10-03
- **LAB / contexto:** LAB-LF-007, smoke funcional post-remediación.
- **Componente:** Mocks / cleanup de pruebas.
- **Síntoma:** el contacto sintético persistía en memoria del mock aunque el cleanup PostgreSQL había terminado.
- **Causa raíz:** el mock mantiene estado efímero sin volumen persistente y no comparte el cleanup de la base.
- **Impacto / riesgo:** evidencia residual que puede contaminar pruebas posteriores.
- **Cómo se diagnosticó:** separación del estado PostgreSQL y el estado en memoria del servicio.
- **Evidencia relevante:** cleanup de filas PASS; reinicio controlado eliminó el contacto y el servicio volvió healthy.
- **Solución aplicada:** reiniciar únicamente el mock sin volumen después de confirmar la naturaleza efímera del estado.
- **Qué no funcionó o debe evitarse:** asumir que limpiar la base limpia todos los componentes.
- **Validación:** mock healthy después del reinicio y datos sintéticos retirados.
- **Prevención:** inventariar estado persistente y efímero por componente en el plan de cleanup.
- **Aplicabilidad / reutilización:** pruebas integradas con servicios mock stateful en memoria.
- **Estado:** ACTIVE

## LF-ISS-021 — Rotar después de corregir el canal de fuga

- **Fecha:** 2026-10-03
- **LAB / contexto:** LAB-LF-007, exposición potencial de bootstrap password.
- **Componente:** Gestión de credenciales.
- **Síntoma:** una credencial apareció en stdout antes de corregir la sanitización.
- **Causa raíz:** una consulta SQL devolvía el valor sensible.
- **Impacto / riesgo:** la credencial debía tratarse como expuesta aunque no se observara uso indebido.
- **Cómo se diagnosticó:** correlación entre salida y `SELECT set_config`.
- **Evidencia relevante:** ejecución posterior sanitizada; autenticación TCP con credencial nueva PASS.
- **Solución aplicada:** corregir primero la fuga, generar una credencial criptográfica sin imprimirla, actualizar configuración, recrear el contenedor sin borrar volumen y aplicar la nueva credencial.
- **Qué no funcionó o debe evitarse:** rotar antes de cerrar el canal, lo que expondría también el secreto nuevo.
- **Validación:** PostgreSQL healthy, flujo Bash sin exposición y `BOOTSTRAP_AUTH=PASS`; credencial anterior reemplazada.
- **Prevención:** secuencia obligatoria de respuesta: contener fuga, validar sanitización, rotar y comprobar autenticación.
- **Aplicabilidad / reutilización:** cualquier secreto potencialmente expuesto en stdout, logs o terminal.
- **Estado:** ACTIVE
