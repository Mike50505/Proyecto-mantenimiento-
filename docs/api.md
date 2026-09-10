# Contratos de API implementados

## Estado vigente

Este documento describe únicamente las rutas existentes en el código actual. Checklists preventivos, horómetros, plantillas y ocurrencias avanzadas están implementados parcialmente; hallazgos, Kaizen, reportes XLSX/PDF e importación XLSX/XLSM todavía no están implementados.

Todas las rutas requieren la cookie de sesión, salvo `/api/health` y `/api/auth/login`. Los errores se devuelven como `{ "error": "..." }` con código HTTP 4xx/5xx.

## Autenticación y permisos

- `POST /api/auth/login`: `{ username, password }`; crea una sesión HttpOnly de 12 horas.
- `POST /api/auth/logout`: revoca la sesión actual.
- `POST /api/auth/change-password`: `{ current_password, new_password }`; cambia una contraseña temporal o vigente y registra la acción.
- `GET /api/auth/me`: devuelve el usuario autenticado, su rol y módulos visibles.
- `GET /api/catalogs`: devuelve catálogos necesarios para captura; el operador solo recibe su propia identidad y no recibe costos ni inventario.

Los roles actuales son Administrador, Jefatura, Técnico y Operador. El servidor valida permisos; ocultar una opción en la interfaz no concede acceso. Los permisos configurables por acción y área ya están activos para las operaciones implementadas; la matriz de trazabilidad conserva los alcances que todavía son parciales.

## Órdenes de trabajo

- `POST /api/orders`: crea una solicitud. Acepta `Idempotency-Key` o `idempotency_key`; repetirla devuelve la misma OT.
- `GET /api/orders` y `GET /api/orders/:id`: consulta con alcance por solicitante. La lista acepta `status`, `priority`, `area`, `technician_id`, `asset_id`, `from`, `to` y `q`; los filtros se aplican en el servidor.
- `PATCH /api/orders/:id`: edita campos operativos y exige `version`. Los técnicos solo pueden editar OT asignadas. Acepta `location`, `scheduled_at`, `closure_notes`, `closure_document_code` y `closure_document_revision`; modificar `requested_at` o `scheduled_at` exige permiso y `date_change_reason`.
- `POST /api/orders/:id/transitions`: `{ to, version, reason?, closure_notes?, closure_document_code?, closure_document_revision? }`. Soporta `Programada`, `En proceso`, `Pausada`, `Espera de material`, `Pendiente de validación`, `Completada`, `Cancelada` y reapertura a `Abierta` cuando corresponde. Terminar exige notas documentales.
- `POST /api/orders/:id/validate`: `{ version, comment? }`; requiere Jefatura o Administrador y valida una OT pendiente de validación.
- `GET/POST /api/orders/:id/time-entries`: `{ started_at, finished_at?, user_id?, pause_reason?, source? }`; rechaza fechas inválidas, intervalos invertidos y traslapes por persona.
- `GET /api/orders/export.csv`: exporta las OT visibles en CSV.

Terminar trabajo y validar cierre son acciones distintas. La versión evita sobrescribir cambios ajenos y la bitácora conserva transiciones, ediciones y registros de tiempo.

## Inventario

- `GET /api/inventory`: lista existencias, mínimos, máximos y alerta de bajo stock.
- `POST /api/inventory`: crea un artículo.
- `PATCH /api/inventory/:id`: actualiza datos del catálogo.
- `GET /api/inventory/:id/movements`: consulta el historial.
- `POST /api/inventory/:id/movement`: `{ type, quantity, version, request_key, unit_cost?, work_order_id?, return_of?, notes? }`.
- `POST /api/inventory/preview-import`: analiza filas CSV sin confirmar cambios.
- `POST /api/inventory/import`: confirma filas CSV previamente revisadas.
- `GET /api/inventory/template.csv` y `GET /api/inventory/export.csv`: plantillas y exportación CSV.

Los movimientos admiten Entrada, Salida, Devolución y Ajuste mediante la migración de integridad vigente. Las salidas, devoluciones, costos históricos, control de versión e idempotencia se procesan en comandos separados. El importador actual es CSV; aún falta el lote de conciliación para XLSX/XLSM.

## Activos, preventivos y paros

