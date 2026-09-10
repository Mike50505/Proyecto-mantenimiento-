# Prompt maestro para desarrollar la aplicación de mantenimiento MESA

Copia el contenido completo de este archivo en la IA que realizará el desarrollo. Si permite adjuntos, agrega los cuatro archivos originales. Si trabajará sobre una aplicación existente, dale acceso al repositorio y a sus instrucciones. El prompt incluye la especificación y el contenido de las tres plantillas preventivas para conservar el contexto.

---

Actúa como un equipo de trabajo integrado en una sola IA: analista de sistemas, diseñador de producto, desarrollador full stack y responsable de calidad. Tu tarea es IMPLEMENTAR una aplicación web funcional de gestión de mantenimiento para Manufacturas Especializadas S.A., Planta Ramos, a partir de la especificación incluida más abajo. Debes entregar software con persistencia real, permisos, flujos completos, pruebas relevantes y documentación. El objetivo del encargo no termina al mostrar una maqueta o describir una arquitectura.

## Instrucción principal y orden de autoridad

Respeta primero las instrucciones actuales del usuario y las restricciones del entorno. Después usa los requisitos expresos de la conversación y los datos validados de los archivos. La especificación adjunta distingue evidencia y propuestas: T es conversación, D es documento y S es sugerencia. Conserva esa distinción en las decisiones del proyecto. Los ejemplos históricos no son datos productivos certificados.

Si hay repositorio existente, inspecciona su estructura, README, instrucciones de agentes, dependencias, rutas, autenticación, datos y pruebas antes de editar. Extiende la arquitectura que ya funciona y conserva el trabajo del usuario. No reescribas todo por preferencia tecnológica ni integres automáticamente otra aplicación como Helian. Si no hay repositorio, crea uno con estructura clara y un monolito modular.

Si los originales están disponibles, inspecciona requisitos.txt y todas las hojas relevantes de los tres libros, incluyendo las filas fuera de filtros. No ejecutes macros. No importes datos de ejemplo a producción sin una decisión expresa. Si faltan archivos, usa esta especificación y los anexos para construir estructura, reglas e interfaz; declara qué datos requieren conciliación y qué no pudiste verificar.

No reutilices contraseñas, conversaciones de acceso ni nombres sueltos como credenciales. Las cuentas se crean mediante el flujo de administración y activación. Mantén secretos fuera del repositorio y archivos de ejemplo.

## Qué debes entregar

Una aplicación ejecutable desde navegador en computadora, tablet y celular. Debe cubrir todos los RF-01 a RF-56 y RNF-01 a RNF-12 del alcance P0/P1. P0 ordena el primer piloto y P1 completa la solución; no sustituyas lo pedido por un prototipo ni marques P1 como mejora descartada. P2 es opcional.

Entrega frontend y backend conectados, base de datos con migraciones, catálogos configurables, importador con vista previa, exportaciones XLSX/PDF, manuales, pruebas críticas y despliegue reproducible. Los botones y formularios visibles deben tener comportamiento real. No simules autenticación, movimientos o KPI con arreglos estáticos o almacenamiento local del navegador. Se permite una semilla demostrativa separada y rotulada, nunca mezclada con operación real.

Para un proyecto nuevo, utiliza una combinación mantenible; por ejemplo TypeScript, React, una API modular y PostgreSQL. Revisa documentación oficial y compatibilidad actual antes de fijar versiones; guarda archivo de bloqueo. Puedes elegir otro stack si el repositorio o el entorno lo justifican y conserva todas las garantías funcionales. Docker Compose es el despliegue inicial propuesto para servidor Linux. Evita microservicios y dependencias externas que no aporten al tamaño del proyecto.

## Método de trabajo

1. Resume los hallazgos y crea una matriz que relacione requisito, módulo, estado, decisión pendiente y prueba de aceptación. No cambies IDs para ocultar un requisito faltante.
2. Registra decisiones de arquitectura y producto. Prioriza los conflictos concretos: folios, activos duplicados, 14 puntos frente a 11 grupos, autónomos sin plantilla entregada, fechas/frecuencias y fórmula gerencial de disponibilidad.
3. Crea el modelo relacional y sus restricciones antes de conectar formularios con datos. Separa estado del activo, criticidad, OT, cumplimiento preventivo y avance de proyecto.
4. Implementa una sección vertical completa: iniciar sesión, crear solicitud, asignar, trabajar, registrar tiempos, terminar, validar, consultar y exportar. Verifica permisos en API desde el inicio.
5. Completa activos, paros, preventivos manuales, calendario y plantillas; después recurrencias por tarea, autónomos, inventario, costos, Kaizen e indicadores.
6. Integra importación, auditoría, reportes, restauración y documentación. Haz una revisión visual en móvil/tablet/escritorio y una revisión de reglas de negocio.
7. Continúa hasta cubrir el alcance o encontrar un bloqueo real de acceso/datos. Ante datos maestros faltantes, deja configuración explícita y avance revisable; no inventes información ni detengas módulos independientes.

Si la sesión termina por límite de contexto, deja un archivo de continuidad con lo implementado, comandos verificados, pendientes y siguiente paso. No afirmes “terminado” sin probar los flujos que lo sustentan. La puesta en producción requiere resolver las decisiones operativas que le correspondan al usuario; prepara el resultado instalable y revisable.

## Arquitectura y contratos de implementación

Organiza módulos de identidad/permisos, catálogo de activos, OT, tiempo/paros, planes y checklist, inventario/costos, Kaizen, reportes/documentos, importación y auditoría. Cada módulo tendrá validación de entrada, lógica de negocio, persistencia y pruebas donde haya riesgo real. La interfaz consume comandos de negocio; no modifica saldos ni estados críticos directamente en tablas genéricas.

Como propuesta de contrato, expón recursos equivalentes a /assets, /work-orders, /work-orders/:id/transitions, /work-orders/:id/time-entries, /downtime-events, /maintenance-plans, /preventive-occurrences, /checklist-templates, /checklist-runs, /findings, /parts, /stock-movements, /kaizen-projects, /reports y /imports. Respeta convenciones del proyecto existente si difieren. Documenta cuerpos, validaciones, permisos y errores con un esquema compartido u OpenAPI.

Las operaciones mutables críticas deben admitir identificador de petición o idempotencia y versión de registro. Devuelve un conflicto explícito si alguien editó el registro antes. Folios se generan mediante secuencia/contador transaccional con unicidad; nunca mediante COUNT + 1 en el navegador. La salida de material, su vínculo a OT y su costo se guardan en la misma transacción. Los filtros y agregaciones trabajan sobre el servidor y aplican permisos.

Implementa una tarea programada durable para generar ocurrencias y actualizar alertas; recuperar después de un reinicio no debe duplicar trabajos. Usa clave única por plan/tarea/ciclo y relaciones verificables con OT. Define cómo agrupar varias tareas debidas del mismo activo sin perder su frecuencia individual. La actualización del dashboard puede usar eventos o consultas periódicas moderadas; muestra última actualización y no modifiques capturas en curso al refrescar.

Guarda timestamps completos, zona de planta configurable y decimales para dinero/cantidades. No mezcles fecha de solicitud, programación, ejecución, validación, movimiento de material y fecha del informe. La creación de registros históricos debe conservar ambas fechas: la del evento y la de su captura/importación.

El importador debe trabajar en dos etapas: analizar/conciliar y confirmar. Conserva valores originales y errores por fila, identifica repetición de lote y permite resolver equivalencias sin modificar los originales. Interpreta hojas, tipos y celdas reales sin confiar en dimensiones infladas. No ingieras dashboard, tablas dinámicas o impresiones como registros nuevos. Escapa fórmulas peligrosas al exportar texto libre a CSV/XLSX y valida límites/tipos de archivos.

En PDF conserva contenido, código, revisión, folio, participantes y corte de datos. La validación es una acción autenticada registrada; no dibujes una firma manuscrita ni afirmes una firma digital certificada inexistente. Diferencia borrador de documento cerrado y guarda información suficiente para reproducir su versión.

## Dirección visual obligatoria

Busca una experiencia refinada inspirada principalmente en Apple, adaptada a una aplicación industrial de uso diario. Prioriza jerarquía tipográfica, agrupación clara, alineación, espacios, navegación estable y respuestas rápidas. Toma Google como referencia secundaria de claridad de controles y mensajes, sin mezclar estilos incompatibles.

Aplica los tokens de la especificación con componentes reutilizables. Usa listas compactas y panel de detalle para trabajo operativo; tarjetas solo donde agrupen información útil. Una acción primaria por contexto, etiquetas claras y estados explicados. Conserva códigos de activo como texto seleccionable/buscable. Diferencia valor faltante de cero con lenguaje visible.

Diseña primero las pantallas que realmente se usan: reporte del operador en móvil, ejecución del técnico en tablet, planificación de jefatura en escritorio y tablero de gerencia. No añadas una landing page comercial, banners promocionales o gráficos decorativos al sistema interno.

La interfaz debe soportar carga, vacío, error, permiso insuficiente, validación, guardado, desconexión y conflicto. Presenta los errores cerca del campo y conserva la captura cuando sea seguro. Los controles de mayor impacto tienen etiquetas inequívocas: “Terminar trabajo”, “Validar cierre”, “Confirmar salida”, “Registrar devolución” y “Reprogramar”.

Muestra el rojo para una máquina parada con texto/icono y causa. Muestra por separado criticidad del activo y prioridad de la solicitud. No dibujes gráficas con datos inventados para llenar espacio; en una base vacía presenta instrucciones para comenzar y “Sin datos suficientes” en métricas que lo requieran.

Verifica legibilidad a 390, 768 y 1440 px, con zoom 200 %, navegación por teclado y foco visible. La página completa no debe desbordar horizontalmente; una tabla ancha tendrá contenedor y alternativa móvil. Respeta movimiento reducido. El diseño debe ser consistente en los módulos secundarios, no solo en el dashboard.

## Pruebas y entrega final

