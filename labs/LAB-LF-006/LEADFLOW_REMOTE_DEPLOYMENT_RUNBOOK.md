# LeadFlow — Procedimiento de Implementación Remota

**Proyecto:** Emactiva LeadFlow  
**LAB:** LAB-LF-006 — Implementación Remota y Despliegue en Clientes  
**Estado:** Procedimiento operativo V1

## 1. Objetivo

Definir el proceso mediante el cual Emactiva puede implementar LeadFlow de forma remota en el entorno autorizado de un cliente, manteniendo seguridad, privacidad, trazabilidad, portabilidad y responsabilidades claras.

Este procedimiento parte de LeadFlow como producto ya desarrollado, probado y documentado.

No implica modificar el núcleo del producto para cada cliente.

Principio:

**Cambia el entorno, no el sistema.**

Las diferencias entre clientes deben resolverse preferentemente mediante:

- configuración;
- variables de entorno;
- credenciales externas;
- adapters o conectores;
- mappings o correspondencias de campos;
- parámetros del entorno.

## 2. Alcance

Este procedimiento cubre:

1. primer contacto técnico;
2. discovery;
3. clasificación del trabajo;
4. definición de alcance;
5. responsabilidades;
6. accesos;
7. preparación del entorno;
8. revisión previa;
9. instalación;
10. configuración;
11. migraciones;
12. pruebas iniciales;
13. primera ejecución controlada;
14. validación;
15. activación productiva;
16. cleanup;
17. rollback;
18. handoff;
19. soporte inicial acordado.

## 3. Fuera de alcance automático

No están incluidos por defecto:

- hosting;
- licencias;
- costos de APIs;
- soporte 24/7;
- mantenimiento ilimitado;
- servicio administrado;
- operación permanente del CRM;
- generación de leads;
- campañas;
- nuevas integraciones no evaluadas;
- nuevas funcionalidades del núcleo;
- cambios posteriores fuera del alcance acordado.

## 4. Flujo general

**Primer contacto técnico → Discovery → Clasificación → Alcance → Responsabilidades → Accesos → Preparación → Preflight → Deployment → Configuración → Migraciones → Smoke test → Primera ejecución controlada → Validación → Producción → Cleanup → Handoff**

El rollback permanece disponible durante todo el proceso desde el momento en que se modifica el entorno.

## 5. Conceptos principales

**Discovery — levantamiento inicial:** revisión para entender qué tiene el cliente, qué necesita y qué restricciones existen antes de modificar sistemas.

**Preflight — revisión previa:** comprobación de que todo lo necesario está preparado antes de comenzar la instalación.

**Deployment — despliegue:** instalación y puesta en funcionamiento de LeadFlow en el entorno autorizado.

**Smoke test — prueba mínima inicial:** comprobación rápida de que los componentes esenciales funcionan antes de realizar pruebas mayores.

**Rollback — vuelta atrás:** procedimiento controlado para regresar a un estado anterior si una instalación o cambio genera problemas.

**Cleanup — limpieza:** eliminación o revocación de datos, accesos y artefactos temporales utilizados durante pruebas.

**Handoff — entrega formal:** cierre de la implementación mediante documentación, responsabilidades, evidencias y pendientes.

## 6. Discovery

Antes de comprometer una implementación deben conocerse, cuando correspondan:

### Cliente y responsables

- organización o proyecto;
- responsable técnico del cliente;
- responsable funcional del cliente;
- responsable Emactiva;
- personas autorizadas para aprobar cambios.

### Proceso

- cómo llegan actualmente los leads;
- fuente o fuentes de leads;
- volumen aproximado cuando sea relevante;
- CRM o sistema destino;
- proceso actual ante duplicados;
- problemas que se busca resolver.

### Datos

- campos recibidos;
- campos necesarios;
- email disponible como identidad de búsqueda en LeadFlow V1;
- necesidad justificada de nombre;
- necesidad justificada de teléfono;
- datos enviados a terceros;
- finalidad del tratamiento;
- requisitos de retención.

### Integraciones

- CRM;
- servicio de enrichment si aplica;
- Slack o canal de alertas;
- sistema origen;
- APIs adicionales expresamente acordadas.

### Infraestructura

- entorno objetivo;
- servidor o infraestructura;
- sistema operativo;
- Docker y Docker Compose cuando corresponda;
- PostgreSQL;
- dominio;
- DNS;
- TLS;
- firewall;
- conectividad;
- almacenamiento persistente;
- backups;
- monitoreo existente.

### Privacidad y contexto

- jurisdicción;
- finalidad;
- terceros;
- transferencias conocidas;
- responsable del tratamiento;
- rol esperado de Emactiva;
- restricciones contractuales o regulatorias conocidas.

Durante discovery no deben solicitarse secretos innecesarios.

