# Inspección de fuentes

Se inspeccionaron los archivos como paquetes XML. No se ejecutaron macros ni se recalcularon fórmulas.

## Libros

| Archivo | Hojas observadas |
|---|---|
| `Sistema_OT_MESA_Planta_Ramos_V3.xlsm` | `DASHBOARD`, `FORMULARIO_OT`, `BASE_DATOS`, `CATALOGOS` |
| `Mantenimiento PLANIFICADO RAMOS.xlsm` | `CALENDARIO`, `PREVENTIVO MAQ`, `PREVENTIVO INFREST`, `PREVENTIVO UNIDADES`, `DASHBOARD`, `BD`, `ALMACEN`, `CRONOGRAMA`, `MANTENIMIENTOS`, `MAQUINAS`, `PM`, `IMPRIMIR`, `BASE DE DATOS`, `Sheet1`, `Sheet2`, `GD`, `PERIODICO KAIZEN DE PENDIENTES`, `CALENDRIA` |
| `Periodico Kaizen.xlsx` | `CELDA AUTOMATIZACION`, `Hoja1` |

## Rangos y observaciones

- OT: `BASE_DATOS` declara `A1:P4`; hay tres registros de referencia.
- Mantenimiento: `MAQUINAS` declara `A1:L77`, `BASE DE DATOS` `A1:T23`, `CALENDARIO` `A1:XEW65453` aunque el contenido útil requiere conciliación. Las hojas de preventivos declaran rangos separados; no se aplicó un único calendario a todos los grupos.
- Kaizen: `CELDA AUTOMATIZACION` declara `A1:G29`; los avances requieren confirmación.
- Se conservaron como alertas de origen `#REF!`, `#DIV/0!` y `#N/A`; no se convierten en métricas de la aplicación.

La importación productiva queda pendiente de una etapa de análisis, conciliación y confirmación. Los libros no se mezclan con la semilla demostrativa actual.