Ejecuta CA-01 a CA-24 de la especificación con pruebas de integración o extremo a extremo según el riesgo, incluyendo concurrencia, permisos, cambio de día, pausas, reprogramación, horómetros, devoluciones, doble envío y cálculos sin datos. Añade pruebas unitarias a cálculo temporal, dinero, recurrencia e indicadores. No llenes el proyecto de pruebas que solo comprueban que existe una etiqueta.

Usa datos sintéticos conocidos para verificar cantidades. Como ejemplo: salida 3 de saldo 10 y devolución 1 deja 8; dos técnicos de 07:00 a 09:00 aportan 4 H-H; dos OT del mismo paro no duplican tiempo indisponible. Para el libro OT de referencia, verifica 3 registros, 2 completados, 1 en proceso, 13.5 H-H y 4,550 de materiales, explicando que no son resultados actuales de planta.

Entrega README con instalación/configuración, variables de ejemplo sin secretos, migraciones, inicio de sesión administrativo seguro, respaldo y restauración. Incluye documentación de requisitos/trazabilidad, modelo de datos, contratos de API, decisiones, manual por rol, importación/conciliación, plan de implantación, registro de cambios y resultados de pruebas.

En tu respuesta final distingue qué funciona, qué se probó, dónde se ejecuta, cómo iniciarlo y qué necesita dato o decisión de planta. Enumera los requisitos incompletos de forma honesta. No reportes como comprobado un comando que no ejecutaste ni una integración que no configuraste.

## Especificación funcional completa que debes implementar

La siguiente especificación forma parte integral de este prompt. Sus decisiones pendientes no autorizan a adivinar datos. Sus propuestas S son la base de implementación reversible mientras el usuario no establezca otra política. Las recomendaciones visuales y técnicas son propias del proyecto; no exigen comprar ningún sistema de terceros.

---

# Sistema de mantenimiento MESA · Planta Ramos

Especificación de requerimientos y necesidades · Versión 1.0 · 8 de septiembre de 2026

Documento de análisis para revisión y desarrollo. Distingue lo solicitado, la evidencia de los archivos y las decisiones propuestas; no equivale a una aprobación del responsable de planta.

## 1. Resultado esperado y necesidades

La aplicación debe centralizar la operación de Mantenimiento de Planta Ramos: recibir solicitudes, ejecutar y documentar trabajos, programar preventivos, capturar revisiones autónomas por turno, administrar activos y refacciones, seguir proyectos Kaizen y presentar resultados a gerencia. Debe funcionar mediante una URL desde computadora, tablet y celular, con una base de datos compartida.

La orden de trabajo (OT) será el registro central de una intervención. Un preventivo programado, una reparación y un trabajo derivado de un hallazgo deben vincularse con sus activos, responsables, tiempos, materiales y evidencias documentales. El tablero debe permitir pasar del indicador al detalle que lo explica.

Las necesidades de negocio identificadas son:

- **Capturar una sola vez:** eliminar la repetición entre formatos, calendarios y resúmenes de Excel.
- **Dar visibilidad a gerencia:** mostrar maquinaria parada, trabajo pendiente, actividades realizadas y gasto sin preparar manualmente cada junta.
- **Planear con anticipación:** distinguir mantenimiento programado, cumplido, atrasado y reprogramado; conocer también los activos sin plan.
- **Facilitar el trabajo en planta:** permitir reportar y actualizar desde las tablets existentes y celulares.
- **Conocer el esfuerzo real:** separar horas hombre, duración de la reparación, esperas y tiempo de paro.
- **Controlar materiales y gastos:** relacionar consumos con cada OT y activo, y vigilar mínimos y máximos.
- **Mantener trazabilidad:** conservar códigos de documentos, versiones, responsables, validaciones y cambios.
- **Documentar la implantación:** registrar situación inicial, decisiones, pruebas, capacitación y resultados del cambio.

## 2. Fuentes y hallazgos comprobados

Se revisó la transcripción completa y el contenido de las 24 hojas de los tres libros. Se inspeccionaron valores, fórmulas almacenadas, catálogos, estructura y elementos de formato relevantes. No se ejecutaron macros ni se auditó el código VBA; las fórmulas no se recalcularon con Excel. Los errores descritos son los valores guardados en los archivos.

| Clave | Archivo | Aporte principal |
| --- | --- | --- |
| T | requisitos.txt | Proceso deseado, usuarios, captura móvil, indicadores y documentación. |
| OT | Sistema_OT_MESA_Planta_Ramos_V3.xlsm | 4 hojas: formulario, base de OT, catálogos y tablero. |
| MP | Mantenimiento PLANIFICADO RAMOS.xlsm | 18 hojas: activos, calendario, 3 preventivos, materiales, costos y reportes. |
| K | Periodico Kaizen.xlsx | 2 hojas; seguimiento de 20 actividades en CELDA AUTOMATIZACION. |

**F01. La OT ya define el proceso principal.** OT/FORMULARIO_OT!B5:C27 contiene folio, solicitud, nómina, prioridad, clasificación, especialidad, área/máquina, falla, acciones, colaborador, inicio, fin, horas hombre, material, costo, estatus y validador. OT/BASE_DATOS!A1:P4 guarda 3 registros de referencia. El formulario contiene material utilizado, pero la base no tiene una columna específica para su detalle: debe corregirse con renglones de materiales relacionados.

**F02. Los catálogos requieren conciliación.** MP/MAQUINAS!A2:L77 y MP/BASE DE DATOS!A2:T77 contienen 76 renglones de activos cada uno; MP/CALENDARIO!A13:H108 contiene 96. Son renglones de origen, no un inventario físico validado. Aparecen códigos repetidos como MESEMP09 en el calendario. TRANSFORMADOR ENERGIA identifica dos registros con características distintas; no deben fusionarse automáticamente. El montacargas aparece en el calendario y no en el catálogo de 76 renglones.

**F03. Los puntos de revisión no tienen una correspondencia segura.** MP/BASE DE DATOS!G1:T1 tiene 14 columnas numeradas 1 a 13, con el 13 repetido; PREVENTIVO MAQ tiene 11 grupos. También existen valores “LO REALIZA PLANTA MTY”. Hace falta mapear cada columna a una actividad y separar aplicabilidad de quién la ejecuta.

**F04. Las frecuencias son por actividad.** MP/PREVENTIVO MAQ!A6:F16 tiene 11 grupos; PREVENTIVO INFREST!A6:F12 tiene 7; PREVENTIVO UNIDADES!A6:F12 tiene 7. Infraestructura incluye 3, 4 y 6 meses, aunque la plática menciona también 6 meses o un año. Unidades incluye intervalos de 250 y 500 horas combinados con meses. No corresponde aplicar una frecuencia única a todo el formulario.

**F05. Algunos indicadores actuales inducen a error.** OT/DASHBOARD!C8 cuenta únicamente “En Proceso” como pendientes; C10 cuenta la clasificación “Proyecto Kaizen” sin comprobar implementación. MP/DASHBOARD!F19 contiene #REF!; MP/MAQUINAS!J2, entre otras celdas, contiene #DIV/0!; MP/MANTENIMIENTOS!O4 contiene #N/A. Los nuevos KPI deben tener definiciones explícitas y tratar la falta de datos.

**F06. Hay inconsistencias históricas que deben conservarse para revisión.** El formulario propone OT-2026-004, mientras la base usa OT-RAMOS-001 a 003. Algunas clasificaciones y especialidades históricas no están en CATALOGOS. La tercera OT tiene hora de fin y sigue “En Proceso”: fin de una sesión y cierre administrativo pueden ser distintos. MP/PM mezcla fechas históricas, códigos y cantidades incompletas; no se debe importar cada renglón como consumo confirmado sin conciliación.

**F07. Kaizen necesita datos estructurados.** K/CELDA AUTOMATIZACION!A6:G25 contiene 20 actividades y comentarios; C5:F5 muestra 25, 50, 75 y 100, pero los avances de los renglones no están almacenados como porcentajes numéricos. Hay diferencias de formato. Importar el texto y dejar el avance por confirmar; cualquier interpretación visual debe pasar por revisión. MP/PERIODICO KAIZEN DE PENDIENTES contiene un listado de activos, pese a su nombre, y no debe importarse como 78 proyectos.

**F08. Existen códigos documentales que deben preservarse.** El calendario muestra RA- FO-IM-14 al pie y revisión 02, además de un encabezado antiguo con revisión 01. Infraestructura contiene RA-FO-IM-15 (Rev. 02). Debe validarse cuál es vigente y el código de cada tipo de documento; no inventar códigos corporativos faltantes.

**F09. Las fotos no forman parte del alcance inicial.** Aunque existe FOTOGRAFIA en MAQUINAS, la conversación prefiere comenzar con información sin fotos. Tampoco se entregó un checklist autónomo completo ni la presentación de métricas cuya fórmula de disponibilidad se menciona.

**F10. Hay hojas y estructuras auxiliares.** BD aporta responsables/áreas; ALMACEN, artículos; PM, consumos; CRONOGRAMA, asignación con fechas; IMPRIMIR, formato documental; GD y DASHBOARD, resultados derivados. Sheet1, Sheet2, CALENDRIA y Hoja1 no deben asumirse como fuentes maestras. CALENDARIO declara un rango usado mucho mayor que sus datos y su filtro termina antes de varios registros: la importación debe recorrer datos reales, incluso fuera del filtro.

## 3. Alcance, prioridades y decisiones

Cada requisito lleva un origen: **T** = pedido en la conversación; **D** = respaldado por un archivo; **S** = solución o mejora propuesta. Un requisito mixto conserva lo pedido, pero su implementación concreta sigue siendo propuesta. **P0** es necesario para el primer piloto funcional; **P1** completa el alcance solicitado y debe implementarse antes de considerar terminada la solución; **P2** es opcional. P1 no significa descartado.

**Incluido:** OT, activos de maquinaria/infraestructura/unidades/fixtures/herramental, preventivos, checklist autónomo, inventario básico, costos, Kaizen, dashboard, exportaciones, usuarios, auditoría y documentación.

