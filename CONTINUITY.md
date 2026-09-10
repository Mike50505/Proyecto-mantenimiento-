# Continuidad del desarrollo

## Estado vigente

La entrega del 8 de septiembre implementó y verificó el rediseño adaptable, los diálogos y pestañas, los comandos separados de salidas y devoluciones, el cierre y validación de OT, el control de conflictos, la migración de integridad y las pruebas base. Las bases local y Docker siguen siendo independientes.

`npm test` pasa actualmente con 9 pruebas. En la iteración 8 se validó sintaxis del servidor y los módulos de tareas/historial modificados. La revisión visual documentada está en `docs/visual-review`; no equivale a una auditoría completa en tablets reales, lectores de pantalla o zoom nativo.

## Alcance pendiente

La solución todavía no cumple todos los RF-01 a RF-56, RNF-01 a RNF-12 ni CA-01 a CA-24. La entrega verificada y la matriz de trazabilidad enumeran los faltantes: permisos por acción y área, catálogos y conciliación de activos, OT operativa completa, preventivos versionados, autónomos, inventario conciliado, Kaizen, indicadores, XLSX/PDF versionados, importación XLSX/XLSM, respaldo externo, restauración integral, HTTPS, rendimiento y accesibilidad completa.

Las decisiones D-01 a D-12 de planta siguen pendientes. Los libros Excel y la semilla demostrativa no deben mezclarse con operación real sin conciliación y aprobación.

## Iteración activa

La primera iteración funcional trabajó solo en seguridad y permisos:

1. permisos configurables por acción y área;
2. activación y administración segura de cuentas;
3. rechazo desde API de operaciones no autorizadas;
4. pruebas de permisos y de los escenarios CA-01/CA-03 relacionados.

La Iteración 2 dejó activos con identidad extendida, tipos adicionales y estado operativo separado. La Iteración 3 agregó filtros de servidor, ubicación sin activo, autorizaciones de fechas y notas documentales de cierre. La Iteración 4 agregó registro y cierre de paros, relación de OT del mismo activo y agenda básica por técnico. La Iteración 5 agregó versión optimista, datos de plantilla, aplicabilidad en texto libre, instrucciones y generación controlada de OT preventivas. El avance y el siguiente paso vigente se detallan abajo.

### Iteración 6 — historial preventivo (cerrada)

Se acotó el bloque anterior para conservar iteraciones cortas. Las altas y ediciones guardan revisiones inmutables con autor y fecha, junto con la auditoría en una transacción. Las nuevas OT preventivas referencian la revisión usada y la API permite consultarla. Las bases existentes conservan únicamente la revisión disponible, identificada como línea base de migración; no se inventa historial anterior.

Verificación: cinco pruebas aprobadas, incluyendo conservación de instrucciones anteriores, permisos de historial por área, protección contra borrado/edición, reversión ante fallo de escritura y migración repetible. Sintaxis validada en los JavaScript modificados. Sin cambios de interfaz en esta iteración.

### Iteración 7 — consulta visual y edición preventiva (cerrada)

El listado permite abrir el historial de revisiones, incluidas las de planes con OT generada. El diálogo muestra contenido, fecha/hora, identificador del autor y motivo; distingue la línea base migrada. La edición conserva responsable y estado, incluso cuando el responsable está fuera del catálogo activo o el estado es Vencido/Ejecutado. La aplicabilidad vacía se muestra como configuración pendiente.

Verificación: cinco pruebas de servidor aprobadas y revisión en Chrome con base temporal. Se comprobó la conservación de responsable/estado tras guardar instrucciones, consulta de dos revisiones, escape de contenido histórico, cierre con Escape y ajuste del diálogo a 390/768/1440 px. Reproducir con MESA_REVIEW_PREVENTIVES_ONLY=1 y node scripts/ui-review.cjs.

### Iteración 8 — tareas y cálculo calendario (cerrada)

