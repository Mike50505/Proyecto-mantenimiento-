# MESA Mantenimiento

Primera versión de la aplicación web para administrar mantenimiento en Planta Ramos.

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
