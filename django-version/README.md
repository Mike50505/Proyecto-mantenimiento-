# MESA Mantenimiento · Django + PostgreSQL

Versión Django activa de MESA, aislada de las instalaciones anteriores. Docker Compose usa el proyecto `mesa-django-v2`.

## Ejecutar

```powershell
cd django-version
docker compose up -d --build
```

Abrir `http://localhost:8001`. El usuario inicial es `administrator` y su contraseña temporal está en `MESA_ADMIN_PASSWORD` dentro del archivo local `.env`; al ingresar, el sistema exige cambiarla. No reemplaces las claves de `.env` al reiniciar: la base ya creada depende de ellas. En una instalación nueva, crea primero un `.env` con `POSTGRES_PASSWORD`, `DJANGO_SECRET_KEY` de al menos 50 caracteres y `MESA_ADMIN_PASSWORD` de al menos 12 caracteres.

La información se conserva en el volumen `mesa-django-v2_mesa_django_postgres`. Las versiones MESA anteriores están detenidas y sus volúmenes permanecen intactos; no se importan sus datos automáticamente.

Para acceso fuera del equipo local, configura `DJANGO_ALLOWED_HOSTS` con el nombre o IP del servidor. Si publicas mediante HTTPS, configura `DJANGO_CSRF_TRUSTED_ORIGINS` con el origen completo (por ejemplo, `https://mantenimiento.ejemplo.com`) y `DJANGO_SECURE_COOKIES=1`. El Compose incluido expone HTTP directamente; coloca un proxy HTTPS delante para proteger credenciales y sesiones en tránsito. El navegador debe cargar la página antes de enviar solicitudes API para recibir el token CSRF.

Al rotar `DJANGO_SECRET_KEY`, puedes pasar la clave anterior en `DJANGO_SECRET_KEY_FALLBACKS` para conservar las sesiones existentes. Retira la clave anterior después del período de sesiones.

## Roles de usuario

### Borrado y cambios de nómina

Órdenes, usuarios, artículos de inventario y activos ofrecen **Borrar** cuando la cuenta tiene el permiso correspondiente: `orders.delete`, `users.delete`, `inventory.delete` o `assets.delete`, además del acceso a la ventana. Se pueden activar en **Usuarios → Administrar → Personalizar permisos → Acciones permitidas**. Administración y Jefe de mantenimiento sin restricciones los incluyen; los demás perfiles requieren que se activen explícitamente.

El borrado exige motivo y conserva el registro y sus relaciones históricas. Se retira de las listas operativas y queda en **Auditoría → Registros borrados** con usuario, fecha, motivo y valores anteriores. No libera por sí mismo un paro ni revierte movimientos de inventario. Una OT pendiente se cancela al retirarla y sus ocurrencias preventivas quedan excluidas. Los códigos y nóminas borrados siguen reservados para conservar la trazabilidad.

No se permite borrar la cuenta propia ni cuentas de administrador; las cuentas con órdenes asignadas pendientes o sesiones abiertas requieren resolverlas antes. Los activos con OT pendientes o paros abiertos y las OT con sesiones abiertas también deben resolverse primero. En **Usuarios → Administrar** se puede cambiar el número de nómina; exige `users.manage`, valida duplicados y conserva el cambio en auditoría.

En **Usuarios → Crear usuario** o **Administrar → Rol** se puede seleccionar **Jefe de mantenimiento**. Por defecto tiene acceso completo como el administrador: tablero, órdenes, activos, preventivos, inventario, catálogos, usuarios, importaciones y auditoría, con todas las acciones y áreas habilitadas. Puede crear usuarios, cambiar roles y restablecer contraseñas. Las cuentas nuevas deben cambiar su contraseña temporal antes de operar.

Operador y Personal de mantenimiento conservan sus accesos actuales. El rol interno Jefatura conserva sus permisos previos.

En **Usuarios → Crear usuario** o **Administrar**, marca **Personalizar permisos de esta cuenta** para elegir **Ventanas visibles**, **Acciones permitidas** y **Áreas autorizadas** mediante casillas, sin escribir códigos ni listas separadas por comas. También se pueden limitar las cuentas con rol Jefe de mantenimiento. Solo el Administrador conserva siempre acceso completo.