Modelo y API para crear/listar tareas por plan con intervalos explícitos en días o meses. La fecha ancla es el primer vencimiento; cada tarea calcula sus fechas independientemente. Los meses conservan el día ancla, ajustándose al fin de mes cuando es necesario (decisión de implementación). El calendario de API es una proyección de consulta de hasta 366 días: no genera OT, no avanza por ejecución ni calcula cumplimiento. Las tareas se incorporan a las nuevas revisiones inmutables. Los planes históricos no se convierten automáticamente y los planes con OT conservan el bloqueo de edición.

Verificación: nueve pruebas aprobadas, con fin de mes, bisiestos, cambio de año, fechas inválidas, proyección repetible, intervalos independientes, conflictos, permisos por área y referencia histórica desde OT. Sin cambios de interfaz.

### Iteración 9 — tareas y fechas desde la interfaz (cerrada)

El listado de preventivos abre “Tareas y fechas”: lista tareas, permite altas con intervalo y primer vencimiento, y consulta una agenda proyectada con fechas desde/hasta. Muestra configuración pendiente, períodos sin fechas y errores de consulta; conserva la captura si guardar falla. El alta respeta permisos y el bloqueo de planes con OT. La interfaz explica que la proyección no genera OT recurrentes ni representa cumplimiento.

Verificación: nueve pruebas aprobadas y sintaxis validada. Chrome con base temporal comprobó dos altas consecutivas, fechas mensuales/trimestrales, escape de contenido, captura conservada ante conflicto, bloqueo con OT y ajuste a 390/768/1440 px. Reproducir con MESA_REVIEW_TASKS_ONLY=1 y node scripts/ui-review.cjs.

### Iteración 10 — ocurrencias persistidas y OT por vencimiento (cerrada)

API para consultar/generar ocurrencias por tarea e índice, con una OT Programada por ocurrencia y referencia a la revisión usada. Identidad y fecha base protegidas; generación atómica incluyendo folio y auditoría. Repetir tarea/índice devuelve la misma OT. La generación es explícita por API, sin planificador ni agrupación automática. Los planes con OT del flujo anterior requieren conciliación; se impide mezclar ambos flujos.

Verificación: nueve pruebas aprobadas con solicitudes simultáneas, mes siguiente, permisos, conflictos, reversión de OT/folio ante fallo, migración repetible y protección de identidad. Sin cambios de interfaz.

### Iteración 11 — generación y consulta desde agenda (cerrada)

“Tareas y fechas” combina la proyección con las ocurrencias guardadas: permite generar una OT por vencimiento y muestra folio, estado y apertura de la OT existente. La generación respeta permisos, bloquea doble clic y muestra conflictos sin cerrar el diálogo. Los planes con OT del flujo anterior muestran que requieren conciliación. Las fechas previstas siguen sin equivaler a ejecución o cumplimiento.

Verificación: nueve pruebas de servidor aprobadas, sintaxis y Chrome con base temporal. Se comprobó generación por doble clic sin duplicados, apertura de la OT, reapertura de agenda con folio persistido y ajuste a 390/768/1440 px. Reproducir con MESA_REVIEW_OCCURRENCES_ONLY=1 y node scripts/ui-review.cjs.

### Iteración 12 — ejecución ligada al flujo de OT (cerrada)

Terminar, validar, devolver a trabajo, cancelar o reabrir una OT con ocurrencia registra un evento preventivo inmutable en la misma transacción. La API expone estado de ejecución vigente y eventos con autor/fecha/notas. Reabrir o devolver conserva los cierres históricos y retira la ejecución/validación vigente; la fecha base y otras ocurrencias permanecen intactas. Se corrigió la comparación de texto que impedía persistir notas documentales al terminar. No se reconstruyen eventos anteriores ni se cambian fechas de recurrencia por cerrar una OT.

Verificación: nueve pruebas aprobadas, incluyendo terminación, devolución, segunda terminación, validación, reapertura, cancelación, rechazo de permisos y reversión atómica ante fallo. Sintaxis validada; sin cambios de interfaz.

### Iteración 13 — estado de ejecución en la interfaz (cerrada)

Las OT con ocurrencia muestran estado de ejecución, fecha base, fechas de terminación/validación y la línea de eventos con notas y motivos. La agenda de tareas refleja el estado de ejecución de las ocurrencias con OT. Las OT sin ocurrencia siguen usando el flujo normal y los planes anteriores sin eventos no reciben un estado inventado.