- `GET/POST /api/assets` y `GET/PATCH /api/assets/:id`: catálogo y expediente básico de activos.
- `GET/POST /api/preventives`: consulta y crea planes preventivos con versión, código de plantilla, aplicabilidad e instrucciones.
- `GET /api/preventives/:id/tasks`: lista tareas configuradas; exige `preventives.read` y acceso al área.
- `POST /api/preventives/:id/tasks`: `{ title, interval_unit, interval_value, anchor_date, version }`. Unidad `days` o `months`, intervalo entero de 1 a 1200, fecha ancla válida `YYYY-MM-DD` desde 1900. Exige `preventives.edit` y área; incrementa versión y guarda tareas en la revisión inmutable junto con auditoría. Rechaza versión antigua o plan con OT generada con 409. No interpreta frecuencias de texto libre existentes.
- `GET /api/preventives/:id/calendar?from=YYYY-MM-DD&to=YYYY-MM-DD`: proyecta fechas base por tarea para un horizonte inclusivo de hasta 366 días. Devuelve `{ configuration_pending, projection_only: true, occurrences: [{ task_id, occurrence_index, base_date }] }`. Exige lectura y área. Las proyecciones no crean OT ni registran ejecución o cumplimiento.
- `GET /api/preventives/:id/compliance?from=YYYY-MM-DD&to=YYYY-MM-DD&as_of=YYYY-MM-DD`: clasifica ocurrencias persistidas del período como `P` pendiente, `T` ejecutada en o antes de la fecha base, `D` ejecutada después, `V` vencida sin ejecución y `R` cancelada/excluida. Devuelve conteos, porcentaje en fecha base, definición y filas detalladas. `as_of` es opcional y sirve para cortes reproducibles; no crea ocurrencias ni OT.
- `PATCH /api/preventives/:id`: edita un plan sin OT generada; exige `version` y responde conflicto si está desactualizado.
- `GET /api/preventives/:id/revisions`: devuelve revisiones en orden descendente, con `version`, `snapshot`, `user_id`, `recorded_at`, `source` y `reason`. Exige `preventives.read` y acceso al área del activo.
- `POST /api/preventives/:id/order`: genera una OT canónica para un plan sin OT.
- `GET /api/preventives/:id/occurrences`: lista ocurrencias persistidas con OT, folio, fecha base, revisión y estado de OT; exige lectura de preventivos y área.
- `POST /api/preventives/:id/occurrences`: `{ task_id, occurrence_index, version }`, números enteros; índice desde cero. Exige `preventives.edit`, `orders.create` y área. Crea atómicamente la ocurrencia y su OT Programada, usando la fecha calculada y la revisión actual. Responde 201 en alta o 200 con `replayed:true` y la misma OT al repetir tarea/índice, incluso tras reiniciar. Nuevas ocurrencias con versión antigua: 409. Una tarea ajena al plan: 404.
- `POST /api/preventives/:id/occurrences/group`: `{ occurrences: [{ task_id, occurrence_index }], version }`. Agrupa dos o más tareas del mismo plan y activo cuando comparten fecha base, creando una sola OT y una ocurrencia persistida por tarea. La ejecución y el cumplimiento se conservan por tarea; repetir el mismo grupo devuelve la misma OT. Rechaza fechas base distintas, duplicados, conflictos o versión antigua.

`GET/POST /api/preventive-templates`: consulta o crea plantillas por familia. `POST /api/preventives/:id/apply-template` aplica una plantilla a un plan vacío, validando familia y versión.
- `GET/POST /api/preventives/:id/tasks/:taskId/checklist`: consulta o agrega ítems del checklist.
- `GET/POST /api/preventives/:id/occurrences/:occurrenceId/checklist`: consulta o guarda respuestas `Sí`, `No` o `N/A` por ocurrencia.
- `POST /api/preventives/:id/occurrences/:occurrenceId/reschedule`: reprograma la fecha operativa con motivo y versión, sin cambiar `base_date`.
- `GET /api/preventives/:id/upcoming`: proyecta próximos vencimientos y marca ocurrencias ya persistidas, sin crear OT.
- `GET/POST /api/assets/:id/meter-readings`: consulta o registra lecturas monotónicas de horómetro.

Una OT recurrente puede contener varias ocurrencias del mismo plan y fecha base; cada tarea conserva su identidad y cumplimiento. La fecha base y referencia histórica son inmutables y no se permite borrar la ocurrencia. La reprogramación cambia solo la fecha operativa de la OT y exige motivo/versionado. No hay planificador automático: la generación requiere invocar el comando explícitamente.
- `GET/POST /api/downtime-events`: consulta o crea un paro con activo, causa, fechas y OT relacionadas.
- `PATCH /api/downtime-events/:id`: cierra o corrige un paro con permiso de mantenimiento y motivo.
- `GET /api/agenda`: devuelve las OT abiertas visibles y el catálogo de técnicos activos para construir la agenda operativa.

Las altas y ediciones preventivas guardan una revisión inmutable y su auditoría en la misma transacción. Las nuevas OT generadas conservan la referencia a esa revisión; el detalle de OT devuelve `preventive_revision` con su contenido. La migración conserva únicamente la versión disponible como `migration-baseline`, sin atribuir autor ni reconstruir versiones anteriores; las OT previas sin referencia devuelven `null`.

El listado de preventivos permite consultar visualmente las revisiones. Las tareas tienen recurrencia calendario independiente: los meses se calculan desde la fecha ancla y se ajustan al último día disponible, recuperando el día ancla en meses siguientes. Las fechas son días calendario sin conversión de zona horaria. Esta política de fin de mes queda documentada como decisión de implementación.

La interfaz “Tareas y fechas” permite altas, listado, proyección, generación explícita, agrupación, checklist, próximos vencimientos, reprogramación y resumen de cumplimiento. El porcentaje usa T sobre ocurrencias elegibles; las fechas proyectadas sin ocurrencia persistida no entran al porcentaje. Faltan aplicabilidad validada, hallazgos, paros con cobertura completa de aceptación e indicadores avanzados.

El detalle de OT devuelve `preventive_execution` y, en OTs agrupadas, sus `items`. Terminar/validar/devolver/cancelar/reabrir registra eventos por ocurrencia. El checklist se consulta por tarea y se responde por ocurrencia; el horómetro se consulta/registra por activo con historial monotónico. La consulta `/upcoming` proyecta vencimientos sin crear OT.

## Auditoría

- `GET /api/audit`: consulta restringida a Jefatura y Administrador.

La bitácora conserva usuario, fecha, entidad, acción, valores anterior/posterior y motivo cuando aplica. Su cobertura completa de configuración, importación y documentos continúa pendiente.

## Compatibilidad con requisitos

La matriz de trazabilidad en `docs/requirements-traceability.md` es la fuente del estado RF/RNF. No se debe interpretar la existencia de una ruta básica como aceptación completa del requisito asociado.