Al marcar una ventana se activa su acción de consulta. **Seleccionar todas** y **Quitar selección** facilitan la configuración. Una cuenta personalizada sin ventanas o acciones seleccionadas no recupera los permisos del rol: queda sin esos accesos. **Todas las áreas** conserva el alcance general; al desmarcarla es obligatorio elegir al menos un área.

Desmarca la personalización para restaurar los accesos predeterminados del rol. Cambiar el rol de una cuenta personalizada conserva su selección. Las modificaciones quedan auditadas y las sesiones existentes actualizan los accesos periódicamente. El servidor rechaza acciones y URLs de ventanas no autorizadas. El rol mantiene las reglas operativas de propiedad de órdenes y participación de técnicos.

La migración `0014_user_custom_permissions` agrega el modo personalizado sin cambiar las cuentas existentes. Los permisos anteriores se muestran seleccionados al editar. Verifica el selector con `node scripts/check-user-permissions.cjs`; las pruebas de servidor están en `maintenance/test_account_permissions.py`.

## Comprobaciones

```powershell
docker compose exec web python manage.py check
docker compose exec web python manage.py test
docker compose exec web python manage.py migrate --check
# Comprobación de seguridad (las advertencias HTTPS requieren un proxy TLS)
docker compose exec web python manage.py check --deploy
```

## Arquitectura

- Django 5.2 LTS y autenticación/sesiones de Django.
- PostgreSQL 17 con transacciones y bloqueo de filas para folios, estados e inventario.
- API JSON compatible con las rutas consumidas por el frontend existente.
- Copia independiente de la interfaz en `static/`, incluidos los temas oscuro y claro.

## Atención de OT y paros

En el detalle de una OT, Jefatura asigna el técnico responsable y colaboradores. Con la OT **En proceso**, cada participante puede iniciar, pausar y terminar su sesión; también existe captura manual de un intervalo completo. La pausa exige motivo y no suma tiempo. Jefatura o Administración pueden corregir un intervalo cerrado con motivo; el cambio queda auditado. No se puede dejar **En proceso** con sesiones abiertas al pausar, esperar material, terminar trabajo o cancelar.

La prioridad **Paro de máquina** pide confirmar si el activo está realmente detenido. Al confirmarlo se abre un evento de paro o se vincula la OT a uno activo del mismo equipo. Cerrar o cancelar una OT no libera por sí solo la máquina: el paro se cierra por separado con motivo. La pantalla de Paros permite vincular varias OT al mismo evento.

La API usa `POST /api/orders/{id}/time-entries/actions` con `action` (`start`, `pause`, `finish`) y `version` de la OT. La captura manual usa `POST /api/orders/{id}/time-entries`; la corrección autorizada usa `PATCH /api/orders/{id}/time-entries/{entry_id}` con `started_at`, `finished_at`, `reason` y `version`. Una versión desactualizada devuelve conflicto 409.

El alta de OT acepta una clave `Idempotency-Key`. Dos envíos concurrentes con la misma clave y datos crean una sola OT; reutilizar la clave con datos distintos devuelve 409.

## Catálogos

La ficha de activos muestra nombre, tipo, ubicación, estado operativo, criticidad y observaciones. Marca, modelo, voltaje, serie y estado administrativo quedan en **Datos técnicos opcionales**. Ya no se capturan códigos, categoría histórica, alias, equivalencias, línea ni ubicación detallada; los valores anteriores se conservan en la base y los activos nuevos reciben un identificador automático para mantener sus relaciones.

La criticidad usa **A: muy crítico**, **B: medianamente crítico** y **C: la producción puede seguir sin él**. La migración conserva el criterio anterior: Crítico pasa a A y Normal a C; B se asigna por revisión de planta. La lista, ficha y exportación XLSX usan esta clasificación, con cambios registrados en auditoría.

