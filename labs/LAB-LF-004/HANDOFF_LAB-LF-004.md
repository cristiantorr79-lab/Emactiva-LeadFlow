# HANDOFF LAB-LF-004

Estado: **CLOSED**

## Objetivo

Validación visual y demo funcional de LeadFlow en n8n.

## Evidencia runtime

- Entorno Docker local levantado: PASS.
- PostgreSQL healthy.
- n8n, crm-mock, enrichment-mock, slack-mock y adapters: healthy.
- Workflow `LeadFlow Core Initial` visible y cargado en n8n: PASS.
- Webhook `POST /leadflow`: PASS.
- Happy path: PASS.
- Duplicado e idempotencia: PASS.
- Entrada inválida: PASS.
- Retry transitorio: PASS.
- Fallo definitivo y alerta: PASS.
- Persistencia PostgreSQL y cleanup local: PASS.

## Hallazgos y remediaciones

### LF004-F01 — Deriva contractual en Authenticate Validate Normalize

- Se eliminó la normalización silenciosa de `source` y se restauraron límites, patrón, case sensitivity e identidad de `event_id` conforme al contrato vigente.
- QA focalizada A–H: PASS 8/8.
- Confirmación runtime tras reprovisionamiento: PASS.

### LF004-F02 — Incompatibilidad de provisionamiento con Windows PowerShell

- Causa: `provision_n8n.ps1` usaba `ConvertTo-Json -AsArray`, parámetro no disponible en Windows PowerShell 5.1.
- Corrección: construcción explícita del array mediante `ConvertTo-Json -InputObject @(...) -Depth 5`, sin cambiar el objeto de credencial ni el flujo de provisionamiento.
- QA técnica focalizada en Windows PowerShell: PASS 4/4 (sintaxis, array de un objeto, parseo y campos esperados); manejo seguro del archivo temporal: PASS 7/7.
- Runtime de provisionamiento: PASS.

### LF004-F03 — Brecha preventiva de proveedores en development

- Se añadió un preflight fail-closed antes del provisioning operativo.
- Con `APP_ENV=development`, exige `CRM_PROVIDER=mock` y `ENRICHMENT_PROVIDER=mock`; cualquier combinación distinta se rechaza con mensaje sanitizado.
- QA focalizada: development mock/mock aceptado; hubspot/mock y mock/hunter rechazados; mensaje sanitizado y orden anterior a provisioning verificados.

## Contención y cleanup externo

- Los dos contactos sintéticos creados accidentalmente en HubSpot fueron eliminados: HTTP 204.
- La búsqueda posterior devolvió 0 contactos.
- `LEADFLOW_WEBHOOK_KEY` fue rotada.
- La clave anterior responde HTTP 401.

## WARN y bloqueos

- WARN reales pendientes: ninguno dentro del alcance de LAB-LF-004.
- Bloqueos para cierre: ninguno.

---

## CIERRE FORMAL LAB-LF-004

**Estado final:** CLOSED
**Fecha de cierre:** 2026-09-29

El objetivo de LAB-LF-004 — validación visual y funcional de LeadFlow en n8n — quedó cumplido.

Las validaciones, remediaciones, cleanup y evidencias aplicables quedaron completadas sin WARN ni bloqueos dentro del alcance del LAB.

La versión publicada y validada del workflow permanece activa. Los cambios visuales locales de disposición de nodos no forman parte del cierre funcional.

**Continuidad:** no reabrir LAB-LF-004 salvo regresión, cambio funcional relacionado o nuevo riesgo real.