Verificación: nueve pruebas de servidor aprobadas, sintaxis validada y Chrome con base temporal. Se comprobó panel en OT, fecha base, historial de eventos, escape de contenido y ajuste del diálogo a 390/768/1440 px. Reproducir con MESA_REVIEW_OCCURRENCES_ONLY=1 y node scripts/ui-review.cjs.

### Iteración 14 — cumplimiento preventivo (cerrada)

Se agregó cálculo por ocurrencias persistidas para distinguir P (pendiente), T (ejecutada dentro de la fecha base), D (ejecutada después), V (vencida sin ejecución) y R (cancelada/excluida). El porcentaje es T entre ocurrencias elegibles; D cuenta como ejecutada pero fuera de fecha. `as_of` permite cortes reproducibles. La agenda muestra el resumen y no convierte fechas proyectadas sin OT en cumplimiento. La fecha base permanece intacta.

Verificación: diez pruebas aprobadas, con fin de plazo, atraso, vencimiento, cancelación, porcentaje, permisos y período invertido; revisión Chrome correcta. Sintaxis validada. Sin generación automática de ocurrencias.

El siguiente paso vigente es la iteración 15: agrupar tareas elegibles del mismo activo en una OT recurrente, conservando fecha base y cumplimiento por tarea. Después: horómetros y checklists en bloques separados. CA-10 y CA-11 todavía no están completos.

### Iteración 15 — OT recurrente agrupada (cerrada)

Las tareas del mismo plan y activo que comparten fecha base pueden generarse en una sola OT mediante `/occurrences/group`. Se conserva una ocurrencia por tarea, por lo que ejecución, historial y cumplimiento siguen siendo independientes. La operación es transaccional, valida versión, evita duplicados y rechaza fechas base distintas.

Verificación: once pruebas aprobadas, incluyendo agrupación y ejecución con múltiples tareas. Sintaxis validada.

El siguiente paso vigente es la iteración 16: horómetros y checklists en bloques separados. Aún faltan historial visual detallado, ocurrencias no persistidas en el corte, programación vigente/reprogramación, próximos vencimientos y plantillas por familia. CA-10 y CA-11 todavía no están completos.

### Iteración 16 — horómetros (cerrada)

Se agregó historial de lecturas por activo mediante `/api/assets/:id/meter-readings`. Las lecturas son monotónicas, actualizan el valor vigente y no pueden editarse por el campo directo del activo. Checklists quedan para la iteración 17.

Verificación: pruebas de alta, consulta, permisos, decremento y bloqueo de edición directa; sintaxis validada.

### Iteración 17 — checklists preventivos (cerrada)

Se agregaron ítems de checklist por tarea y respuestas por ocurrencia. Los ítems obligatorios deben responderse con `Sí`, `No` o `N/A`; cada respuesta conserva usuario y fecha, y las respuestas quedan vinculadas a la OT sin alterar la fecha base ni el estado de ejecución.

Verificación: 10 pruebas aprobadas, incluyendo alta, consulta, duplicado, obligatoriedad y permisos. Sintaxis validada.

El siguiente paso vigente es la iteración 18: mostrar y capturar el checklist desde la interfaz de preventivos/OT. Después continuarán historial visual detallado, reprogramación, próximos vencimientos y plantillas por familia.

### Iteración 18 — checklist en interfaz (cerrada)

La ventana “Tareas y fechas” permite configurar ítems por tarea y responder el checklist desde una ocurrencia con OT. Se muestran obligatoriedad, notas y respuestas; la interfaz conserva los permisos del backend y se actualizó la versión del recurso JS para evitar caché antiguo.

Verificación: sintaxis validada, 10 pruebas aprobadas y caché de `app.js` actualizado.

El siguiente paso vigente es la iteración 19: historial visual detallado de cumplimiento y ejecución por tarea. Después continuarán reprogramación, próximos vencimientos y plantillas por familia.

### Iteración 19 — detalle visual de cumplimiento (cerrada)