**Opcional posterior:** fotos, QR, modo oscuro, captura completa sin conexión, integración con Helian/producción, avisos por correo, compras con aprobaciones multinivel y una presentación PowerPoint automática. Para las juntas se propone primero un modo de presentación del tablero y un resumen PDF.

**Fuera del alcance inicial:** nómina y cálculo de salarios institucional, contabilidad fiscal, facturación electrónica, ERP completo, control automático de maquinaria, sensores IoT y mantenimiento predictivo con IA. Referenciar una factura no implica emitirla.

**Decisiones de partida propuestas:** aplicación web interna para una planta, español de México, importes en MXN y zona horaria America/Monterrey, configurables. Acceso por URL no implica publicación abierta en Internet. La elección entre servidor de MESA o equipo dedicado queda pendiente; la aplicación debe admitir ambos. No se asume integración con la app Helian solo porque se utilizó como ejemplo.

## 4. Usuarios y permisos

Los perfiles son una propuesta basada en la separación operador/Mantenimiento y la administración de visibilidad mencionada. Una persona podrá tener varios perfiles; nombres en Excel no son cuentas activas ni determinan permisos.

| Perfil | Trabajo principal | Alcance propuesto |
| --- | --- | --- |
| Operador / solicitante | Reportar falla, revisar su turno, consultar solicitudes. | Su área y registros autorizados. |
| Técnico de mantenimiento | Diagnosticar, ejecutar, registrar tiempo y material. | OT asignadas y activos relacionados. |
| Jefatura de mantenimiento | Priorizar, asignar, programar, validar y reabrir. | Operación y resultados de planta. |
| Almacén / Tool Crib | Entradas, salidas, devoluciones y existencias. | Inventario y solicitudes de material. |
| Gerencia / consulta | Ver indicadores, detalle y reportes. | Lectura de información autorizada. |
| Administrador | Usuarios, catálogos, permisos y parámetros. | Administración; validación técnica solo con ese permiso. |

El permiso de cerrar, validar o modificar fechas debe asignarse explícitamente. Ocultar un menú no basta: el servidor también debe rechazar una operación no autorizada. La nómina identifica al usuario, pero no sustituye la autenticación.

## 5. Requerimientos funcionales

### A. Acceso, catálogos y activos

- **RF-01 · T/S · P0. Acceso compartido.** Inicio de sesión individual, cierre de sesión y navegación por perfil desde una URL. Se acepta cuando dos dispositivos ven el mismo registro guardado y un usuario no autorizado no obtiene sus datos.
- **RF-02 · T/D/S · P0. Catálogos administrables.** Administrar áreas, líneas, activos, especialidades, clasificaciones, prioridades, turnos y personal. Permitir desactivar valores conservando el historial; impedir eliminar referencias utilizadas.
- **RF-03 · T/D · P0. Maestro de activos.** Código, nombre/descripción, tipo, área, línea/ubicación, marca, modelo, serie, voltaje u otras características, observaciones y estado administrativo. Admitir instalaciones y vehículos sin obligar a llenar características eléctricas que no correspondan.
- **RF-04 · T/D/S · P0. Identificación estable.** Separar ID interno, código de negocio y alias/código original. Conservar ceros iniciales y guiones. Validar unicidad por planta; resolver duplicados mediante una tabla de equivalencias revisada.
- **RF-05 · T/S · P0. Estado operativo.** Registrar operativa, parada, en mantenimiento, operación restringida y sin información como propuesta de catálogo. Separarlo de la criticidad permanente del activo, prioridad de la OT y baja administrativa. Mostrar causa, última actualización y OT asociadas.
- **RF-06 · T/D/S · P0. Historial del activo.** Consultar OT, preventivos, hallazgos, paros, materiales y costos por activo. Permitir alta de un fixture o herramental nuevo y vincularlo a una solicitud, respetando permisos.

### B. Órdenes de trabajo

- **RF-07 · T/D · P0. Folio automático.** Generar año y consecutivo en el servidor. Formato propuesto OT-2026-0001, configurable tras validar el corporativo. Dos solicitudes simultáneas reciben folios únicos; conservar folio original de importación y no reutilizar cancelados. No prometer consecutivos sin saltos.
- **RF-08 · T/D · P0. Reporte del operador.** Autocompletar fecha y solicitante/nómina desde la sesión; pedir activo o instalación/ubicación, prioridad, clasificación y falla/necesidad. Especialidad opcional para el operador y confirmada por Mantenimiento. Los campos técnicos posteriores no bloquean el reporte inicial.
- **RF-09 · T/D · P0. Prioridades.** Conservar Paro de Máquina, Alta, Media, Baja y el valor Seguimiento del catálogo. Dar máxima visibilidad a Paro de Máquina. La semántica y orden de Seguimiento requieren validación; no eliminarlo ni inventar tiempos de respuesta obligatorios.
- **RF-10 · T/D · P0. Clasificaciones.** Preservar Mantenimiento Preventivo, Mantenimiento Correctivo, Mantenimiento Autónomo, Apoyo para ajuste de máquina, Daño de Herramental, Daño de Fixture y Proyecto Kaizen. Guardar equivalencias aprobadas para valores históricos diferentes.
- **RF-11 · T/D · P0. Especialidades.** Preservar Eléctrico 440V/110V/220V, Mecánica, Soldadura, Hidráulica/Neumática, Modificación de pieza y Reparación de activo. El catálogo organiza los trabajos; no certifica competencias ni autoriza intervenciones por sí solo.
- **RF-12 · T/D/S · P0. Asignación y atención.** Jefatura asigna responsable y, si participan varias personas, colaboradores. Mantenimiento completa diagnóstico, acciones/despiece, observaciones, programación, tiempos, materiales y estado. Conservar descripción original y correcciones auditadas.
- **RF-13 · D/S · P0. Ciclo de estados.** Soportar Abierta, En Proceso, Espera de Material, Completada y Cancelada. Añadir Programada, Pausada y Pendiente de validación como propuesta. Registrar autor y fecha en cada transición; una espera no se considera trabajo activo automáticamente.
- **RF-14 · T/D/S · P0. Cierre validado.** Terminar trabajo y validar pueden ser acciones distintas. Exigir acciones realizadas, responsables, tiempos coherentes, tratamiento de materiales y respuestas del checklist aplicable antes del cierre validado. Permitir trabajo sin materiales con costo cero explícito; ausencia de precio no equivale a cero.
- **RF-15 · T/D/S · P0. Edición y reapertura.** Permitir captura tardía y corrección autorizada con motivo, fecha anterior y nueva. Reabrir una OT conservando cierre anterior, historial y consumos. Cancelar requiere motivo y tratamiento de reservas/consumos, sin borrar el registro.
- **RF-16 · T/S · P0. Consulta operativa.** Buscar por folio, código, falla o responsable; filtrar por rango, área, tipo, prioridad, estado, técnico y activo. Mostrar abiertas, vencidas y asignadas; permitir detalle y exportación con los mismos filtros.

### C. Tiempos y paros

- **RF-17 · T/S · P0. Sesiones de trabajo.** Botones Iniciar, Pausar y Terminar, más captura manual autorizada. Guardar fecha y hora completas por técnico, cruzando medianoche o varios días. No calcular solo con HH:MM ni asumir que toda la noche fue trabajada.
- **RF-18 · T/S · P0. Horas hombre.** Sumar intervalos trabajados de cada participante, excluyendo pausas. Evitar doble conteo de intervalos superpuestos de una misma persona. Las asignaciones por sí solas no generan horas.
- **RF-19 · T/S · P0. Paro independiente.** Registrar inicio, fin, causa, activo y origen del paro, vinculado a una o varias OT. Crear una OT no prueba automáticamente que el activo está parado; para prioridad Paro de Máquina pedir confirmación del evento. Cerrar una OT no libera el equipo si queda otra causa activa.
- **RF-20 · T/S · P1. Carga de trabajo.** Mostrar agenda de técnicos, pendientes asignados, horas reales y duración estimada cuando exista. Advertir solapamientos de asignación y sobrecarga; no confundir duración estimada con capacidad laboral disponible.

### D. Preventivos y programación

- **RF-21 · T/D · P0. Tres familias de preventivos.** Crear plantillas versionadas para maquinaria, infraestructura y unidades móviles. Cada grupo conserva descripción completa, frecuencia, aplicabilidad, resultado, tiempo y materiales, más comentarios, responsable y control documental.
- **RF-22 · T/D/S · P0. Autocompletado por activo.** Seleccionar código y cargar marca/modelo, ubicación y actividades asignadas a ese activo. La matriz de aplicabilidad debe estar validada. Si no existe, informar “Configuración pendiente”; no adivinar ni aprobar todos los puntos.
- **RF-23 · T/D/S · P0. Programación mediante OT.** Crear una OT preventiva desde el flujo de OT y mostrar esa misma intervención en Preventivos. Los accesos desde calendario/activo abrirán el mismo formulario o comando. Una ocurrencia programada tendrá una OT canónica, sin recaptura ni duplicación.
- **RF-24 · T/D · P0. Calendario de mantenimiento.** Vista mensual, semanal y agenda; vista anual por activo y mes para continuidad con Excel. Permitir programar con al menos un mes de anticipación y cambiar el horizonte. Mostrar P, T, D, R y V con nombre completo y leyenda.
- **RF-25 · T/D/S · P0. Cumplimiento trazable.** P = planeado; T = ejecutado dentro de plazo; D = ejecutado fuera de plazo; V = abierto con plazo vencido. R es además un evento histórico de reprogramación, compatible con T/D/V. Conservar fecha base, fecha actual, ejecutado y validado; la reprogramación no debe borrar atrasos contra la base.
- **RF-26 · T/D/S · P1. Recurrencias por tarea.** Admitir meses, días y lecturas de horómetro. Generar trabajo por tareas efectivamente vencederas, agrupables en una OT del mismo activo. Mantener siguiente vencimiento por tarea para que una revisión mensual no reinicie una actividad trimestral no ejecutada.
- **RF-27 · D/S · P1. Intervalos mixtos.** Representar 1 mes/250 horas y 3 meses/500 horas; proponer “lo que ocurra primero” como política pendiente de validar con Mantenimiento. Guardar lectura base, lectura actual, fecha y origen. Sin lectura suficiente, mostrar condición por horas desconocida y mantener la fecha calendario.
- **RF-28 · T/D/S · P0. Reprogramación y cobertura.** Registrar motivo, autor, fecha anterior y nueva; advertir impacto. Mostrar activos sin plan activo, plantilla incompleta o fecha base faltante. Un equipo nunca programado no debe aparecer como preventivo cumplido.
- **RF-29 · D/S · P1. Ejecución interna o externa.** Modelar quién realiza cada actividad, incluyendo Planta MTY o proveedor cuando se confirme. “Lo realiza Planta MTY” no equivale a “No aplica”. Conservar seguimiento y validación sin crear automáticamente una operación multiempresa.

