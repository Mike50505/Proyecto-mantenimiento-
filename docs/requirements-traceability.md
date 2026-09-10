# Matriz de trazabilidad MESA

Estado revisado el 8 de septiembre de 2026. `T` es evidencia de conversación, `D` proviene de archivos y `S` es una decisión propuesta. Los libros se inspeccionaron como ZIP/XML sin ejecutar macros. Los registros históricos no se cargan como datos operativos sin conciliación.

| Requisito | Módulo | Estado actual | Decisión o pendiente | Aceptación |
|---|---|---|---|---|
| RF-01, RF-02 | Identidad y catálogos | Parcial | Perfiles actuales se deben ampliar a permisos por acción y área | CA-01, CA-03 |
| RF-03 a RF-06 | Activos | Parcial avanzado | Ya existen alias/código original, tipos Fixture/Herramental y estado operativo separado con causa; falta conciliación formal de duplicados, catálogo administrable y cobertura completa de historial | CA-07 |
| RF-07 a RF-16 | Órdenes de trabajo | Base implementada; flujo de cierre por completar | Separar terminar de validar; folio transaccional e idempotencia | CA-01, CA-02, CA-05 |
| RF-17 a RF-20 | Tiempo y paros | Parcial | Sesiones de trabajo y paros independientes, con relación de OT y agenda básica; faltan aceptación completa e indicadores avanzados | CA-04, CA-06 |
| RF-21 a RF-29 | Preventivos | Parcial | Revisiones, agenda y OT muestran ejecución; API/UI clasifican P/T/D/V/R, agrupan ocurrencias, permiten reprogramar, consultar próximos vencimientos, usar plantillas por familia, horómetros y checklists. Faltan aplicabilidad validada y aceptación integral. CA-10/11 pendientes | CA-07 a CA-12 |
| RF-30 a RF-34 | Autónomos y hallazgos | Parcial | Checklist preventivo por tarea/ocurrencia implementado; checklist autónomo y hallazgos todavía pendientes de definición y aceptación | CA-12, CA-13 |
| RF-35 a RF-40 | Inventario y costos | Parcial | Existe catálogo/movimiento base; falta salida atómica desde OT, devolución e histórico de costo | CA-14, CA-15 |
| RF-41 a RF-44 | Kaizen | Pendiente | Importar 20 actividades a zona de conciliación; avance requiere confirmación | CA-16 |
| RF-45 a RF-51 | Dashboard, exportes y documentos | Parcial | Falta corte configurable, indicadores con denominador, PDF versionado y XLSX | CA-17 a CA-19 |
| RF-52 a RF-56 | Auditoría, importación y operación | Parcial | Crear lote de importación, auditoría completa, respaldo/restauración y manuales | CA-20, CA-23, CA-24 |
| RNF-01 a RNF-12 | Calidad transversal | Parcial | Revisar 390/768/1440 px, teclado, conflicto, rendimiento y recuperación | CA-21 a CA-24 |

## Evidencia de archivos

- `Requerimientos_Mantenimiento_MESA.docx`: contiene la especificación v1.0 y CA-01 a CA-24.
- `Sistema_OT_MESA_Planta_Ramos_V3.xlsm`: hojas `DASHBOARD`, `FORMULARIO_OT`, `BASE_DATOS` y `CATALOGOS`; `BASE_DATOS` tiene 3 registros de referencia.
- `Mantenimiento PLANIFICADO RAMOS.xlsm`: 18 hojas. Se observaron rangos declarados más amplios que los datos y errores guardados `#REF!`, `#DIV/0!` y `#N/A`; no se importan automáticamente.
- `Periodico Kaizen.xlsx`: `CELDA AUTOMATIZACION` y `Hoja1`; la primera conserva las actividades a revisar, no un avance numérico certificado.

## Criterio de carga

Los libros permanecen como fuentes de conciliación. La aplicación no debe activar usuarios desde nombres de hojas ni convertir saldos, avances, duplicados o puntos de preventivo en operación confirmada.