El resumen de cumplimiento ahora incluye un detalle desplegable por tarea y ocurrencia, con fecha base, clasificación P/T/D/V/R, motivo y fecha de ejecución. Se actualizó el recurso JS para evitar caché anterior. El cálculo de servidor no fue modificado.

Verificación: sintaxis validada y 10 pruebas aprobadas.

El siguiente paso vigente es la iteración 20: reprogramación controlada y próximos vencimientos.

### Iteración 20 — reprogramación y próximos vencimientos (cerrada)

Se agregó reprogramación controlada por ocurrencia, con motivo, versión de OT y auditoría; `base_date` permanece intacta. También se agregó `/upcoming`, que proyecta vencimientos en un período sin crear ocurrencias ni OT y marca cuáles ya están persistidos.

Verificación: 10 pruebas aprobadas, incluyendo fecha base conservada, período invertido y conflicto de versión. Servidor saludable.

El siguiente paso vigente es la iteración 21: integrar próximos vencimientos y reprogramación en la interfaz.

### Iteración 21 — próximos vencimientos y reprogramación en UI (cerrada)

La ventana de tareas ahora consulta próximos vencimientos y permite reprogramar ocurrencias con OT, solicitando nueva fecha y motivo. La fecha base se conserva y el backend sigue validando versión y permisos. Se actualizó el caché de `app.js`.

Verificación: sintaxis validada y 10 pruebas aprobadas.

El siguiente paso vigente es la iteración 22: plantillas reutilizables por familia de activo.

### Iteración 22 — plantillas por familia (cerrada)

Se agregó catálogo de plantillas preventivas reutilizables por familia de activo, con tareas, intervalos e instrucciones. Aplicar una plantilla valida familia, versión y que el plan no tenga tareas ni OT; la actualización y la revisión histórica ocurren en una sola transacción.

Verificación: 10 pruebas aprobadas, sintaxis validada y servidor saludable.

El siguiente paso vigente es la iteración 23: mejorar la administración visual del catálogo y la selección de plantilla desde preventivos.

### Iteración 23 — catálogo visual de plantillas (cerrada)

Preventivos muestra ahora acceso al catálogo de plantillas por familia, con código, familia, nombre y cantidad de tareas. La API de aplicación permanece controlada por familia, versión y estado del plan; la selección automática dentro del formulario queda como mejora posterior.

Verificación: sintaxis validada y 10 pruebas aprobadas.

El siguiente paso vigente es la iteración 24: integrar selección/aplicación de plantilla desde el formulario de alta y completar la revisión de trazabilidad.

### Iteración 24 — aplicación de plantilla desde alta (cerrada)

El formulario de alta de preventivos permite seleccionar una plantilla opcional. Al guardar, crea el plan y aplica la plantilla en un flujo controlado; si la familia no coincide, el backend rechaza la operación. El flujo de edición existente permanece separado.

Verificación: sintaxis validada, 10 pruebas aprobadas y caché de `app.js` actualizado.

El siguiente paso vigente es la iteración 25: revisión final de trazabilidad, contratos y regresión.

### Iteración 25 — revisión final del bloque preventivo (cerrada)

Se actualizaron `docs/api.md` y `docs/requirements-traceability.md` para reflejar plantillas, checklists, horómetros, agrupación, reprogramación y próximos vencimientos, retirando contratos obsoletos. Se ejecutó revisión de sintaxis y regresión completa.

Verificación final: 10 pruebas aprobadas y sin errores de sintaxis. El bloque preventivo avanzado queda funcional pero RF-21 a RF-34 continúan parciales por aplicabilidad validada, checklist autónomo, hallazgos y aceptación integral.

## Reglas de continuidad

- Ejecutar `node --check` sobre los archivos JavaScript modificados.
- Ejecutar `npm test` antes de entregar una iteración.
- No importar datos históricos a producción sin lote revisado.
- No declarar aceptación completa de una familia RF/RNF por tener únicamente una pantalla o una ruta básica.
- Mantener separados cierre técnico, validación autenticada, estado del activo, criticidad, OT y paro.