### E. Checklists autónomos y hallazgos

- **RF-30 · T · P1. Revisión por turno.** Operador selecciona activo y turno; el sistema carga la plantilla autónoma vigente. Guardar fecha operativa, turno, usuario, respuestas y observaciones. La fecha operativa debe resolver turnos que cruzan medianoche.
- **RF-31 · T/S · P1. Respuestas claras.** Distinguir Pendiente, Correcto, Anomalía y No aplica, según configuración. Aplicabilidad y resultado son datos diferentes. No marcar todos los puntos como correctos al abrir el formulario; conservar motivo de no aplicabilidad.
- **RF-32 · T/S · P1. Hallazgos accionables.** Una anomalía crea un hallazgo que permite generar o asociar una OT con activo, descripción y origen precargados. Proponer confirmación antes de generar; evitar una OT duplicada por reenvío o por cada consulta del mismo hallazgo.
- **RF-33 · T/S · P1. Cumplimiento del autónomo.** Ver revisiones esperadas, completadas, omitidas y con anomalías por turno/activo. La obligación depende de asignación del activo, calendario y turno activo, no de asumir que todas las máquinas trabajan siempre.
- **RF-34 · S · P1. Plantillas e historial.** Versionar preguntas, instrucciones y asignaciones. Una revisión cerrada conserva su versión original; cambios posteriores no alteran evidencia histórica. El checklist autónomo real debe entregarse/validarse antes del uso operativo.

### F. Inventario, Tool Crib y costos

- **RF-35 · T/D · P1. Catálogo de refacciones.** Código, descripción, unidad, ubicación, existencia, costo unitario, mínimo y máximo. Tomar ALMACEN como estructura inicial, no como saldo físico certificado. Diferenciar refacciones consumibles de fixtures/herramental reparables identificados como activos.
- **RF-36 · T/D/S · P1. Movimientos.** Registrar entrada, salida a OT, devolución, ajuste e inventario inicial, con cantidad, unidad, costo, fecha, usuario y referencia. La existencia proviene del historial de movimientos; los ajustes requieren motivo.
- **RF-37 · T/D/S · P1. Consumo ligado a OT.** Seleccionar artículo y cantidad en la OT; confirmar salida una sola vez en una transacción. Mostrar costo al momento de salida. La reapertura o un doble clic no descuentan nuevamente. Una devolución crea el movimiento inverso ligado al original.
- **RF-38 · T/S · P1. Mínimos y máximos.** Alertar bajo mínimo y sugerir reposición hasta máximo. Validar mínimo no negativo y máximo mayor o igual al mínimo. Las alertas no generan compras automáticamente. Si se habilitan reservas, mostrar existencia, reservado y disponible por separado.
- **RF-39 · T/D/S · P1. Gasto rastreable.** Mostrar materiales, mano de obra y servicios por separado, por OT, activo, área y período. Materiales consumidos y compras recibidas son métricas diferentes. Conservar precios históricos y moneda; no recalcular trabajos antiguos con el precio actual del catálogo.
- **RF-40 · T/D/S · P1. Referencias de compra.** Permitir proveedor, referencia de factura/compra y costo cuando corresponda; registrar material de compra directa sin duplicarlo en almacén. No exigir emisión fiscal ni construir cuentas por pagar. La base de costo de mano de obra y la valoración del inventario requieren decisión.

### G. Proyectos y periódico Kaizen

- **RF-41 · T/D · P1. Seguimiento de actividades.** Registrar título, descripción, responsable, fecha de registro, fecha compromiso, estado, avance y comentarios. Ofrecer hitos 0/25/50/75/100, con porcentaje numérico 0–100 y registro de actualizaciones.
- **RF-42 · T/D/S · P1. Relación con mantenimiento.** Vincular proyecto con activos, hallazgos y una o varias OT. Contar proyectos y OT por separado. El periódico incrustado en los preventivos alimenta este mismo módulo.
- **RF-43 · D/S · P1. Validación del avance.** Distinguir avance reportado de implementación validada. Un proyecto al 100 % sin validación no se presenta automáticamente como implementado. Registrar bloqueos, responsable del siguiente paso y fecha compromiso.
- **RF-44 · D/S · P1. Migración Kaizen.** Incorporar las 20 actividades de K con comentarios y procedencia. No convertir un porcentaje desconocido en 0 confirmado ni interpretar un comentario como cierre. Ofrecer tabla, tablero de estados y resumen exportable.

### H. Indicadores, alertas y documentos

- **RF-45 · T/D · P0. Dashboard operativo.** Resumir OT registradas, abiertas, completadas, críticas y en espera; mostrar máquinas paradas y pendientes prioritarios. Indicar fecha de actualización y separar situación actual de resultados del período.
- **RF-46 · T/D/S · P1. Dashboard gerencial.** Añadir actividades por tipo, fixtures y máquinas reparados, preventivos, autónomos, horas hombre, materiales, gasto y Kaizen. Cada indicador abre sus registros, conserva filtros y muestra fórmula/denominador consultable.
- **RF-47 · T/D/S · P1. Disponibilidad y confiabilidad.** Mostrar por separado porcentaje de equipos operativos al momento y disponibilidad temporal. Calcular MTTR/MTBF únicamente con datos y definiciones suficientes; de otro modo indicar “Sin datos suficientes”. No inventar la fórmula de la presentación no adjunta.
- **RF-48 · T/S · P0. Alertas dentro de la aplicación.** Priorizar paro de máquina, preventivos vencidos, solicitudes pendientes y, cuando se habilite inventario, bajo mínimo. Registrar lectura/atención cuando aporte valor; evitar notificaciones repetidas por el mismo evento.
- **RF-49 · T/D/S · P0. Exportación Excel.** Descargar OT y reportes filtrados con columnas tipadas y fechas completas; en P1 añadir activos, consumos, preventivos, autónomos y Kaizen. Exportar solo lo autorizado, sin contraseñas ni información interna de autenticación.
- **RF-50 · T/D/S · P0. Documentos PDF.** Emitir OT imprimible con folio, código documental, revisión, activo/ubicación, solicitud, ejecución, tiempos, materiales y validación. En P1 incluir formatos preventivos, autónomos y resumen mensual. Identificar borradores y conservar la versión usada al cierre.
- **RF-51 · T/S · P1. Presentación para juntas.** Vista de pantalla completa con período, maquinaria crítica, actividad, cumplimiento, gasto y pendientes; exportar resumen PDF con el mismo corte. Una exportación PPTX es mejora opcional pendiente de definir.

### I. Gobierno e implantación

- **RF-52 · T/S · P0. Auditoría.** Bitácora de creación, cambios relevantes, fechas editadas, estados, validaciones, reaperturas, inventario y configuración. Guardar quién, cuándo, qué cambió y motivo donde corresponda; acceso restringido a su consulta.
- **RF-53 · T/D/S · P0. Control documental.** Mantener tipo de formato, código, revisión, vigencia y aprobador. Conservar códigos originales y equivalencias de normalización. Un nombre de validador digitado libremente no sustituye una validación autenticada.
- **RF-54 · D/S · P0. Importación revisable.** Leer XLSX/XLSM sin ejecutar VBA; presentar vista previa, conflictos y errores por archivo/hoja/fila. Ofrecer confirmar lote válido, corregir o descartar. Importar primero catálogos y luego transacciones, sin duplicar al repetir un lote.
- **RF-55 · T/S · P0. Documentación del proyecto.** Entregar proceso actual/futuro, requisitos, decisiones, modelo de datos, instalación, operación, respaldo/restauración, pruebas, cambios, manual por rol y capacitación. Registrar responsables de aceptación y pendientes de arranque.
- **RF-56 · T/S · P0. Operación continua.** Despliegue en servidor de MESA o equipo dedicado encendido, con respaldo, recuperación y protección eléctrica mediante UPS prevista en la plática. Documentar responsables y ubicación; el software no sustituye estas necesidades físicas.

## 6. Contenido de las plantillas preventivas

Importar el texto completo de las actividades desde los archivos; la siguiente tabla identifica los grupos y frecuencias, sin sustituir sus instrucciones técnicas. Los procedimientos y frecuencias deben ser revisados por Mantenimiento para cada activo.

| Maquinaria · PREVENTIVO MAQ | Frecuencia del archivo |
| --- | --- |
| Reductores, cadenas, sprockets y tornillería | 1 mes |
| Sensores y limit switches | 1 mes |
| Sistema neumático y válvulas | 3 meses |
| Unidad y válvulas hidráulicas | 1 mes |
| Pistones hidráulicos y neumáticos | 3 meses |
| Servomotores y ejes CNC | 3 meses |
| Enfriamiento y ventilación | 1 mes |
| Baleros y bandas | 3 meses |
| Lubricación | 3 meses |
| Tablero y componentes eléctricos | 3 meses |
| Verificación de seguridad | 1 mes |