Administración y Jefatura tienen la pantalla **Catálogos** para agregar y activar o desactivar prioridades, clasificaciones, especialidades, áreas, líneas y turnos. La desactivación impide usar el valor en capturas nuevas y conserva el texto de registros anteriores. La prioridad `Seguimiento` está disponible, pero su orden y significado requieren validación de planta. Áreas, líneas y turnos oficiales aún deben configurarse.
La ficha de activo ya guarda línea y ubicación detallada. Los turnos aún no están vinculados a activos ni revisiones.

## Planificador preventivo

### Flujo simple: OT futuras con repetición opcional

**Borrar repetición completa** está disponible junto a la OT recurrente en Órdenes y Preventivos, y en **Repeticiones activas**. Requiere `orders.delete`, `preventives.edit` y acceso a ambas ventanas. Primero muestra cuántas OT se borrarán y permite elegir todas (incluidas terminadas/canceladas) o solo pendientes. Exige motivo y una confirmación vigente; si cambian las OT, se debe abrir de nuevo la confirmación. El borrado y la detención de futuras generaciones son atómicos. Se preservan registros y relaciones históricas, con auditoría individual por OT y resumen de la repetición. Las sesiones de trabajo abiertas bloquean todo el lote hasta resolverlas.

En **Preventivos → Programar OT preventiva** se captura trabajo, activo, primera fecha/hora, responsable y repetición. **Una sola vez** crea una OT Programada; repetir por días, semanas, meses o años crea OT independientes en las fechas siguientes. Por ejemplo, el día 20 de cada mes conserva ese anclaje; cerrar una OT no mueve las próximas fechas. Cada orden aparece tanto en la agenda preventiva como en Órdenes y se atiende mediante el flujo habitual.

Las series programan los próximos 90 días y el servicio `schedules` amplía esa agenda cada hora, también después de un reinicio, sin duplicar órdenes. Una primera fecha más lejana se guarda de inmediato. La fecha final de repetición es opcional. **Repeticiones activas → Detener repetición** deja de crear nuevas OT, conserva las ya programadas y registra el motivo en Auditoría. Cancelar o borrar una OT individual no detiene toda la repetición.

El calendario y la lista de Preventivos muestran todas las fechas programadas. En la bandeja de Órdenes de trabajo se muestra solo la OT preventiva programada más próxima de cada repetición; al cerrarla, cancelarla o borrarla aparece la siguiente. Las OT en atención, las correctivas y el historial conservan su visibilidad. CSV y XLSX de la bandeja respetan este mismo filtro (`next_preventive=1`).

La captura exige `preventives.edit`, `orders.create`, acceso a ambas ventanas y alcance de área; asignar responsable también requiere `orders.assign`. La generación automática respeta los permisos vigentes de quien programó la serie y pausa si su cuenta, permisos, responsable o activo dejan de estar disponibles. Las programaciones anteriores se conservan; las que no tienen tareas ni OT pueden convertirse desde **Programaciones anteriores → Programar como OT**.

El planificador opcional descrito abajo conserva el flujo avanzado anterior; el flujo simple no necesita configurar tareas, plantillas ni aplicabilidad manualmente.

El comando `plan_preventives` consulta fechas base de tareas con aplicabilidad Interna o Externa. Sin `--apply` solo muestra cuántas OT crearía. La ventana de búsqueda se indica explícitamente; por ejemplo:

```powershell
docker compose run --rm web python manage.py plan_preventives --lookback-days 0 --lookahead-days 30
```

Para crear OT se añaden `--apply --user USUARIO` después de revisar la vista previa. El usuario debe ser Administrador o Jefatura activa con permisos de preventivos y OT. El comando conserva el anclaje fijo de cada tarea, bloquea un nuevo vencimiento si la tarea tiene una OT anterior abierta y usa la ocurrencia guardada para que repetirlo tras un reinicio no duplique órdenes. `--max-new-orders` limita el lote. `--allow-overlap` cambia explícitamente la política de OT anterior abierta.

El servicio opcional `planner` de Compose está desactivado por defecto. Cuando planta confirme ventana, anclaje y arrastre de pendientes (D-06), configura `MESA_PLANNER_USER`, `MESA_PLANNER_LOOKBACK_DAYS` y `MESA_PLANNER_LOOKAHEAD_DAYS` en `.env` y activa `docker compose --profile planner up -d --build planner`. Ejecuta el comando cada hora y al reiniciar. No activa reglas por horómetro ni cambia fechas según la última ejecución.

