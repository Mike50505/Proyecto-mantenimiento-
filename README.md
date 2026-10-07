# MESA Mantenimiento — versión Django

La aplicación activa está en [django-version](django-version/README.md). Usa Django y PostgreSQL; el servicio local se abre en http://localhost:8001. Los archivos de Node.js en la raíz pertenecen a una versión anterior y no son necesarios para iniciar la versión Django.

## Estado

La versión Django ofrece órdenes de trabajo, activos, preventivos, paros, inventario, usuarios y un tablero básico. La instancia actual aún no contiene los datos históricos de los libros Excel. La [especificación](Requerimientos_Mantenimiento_MESA.docx) separa la entrega de piloto P0 del alcance completo P1. Consulta [el estado de implementación](django-version/IMPLEMENTATION_STATUS.md) antes de usarla para operación de planta.

## Iniciar y verificar

```powershell
cd django-version
docker compose up -d --build
docker compose exec web python manage.py check
docker compose exec web python manage.py test
```

La configuración de usuario inicial, acceso por red, seguridad y respaldo está en [django-version/README.md](django-version/README.md). No se deben dar por importados los datos Excel por el hecho de iniciar el servicio.