Infraestructura tiene siete grupos: iluminación/eléctrico general (3 meses), estructura/techumbres (6), accesos/puertas (3), instalaciones hidrosanitarias (3), redes generales de aire/agua (6), obra civil/pintura (6), seguridad/instalaciones especiales (4).

Unidades tiene siete grupos: fluidos/niveles (1 mes/250 h), mecánica/filtros (3 meses/500 h), hidráulico/izaje del montacargas (1 mes/250 h), llantas/frenos/dirección (1 mes), eléctrico/seguridad (1 mes), cabina/controles (1 mes), caja seca del camión (1 mes). Izaje y caja seca deben aplicarse según el tipo de unidad.

**Regla de modelado:** distinguir grupo y subactividad. Si el tiempo se captura por grupo, no sumarlo otra vez desde subactividades. Permitir un total por intervención cuando así se haya medido, señalando su modalidad. La plática menciona 50 minutos de trabajo y el archivo los coloca en el primer grupo: confirmar si corresponden al grupo o a la máquina completa.

## 7. Flujos y reglas de negocio

### Flujo de una solicitud correctiva

El operador reporta activo/ubicación y necesidad. Se genera folio y estado Abierta. Jefatura revisa clasificación y asigna. El técnico inicia y registra sesiones, diagnóstico, acciones y materiales; puede pasar a Espera de Material sin cerrar la OT. Al terminar registra el resultado y pasa a validación. El perfil autorizado valida y la OT queda Completada. Si hubo paro, la liberación del activo exige confirmar su condición y las demás causas abiertas.

### Flujo de un preventivo

Jefatura selecciona activo, plantilla y tareas con vencimiento; programa mediante la OT. Calendario y listado muestran la misma ocurrencia. El técnico ejecuta la versión asignada, registra respuestas, tiempos y consumos. Cierra ejecución y se valida. Se calcula cumplimiento contra fecha base y contra programación vigente, y se actualiza el próximo vencimiento de las tareas realizadas. Un nuevo hallazgo puede vincular otra OT sin duplicar la intervención preventiva.

### Flujo de revisión autónoma

El operador abre “Mi turno”, selecciona equipo y contesta puntos. Una anomalía abre un hallazgo con decisión de atender, asociar OT existente o crear solicitud. El checklist conserva sus respuestas, responsable y turno; se consulta su cumplimiento sin sumar cada punto como una OT independiente.

### Flujo de material

Almacén registra recepción con cantidad y costo. La OT solicita o selecciona material. Al confirmar entrega se registra salida y costo histórico; la disponibilidad cambia de forma atómica. Si regresa material, se registra devolución. Si la OT se cancela, las reservas se liberan; el consumo real permanece hasta que se documente su devolución. Los materiales de compra directa se identifican para evitar sumarlos dos veces.

### Reglas transversales propuestas

- Fechas de servidor para creación/auditoría; fecha real del trabajo editable bajo permiso y motivo. Guardar tiempo en UTC y mostrar zona de planta. La fecha de solicitud guardada no debe cambiar cada día como TODAY().
- Generar folios y movimientos dentro de transacciones; rechazar doble envío con una clave de idempotencia. Controlar actualizaciones simultáneas para no sobrescribir cambios ajenos silenciosamente.
- Mantener estados independientes: OT, estado operativo del activo, criticidad del activo, cumplimiento preventivo, avance Kaizen y disponibilidad del material.
- Conservar la fecha base de cada ocurrencia. Una recurrencia mensual usa meses calendario, no 30 días fijos; definir el ajuste de fin de mes. Una modificación de regla solo afecta ocurrencias futuras salvo acción explícita auditada.
- El planificador debe recuperar ejecuciones después de reiniciar y detectar ocurrencias vencidas, sin duplicar OT. La política de arrastre de tareas pendientes y el anclaje a fecha fija o última ejecución requieren configuración explícita.
- Para la primera ocurrencia se requiere fecha base o lectura base verificada. Un valor faltante crea pendiente de configuración; no una ejecución histórica inventada.
- No permitir stock negativo por defecto. Saldos iniciales y ajustes se aprueban con responsables operativos, sin alterar silenciosamente el historial.
- Los importes se manejan con decimales y reglas de redondeo documentadas. Las cantidades respetan unidad de medida; una caja no se descuenta como pieza sin conversión definida.
- La propuesta de valoración inicial es costo promedio ponderado en entradas; confirmar antes del uso contable. Las salidas guardan su costo unitario y las devoluciones referencian el costo de origen. Una tarifa laboral desconocida deja costo de mano de obra pendiente.

## 8. Definición de indicadores

Estas son definiciones propuestas para evitar ambigüedad. Todas requieren período, población elegible, exclusiones y acceso al detalle. Las cancelaciones se reportan aparte; no se suman como trabajo completado.

| Indicador | Regla propuesta |
| --- | --- |
| OT registradas | OT con solicitud dentro del período seleccionado. |
| OT completadas | OT con cierre validado dentro del período. |
| Pendientes actuales | Todas las OT no completadas ni canceladas al corte. |
| Activos reparados | Activos distintos en OT de reparación completadas del período. |
| Horas hombre | Suma de minutos activos por persona / 60. |
| Cumplimiento preventivo en tiempo | Ocurrencias debidas en el período ejecutadas dentro de fecha base / ocurrencias debidas elegibles × 100. |
| Cumplimiento autónomo | Revisiones completadas / revisiones esperadas elegibles × 100. |
| Kaizen implementados | Proyectos únicos con implementación validada en el período. |
| Costo de materiales consumidos | Salidas a OT menos devoluciones, a costo histórico. |

**Cortes y cohortes.** Registradas y completadas pueden pertenecer a grupos distintos; no forzar registradas = completadas + pendientes si se filtran por fechas diferentes. Permitir un análisis por cohorte de solicitudes cuando se quiera esa conciliación. El backlog a una fecha pasada debe reconstruirse desde el historial de estados. Las horas y paros se recortan al período consultado; las salidas/devoluciones se imputan por fecha de movimiento.

**Horas hombre versus duración.** Una persona de 07:00 a 09:00 aporta 2 H-H. Dos personas durante ese intervalo aportan 4 H-H; la duración transcurrida sigue siendo 2 horas. De 23:00 a 01:00 del día siguiente son 2 horas. De lunes 16:00 a martes 08:00 no se asumen 16 horas trabajadas si hubo pausa nocturna.

**Porcentaje de equipos operativos al momento.** Equipos operativos / equipos elegibles con estado conocido × 100, mostrando además cuántos equipos tienen estado desconocido y la cobertura de información. El subconjunto de equipos críticos usa exactamente la misma regla. Esta es una foto de estado, no disponibilidad temporal.

**Disponibilidad temporal.** (Tiempo programado de operación − tiempo indisponible dentro de ese programa) / tiempo programado de operación × 100. Sumar tiempos de equipos elegibles, unificar paros superpuestos por activo y recortar al calendario operativo. No promediar porcentajes por equipo sin ponderar. Debe confirmarse cómo se consideran paros planeados, operación restringida y equipos fuera de servicio. Sin calendario/horas y eventos confiables: “Sin datos suficientes”.

**MTTR y MTBF.** Proponer MTTR = tiempo activo de reparación asociado a fallas correctivas resueltas / número de eventos de falla resueltos; el tiempo se mide por evento y no suma personas simultáneas. Proponer MTBF = horas efectivas de funcionamiento de activos reparables / eventos de falla del período. Definir catálogo de falla, agrupar OT del mismo evento y excluir preventivos. Con cero fallas o horas insuficientes mostrar “No calculable” con el motivo, no infinito ni 100 %.

**Costos y completitud.** Costo de intervención = materiales netos + mano de obra conocida + servicios. Mostrar subtotal conocido y número de registros sin costear cuando falten precios. Las compras son desembolsos/recepciones de otro reporte. Para el dashboard de referencia de OT hay 3 registros, 2 completados, 1 en proceso, 13.5 H-H y 4,550 de materiales; sirven para conciliar la importación, no para afirmar la situación actual de planta.

## 9. Interfaz limpia, con referencia principal en Apple

La dirección visual propuesta toma de Apple jerarquía, consistencia, navegación clara y adaptación al dispositivo; como referencia funcional se revisaron Odoo Maintenance y MaintainX. Se propone combinar listas operativas, ficha del activo, calendario y material ligado a OT. Los siguientes tokens y pantallas son una propuesta propia para MESA, no especificaciones oficiales de Apple ni una copia de esos productos.

**Identidad:** aplicación de trabajo sobria y clara, con blanco y grises, tipografía de sistema, acento azul, bordes suaves y separación generosa. La inspiración es la organización de Ajustes, Mail, Calendario y Finder. Priorizar la lectura de datos y la rapidez de captura. Evitar convertir todos los registros en tarjetas enormes o esconder acciones esenciales para obtener una pantalla vacía.

| Elemento | Propuesta visual para la web |
| --- | --- |
| Fondo y superficie | #F5F5F7 y #FFFFFF. |
| Texto principal / secundario | #1D1D1F / #636366, verificando contraste. |
| Acción primaria | #0066CC con texto blanco y estado de foco visible. |
| Bordes | #D2D2D7; separadores discretos. |
| Estados | Verde oscuro: correcto; ámbar oscuro: advertencia; rojo oscuro: crítico; siempre con texto/icono. |
| Tipografía | -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif. |
| Tamaños | Cuerpo 15–16 px; títulos 24–32 px; cifras destacadas 28–36 px. |
| Geometría | Espaciado 4/8/12/16/24/32 px; radios 10–14 px. |
| Interacción | Controles táctiles de al menos 44 × 44 CSS px como objetivo del proyecto. |

No distribuir archivos de SF Pro o SF Symbols como recursos web por asumir que su uso es libre; utilizar fuentes del sistema y un conjunto de iconos con licencia compatible. Aplicar una sola familia de iconos. Reservar transparencias suaves para la navegación cuando no perjudiquen legibilidad/rendimiento; las tablas y formularios deben tener fondo legible.