## 7. Clasificación del trabajo

### STANDARD / CORE

LeadFlow funciona con las capacidades ya existentes. Cambian principalmente valores de configuración.

### CONFIGURATION / INTEGRATION

Requiere configuración, correspondencia de campos o conexión con un proveedor compatible. No modifica el comportamiento del núcleo.

### PRODUCT ADAPTATION

Existe una necesidad real que requiere ampliar una capacidad o contrato de LeadFlow. Debe evaluarse y aprobarse como cambio del producto antes de implementarse.

### CUSTOM / OTHER PRODUCT

La necesidad del cliente excede razonablemente LeadFlow. No debe forzarse dentro del producto.

## 8. Responsabilidades

### Emactiva

Dentro del alcance acordado, Emactiva puede asumir:

- análisis técnico;
- revisión del entorno;
- configuración de LeadFlow;
- deployment;
- migraciones;
- configuración de adapters;
- pruebas técnicas;
- validación de integración;
- evidencia;
- documentación;
- cleanup;
- handoff.

### Cliente

El cliente debe asumir, según corresponda:

- contratación y propiedad de infraestructura;
- cuentas de proveedores;
- licencias;
- costos de APIs;
- autorización de accesos;
- aprobación de cambios;
- definición de finalidad;
- decisiones sobre datos;
- aceptación funcional;
- operación posterior.

### Responsabilidad compartida

Según el entorno pueden requerir coordinación:

- DNS;
- TLS;
- firewall;
- red;
- IAM;
- ventanas de mantenimiento;
- backups;
- restore;
- activación productiva;
- revocación de accesos.

## 9. Accesos y credenciales

Aplicar mínimo privilegio.

Solicitar únicamente los accesos necesarios para realizar el trabajo aprobado.

Por cada acceso debe conocerse:

- recurso;
- finalidad;
- nivel de permiso;
- responsable;
- mecanismo autorizado de entrega;
- duración;
- necesidad de revocación.

Preferir cuentas técnicas, tokens, API keys, permisos mínimos, accesos temporales y credenciales revocables.

Nunca almacenar secretos en Git, documentación, HANDOFF, capturas, logs ni plantillas del cliente.

## 10. Preparación del entorno

Antes del deployment debe confirmarse:

- entorno autorizado;
- recursos disponibles;
- persistencia disponible;
- mecanismo de configuración;
- mecanismo de secretos;
- conectividad requerida;
- base de datos;
- dominio cuando corresponda;
- DNS cuando corresponda;
- TLS previsto;
- ubicación de logs;
- backups definidos cuando correspondan;
- separación respecto de development y demo.

LeadFlow no debe adaptarse mediante hardcodes específicos del cliente.

## 11. Preflight

Debe comprobar como mínimo:

- alcance confirmado;
- responsables disponibles;
- entorno autorizado;
- configuración requerida identificada;
- secretos disponibles mediante mecanismo externo;
- endpoints definidos;
- PostgreSQL disponible;
- rol administrativo/bootstrap interno definido y separado;
- rol de migraciones definido;
- rol de aplicación definido;
- conectividad necesaria disponible;
- integraciones preparadas;
- migraciones identificadas;
- backup y restore definidos cuando correspondan;
- rollback previsto;
- datos sintéticos de prueba disponibles;
- cleanup definido;
- ventana de implementación autorizada.

Si existe un bloqueo crítico:

**NO SE EJECUTA EL DEPLOYMENT.**

## 12. Deployment

Secuencia general:

1. preparar el entorno;
2. cargar configuración;
3. inyectar secretos externamente;
4. preparar PostgreSQL;
5. ejecutar migraciones pendientes;
6. desplegar componentes;
7. configurar adapters;
8. configurar endpoint de entrada;
9. verificar disponibilidad inicial.

No se debe exponer innecesariamente PostgreSQL, n8n, Adapter ni servicios internos.

## 13. Configuración

Puede incluir:

- APP_ENV;
- host público;
- fuentes permitidas;
- proveedor CRM;
- proveedor de enrichment;
- endpoints;
- propiedades o mappings;
- retención;
- timeouts;
- retries;
- parámetros operacionales.

Los secretos no se incluyen en plantillas versionadas.

## 14. Migraciones

Las migraciones deben:

- estar versionadas;
- ejecutarse mediante el mecanismo oficial;
- mantener ON_ERROR_STOP;
- ejecutarse con rol de migraciones;
- comprobar que el rol de migraciones sea `NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION` y tenga CREATE solo en el schema LeadFlow;
- mantener separado el rol de aplicación;
- comprobar atributos y privilegios efectivos de cada rol, no solo la existencia de usuarios distintos;
- no editar migraciones ya aplicadas;
- no marcar versiones manualmente;
- no ejecutar cambios destructivos improvisados.