## Respaldo y restauración de prueba

Con la base activa, ejecuta desde esta carpeta:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\backup.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\verify-backup.ps1 -BackupFile .\backups\mesa-mantenimiento-AAAAMMDD-HHMMSS.dump
```

`backup.ps1` crea un archivo PostgreSQL en `backups/`. `verify-backup.ps1` lo restaura en una base temporal, consulta una tabla y elimina esa base temporal; no modifica la base operativa. Programa el primer script en el servidor definitivo y copia los archivos fuera de ese equipo. Define retención y frecuencia con el responsable de TI antes del arranque. Los respaldos incluyen datos sensibles: limita el acceso a la carpeta y a sus copias.

El procedimiento de recuperación de la base operativa debe ejecutarse solo después de detener la aplicación, conservar una copia del estado actual y confirmar el archivo y punto de restauración con el responsable. La prueba anterior permite verificar el archivo sin reemplazar datos activos.
## Vista previa de libros Excel

Un administrador puede abrir **Importación** y seleccionar un archivo `.xlsx` o `.xlsm`. La pantalla muestra hojas, primeras filas y códigos duplicados detectados en las columnas conocidas. Esta operación no ejecuta macros ni modifica activos, OT o inventario. Antes de cargar datos definitivos hay que confirmar qué filas son reales, resolver equivalencias de activos y validar las plantillas con Mantenimiento.
Cada vista previa crea un lote de revisión con hash del archivo; repetir el mismo contenido reutiliza el lote. Administración puede consultar lotes previos y descartarlos con motivo. El lote conserva el resumen y todas las filas legibles con hoja, número de fila, valores y fórmulas guardadas; la consulta es paginada. El archivo original no se conserva. Cada fila admite una decisión auditada: pendiente, excluida o propuesta de vínculo con un activo existente, siempre con motivo. Las propuestas no modifican los activos. No hay acción para confirmar una importación operativa.
En el detalle del lote, **Ver conciliación** agrupa códigos de `MAQUINAS`, `BASE DE DATOS` y `CALENDARIO`, muestra sus filas de origen y repeticiones dentro de cada hoja, y compara con códigos vigentes y equivalencias aprobadas. La coincidencia es informativa y requiere validación humana.
Cada fila muestra también campos identificados según su hoja. Son una interpretación provisional calculada al consultar; las celdas originales siguen disponibles. Las fechas numéricas con formato reconocido muestran por separado su interpretación y el sistema Excel usado; también se señalan errores de celda. Las fechas textuales, los puntos de revisión y las marcas de avance no se convierten a datos operativos. Consulta `IMPORT_REVIEW.md` para ver las columnas y decisiones pendientes.
El panel de incidencias agrupa errores de Excel y fechas numéricas con formato temporal que no se pudieron interpretar. Permite abrir la fila fuente para documentar una decisión de revisión.

## Exportación de órdenes

La bandeja permite descargar CSV o XLSX. XLSX conserva fechas y cantidades/costos como valores tipados y exporta las órdenes visibles conforme a los filtros de búsqueda/estado y al alcance autorizado del usuario. Los perfiles solicitantes no reciben columnas de costos ni notas de cierre; Jefatura, Administración y técnicos reciben esos datos conforme al acceso de la aplicación. Su presentación y uso oficial deben validarse antes del piloto.


La pantalla de activos también ofrece `GET /api/assets/export.xlsx`, disponible con `assets.read`. Exporta los campos de la ficha técnica y conserva las áreas autorizadas; el término de búsqueda actual se aplica al archivo igual que en la lista.

El tablero permite filtrar las métricas y listas de OT por fecha de solicitud y exportar ese mismo conjunto a `GET /api/dashboard/export.xlsx`. Se conservan los permisos de órdenes y áreas. El período no reinterpreta como históricos los indicadores actuales de activos, inventario, preventivos y alertas; la pantalla lo aclara.

## PDF versionado de órdenes

En el detalle de una OT, usuarios internos con permiso de edición pueden crear una copia PDF versionada. El sistema guarda el archivo y su captura, folio de documento, versión, número de versión de la OT, usuario, SHA-256 y evento de auditoría. Los reintentos sin cambios abren la versión existente. Las copias incluyen materiales netos y, cuando corresponda, respuestas del checklist preventivo, eventos de ejecución o revisión autónoma. Las personas solicitantes no pueden descargar copias internas; las áreas autorizadas se aplican al historial y a la descarga.

La captura se identifica como versión MESA; código y revisión se copian desde la OT si están configurados. Aún falta el registro maestro con vigencia/aprobador y aprobación del formato oficial de planta. La copia del sistema no sustituye ese control.

## Exportación del programa preventivo

La pantalla de preventivos ofrece `/api/preventives/export.xlsx`, disponible con `preventives.read`. Exporta las filas del programa en el alcance de áreas del usuario, ordenadas por próxima fecha, activo y actividad. La fecha queda como celda de fecha e incluye activo/área, actividad, plantilla, aplicabilidad, frecuencia, responsable, estado, versión y folio de OT.

## Consulta de auditoría

Administración y Jefatura pueden abrir **Auditoría** cuando su rol incluya `audit.read`. La lista es paginada y admite fechas, tipo/ID de entidad, acción y búsqueda de usuario/motivo; `GET /api/audit` devuelve 50 filas por página y total. `GET /api/audit/export.xlsx` exporta todos los cambios que coincidan con los mismos filtros. Si el usuario tiene áreas restringidas, el historial incluye solo entidades operativas de esas áreas e inventario, que conserva el acceso global existente. Antes/después se muestran como JSON y la fecha se guarda como celda temporal en XLSX.

## Alertas operativas

El tablero mantiene alertas para activos en parada, OT abiertas con prioridad `Paro de máquina`, preventivos cuya próxima fecha es hoy o anterior, e insumos activos en o bajo su mínimo. La condición y el detalle se actualizan desde sus registros de origen; al desaparecer la causa, la alerta queda cerrada. Mantenimiento puede registrar o actualizar una nota de atención, con usuario, fecha y entrada de auditoría. El endpoint `GET /api/alerts` lista alertas activas y `POST /api/alerts` registra la atención. El acceso sigue el permiso de lectura de OT y limita por las áreas configuradas; inventario conserva el alcance global que ya tenía su indicador en el tablero.

La vista de inventario también exporta XLSX de los insumos activos. Existencias, mínimos, máximos y costo unitario quedan como números con cuatro decimales; el valor en existencia usa existencias por costo unitario y se presenta a dos decimales.

## Datos locales de prueba

Para poblar una instancia local sin cargar libros reales, ejecuta `docker compose exec web python manage.py demo_data load --password "<contrasena-temporal-de-12-caracteres-o-mas>"`. Crea cuatro usuarios `prueba_mesa_*`, cinco activos, siete OT, un plan preventivo con tres tareas, cuatro insumos, movimientos iniciales y dos paros. El prefijo `PRUEBA-MESA-` identifica los datos; repetir `load` no los duplica. Para retirar exclusivamente este conjunto: `docker compose exec web python manage.py demo_data clear`. No usar estas cuentas ni estos registros en produccion.

## Flujo para terminar y cerrar una OT

1. En una orden activa, asigna uno o varios tecnicos y cambia el estado a `En proceso`.
2. Indica inicio y fin del trabajo. MESA calcula horas hombre = horas transcurridas multiplicadas por el numero de tecnicos asignados. Admite trabajo que cruza la medianoche.
3. Registra las acciones y notas de cierre. El boton `Terminar trabajo - enviar a validacion` guarda los cambios pendientes y pasa la OT a `Pendiente de validacion` sin cerrar el detalle.
4. Administracion o Jefatura revisa y selecciona `Validar y cerrar OT`; el estado pasa a `Completada`.

`Guardar` conserva abierto el detalle de la OT. El codigo y revision documental siguen almacenados en registros anteriores y PDF versionados, pero ya no aparecen en este formulario. El motivo de cambio de fecha es opcional. Las sesiones historicas conservan su registro; el formulario de OT usa inicio, fin y tecnicos asignados para calcular nuevas horas hombre.