**Navegación de escritorio:** barra lateral de aproximadamente 232 px con Inicio, Órdenes, Preventivos, Checklist de turno, Activos, Inventario, Kaizen y Reportes; Configuración al pie y solo según permisos. Encabezado con título, filtros relevantes y una acción primaria. Búsqueda contextual visible. Permitir lista con panel de detalle en pantallas amplias.

**Móvil/tablet:** panel lateral colapsable en tablet; en móvil, navegación inferior para Inicio, Órdenes, Checklist y Más, adaptada al rol. Formularios de una columna, selectores de activo buscables y botones accesibles con el pulgar. Convertir listados a filas compactas con prioridad, folio, activo y estado. La vista anual tendrá alternativa de agenda; no forzar una cuadrícula de doce meses en una pantalla angosta.

**Pantallas mínimas:** acceso; dashboard; listado y detalle de OT; crear solicitud; capturar ejecución; calendario/agenda preventiva; editor de plantillas y aplicabilidad; checklist de turno; listado/ficha de activo; inventario/movimientos; Kaizen; reportes; usuarios/permisos; importación con conflictos y control documental.

**Diseño de OT:** bloque de solicitud, bloque técnico y cierre progresivo según rol. En escritorio, detalle por pestañas Resumen, Trabajo, Materiales e Historial. Encabezado persistente con folio y estado; acciones contextuales Iniciar, Pausar, Registrar material, Terminar y Validar. No colocar todo en una tabla editable de Excel.

**Dashboard:** primero alerta de máquinas paradas y trabajo urgente; luego 4–6 indicadores principales, gráficos de tendencia/composición y una tabla de pendientes. Filtros por período, área, tipo y criticidad. Los colores intensos deben guiar hacia excepciones. El estado crítico usa rojo, icono y texto “Parada”, con causa y duración.

**Estados de interfaz:** carga con esqueletos discretos; vacío con siguiente acción; error con mensaje específico y reintento; guardado confirmado; conflicto con opción de revisar cambios; desconexión visible sin afirmar que se guardó. Botones deshabilitados explican el motivo. Recuperar foco al cerrar un diálogo y navegar completamente con teclado.

**Calidad visual:** contraste medido, textos al ampliar al 200 %, foco visible, etiquetas persistentes, mensajes junto al campo y movimiento reducido cuando el usuario lo solicite. Objetivo de proyecto: WCAG 2.2 AA, a verificar, sin afirmar certificación. Probar a 390, 768 y 1440 px, más las tablets reales de planta.

## 10. Datos y arquitectura sugeridos

Es una recomendación técnica, no un requisito impuesto por la conversación. Si existe una aplicación previa, inspeccionarla y extenderla coherentemente. Para un desarrollo nuevo: aplicación web con interfaz, API y base relacional; monolito modular y despliegue reproducible en Linux mediante Docker Compose. PostgreSQL es una opción inicial razonable; puede conservarse otro motor ya establecido si cumple transacciones e integridad. No fijar versiones sin verificar soporte y compatibilidad al implementar.

| Entidad o grupo | Información/relación indispensable |
| --- | --- |
| Planta, área, línea, ubicación | Jerarquía y parámetros operativos. |
| Usuario, perfil, permiso, personal | Autenticación separada de nómina y personas históricas. |
| Activo y alias | Identidad, tipo, ficha, ubicación, estado y criticidad. |
| OT y asignación | Solicitud, clasificación, prioridad, responsables y fechas. |
| Sesión de trabajo | Persona, OT, inicio, fin, pausa/origen y correcciones. |
| Evento de paro y vínculo OT | Activo, intervalos, causa y liberación. |
| Plantilla, versión, grupo e ítem | Instrucciones y frecuencia por actividad. |
| Aplicabilidad por activo | Ítem, aplica, responsable interno/externo y vigencia. |
| Plan y ocurrencia preventiva | Base, vencimiento, revisión de agenda y OT única. |
| Medidor y lectura | Horómetro, valor, fecha, origen y reinicios registrados. |
| Turno y calendario operativo | Obligaciones de revisión y horas programadas. |
| Ejecución checklist y respuesta | Versión, turno, activo, resultado y observaciones. |
| Hallazgo | Origen, gravedad, estado y OT asociada. |
| Artículo y ubicación de almacén | Unidad, umbrales y costo de referencia. |
| Movimiento y renglón de material OT | Cantidad, costo histórico, origen y devolución. |
| Proyecto Kaizen y actualización | Avance, fechas, bloqueo, validación y vínculos OT. |
| Documento y revisión | Código, formato, vigencia y representación histórica. |
| Auditoría, alerta y lote de importación | Eventos, notificación, procedencia y resolución de errores. |

Integridad mínima: claves foráneas, índices de búsqueda, folio único, cantidad válida, tiempo final posterior al inicial y una OT por ocurrencia. Una OT puede referirse a una ubicación aun sin máquina, para atender infraestructura. En el piloto se propone un activo principal por OT; los proyectos pueden relacionar varios. Mantener snapshots de nombres/precios/versiones necesarios para reproducir documentos históricos.

La API debe cubrir autenticación, catálogos, búsqueda, OT y transiciones, sesiones, paros, planes y ocurrencias, checklist, inventario, Kaizen, indicadores, exportación e importación. Aplicar permisos, validación y reglas de negocio en servidor. La interfaz no calcula saldos finales ni autoriza cierres por su cuenta.

## 11. Requerimientos no funcionales y necesidades operativas

- **RNF-01 · T/S · P0. Usabilidad:** completar el reporte básico desde celular sin navegar por todos los módulos. Objetivo propuesto: menos de 2 minutos con catálogo correcto; validar con operadores reales.
- **RNF-02 · T/S · P0. Compatibilidad:** navegador en Windows, Linux, Android y iOS/iPadOS; confirmar versiones mínimas en las tablets disponibles. Sin requerir Excel instalado para trabajar.
- **RNF-03 · S · P0. Seguridad:** autenticación, permisos por acción/área, contraseñas con hash seguro, sesiones revocables y HTTPS en el despliegue. No usar credenciales mencionadas incidentalmente en la conversación.
- **RNF-04 · S · P0. Integridad:** transacciones en folios, movimientos y cierres; idempotencia y control de concurrencia. Registrar fallos sin exponer datos sensibles.
- **RNF-05 · S · P0. Rendimiento:** objetivo inicial propuesto de 20 usuarios concurrentes, consulta habitual p95 menor de 2 s y actualización del tablero menor de 30 s en LAN, con volumen de prueba documentado. Son metas de diseño, no mediciones ni cifras confirmadas por los archivos.
- **RNF-06 · T/S · P0. Disponibilidad:** servicio con reinicio automático y datos persistentes. En red interna puede funcionar sin Internet si servidor, LAN, autenticación y recursos locales siguen disponibles. Perder Wi‑Fi o acceso al servidor es un caso diferente; no se incluye sincronización offline completa.
- **RNF-07 · T/S · P0. Continuidad:** respaldo automático y copia fuera del equipo servidor, retención definida y prueba de restauración. Proponer respaldo diario, RPO ≤ 24 h y RTO ≤ 4 h, sujetos a aprobación operativa.
- **RNF-08 · T/S · P0. Trazabilidad:** conservar procedencia de importación, cambios y versiones de documentos; política de retención pendiente. No afirmar cumplimiento de una norma o auditoría por generar un PDF.
- **RNF-09 · S · P0. Accesibilidad:** teclado, lectores de pantalla, contraste, zoom y estados que no dependan solo de color; incorporar verificaciones automáticas y revisión manual.
- **RNF-10 · T/S · P0. Mantenibilidad:** estructura modular, migraciones de base, configuración separada, registro de versiones, documentación y pruebas de las reglas críticas.
- **RNF-11 · S · P0. Portabilidad:** instalación repetible en un equipo limpio, exportación de datos y procedimiento de migración/restauración; evitar servicios externos obligatorios para la operación LAN.
- **RNF-12 · S · P0. Privacidad y recuperación de captura:** acceso a costos/nómina por permisos; guardado de borradores controlado, mensajes de desconexión y prevención de pérdida accidental. Limpiar datos del usuario al cerrar sesión en tablets compartidas.

Necesidades fuera del código: responsable funcional de Mantenimiento; responsable de catálogos/inventario; disponibilidad de operadores para validar; servidor encendido; espacio y alimentación protegida; UPS; cobertura Wi‑Fi/LAN; nombre interno o dominio; respaldo externo; procedimiento de soporte y restauración; formatos y códigos aprobados; tiempo para capacitación y conciliación inicial.

## 12. Migración y puntos por confirmar

### Migración propuesta

Crear una zona de importación separada de los datos operativos. Conservar archivo, hoja, fila, valor original, valor normalizado, fecha de importación y responsable de conciliación. No ejecutar las macros. Interpretar formatos de fecha y hora con el sistema de fechas del libro; distinguir cadenas, números y valores de error.

Importar candidatos de activos desde CALENDARIO, MAQUINAS y BASE DE DATOS; comparar código, nombre, marca, modelo y ubicación. Aprobar equivalencias y duplicados antes de la carga definitiva. Después cargar catálogos, plantillas completas, aplicabilidad revisada, OT históricas, existencias verificadas y Kaizen. No activar cuentas a partir de nombres sueltos ni reemitir folios históricos.

Validar referencias de MANTENIMIENTOS y PM con su catálogo de IDs de origen. Preservar registros incompletos como incidencias revisables. No importar tablas dinámicas, dashboard y hoja IMPRIMIR como nuevas transacciones. No convertir formatos visuales ni celdas vacías en estados ejecutados.

### Decisiones pendientes, sin impedir el desarrollo estructural

