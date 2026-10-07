# LeadFlow — Implementation Playbook

## Flujo de trabajo

`contacto → diagnóstico → levantamiento del proceso → definición de alcance → preparación de accesos → preparación del entorno → configuración/integración → pruebas → validación del cliente → puesta en marcha → handoff`

Cada etapa conserva evidencia proporcional. Un fallo real se diagnostica antes de cambiar componentes; no se repiten baterías ya cerradas sin impacto que lo justifique.

## Pre-check LeadFlow

Antes de comprometer alcance, confirmar:

- existe un proceso real y recurrente de leads;
- la fuente es integrable;
- el sistema destino está identificado;
- el email está disponible como identidad en V1;
- se definió si interaction aplica y si un contacto puede realizar múltiples consultas;
- `interest` y/o `message`, su finalidad y minimización están definidos cuando corresponda;
- la representación de interaction en CRM está acordada;
- las capabilities `interaction_write`, `interaction_idempotency` e `interaction_reconciliation` están demostradas o clasificadas;
- CRM/API es compatible o queda sujeto a evaluación;
- campos de entrada y destino están identificados y justificados;
- restricciones técnicas, operacionales, de privacidad y jurisdicción conocidas están registradas;
- el trabajo se clasifica como `STANDARD / CORE`, `CONFIGURATION / INTEGRATION`, `PRODUCT ADAPTATION` o `CUSTOM / OTHER PRODUCT`;
- la modalidad es Entrega técnica o Implementado por Emactiva.

La validación técnica de Emactiva y la validación funcional del cliente son gates separados.

Clasificar como `STANDARD / CORE` cuando las capabilities necesarias ya existen y están demostradas; como `CONFIGURATION / INTEGRATION` cuando basta configuración, mapping o un provider compatible; como `PRODUCT ADAPTATION` cuando el CRM/provider exige una capacidad o cambio de contrato nuevo; y como `CUSTOM / OTHER PRODUCT` cuando la necesidad excede razonablemente LeadFlow. HubSpot interaction mediante Ticket es una capability real demostrada si el entorno, configuración y scopes requeridos están satisfechos; otros CRM deben evaluarse por sus propias garantías.

Si falta una respuesta dependiente del cliente o del entorno, se registra como pendiente o `NOT_VERIFIED`; no se convierte en promesa.

## Regla de reutilización

Un nuevo cliente no crea una copia divergente del core. La variación se resuelve preferentemente mediante configuración, adapters, mappings y environment. Un cambio de contrato o comportamiento requiere evaluación explícita como adaptación de producto. Los patrones útiles observados pueden registrarse como candidatos, pero no se elevan automáticamente a baseline corporativa.

## Entornos

### DEVELOPMENT

- Mocks y datos sintéticos.
- Proveedores reales bloqueados por defecto.
- Configuración local separada y fail-closed ya definida por LeadFlow.
- Se valida el cambio afectado sin contaminar producción.

### DEMO

- Entorno controlado, reproducible y con datos sintéticos.
- Sin efectos reales innecesarios ni credenciales expuestas.
- El Demo Sender de LAB-LF-005 es una herramienta aislada, no una interfaz productiva.
- Fallos/retries se muestran con evidencia preparada; no se añade un simulador al Sender.

### PRODUCTION

- Proveedores, credenciales e infraestructura reales y autorizados.
- TLS, IAM, backups/restore, red, permisos, monitoreo, logs, retención y operación se definen según el entorno.
- Los controles `HYBRID` y `ENVIRONMENT` se verifican con el deployment real y permanecen `NOT_VERIFIED` mientras no exista esa evidencia.
- Se completa el perfil de privacidad aplicable: finalidad, rol, jurisdicción, terceros, transferencias, retención, derechos y evaluación de impacto cuando corresponda.

## Handoff por modalidad

En Entrega técnica, el handoff identifica artefactos, configuración requerida, dependencias, límites, QA disponible y verificaciones que quedan a cargo del cliente. En Implementado por Emactiva añade evidencia del deployment autorizado, resultados de QA, cleanup, riesgos residuales, criterios aceptados y responsabilidades operacionales posteriores.

LeadFlow puede implementarse remotamente. El discovery operativo detallado, accesos, deployment, preflight, rollback, cleanup, handoff y responsabilidades están definidos por LAB-LF-006 en `LEADFLOW_REMOTE_DEPLOYMENT_RUNBOOK.md`; los controles dependientes del cliente se verifican en su entorno concreto.
