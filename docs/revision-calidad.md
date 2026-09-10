# Revisión de calidad del alcance pendiente

**Revisión histórica.** Las correcciones posteriores de diseño, OT e inventario y sus pruebas están en [entrega-2026-09-08.md](entrega-2026-09-08.md). Ya se retiró la reconstrucción de salidas, se agregó Pendiente de validación como estado real, se exige versión para edición/transición y se condicionó la semilla a MESA_DEMO. Persisten los pendientes allí enumerados; esta lista anterior no refleja por sí sola el estado actual.

Esta revisión corrige afirmaciones de la entrega anterior. Cinco pruebas automatizadas pasan, pero no representan la aceptación completa de CA-01 a CA-24.

## Correcciones verificadas

- El operador recibe 403 al intentar PATCH de OT, validar cierre o ajustar inventario.
- Las consultas del operador excluyen costos y renglones internos de materiales. El catálogo no revela precios de almacén.
- Consultar tiempos de una OT ajena devuelve 403.
- Un error de existencia revierte también acciones, versión, costo y materiales de la OT.
- Fechas inválidas, duración cero e intervalos invertidos son rechazados por el cálculo temporal.
- La duración conserva precisión antes de sumar; sesenta intervalos de un minuto suman una hora.
- Las pruebas unitarias de tiempo ya no importan el servidor ni abren la base de trabajo.

## Defectos todavía pendientes

- La edición de materiales borra y reconstruye salidas: debe sustituirse por comandos de salida y devolución con historial inmutable, precios de origen e idempotencia transaccional.
- Completada se usa prematuramente antes de validar; falta Pendiente de validación como estado real y permisos técnicos explícitos.
- El control de versión es opcional y la interfaz no lo envía consistentemente.
- El arranque sigue sembrando demostraciones automáticamente y conserva el mecanismo administrativo anterior; no se ha implementado activación segura.
- Los permisos de técnicos no limitan todavía la operación a sus asignaciones y áreas.
- Las inspecciones anteriores de Excel fueron parciales: listar hojas y dimensiones no equivale a validar todas las filas. La afirmación de lectura completa necesita nueva evidencia.
- La documentación anterior contiene un rango incorrecto para BASE DE DATOS y afirma aislamiento de demostraciones que todavía no existe.
- Faltan implementación y aceptación completas de preventivos, autónomos, Kaizen, importador, XLSX/PDF versionados, respaldo y restauración y revisión visual.

No utilizar esta versión como solución aceptada para producción. No se han reiniciado los servidores existentes para publicar estas correcciones.