- **D-01:** servidor de MESA o equipo dedicado; acceso solo interno o remoto autorizado; infraestructura y responsable de operación.
- **D-02:** catálogo oficial de activos y ubicaciones; resolución de códigos repetidos y activos adicionales del calendario.
- **D-03:** formato de folio, códigos documentales y revisiones vigentes; discrepancia entre revisión 01 y 02 del calendario.
- **D-04:** equivalencias entre los 14 puntos de BASE DE DATOS y los 11 grupos de maquinaria; actividades realizadas por MTY.
- **D-05:** checklist autónomo completo, turnos, equipos elegibles y reglas de omisión; no adjunto.
- **D-06:** frecuencias definitivas por activo/actividad; intervalos mixtos, hora base, anclaje y política de reprogramación. Confirmar si 50 minutos corresponden a grupo o total.
- **D-07:** fórmula gerencial de disponibilidad, calendario operativo, población crítica y clasificación de paros. Solicitar la presentación de métricas mencionada.
- **D-08:** personas y perfiles autorizados para cerrar, validar, editar tiempos y ajustar almacén; posibilidad de autovalidación.
- **D-09:** mínimos/máximos, saldos físicos, unidades, precios, tarifas de mano de obra y método de valoración. Confirmar necesidad de reservas y alcance de proveedores/facturas.
- **D-10:** avance real de los 20 pendientes Kaizen, responsables y fechas compromiso; criterio de implementación validada.
- **D-11:** significado de Seguimiento y equivalencias de clasificaciones/especialidades históricas.
- **D-12:** corte de migración, cuáles registros son reales o ejemplos, retención, respaldo y aprobación del piloto.

Si falta una definición, implementar el campo/configuración y marcar “Pendiente de configurar”; utilizar datos sintéticos solo en un ambiente demostrativo identificado. No bloquear todo el proyecto por valores maestros faltantes, pero tampoco habilitar automatismos con supuestos silenciosos.

## 13. Entregas y criterios de aceptación

**Entrega A — base del piloto:** acceso y permisos, catálogos/activos, OT, sesiones, paro, calendario preventivo manual y plantillas, tablero básico, exportación OT, auditoría, importación revisable, despliegue y respaldo. Debe cerrar una intervención de extremo a extremo.

**Entrega B — operación completa:** recurrencias por actividad/horómetro, autónomos por turno, inventario integrado, costos, Kaizen, indicadores completos y reportes para juntas. Incluye todos los P1 y la resolución/configuración de los datos necesarios para su uso operativo.

**Entrega C — mejoras opcionales:** QR/fotos, modo oscuro, offline, integraciones, comunicaciones externas y PPTX automático cuando se soliciten. No retrasar los módulos pedidos por implementar estas mejoras.

La solución se acepta con evidencia de los siguientes escenarios:

- **CA-01 / RF-07, RNF-04:** dos operadores crean OT simultáneamente y obtienen folios distintos; reintentar la misma petición no crea otra OT.
- **CA-02 / RF-08, RF-12:** un operador reporta sin capturar diagnóstico técnico ni costos; Mantenimiento completa su sección y conserva el reporte original.
- **CA-03 / RF-01, RF-52:** un operador no puede validar, ajustar inventario ni consultar costos restringidos llamando directamente a la API.
- **CA-04 / RF-17–18:** 07:00–09:00 = 2 H-H por persona; dos participantes = 4 H-H; 23:00–01:00 = 2 h; una pausa no incrementa tiempo activo. Rechazar intervalos imposibles y evitar superposición por persona.
- **CA-05 / RF-15, RF-52:** corregir un horario exige permiso y motivo y conserva ambos valores. Reabrir conserva consumo y validación previa.
- **CA-06 / RF-05, RF-19:** dos OT asociadas a un mismo paro no duplican indisponibilidad; cerrar una no libera el activo con causa pendiente.
- **CA-07 / RF-21–23:** seleccionar un activo con configuración validada carga marca/modelo y tareas correctas; no aplica se distingue de correcto y de ejecución externa.
- **CA-08 / RF-23–25:** programar desde OT o desde calendario usa la misma intervención; al vencer aparece V sin esperar captura manual.
- **CA-09 / RF-25, RF-28:** reprogramar un vencido conserva fecha base y evento R; no mejora artificialmente el cumplimiento original.
- **CA-10 / RF-26:** ejecutar un grupo mensual no reinicia el vencimiento del grupo trimestral que no se realizó; el planificador reiniciado no duplica OT.
- **CA-11 / RF-27:** en una regla mixta validada, alcanzar horas o fecha dispara lo debido una sola vez; una lectura faltante muestra incertidumbre. Registrar sustitución/reinicio de horómetro sin producir consumo negativo de horas.
- **CA-12 / RF-28, RF-33:** activo sin plan o turno sin checklist no aparece como cumplimiento perfecto; mostrar obligación y configuración faltante.
- **CA-13 / RF-30–34:** turno que cruza medianoche conserva fecha operativa; una revisión no se duplica y el hallazgo conserva su OT asociada.
- **CA-14 / RF-36–38:** saldo 10, salida 3 y devolución 1 produce 8; doble clic y reapertura mantienen 8. Dos salidas concurrentes no generan saldo negativo.
- **CA-15 / RF-39–40:** actualizar precio actual no modifica el costo histórico de una salida; costos faltantes permanecen identificados y compra directa no se suma dos veces.
- **CA-16 / RF-41–44:** Kaizen al 100 % sin validación no se cuenta como implementado; importar avance desconocido conserva ese estado.
- **CA-17 / RF-45–47:** tablero, listado y Excel concilian bajo la misma definición y corte; pendientes incluyen Abierta y Espera de Material además de En Proceso.
- **CA-18 / RF-47:** paros superpuestos se unifican y recortan al horario operativo; falta de denominador muestra explicación, nunca #DIV/0! ni un porcentaje fabricado.
- **CA-19 / RF-49–50:** PDF y Excel contienen datos reales, filtros y revisión correctos, con páginas legibles; exportaciones respetan permisos.
- **CA-20 / RF-54:** volver a importar el mismo archivo no duplica registros; duplicados de activos, 14/11 puntos y errores de origen se presentan para conciliación.
- **CA-21 / RF-01, RNF-01–02, RNF-09:** flujo de solicitud y ejecución utilizable en teléfono, tablet y escritorio, con teclado, zoom y foco visible.
- **CA-22 / RNF-04–06:** dos técnicos editando reciben control de conflicto; un fallo de conexión no muestra un guardado falso; se verifica persistencia tras reiniciar.
- **CA-23 / RF-55–56, RNF-07:** instalar en ambiente limpio y restaurar una copia recupera registros y documentos; la guía permite a TI repetir el proceso.
- **CA-24 / RF-53–55:** cada formato y regla tiene versión y procedencia; responsable de planta revisa piloto, excepciones y capacitación antes del arranque operativo.

## 14. Referencias externas y uso de la propuesta

Fuentes oficiales consultadas el 8 de septiembre de 2026. Se usan como referencias de patrones, sin recomendar la compra ni afirmar equivalencia completa con esos productos.

- **Apple Human Interface Guidelines — Layout:** jerarquía, alineación, organización y adaptación. https://developer.apple.com/design/human-interface-guidelines/layout
- **Apple Human Interface Guidelines — Accessibility:** legibilidad, interacción perceptible y contraste. https://developer.apple.com/design/human-interface-guidelines/accessibility
- **Apple Human Interface Guidelines — Lists and tables:** listas, datos en columnas y navegación al detalle. https://developer.apple.com/design/human-interface-guidelines/lists-and-tables
- **Odoo Maintenance — solicitudes/calendario:** referencia de solicitudes vinculadas a equipos y planificación; consulta mediante resultados indexados de documentación oficial. https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/maintenance/maintenance_requests.html
- **MaintainX — About Parts:** relación de materiales, activos y OT; existencia, disponible, mínimos y máximos. https://help.getmaintainx.com/about-parts
- **MaintainX — Help Center:** recurrencia, lecturas, checklists y tablero integrado. https://help.getmaintainx.com/

La especificación transforma las fuentes en un alcance verificable. Los detalles de arquitectura, permisos finos, fórmulas propuestas y tokens visuales deben tratarse como decisiones de diseño revisables. Las instrucciones técnicas de mantenimiento siguen bajo responsabilidad de las personas autorizadas de planta.


---

# Anexo del prompt: instrucciones originales de los preventivos

Estos textos proceden de las hojas adjuntas. Conserva su contenido al importar, separa grupo/subactividad y deja su aprobación técnica y aplicabilidad a Mantenimiento. No conviertas las instrucciones en una autorización automática de intervención.

## PREVENTIVO MAQ

### Grupo 1: REDUCTORES, CADENAS, SPROCKETS Y TORNILLERÍA

Frecuencia de origen: 1 MES.

- Revisión de nivel de aceite a reductor y juego en engranes.
- Revisar y/o ajustar cadenas y sprockets.
- Revisar estado de cuñas, opresores y apretar tornillería floja.

### Grupo 2: SENSORES Y LIMIT SWITCHES

Frecuencia de origen: 1 MES.

- Revisión de cableado y prueba de sensado/señales.
- Revisar que estén libres de polvo/golpes y verificar sujeción (roscas, bases).

### Grupo 3: SISTEMA NEUMÁTICO Y VÁLVULAS

Frecuencia de origen: 3 MESES.

- Revisión de Unidad FRL (Filtro, Regulador, Lubricador): purgar agua y revisar nivel de aceite.
- Revisar válvulas: desgaste, fugas y estado de empaques.

### Grupo 4: UNIDAD Y VÁLVULAS HIDRÁULICAS

Frecuencia de origen: 1 MES.

- Revisión del Cople del Motor y Bomba Hidráulica.
- Cambio de filtros del depósito y aceite.
- Válvulas: Revisar fugas, estado de solenoides y limpieza de terminales.

### Grupo 5: PISTONES HIDRÁULICOS Y NEUMÁTICOS

Frecuencia de origen: 3 MESES.

- Revisión y ajustes en la carrera del pistón.
- Revisión de mangueras y conexiones del sistema buscando fugas o desgaste.

### Grupo 6: SERVOMOTORES Y EJES CNC (REVISIÓN INTEGRAL)

Frecuencia de origen: 3 MESES.

- Revisión de coples a servomotor.
- Revisar temperatura general y del servomotor de cada eje.
- Revisar el aislamiento eléctrico al servomotor de cada eje.

