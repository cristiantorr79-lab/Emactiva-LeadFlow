# HANDOFF — LAB-LF-006

**Proyecto:** Emactiva LeadFlow  
**LAB:** LAB-LF-006 — Implementación Remota y Despliegue en Clientes  
**Estado:** CERRADO — PASS  
**Fecha:** 2026-10-01

## 1. Objetivo

Definir y preparar el proceso profesional mediante el cual Emactiva puede implementar LeadFlow remotamente en el entorno autorizado de un cliente, manteniendo seguridad, privacidad, portabilidad, trazabilidad, capacidad de recuperación y responsabilidades claras.

LAB-LF-006 sirve como puente entre:

**LeadFlow demostrable y empaquetado**

y

**LeadFlow preparado para una implementación real en cliente.**

## 2. Estado anterior

LAB-LF-005:

**CERRADO — PASS — PUSHED — SINCRONIZADO**

Commit de cierre:

`ffdb9ec`

No se reabre LAB-LF-005.

## 3. Alcance resuelto

Se definió el procedimiento para:

- discovery;
- clasificación;
- alcance;
- responsabilidades;
- accesos;
- gestión segura de credenciales;
- preparación del entorno;
- preflight;
- deployment;
- configuración;
- adapters;
- endpoints;
- migraciones;
- smoke test;
- primera ejecución controlada;
- validación;
- producción;
- rollback;
- cleanup;
- handoff;
- soporte inicial;
- evidencia mínima de implementación;
- separación SYSTEM / HYBRID / ENVIRONMENT.

## 4. Fuera de alcance respetado

No se incorporaron:

- nuevas funciones del core;
- rediseño arquitectónico;
- identidad por teléfono/WhatsApp;
- managed service;
- SLA completo;
- soporte 24/7;
- pricing definitivo;
- landing Emactiva;
- campañas;
- OpportunityFlow / MarketFlow;
- DemoFactory;
- implementación de un cliente real.

## 5. Decisiones

### LF006-D01 — No crear forks por cliente

La personalización debe resolverse preferentemente mediante configuración, adapters, mappings y environment.

### LF006-D02 — Discovery antes de accesos

No solicitar credenciales indiscriminadamente. Primero se determina qué recursos y permisos son realmente necesarios.

### LF006-D03 — Mínimo privilegio

Todo acceso debe limitarse a recurso necesario, finalidad definida, permiso mínimo y periodo necesario.

### LF006-D04 — No secretos en documentación

Las plantillas, HANDOFFs, logs y repositorio no deben contener passwords, API keys, tokens, webhooks secretos, connection strings ni secretos equivalentes.

### LF006-D05 — No producción sin validación controlada

Antes de habilitar tráfico real deben completarse preflight, deployment, smoke test, primera ejecución controlada, validaciones aplicables y aprobación funcional.

### LF006-D06 — Rollback previo a producción

La estrategia para volver atrás debe conocerse antes de habilitar tráfico real.

### LF006-D07 — Datos sintéticos primero

La primera ejecución debe utilizar preferentemente datos sintéticos o controlados.

### LF006-D08 — Controles reales requieren evidencia real

Red, TLS, IAM, firewall, backups, restore, monitoreo, rotación e infraestructura productiva no pueden marcarse PASS sin deployment real.

## 6. Artefactos definidos

### Nuevo

`labs/LAB-LF-006/LEADFLOW_REMOTE_DEPLOYMENT_RUNBOOK.md`

### Nuevo

`labs/LAB-LF-006/LEADFLOW_CLIENT_IMPLEMENTATION_TEMPLATE.md`

### Nuevo

`labs/LAB-LF-006/HANDOFF_LAB-LF-006.md`

## 7. Artefactos existentes reutilizados

LAB-LF-006 no reconstruye mecanismos ya existentes.

Debe reutilizar:

- `.env.example`;
- `compose.production.yaml`;
- `docs/setup/SETUP.md`;
- `docs/runbooks/BACKUP_RESTORE.md`;
- `config/backup-policy.json`;
- `scripts/validation/validate_deployment_config.py`;
- `scripts/database/apply_migrations.ps1`;
- `scripts/database/sync_database_roles.ps1`;
- artefactos comerciales y de intake de LAB-LF-005.

## 8. Arquitectura preservada

No se modifica la separación existente:

**core / adapters / environment**

LeadFlow mantiene PostgreSQL como autoridad de idempotencia y trazabilidad.

## 9. Privacidad

Se mantienen:

- email necesario en V1;
- nombres opcionales;
- teléfono sujeto a justificación;
- source por allowlist;
- event_id técnico;
- lead_identifier/hash como dato seudonimizado;
- enrichment limitado a industry, company_size y website;
- enrichment sin sobrescribir email, nombre ni teléfono;
- logs mínimos y sanitizados;
- datos sintéticos preferidos para pruebas.

## 10. Retención

Se mantiene:

- success / duplicate: 90 días;
- failed: 180 días;
- processing / recovery sin progreso: máximo 7 días.

## 11. DSR

Se mantienen donde son controlables:

- LOCATE;
- EXPORT;
- CORRECT / ANNOTATE;
- DELETE;
- RESTRICT.

DELETE y RESTRICT destructivos requieren aprobación independiente.

## 12. Clasificación de controles

### SYSTEM

Puede validarse sin infraestructura real.

### HYBRID

Una parte pertenece al sistema y otra al entorno real.

### ENVIRONMENT

Requiere infraestructura real.

## 13. Estado actual de controles

### PASS documental y de repositorio

- proceso remoto definido;
- clasificación de implementaciones definida;
- responsabilidades definidas;
- política de accesos definida;
- preflight definido;
- secuencia de deployment definida;
- migraciones integradas al proceso;
- smoke definido;
- primera ejecución controlada definida;
- activación productiva definida;
- rollback definido;
- cleanup definido;
- handoff definido;
- límites de soporte definidos;
- plantilla reutilizable definida;
- SYSTEM / HYBRID / ENVIRONMENT diferenciados.

Estos controles cuentan con evidencia documental y validación estática focalizada en el repositorio.

### NOT_VERIFIED

Permanecen correctamente pendientes hasta deployment real:

- red real;
- DNS real;
- TLS real;
- firewall real;
- IAM real;
- cifrado real;
- backup real;
- restore real;
- monitoreo real;
- rotación real;
- infraestructura productiva;
- controles post-deployment dependientes del cliente.

`NOT_VERIFIED` no equivale a `PASS`.

## 14. QA requerida para cierre

Antes de cambiar este HANDOFF a `CERRADO — PASS` debe verificarse únicamente lo proporcional al cambio.

No ejecutar regresión completa de LeadFlow.

Validaciones previstas:

- artefactos LF-006 presentes;
- contenido mínimo esperado;
- ausencia de secretos;
- referencias técnicas existentes;
- configuración productiva fail-closed mediante datos sintéticos;
- documentación consistente;
- `git diff --check`;
- árbol Git revisado.

No levantar infraestructura real solo para cerrar este LAB documental/preparatorio.

### Evidencia de cierre

- `python scripts/validation/validate_lab_lf_006.py`: PASS (`checks=22/22`);
- `python -m py_compile scripts/validation/validate_lab_lf_006.py`: PASS;
- `git diff --check`: PASS;
- revisión focalizada de documentos y artefactos técnicos: coherente;
- core sin cambios;
- workflows sin cambios;
- adapters sin cambios;
- migraciones sin cambios;
- LABs cerrados anteriores sin cambios;
- sin secretos ni datos reales;
- sin Docker ni proveedores reales.

## 15. Cleanup

LAB-LF-006 no necesita crear datos reales de cliente.

Cualquier dato sintético creado durante futuras pruebas técnicas debe eliminarse o mantenerse únicamente con justificación explícita.

## 16. WARN

No existen WARN técnicos bloqueantes para el cierre documental. Los controles que requieren infraestructura o cliente real permanecen `NOT_VERIFIED`.

## 17. Riesgos residuales

El principal riesgo pendiente no pertenece al core de LeadFlow.

Corresponde a variaciones del entorno real del primer cliente: infraestructura, políticas corporativas, proveedores, permisos, red, TLS, backups, monitoreo y operación.

## 18. Criterio de cierre

LAB-LF-006 podrá declararse:

**CERRADO — PASS**

cuando:

- procedimiento esté versionado;
- plantilla esté versionada;
- HANDOFF esté completo;
- validación focalizada pase;
- no existan secretos;
- no existan FAIL SYSTEM bloqueantes;
- NOT_VERIFIED de entorno estén correctamente delimitados;
- Git esté limpio o con cambios de cierre claramente identificados;
- no se hayan modificado innecesariamente core, workflows, adapters o migraciones.

## 19. Siguiente paso exacto

Materializar estos artefactos en el repositorio y ejecutar una validación técnica focalizada.

Codex solo debe utilizarse para trabajo técnico concreto y proporcional.

---

**Estado actual:** CERRADO — PASS

**Pendiente posterior:** obtener evidencia real durante un deployment autorizado sin alterar el estado `NOT_VERIFIED` de los controles de entorno hasta entonces.
