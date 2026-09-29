# Backup y restore portable

El contrato base exige backup diario, retención rolling de 30 días, RPO máximo de 24 horas y RTO máximo de 8 horas. La custodia, el almacenamiento, las identidades y el mecanismo de cifrado se configuran por entorno; el cifrado es obligatorio. `config/backup-policy.json` es la fuente validable de estos límites.

Un restore se realiza en un entorno aislado, verifica integridad y migraciones, y antes de habilitar tráfico reaplica `dsr_tombstones` y solicitudes `restricted` desde la evidencia administrativa más reciente. Después se comprueba que un subject token borrado o restringido no puede crear una ejecución. Este mecanismo usa tokens HMAC no reversibles y no agrega email, nombre, teléfono ni payload a la copia.

La ejecución real de backup, expiración, cifrado, custodia, restore y medición de RPO/RTO permanece HYBRID/ENVIRONMENT y requiere evidencia del despliegue. Un restore no se declara correcto si omite la reaplicación DSR o si los controles del entorno siguen sin verificarse.