### Grupo 7: SISTEMAS DE ENFRIAMIENTO Y VENTILACIÓN

Frecuencia de origen: 1 MES.

- Limpieza de filtros de ventiladores en el gabinete eléctrico.
- Revisión y limpieza del intercambiador de calor (chiller/radiador) para evitar alarmas de temperatura.

### Grupo 8: BALEROS Y BANDAS

Frecuencia de origen: 3 MESES.

- Revisión de poleas y/o engranes en los equipos.
- Revisión de baleros (ruido/temperatura) y estado de las bandas.

### Grupo 9: SISTEMA DE LUBRICACIÓN

Frecuencia de origen: 3 MESES.

- Verificar funcionamiento del sistema automático o manual de lubricación a guías y carros.

### Grupo 10: TABLERO Y COMPONENTES ELÉCTRICOS

Frecuencia de origen: 3 MESES.

- Revisar motores, contactores, relevadores y componentes eléctricos.
- Revisión de cableado y reapriete de conexiones (evitar falsos por vibración).
- Limpieza general del tablero eléctrico.

### Grupo 11: VERIFICACIÓN DE SEGURIDAD

Frecuencia de origen: 1 MES.

- Puntos de seguridad, paros de emergencia, sensores de guardas y 5's en la maquinaria.

## PREVENTIVO INFREST

### Grupo 1: ILUMINACIÓN Y ELÉCTRICO GENERAL

Frecuencia de origen: 3 MESES.

- Revisar centros de carga (110V/220V/440V). Verificar que no existan cables expuestos, terminales flojas o sobrecalentamiento.
- Cambio de lámparas fundidas en nave y oficinas.
- Revisar que apagadores y contactos funcionen correctamente y estén fijos a fase/neutro según normativa.

### Grupo 2: ESTRUCTURA Y TECHUMBRES

Frecuencia de origen: 6 MESES.

- Inspección visual de techumbre, canaletas y bajadas pluviales. Limpieza de hojas o basura para evitar taponamientos.
- Revisión de estructura metálica (marcos, PTR) buscando puntos de oxidación o fatiga.
- Detección y sellado de goteras o filtraciones.

### Grupo 3: ACCESOS Y PUERTAS

Frecuencia de origen: 3 MESES.

- Revisión, lubricación y ajuste de cortinas metálicas (rieles y cadena).
- Mantenimiento a portones de acceso principal (bisagras, motores si aplican).
- Revisión de puertas peatonales y barras de pánico.

### Grupo 4: INSTALACIONES HIDROSANITARIAS

Frecuencia de origen: 3 MESES.

- Revisión general de sanitarios, mingitorios y lavabos.
- Búsqueda de fugas en tuberías de alimentación y descargas.
- Limpieza de trampas de grasa o registros si aplica.

### Grupo 5: REDES GENERALES (AIRE Y AGUA)

Frecuencia de origen: 6 MESES.

- Inspección de línea principal de aire comprimido. Reemplazo de conectores para prueba de fuga en bajantes.
- Revisión de válvulas de paso generales y aislamiento de tuberías.

### Grupo 6: OBRA CIVIL Y PINTURA

Frecuencia de origen: 6 MESES.

- Mantenimiento preventivo a pisos (resane de grietas o baches menores).
- Retoque de pintura en líneas de delimitación peatonal, topes y rampas.
- Inspección de muros perimetrales.

### Grupo 7: SEGURIDAD E INSTALACIONES ESPECIALES

Frecuencia de origen: 4 MESES.

- Revisión de luces de emergencia y letreros de evacuación.
- Verificación de montaje y señalización de extintores.
- Limpieza de extractores o ventiladores de nave (louvers).

## PREVENTIVO UNIDADES

### Grupo 1: REVISIÓN DE FLUIDOS Y NIVELES

Frecuencia de origen: 1 MES / 250 HRS.

- Revisar nivel de aceite de motor, transmisión y líquido de frenos.
- Revisión de aceite hidráulico (crítico para el sistema de levante del montacargas).
- Verificación de anticongelante y líquido limpiaparabrisas.

### Grupo 2: SISTEMA MECÁNICO Y FILTROS

Frecuencia de origen: 3 MESES / 500 HRS.

- Cambio o revisión de filtro de aire, aceite y combustible.
- Inspección de bandas y mangueras (verificar que no haya grietas ni fugas).
- Lubricación y engrasado general (crucetas, baleros, puntos de engrase en dirección).

### Grupo 3: SISTEMA HIDRÁULICO Y DE IZAJE (MONTACARGAS)

Frecuencia de origen: 1 MES / 250 HRS.

- Revisión de cilindros de levante e inclinación (cero fugas, estado óptimo de sellos).
- Tensión y correcta lubricación de cadenas del mástil.
- Desgaste, fisuras y alineación de las horquillas/cuchillas.

### Grupo 4: LLANTAS, FRENOS Y DIRECCIÓN

Frecuencia de origen: 1 MES.

- Revisión de presión y desgaste de neumáticos (o estado de llantas sólidas en montacargas).
- Apriete de birlos y revisión de rines.
- Pruebas de frenado (respuesta del pedal y anclaje del freno de estacionamiento).

### Grupo 5: SISTEMA ELÉCTRICO Y SEGURIDAD (LUCES)

Frecuencia de origen: 1 MES.

- Batería: revisar terminales y nivel de electrolito.
- Verificación de Luces: faros delanteros, stop, direccionales, luces de gálibo/navegación (en la caja del camión) y faros de trabajo (montacargas).
- Torretas estroboscópicas, claxon y alarma de reversa (indispensable por normativa).

### Grupo 6: CABINA Y CONTROLES

Frecuencia de origen: 1 MES.

- Revisión de panel de instrumentos (testigos, medidores de temperatura y combustible).
- Verificación de cinturón de seguridad y espejos retrovisores.
- Revisión de caducidad y presión del extintor de la unidad.

### Grupo 7: ESTRUCTURA DE CAJA SECA (CAMIÓN)

Frecuencia de origen: 1 MES.

- Limpieza y Orden: Verificar que el interior de la caja esté barrido, limpio y libre de escombros, grasa o derrames.
- Estado de la Madera: Revisión del piso y paredes de triplay/madera. Asegurar que no haya tablas rotas, hundimientos o astillas peligrosas.
- Puertas y Toldo: Inspección de bisagras, cerrojos de las puertas traseras y asegurar que el techo (toldo) no presente filtraciones de agua ni daños estructurales.

# Anexo del prompt: actividades Kaizen de origen

Carga estos textos solo en la etapa de importación revisada o como conjunto de prueba claramente identificado. El avance, responsable y fecha compromiso requieren confirmación. No interpretes comentarios como validación.

- **1. SOPORTE 100% T DRILL DESDE TOOL CRIB** — Comentario de origen: SE MANDO A COTIZAR CON T DRILL.
- **2. HABILITAR MAQUINA ALCUN009 CUT OFF HEALING** — Comentario de origen: PENDIENTE INSTALACIONES PARA BAJADAS.
- **3. GENERAR CONTROL DE MINIMOS Y MAXIMOS TOOL CRIB** — Comentario de origen: SE ESTA DESARROLLANDO DOCUMENTO.
- **4. CONTROL DE REPARACION DE FIXTURES** — Comentario de origen: SE TIENE CONTROL SE VA MEJORAR.
- **5. PLANTILLA PARA TALADRO 62699-01 URGENTE** — Comentario de origen: YA SE MANDO DISEÑO PARA COTIZACION.
- **6. ESTANTES PARA TABLETS** — Comentario de origen: FALTA ELECTRICIDAD.
- **7. TECHO PARA CONTENEDORES** — Comentario de origen: NO HAY PROVEDOR ASIGNADO SE TIENEN QUE DAR DE ALTA.
- **8. MOVIMIENTO DE COMPRESOR** — Comentario de origen: SE VA REALIZAR LAY OUT PARA MODIFICACION.
- **9. REPARACION DE BAÑOS COMEDOR** — Comentario de origen: GENERAR CULTURA CON EL PERSONAL.
- **10. INSTALACION DE OFICINAS PLANTA** — Comentario de origen: YA SE ESTA REALIZANDO EL TRABAJO FALTA VALIDAR.
- **11. DESAROLLAR STOCK PARA VARILLAS DOBLES Y PERFORADO** — Comentario de origen: SE ACABO STOCK SE TIENE QUE HACER UNO DE 0.
- **12. MATRICES Y PUNZONES** — Comentario de origen: YA SE ESTA SOLICITANDO Y CONTROLANDO FALTA MEJORAR.
- **13. MOVIMIENTO DE MESAS DE EMPAQUE PARA MEJORAR FLUJO** — Comentario de origen: YA SE DEFINIO LAY OUT+.
- **14. INSTALACION DE ESPEJOS AREA DE EMBARQUE** — Comentario de origen: YA LOS TIENE MANTENIMIENTO.
- **15. MAQUINA DE SOLDADURA AUTOMATICA ARRANQUE** — Comentario de origen: ESTA EN SEGUIMIENTO CON COMPAÑEROS.
- **16. CONTROL DE EDH** — Comentario de origen: DAIKIN OK FALTA RHEMM Y LENNOX.
- **17. EXTRACTORES PLANTA RAMOS** — Comentario de origen: SE REPARO MOTOR.
- **18. REVISAR VARIACION DE VOLTAJE** — Comentario de origen: YA SE REALIZO ANALISIS.
- **19. PINTURA EXTERIOR PLANTA** — Comentario de origen: YA ESTA COTIZADO.
- **20. LIBERAR AREA DE COMPRESORES** — Comentario de origen: Sin comentario registrado.

# Comienza el trabajo

Inspecciona primero los archivos y el proyecto disponibles, registra decisiones y construye el primer flujo completo de OT. Después continúa con el resto de P0/P1. Usa toda la especificación como contrato de alcance, conserva la trazabilidad y entrega evidencia verificable.
