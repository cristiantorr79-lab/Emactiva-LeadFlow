# LeadFlow — Definición del servicio

## Posición y propósito

LeadFlow es el primer producto/servicio técnicamente terminado de Emactiva que entra en preparación comercial. Emactiva es la empresa y marca madre; LeadFlow es una oferta dentro de ella y no define por sí sola toda la empresa.

LeadFlow recibe y procesa inicialmente leads de forma confiable: valida y normaliza entradas, aplica idempotencia y deduplicación, coordina el CRM y el enrichment permitido, ejecuta retries controlados y mantiene trazabilidad y alertas sanitizadas. En V1 el email es la identidad de búsqueda. El producto no promete una interfaz productiva para usuarios finales.

Definición comercial aprobada: **LeadFlow ayuda a empresas a recibir y gestionar leads de forma más ordenada, evitando duplicados, reduciendo tareas manuales y manteniendo trazabilidad cuando algo falla.**

## ICP operacional preliminar

Hipótesis pendiente de consolidar con el estudio de mercado: empresa que recibe leads digitales recurrentes y sufre fricción por tareas manuales, duplicación, retrasos, falta de integración o baja trazabilidad. No se fija todavía un rubro, tamaño de empresa o país definitivo.

## Modalidades aprobadas

### 1. LeadFlow — Entrega técnica

Emactiva entrega el producto, su configuración documentada, documentación técnica y handoff. El cliente implementa, despliega y opera. Emactiva responde por la integridad de los artefactos y evidencias incluidos en el alcance; el cliente responde por infraestructura, credenciales, configuración del entorno, proveedores, despliegue, operación, seguridad operacional y aceptación.

### 2. LeadFlow — Implementado por Emactiva

Emactiva configura, integra, despliega y valida lo expresamente acordado. El cliente entrega información y accesos autorizados, valida finalidad y contexto aplicable, participa en decisiones de proveedores y realiza la aceptación funcional. Tras el handoff, el cliente asume la operación, salvo un acuerdo futuro separado. Esta modalidad no incluye servicio administrado, hosting permanente, monitoreo 24/7, mantenimiento continuo ni soporte indefinido.

## Clasificación del trabajo

| Clasificación | Criterio |
|---|---|
| `STANDARD / CORE` | LeadFlow se usa con capacidades y contratos ya soportados, variando solo valores previstos. |
| `CONFIGURATION / INTEGRATION` | Requiere configuración, mappings o conexión de un adapter compatible sin alterar el comportamiento del core. |
| `PRODUCT ADAPTATION` | Requiere ampliar una capacidad o contrato del producto; se estima y valida como cambio de producto. |
| `CUSTOM / OTHER PRODUCT` | La necesidad excede LeadFlow o constituye una solución diferente. |

La clasificación se confirma durante el diagnóstico; no se presume por el nombre del CRM o proveedor.

## Responsabilidades por modalidad

| Área | Entrega técnica | Implementado por Emactiva |
|---|---|---|
| Diagnóstico y alcance | Compartido; cliente confirma contexto | Compartido; Emactiva conduce la definición técnica |
| Artefactos y documentación | Emactiva entrega | Emactiva entrega y adapta según alcance |
| Infraestructura y cuentas | Cliente | Cliente provee/autoriza; Emactiva configura solo lo acordado |
| Secretos | Cliente los gestiona externamente | Cliente autoriza el mecanismo; Emactiva no los documenta ni versiona |
| Integración y deployment | Cliente | Emactiva, dentro del alcance y entorno autorizados |
| QA técnica | Cliente sobre su deployment; evidencia del producto incluida | Emactiva ejecuta QA acordada; controles de entorno requieren evidencia real |
| Aceptación funcional | Cliente | Cliente |
| Operación posterior | Cliente | Cliente después del handoff |

## Límites comerciales y técnicos

- Toda integración nueva se evalúa antes de confirmar alcance.
- Un CRM, proveedor o API nuevo no se considera automáticamente incluido ni compatible.
- Costos de terceros, licencias, infraestructura, soporte recurrente y nuevas funcionalidades no están incluidos automáticamente.
- Tampoco se incluyen por defecto hosting, costos de API, soporte 24/7, mantenimiento ilimitado, campañas, generación de leads, operación permanente del CRM ni integraciones futuras no evaluadas.
- Todo lo que no esté expresamente incluido en el alcance acordado se evalúa antes de implementarse.
- Pricing definitivo, suscripción, SLA y modalidad administrada se definirán en otra etapa.
- La adaptación de identidad a teléfono o WhatsApp está diferida.
- Privacidad, jurisdicción, rol de Emactiva, base aplicable, contratos y controles de infraestructura se confirman por cliente y deployment; no se infieren desde esta definición.
