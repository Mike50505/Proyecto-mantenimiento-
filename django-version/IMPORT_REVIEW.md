# Revisión inicial de libros para migración

Fecha: 23 de septiembre de 2026. Lectura de solo vista previa, sin ejecutar macros ni modificar la base Django.

| Libro y hoja | Filas con datos | Observación |
| --- | ---: | --- |
| Sistema_OT_MESA_Planta_Ramos_V3.xlsm / BASE_DATOS | 4 | Encabezado y tres OT con folios OT-RAMOS-001 a OT-RAMOS-003. Confirmar si son registros reales o ejemplos. |
| Mantenimiento PLANIFICADO RAMOS.xlsm / CALENDARIO | 104 | Requiere cotejo con el catálogo de activos y sus fechas base. |
| Mantenimiento PLANIFICADO RAMOS.xlsm / MAQUINAS | 77 | Incluye dos filas con el nombre/código TRANSFORMADOR ENERGIA; la segunda está en la fila 74. |
| Mantenimiento PLANIFICADO RAMOS.xlsm / BASE DE DATOS | 77 | También repite TRANSFORMADOR ENERGIA en la fila 74. La equivalencia con MAQUINAS requiere revisión. |
| Mantenimiento PLANIFICADO RAMOS.xlsm / ALMACEN | 5 | Los saldos y costos deben cotejarse con inventario físico; la hoja no los certifica. |
| Mantenimiento PLANIFICADO RAMOS.xlsm / MANTENIMIENTOS | 4 | Contiene IDs de activo que deben resolverse contra el catálogo antes de cargar OT históricas. |
| Mantenimiento PLANIFICADO RAMOS.xlsm / PM | 11 | La correspondencia con plantillas y aplicabilidad está pendiente. |
| Periodico Kaizen.xlsx | 2 hojas, 23 filas con datos en total | Deben conservarse estado, comentarios y procedencia sin inferir avance faltante. |

La vista previa integrada en Django detectó dos conflictos de código en el libro de mantenimiento. No se ha importado ningún registro. Antes de confirmar lotes se necesita decidir qué filas son operativas, resolver códigos repetidos y validar frecuencias, puntos de revisión, saldos y avance Kaizen con Mantenimiento.

## Mapeo provisional comprobado el 28 de septiembre de 2026

Las filas de los libros se leyeron de nuevo en modo de solo lectura. La API de lotes muestra campos identificados junto a las celdas originales. El mapeo se calcula durante la consulta; las celdas, fórmulas y decisiones de revisión persistidas no cambian.

| Hoja | Inicio | Campos identificados | Interpretación pendiente |
| --- | ---: | --- | --- |
| `MAQUINAS` | 2 | A ID de origen, B código, C marca, D modelo, E voltaje, F serie, G observaciones, K área | Confirmar nombre oficial, activos duplicados y códigos de origen. |
| `BASE DE DATOS` | 2 | A código, B nombre, C material, D marca, E modelo, F voltaje | G:T son puntos de revisión; no se traducen a tareas hasta acordar D-04. |
| `CALENDARIO` | 13 | B código, C nombre, D línea, F marca, G modelo, H voltaje | I:AF contienen pares planeado/estatus; no se infiere ejecución ni frecuencia. |
| `ALMACEN` | 2 | A código, B descripción, C unidad, D existencia original, E costo original | Saldos, unidades y precios requieren D-09 y conteo físico. |
| `MANTENIMIENTOS` | 2 | A ID, B ID de activo de origen, C fecha original, D hora, E clasificación, F descripción y campos históricos relacionados | Los seriales con formato de fecha muestran interpretación separada; personas y estados requieren validación. |
| `PM` | 2 | A ID de mantenimiento, B fecha original, C código de material, D descripción, E cantidad y F costo originales | Resolver referencias a mantenimiento y almacén antes de cargar. |
| `BASE_DATOS` del libro de OT | 2 | A folio, B fecha original, C:P solicitante, prioridad, clasificación, especialidad, ubicación, falla, acciones, técnico, horas, costo, estado y validador | Confirmar si las tres OT son reales o ejemplos; no activar personas ni reemitir folios. |
| `CELDA AUTOMATIZACION` del libro Kaizen | 6 | A ítem, B descripción, G comentarios | C:F son marcas de avance; no se convierten en porcentaje validado. |

