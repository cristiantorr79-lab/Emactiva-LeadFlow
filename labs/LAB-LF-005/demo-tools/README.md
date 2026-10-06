# Herramientas seguras de preparación de demo

Ejecutar desde la raíz del repositorio con PowerShell:

```powershell
.\labs\LAB-LF-005\demo-tools\demo.ps1 status
.\labs\LAB-LF-005\demo-tools\demo.ps1 prepare
.\labs\LAB-LF-005\demo-tools\demo.ps1 cleanup -Session 20261001-a1b2c3
```

## Qué hace cada comando

- `status`: comprueba health y contadores de los tres mocks, además de accesibilidad básica de PostgreSQL. No ejecuta flujos ni muestra payloads o secretos.
- `prepare`: reinicia exclusivamente `crm-mock`, `enrichment-mock` y `slack-mock`; después exige que sus contadores/datos estén limpios. No reinicia PostgreSQL ni n8n.
- `cleanup`: valida el namespace reservado `demo-lf009-<YYYYMMDD-xxxxxx>-<n>`, pero actualmente **falla cerrado sin ejecutar DELETE**.

## Salvaguarda del cleanup

LeadFlow minimiza `event_id` y no lo persiste. Por ello PostgreSQL no permite relacionar de forma demostrable un prefijo de sesión con sus `execution_id`. Está prohibido sustituir esa relación por email, fecha, últimas filas o un DELETE amplio. Hasta aprobar un mecanismo de trazabilidad local de demo, el cleanup de PostgreSQL continúa manual y exige la lista explícita de `execution_id` observados durante la sesión.

Estas herramientas son exclusivas de LAB-LF-005, no forman parte del producto y no usan proveedores reales.