## 15. Smoke test

Debe comprobar, cuando corresponda:

- PostgreSQL disponible;
- n8n disponible;
- Adapter disponible;
- configuración aceptada;
- autenticación;
- comunicación interna;
- logs disponibles;
- endpoint esperado;
- ausencia de fallos críticos.

Si falla una condición crítica, se detienen las pruebas dependientes y se diagnostica el primer fallo real.

## 16. Primera ejecución controlada

La primera ejecución debe realizarse con un lead sintético o expresamente controlado.

Se valida:

**entrada → validación → idempotencia → CRM → enrichment → persistencia → trazabilidad → respuesta**

También debe repetirse el mismo evento para comprobar:

- detección de duplicado;
- referencia a la ejecución original;
- ausencia de efectos externos duplicados.

## 17. Validación previa a producción

Antes de habilitar tráfico real deben validarse las partes que cambian por el entorno del cliente.

Pueden incluir:

- CRM real;
- enrichment real;
- Slack;
- conectividad;
- autenticación;
- autorización;
- persistencia;
- TLS;
- red;
- IAM;
- backups;
- monitoreo.

No se repiten baterías históricas completas sin riesgo o cambio que lo justifique.

## 18. Activación productiva

LeadFlow puede pasar a tráfico real cuando:

- preflight: PASS;
- deployment técnico: PASS;
- smoke test: PASS;
- primera ejecución controlada: PASS;
- integraciones críticas aplicables: PASS;
- no existe FAIL crítico;
- rollback está disponible;
- riesgos residuales están documentados;
- el cliente aprueba la activación funcional.

## 19. Rollback

Debe definirse antes de producción para aplicación/workflows, configuración, base de datos, integraciones y tráfico.

No se presume que toda migración pueda revertirse automáticamente.

Cuando un rollback SQL no sea seguro, debe usarse restore o recuperación documentada.

Un rollback no debe romper las garantías de idempotencia ni provocar repetición ciega de efectos externos.

## 20. Cleanup

Después de las pruebas deben eliminarse o revocarse, según corresponda:

- leads sintéticos;
- contactos de prueba;
- archivos temporales;
- datos temporales;
- accesos temporales;
- tokens temporales;
- credenciales temporales;
- configuraciones de prueba;
- artefactos auxiliares.

Debe realizarse un post-check cuando sea técnicamente controlable.

## 21. Handoff

Al terminar la implementación se registra:

- cliente/proyecto;
- versión instalada;
- commit o release;
- entorno;
- componentes;
- integraciones;
- configuración necesaria sin secretos;
- migraciones;
- responsabilidades;
- backups;
- restore;
- monitoreo;
- rollback;
- retención;
- controles de privacidad;
- riesgos;
- WARN;
- NOT_VERIFIED;
- soporte incluido;
- soporte no incluido;
- pendientes;
- aceptación funcional.

## 22. Soporte posterior

La implementación puede contemplar una ventana inicial de estabilización según el acuerdo comercial.

No incluye automáticamente soporte permanente, hosting, monitoreo 24/7, mantenimiento ilimitado, nuevas integraciones, nuevas funciones, operación del CRM ni infraestructura ajena al alcance acordado.

## 23. Clasificación de controles

### SYSTEM — Sistema

Puede comprobarse sobre LeadFlow sin necesitar infraestructura real de cliente.

### HYBRID — Mixto

Una parte puede comprobarse sobre LeadFlow y otra depende del entorno real.

### ENVIRONMENT — Entorno

Solo puede demostrarse en la infraestructura concreta del cliente.

## 24. Estados

- **PASS:** requisito demostrado y satisfecho.
- **WARN:** existe un riesgo o desviación conocida que no bloquea necesariamente la implementación.
- **FAIL:** requisito aplicable incumplido.
- **N/A:** requisito realmente no aplica y existe justificación.
- **NOT_VERIFIED:** requisito aplica, pero todavía no existe evidencia suficiente o requiere infraestructura real.

`NOT_VERIFIED` nunca equivale a `PASS`.

## 25. Evidencia mínima para declarar una implementación PASS

Debe existir evidencia de:

- alcance confirmado;
- preflight completado;
- configuración validada;
- migraciones aplicadas;
- servicios desplegados;
- smoke test satisfactorio;
- primera ejecución controlada satisfactoria;
- duplicado comprobado;
- persistencia comprobada;
- cleanup resuelto;
- rollback definido;
- aceptación funcional del cliente;
- handoff completado;
- riesgos y pendientes registrados.

## 26. Principio final

El objetivo de una implementación remota de LeadFlow no es simplemente “dejarlo funcionando”.

Debe quedar:

**funcionando + probado + documentado + recuperable + entregado con responsabilidades claras.**
