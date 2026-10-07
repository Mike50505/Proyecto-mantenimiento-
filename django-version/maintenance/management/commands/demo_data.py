from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from maintenance.models import (
    Asset, AuditLog, CatalogEntry, DowntimeEvent, FolioSequence, InventoryItem,
    InventoryMovement, PreventivePlan, PreventivePlanRevision, PreventiveTask,
    User, WorkOrder, WorkOrderEvent,
)

PREFIX = "PRUEBA-MESA-"


class Command(BaseCommand):
    help = "Crea o elimina datos DEMO identificados para probar la interfaz local."

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["load", "clear", "repair-text"])
        parser.add_argument("--password", default="")

    @transaction.atomic
    def handle(self, *args, **options):
        if options["action"] == "clear":
            self.clear_demo()
            return
        if options["action"] == "repair-text":
            self.repair_text()
            return
        self.load_demo(options["password"])

    def repair_text(self):
        corrections = {
            "demostraci?n": "demostración", "Demostraci?n": "Demostración",
            "L?nea": "Línea", "l?nea": "línea", "Inspecci?n": "Inspección",
            "inspecci?n": "inspección", "Mec?nica": "Mecánica",
            "El?ctrica": "Eléctrica", "Hidr?ulica": "Hidráulica",
            "hidr?ulica": "hidráulica", "Neum?tica": "Neumática",
            "vibraci?n": "vibración", "revisi?n": "revisión",
            "multiprop?sito": "multipropósito", "Refacci?n": "Refacción",
            "Almac?n": "Almacén", "lubricaci?n": "lubricación",
            "tensi?n": "tensión", "conexi?n": "conexión",
            "posici?n": "posición", "presi?n": "presión",
            "navegaci?n": "navegación", "diagn?stico": "diagnóstico",
            "refrigeraci?n": "refrigeración", "Tecnico": "Técnico",
        }

        def corrected(value):
            for old, new in corrections.items():
                value = value.replace(old, new)
            return value

        targets = [
            (User.objects.filter(username__startswith="prueba_mesa_"), ("first_name", "last_name")),
            (Asset.objects.filter(code__startswith=PREFIX), ("name", "line", "brand", "operational_status_cause")),
            (InventoryItem.objects.filter(code__startswith=PREFIX), ("name", "category", "location")),
            (PreventivePlan.objects.filter(title__startswith=PREFIX), ("title", "instructions", "applies_when")),
            (PreventiveTask.objects.filter(title__startswith=PREFIX), ("title",)),
            (WorkOrder.objects.filter(original_folio__startswith=PREFIX), ("classification", "specialty", "reported_failure", "actions", "location")),
            (DowntimeEvent.objects.filter(cause__startswith=PREFIX), ("cause", "close_reason")),
        ]
        updated = 0
        for records, fields in targets:
            for record in records:
                changed = []
                for field in fields:
                    old = getattr(record, field)
                    new = corrected(old)
                    if new != old:
                        setattr(record, field, new)
                        changed.append(field)
                if changed:
                    record.save(update_fields=changed)
                    updated += 1

        catalog = CatalogEntry.objects.filter(value__contains="?")
        for entry in catalog:
            if entry.kind not in {"line", "classification", "specialty"}:
                continue
            if entry.kind == "line" and not entry.value.startswith(PREFIX):
                continue
            new = corrected(entry.value)
            if new == entry.value:
                continue
            if CatalogEntry.objects.filter(kind=entry.kind, value=new).exclude(pk=entry.pk).exists():
                entry.delete()
            else:
                entry.value = new
                entry.save(update_fields=["value"])
            updated += 1
        self.stdout.write(self.style.SUCCESS(f"Textos de demostración corregidos: {updated} registros"))

    def clear_demo(self):
        # Delete only records carrying our explicit DEMO prefix/tag.
        orders = WorkOrder.objects.filter(original_folio__startswith=PREFIX)
        order_ids = list(orders.values_list("id", flat=True))
        downtime = DowntimeEvent.objects.filter(cause__startswith=PREFIX)
        plans = PreventivePlan.objects.filter(title__startswith=PREFIX)
        assets = Asset.objects.filter(code__startswith=PREFIX)
        inventory = InventoryItem.objects.filter(code__startswith=PREFIX)
        movements = InventoryMovement.objects.filter(item__code__startswith=PREFIX)
        demo_users = User.objects.filter(username__startswith="prueba_mesa_")
        counts = {"orders": orders.count(), "paros": downtime.count(), "preventivos": plans.count(), "activos": assets.count(), "insumos": inventory.count(), "movimientos": movements.count(), "usuarios": demo_users.count()}
        orders.delete()
        downtime.delete()
        plans.delete()
        movements.delete()
        inventory.delete()
        assets.delete()
        demo_users.delete()
        CatalogEntry.objects.filter(value__startswith=PREFIX).delete()
        AuditLog.objects.filter(reason__startswith=PREFIX).delete()
        self.stdout.write(self.style.SUCCESS(f"Datos de demostración retirados: {counts}"))

    def load_demo(self, password):
        if len(password) < 12:
            raise CommandError("Indica una contraseña temporal de al menos 12 caracteres con --password")
        existing = (WorkOrder.objects.filter(original_folio__startswith=PREFIX).exists()
                    or Asset.objects.filter(code__startswith=PREFIX).exists()
                    or InventoryItem.objects.filter(code__startswith=PREFIX).exists())
        if existing:
            self.stdout.write("Los datos DEMO ya existen; se conservan (operación idempotente). Usa clear y luego load para recrearlos.")
            return
        now = timezone.now()
        today = timezone.localdate()
        areas = ["PRUEBA-MESA-Ensambles", "PRUEBA-MESA-Maquinado", "PRUEBA-MESA-Servicios"]
        for kind, values in {
            "area": areas,
            "line": ["PRUEBA-MESA-Línea 1", "PRUEBA-MESA-Línea 2"],
            "priority": ["Baja", "Media", "Alta", "Paro de m\u00e1quina", "Seguimiento"],
            "classification": ["Mantenimiento Correctivo", "Mantenimiento Preventivo", "Mejora", "Inspección"],
            "specialty": ["Mecánica", "Eléctrica", "Hidráulica", "Neumática"],
        }.items():
            for order, value in enumerate(values):
                CatalogEntry.objects.get_or_create(kind=kind, value=value, defaults={"sort_order": order})
        manager = User.objects.create_user(
            username="prueba_mesa_jefatura", password=password, employee_number="PRUEBA-MESA-JEF-01",
            first_name="Jefatura", last_name="Demostración", role="Jefatura",
            area_permissions=areas,
        )
        tech_a = User.objects.create_user(
            username="prueba_mesa_tecnico1", password=password, employee_number="PRUEBA-MESA-TEC-01",
            first_name="Técnico Ana", last_name="Prueba", role="T\u00e9cnico",
            area_permissions=areas,
        )
        tech_b = User.objects.create_user(
            username="prueba_mesa_tecnico2", password=password, employee_number="PRUEBA-MESA-TEC-02",
            first_name="Técnico Luis", last_name="Prueba", role="T\u00e9cnico",
            area_permissions=areas,
        )
        requester = User.objects.create_user(
            username="prueba_mesa_solicitante", password=password, employee_number="PRUEBA-MESA-OP-01",
            first_name="Operador", last_name="Demostración", role="Solicitante",
            area_permissions=areas,
        )
        assets = []
        specs = [
            ("ENS-01", "Prensa hidráulica DEMO", areas[0], "Operativa", False),
            ("ENS-02", "Transportador DEMO", areas[0], "Parada", True),
            ("MAQ-01", "Centro de maquinado DEMO", areas[1], "Operativa", True),
            ("SRV-01", "Compresor DEMO", areas[2], "Operativa", False),
            ("SRV-02", "Bomba de refrigeración DEMO", areas[2], "Operativa", False),
        ]
        for suffix, name, area, status, critical in specs:
            assets.append(Asset.objects.create(
                code=f"{PREFIX}{suffix}", name=name, category="Maquinaria",
                asset_type="Maquinaria", area=area, line=f"{PREFIX}Línea 1",
                location_detail="Zona DEMO", brand="Equipo demostración",
                model="M-01", voltage="440 V", operating_hours=Decimal("1250"),
                operational_status=status,
                operational_status_cause=f"{PREFIX} vibración y revisión" if status == "Parada" else "",
                operational_status_updated_at=now, administrative_status="Activo", critical=critical,
            ))
        items=[]
        for code,name,stock,minimum,maximum,cost in [
            ("ROD-6205","Rodamiento 6205",Decimal("4"),Decimal("3"),Decimal("12"),Decimal("185.50")),
            ("GRS-001","Grasa multipropósito",Decimal("2"),Decimal("5"),Decimal("20"),Decimal("92.00")),
            ("FLT-010","Filtro de aire",Decimal("9"),Decimal("2"),Decimal("15"),Decimal("240.00")),
            ("COR-032","Banda 32 pulgadas",Decimal("0"),Decimal("1"),Decimal("4"),Decimal("510.00")),
        ]:
            item=InventoryItem.objects.create(code=f"{PREFIX}{code}",name=f"{name} DEMO",category="Refacción",unit="pieza",stock=stock,min_stock=minimum,max_stock=maximum,unit_cost=cost,location="Almacén DEMO")
            items.append(item)
            if stock:
                InventoryMovement.objects.create(item=item,type="Ajuste",quantity=stock,unit_cost=cost,user=manager,notes=f"{PREFIX} saldo inicial de demostración",request_key=f"{PREFIX}seed-{item.code}",request_hash=f"{PREFIX}{item.code}"[:64])
        plan=PreventivePlan.objects.create(
            asset=assets[0], title=f"{PREFIX} inspección semanal de prensa", frequency="Semanal",
            next_date=today+timedelta(days=5), responsible=tech_a, status="Programado",
            template_code=f"{PREFIX}PM-01", instructions="Verificar lubricación, guardas y fugas.",
            applies_when="Aplicable para datos de demostración",
        )
        PreventivePlanRevision.objects.create(plan=plan,version=1,snapshot={"title":plan.title,"frequency":plan.frequency,"next_date":plan.next_date.isoformat(),"status":plan.status},user=manager,source="demo-seed",reason=PREFIX)
        for title,days in [("Inspeccionar nivel de aceite",0),("Revisar tensión de banda",7),("Limpiar guardas",14)]:
            PreventiveTask.objects.create(plan=plan,title=f"{PREFIX}{title}",interval_unit="days",interval_value=7,anchor_date=today+timedelta(days=days),created_by=manager,applicability_status="Interna",applicability_reason=f"{PREFIX} punto de prueba",validated_by=manager,validated_at=now)
        offsets=[-2,0,0,1,3,6,10]
        states=["Abierta","En proceso","Programada","Pausada","Espera de material","Pendiente de validaci\u00f3n","Abierta"]
        titles=["Fuga en conexión","Inspección de guardas","Ajustar sensor de posición","Cambio de rodamiento","Revisar vibración","Mantenimiento de banda","Validar presión de línea"]
        priorities=["Alta","Paro de m\u00e1quina","Media","Alta","Seguimiento","Media","Baja"]
        orders=[]
        for index,(offset,status,title,priority) in enumerate(zip(offsets,states,titles,priorities)):
            asset=assets[index%len(assets)]
            request_at=timezone.make_aware(datetime.combine(today+timedelta(days=offset),time(8+index%8,15)))
            scheduled=timezone.make_aware(datetime.combine(today+timedelta(days=offset),time(9+index%6,0)))
            technician=[tech_a,tech_b,None,tech_a,tech_b,None,tech_a][index]
            order=WorkOrder.objects.create(
                folio=f"OT-{today.year}-PRUEBA-MESA-{index+1:03d}",original_folio=f"{PREFIX}OT-{index+1:03d}",
                requested_at=request_at,requester=requester if index%2==0 else manager,
                priority=priority,classification="Mantenimiento Correctivo" if index!=1 else "Inspección",
                specialty=["Mecánica","Eléctrica","Hidráulica"][index%3],asset=asset,
                location=asset.area,reported_failure=f"{PREFIX}{title} reportado para prueba de navegación.",
                actions=f"{PREFIX} inspeccion de prueba" if status in ["En proceso","Pendiente de validaci\u00f3n"] else "",
                technician=technician,scheduled_at=scheduled,status=status,
                started_at=request_at if status in ["En proceso","Pausada","Espera de material","Pendiente de validaci\u00f3n"] else None,
                finished_at=request_at+timedelta(hours=1) if status=="Pendiente de validaci\u00f3n" else None,
                labor_hours=Decimal(index+1),labor_cost=Decimal((index+1)*150),
                material_cost=Decimal("185.50") if index==3 else Decimal("0"),
                validation_status="Pendiente" if status=="Pendiente de validaci\u00f3n" else "No aplica",
            )
            orders.append(order)
            WorkOrderEvent.objects.create(work_order=order,user=manager,event="Creada",details=PREFIX)
            WorkOrderEvent.objects.create(work_order=order,user=manager,event="Datos de prueba",details=PREFIX)
        open_downtime=DowntimeEvent.objects.create(asset=assets[1],cause=f"{PREFIX} diagnóstico de prueba",started_at=now-timedelta(hours=3),created_by=manager)
        open_downtime.work_orders.add(orders[1])
        closed=DowntimeEvent.objects.create(asset=assets[2],cause=f"{PREFIX} prueba concluida",started_at=now-timedelta(days=3),finished_at=now-timedelta(days=3)+timedelta(hours=2),created_by=manager,closed_by=manager,close_reason=f"{PREFIX} cierre demostrativo")
        closed.work_orders.add(orders[4])
        self.stdout.write(self.style.SUCCESS(
            "Datos PRUEBA-MESA cargados: 4 usuarios de prueba, 5 activos, 7 OT, "
            "1 preventivo/3 tareas, 4 insumos, movimientos y 2 paros. "
            "Cuentas: prueba_mesa_jefatura, prueba_mesa_tecnico1, prueba_mesa_tecnico2, prueba_mesa_solicitante."
        ))
