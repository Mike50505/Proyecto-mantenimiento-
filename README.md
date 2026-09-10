# MESA Mantenimiento

Primera versión de la aplicación web para administrar mantenimiento en Planta Ramos.

**Estado actualizado:** consulta [la entrega verificada del 8 de septiembre](docs/entrega-2026-09-08.md) para cambios, pruebas, URLs y pendientes. Este documento de entrega prevalece sobre las descripciones históricas de alcance de este README.

La interfaz actual usa recursos locales, navegación adaptable y pestañas de OT. Terminar pasa a **Pendiente de validación**; validar pasa a **Completada**. Las salidas y devoluciones se confirman desde sus acciones y conservan el historial. Las semillas requieren `MESA_DEMO=1`; no activar esa variable en operación.

Respaldo manual: `node scripts/backup.cjs`. Comprobación de migración sobre una copia: `node scripts/check-upgrade.cjs <archivo.db>`. Revisión de navegador con datos sintéticos: `node scripts/ui-review.cjs` (requiere Chrome).

## Requisitos

- Node.js 22.5 o superior (se recomienda Node.js 24).

No requiere instalar paquetes adicionales.

## Iniciar

```powershell
npm start
```

Abrir `http://localhost:3000` en el navegador. Para acceder desde otro dispositivo de la misma red, usar la dirección IP del equipo y el puerto 3000.

## Alcance actual

- Dashboard operativo.
- Alta y consulta de órdenes de trabajo.
- Bandeja compartida con actualización automática y aviso de nuevos reportes.
- Asignación de técnicos, ejecución, espera de material, cierre e historial de cambios.
- Registro de horas hombre, materiales y costos.
- Exportación de órdenes en CSV compatible con Excel.
- Catálogo de activos.
- Expediente técnico por máquina: marca, modelo, voltaje, serie, área, horas y observaciones.
- Historial y métricas de mantenimiento por máquina.
- Registro detallado de insumos con cantidad, costo unitario y total.
- Formato A4 imprimible o guardable como PDF para cada mantenimiento.
- Programa preventivo con generación de órdenes vinculadas.
- Base SQLite creada automáticamente en `data/mantenimiento.db`.
- Datos ficticios mínimos para demostrar el funcionamiento.
- Inicio de sesión mediante usuario y contraseña.
- Administración de usuarios y asignación de roles.
- Inventario de insumos con código, unidad, existencia, mínimos y máximos.
- Registro de entradas, salidas, ajustes y alerta de reabastecimiento.
- Flujo vertical de OT con inicio, sesiones de trabajo, término, validación autenticada, control de versión e idempotencia.
- Registro de paros independientes y bitácora de auditoría.

### Documentación del proyecto

- [Matriz de trazabilidad](docs/requirements-traceability.md)
- [Decisiones de arquitectura y producto](docs/decisions.md)
- [Inspección de fuentes](docs/source-inspection.md)
- [Contratos de API](docs/api.md)
- [Continuidad del desarrollo](CONTINUITY.md)

Las pruebas se ejecutan con `npm test`. La base actual contiene una semilla demostrativa separada; los libros Excel y el DOCX se mantienen como fuentes de conciliación y no se cargan automáticamente.

### Roles

- **Administrador:** acceso completo, incluida la administración de usuarios y contraseñas.
- **Personal de mantenimiento:** acceso al panel, órdenes, activos y preventivos; no puede administrar usuarios.
- **Operador:** puede levantar reportes y consultar el estado de sus propias solicitudes. No puede ver reportes de otros operadores ni modificar la atención técnica.

El usuario administrativo inicial es `administrator`. Por seguridad, su contraseña se almacena únicamente mediante un hash criptográfico.

Los datos reales de los archivos Excel no han sido importados.

## Configuración opcional

```powershell
$env:PORT=8080
$env:HOST='0.0.0.0'
npm start
```

## Ejecutar con Docker

Docker es la forma recomendada para instalar la aplicación en un servidor.

```powershell
docker compose up -d --build
```

Abrir `http://localhost:3000`. Desde otro equipo de la red, sustituir `localhost` por la dirección IP o nombre del servidor.

Consultar el estado y los registros:

```powershell
docker compose ps
docker compose logs -f mantenimiento
```

Detener la aplicación sin perder información:

```powershell
docker compose down
```

Actualizar después de copiar una versión nueva del proyecto:

```powershell
docker compose up -d --build
```

La base SQLite se conserva en el volumen `mesa_mantenimiento_data`. El comando `docker compose down` no elimina ese volumen. No se debe utilizar `docker compose down -v` salvo que se quiera borrar definitivamente toda la información.

Para utilizar otro puerto en el servidor, cambiar la sección `ports` de `compose.yaml`. Por ejemplo, `"8080:3000"` publicará la aplicación en el puerto 8080.
