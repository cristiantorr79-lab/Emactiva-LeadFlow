# Plan de pruebas LF V1

**Definido, no ejecutado:** requiere runtime n8n, PostgreSQL y mocks del próximo LAB. Cada caso usa base aislada, CRM inspeccionable y reloj/delays observables. Entrada base E: ejemplo válido de CONTRACTS con event_id único; todos los correos son de example.com. Se comprueban llamadas, filas y respuestas, no solo HTTP.

| Caso | Objetivo | Precondición | Entrada | Resultado esperado | Criterio PASS |
|---|---|---|---|---|---|
| LF-T01 | Crear lead nuevo | CRM vacío; enriquecimiento OK | E | success, created | Un contacto, enriquecido y una ejecución success |
| LF-T02 | Actualizar existente | Email de E ya existe | E con company cambiado | success, updated | Mismo ID, campo actualizado, cero CREATE |
| LF-T03 | Rechazar email inválido | CRM vacío | E con email sin @ | HTTP 400 validation_error | failed en validation; cero llamadas CRM y cero retries |
| LF-T04 | Exigir campos | CRM vacío | E sin event_id, sin source o sin lead.email; tres variantes | HTTP 400 | Las tres fallan y no llaman dependencias |
| LF-T05 | Deduplicar reenvío | E completado | E otra vez | duplicate | Un propietario UNIQUE, recepción duplicate enlazada y ningún efecto adicional |
| LF-T06 | Evitar carrera | CRM vacío; barrera de inicio | Dos E simultáneos | Un propietario, un duplicate | Una sola ejecución procesa y un contacto total |
| LF-T07 | Reintentar timeout | Enrichment timeout en tres intentos | E | failed tras 3 intentos | Esperas 5/15, retry_count=2 y sin repetir CREATE |
| LF-T08 | Manejar 429 | Enrichment 429 con Retry-After=10, después OK | E | retrying → success | Dos llamadas, espera al menos 10 s, un contacto |
| LF-T09 | No retry 400 | Enrichment responde 400 | E | failed inmediato | Una llamada enrichment, cero retries, error sanitizado |
| LF-T10 | No retry 401 | Enrichment responde 401 | E | failed inmediato | Una llamada y ninguna API key en registro/respuesta |
| LF-T11 | Reintentar 500 | Enrichment 500, 500, OK | E | success en tercer intento | Tres llamadas, delays 5/15 y retry_count=2 |
| LF-T12 | Tolerar CRM caído | Lookup 503, luego OK | E | Recupera y continúa | Dos lookup, una creación, success |
| LF-T13 | Reconciliar CREATE ambiguo | Mock crea y pierde respuesta | E | Lookup encuentra contacto creado | Un contacto y un CREATE efectivo; continúa enriquecimiento |
| LF-T14 | Recuperarse en retry | CRM update 502, luego OK; contacto existe | E | success | Dos update, mismo ID, retry_count=1 |
| LF-T15 | Agotar presupuesto | Lookup siempre 503 | E | failed definitivo | Exactamente 3 lookup, delays 5/15, sin cuarto intento |
| LF-T16 | Alertar fallo definitivo | LF-T15; receptor Slack simulado | E | Alerta después de failed persistido | Un envío aceptado con ID y error sanitizado; fallo Slack adicional no genera recursión |
| LF-T17 | Registrar éxito | Servicios OK | E | Resumen e historial persistidos | Todos los campos mínimos presentes o NULL justificado; finished_at y contacto informados |
| LF-T18 | Registrar fallo | Enrichment 400 | E | failed en enrichment | Código, tipo, tiempos, contacto previo y eventos conservados |
| LF-T19 | Excluir secretos | Dependencia devuelve mensaje con secreto canario ficticio | E | Mensaje redactado | Canario, headers y payload completo ausentes en DB, Slack, salida y respuesta |
| LF-T20 | Evitar duplicado en retry/reenvío | CREATE ambiguo y reenvío posterior; luego nuevo evento mismo email | E, E, E con otro event_id | Reconciliar, deduplicar y actualizar | Un solo contacto en las tres entregas; nuevo evento no crea otro |

Comprobaciones complementarias al implementar: trim/lowercase converge a un email; HTTP 403/404 técnico sin retry; HTTP 408/502/504 y red temporal con retry; 409 de CREATE reconcilia y otro 409 falla; caída PostgreSQL no permite efectos; repetición de migración revierte sin pérdida; proceso interrumpido no libera clave automáticamente. Probar también ausencia confirmada tras CREATE ambiguo y límite del presupuesto de reconciliación.