La hoja `PERIODICO KAIZEN DE PENDIENTES` del libro de mantenimiento contiene columnas de catálogo de máquinas en las filas inspeccionadas, a pesar de su nombre. Permanece sin mapeo automático hasta confirmar su función. La comparación de activos ahora muestra valores distintos de nombre, marca, modelo y voltaje para revisión; ninguna diferencia se corrige automáticamente.

## Tipos de celda y fechas

El lector conserva el valor original y registra por separado si una celda es número, booleano, error de Excel, fecha u hora con formato reconocido. La migración `0010` añade esos metadatos a cada fila; la pantalla muestra la fecha interpretada y el sistema 1900/1904 cuando aplica. El serial 60 del sistema 1900 se deja como fecha no interpretable por la anomalía histórica de ese calendario. Las fechas que vienen como texto permanecen como texto hasta que se valide su formato por fuente.

La lectura de prueba, sin crear lotes, encontró en `Mantenimiento PLANIFICADO RAMOS.xlsm` 504 celdas con fecha, 2 con fecha y hora, 81 errores de Excel, 4 booleanos y 500 números; ninguna de las fechas detectadas quedó sin interpretar. En `Periodico Kaizen.xlsx` encontró 24 números. En `Sistema_OT_MESA_Planta_Ramos_V3.xlsm` encontró 15 números, 1 fecha y 2 horas; la fecha `28/08/2026` de `BASE_DATOS` se conserva como texto. Los tres libros usan el sistema de fechas 1900. La celda `MANTENIMIENTOS!C2` conserva `46224` y muestra `2026-07-21` como interpretación.

En libros que contienen `MANTENIMIENTOS`, `PM`, `MAQUINAS` y `ALMACEN`, **Revisar referencias** coteja `MANTENIMIENTOS.B` con el ID de `MAQUINAS.A`, `PM.A` con `MANTENIMIENTOS.A` y `PM.C` con `ALMACEN.A`. Señala coincidencia única, sin coincidencia, referencia ambigua o valor vacío. Al resolver un ID de máquina, también muestra el código y las filas homónimas de las hojas de activos, señala repeticiones dentro de una hoja y atributos distintos de nombre, marca, modelo o voltaje. Es un cruce de claves de origen; no crea OT ni movimientos de almacén y no demuestra que las filas sean registros reales.

La consulta se activa en el detalle cuando el libro contiene `MANTENIMIENTOS` y `PM`. La compilación Docker del 28/09/2026 y la consulta de salud respondieron correctamente; en esta iteración no se ejecutó la suite de pruebas.

El panel **Incidencias de lectura** reúne por fila errores de Excel y fechas numéricas con formato temporal que no pudieron interpretarse. Expone coordenada, valor original y fórmula, y enlaza a la fila completa para documentar una decisión de revisión existente. La búsqueda pagina a 50 filas y no corrige la celda ni aplica datos operativos.

### Hallazgos del cruce directo de claves (28/09/2026)

- `CALENDARIO` tiene seis códigos repetidos dentro de la hoja: `REBAB007`, `REBAB008`, `MESEMP09`, `PAENM044`, `FAENM046` y `ALENM06` (este último aparece cuatro veces).
- `MAQUINAS` y `BASE DE DATOS` repiten `TRANSFORMADOR ENERGIA` en las filas 4 y 74 de cada hoja. Otros códigos que aparecen en ambas hojas son coincidencias entre hojas espejo, por eso se reportan aparte de duplicados internos.
- No se encontraron IDs de origen repetidos en `MAQUINAS` o `MANTENIMIENTOS`, ni códigos repetidos en `ALMACEN`, ni folios repetidos en `BASE_DATOS` de órdenes.
- En `MANTENIMIENTOS`, la fila 4 no tiene ID de activo. En `PM`, la fila 4 refiere al ID de mantenimiento `3`, que no está en `MANTENIMIENTOS`. Los demás cruces de activo y material tuvieron una coincidencia única.

El panel de referencias del lote muestra claves repetidas dentro de cada hoja junto con las filas faltantes; los códigos iguales entre hojas espejo permanecen agrupados como coincidencias entre fuentes. El análisis de origen fue solo lectura y no registró lotes.
