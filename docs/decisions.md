# Decisiones de arquitectura y producto

## DEC-001 · Extender el monolito actual

Se conserva Node.js con SQLite, frontend HTML/CSS/JavaScript sin dependencias externas y Docker Compose. Ya existe autenticación, sesiones, API y persistencia; reemplazar el stack aumentaría el riesgo y no aporta al piloto LAN. Se mantiene una frontera modular por rutas y tablas hasta que el volumen o una decisión de TI justifique otro motor.

## DEC-002 · OT con cierre y validación separados

`Completada` representa que el técnico terminó el trabajo. La validación autenticada se conservará separada mediante `validation_status`, `validator_id`, `validated_at` y eventos; no se usará el nombre digitado como firma.

## DEC-003 · Datos maestros pendientes visibles

Los activos duplicados de los libros, la diferencia de 14 columnas frente a 11 grupos, las actividades de Planta MTY, los checklist autónomos y la fórmula de disponibilidad requieren aprobación funcional. Se implementan campos y estados de configuración pendiente antes de automatizar.

## DEC-004 · Inventario por movimientos

La existencia no se modifica desde la pantalla sin registrar un movimiento. Las salidas a OT, devoluciones y ajustes deben estar ligadas a usuario, fecha, costo y referencia; no se permiten saldos negativos.

## DEC-005 · Datos demo aislados

La semilla actual sirve para demostración técnica y se mantiene identificable. Los libros no se importan a producción hasta que se confirme el lote y se resuelvan duplicados, saldos físicos y responsables.

## Decisiones pendientes de planta

Servidor y alcance de red, folio corporativo, códigos documentales vigentes, población oficial de activos, perfiles de validación, turnos, checklist autónomo, política de horómetro, valoración de inventario, tarifas de mano de obra, avance Kaizen y corte de migración.
