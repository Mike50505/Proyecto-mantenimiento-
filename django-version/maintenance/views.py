import calendar
import csv
import hashlib
import io
import json
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.db import IntegrityError, transaction
from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.http import FileResponse, HttpResponse, JsonResponse
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.middleware.csrf import get_token

from .workbook_preview import CODE_COLUMNS, preview_workbook
from .import_mapping import map_source_row
from .xlsx_export import make_workbook
from .pdf_documents import render_work_order_pdf, work_order_snapshot

from .models import Asset, AssetCodeEquivalence, AuditLog, CatalogEntry, ChecklistAnswer, ChecklistItem, DowntimeEvent, FolioSequence, ImportBatch, ImportRow, InventoryItem, InventoryMovement, MaintenanceMaterial, MeterReading, OperationalAlert, PreventiveExecutionEvent, PreventiveOccurrence, PreventivePlan, PreventivePlanRevision, PreventiveTask, PreventiveTemplate, TimeEntry, User, WorkOrder, WorkOrderDocument, WorkOrderEvent

MODULES = ["dashboard", "orders", "assets", "preventives", "inventory", "catalogs", "users", "imports", "audit"]
ACTIONS = ["orders.create", "orders.read", "orders.edit", "orders.edit_dates", "orders.assign", "orders.transition", "orders.validate", "orders.time", "assets.read", "assets.edit", "preventives.read", "preventives.edit", "inventory.read", "inventory.move", "inventory.adjust", "catalogs.manage", "users.manage", "audit.read"]
ROLE_MODULES = {"Administrador": MODULES, "Jefatura": [x for x in MODULES if x not in ("users", "imports")], "Técnico": [x for x in MODULES if x not in ("users", "imports", "catalogs", "audit")], "Solicitante": ["orders"]}
ROLE_ACTIONS = {
    "Administrador": ACTIONS,
    "Jefatura": [x for x in ACTIONS if x != "users.manage"],
    "Técnico": ["orders.read", "orders.edit", "orders.transition", "orders.time", "assets.read", "preventives.read", "inventory.read"],
    "Solicitante": ["orders.create", "orders.read"],
}


class ApiError(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status


def payload(request):
    try:
        return json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        raise ApiError("JSON inválido")


def iso(value):
    if not value: return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


def parse_day(value, label="fecha"):
    try: return date.fromisoformat(str(value))
    except ValueError: raise ApiError(f"{label.capitalize()} inválida")


def task_due(task, index):
    if index < 0: raise ApiError("Índice de ocurrencia inválido")
    if task.interval_unit == "days": return task.anchor_date + timedelta(days=task.interval_value * index)
    months = task.anchor_date.month - 1 + task.interval_value * index
    year, month = task.anchor_date.year + months // 12, months % 12 + 1
    return date(year, month, min(task.anchor_date.day, calendar.monthrange(year, month)[1]))


def task_projection(task, start, end):
    rows = []
    for index in range(5000):
        due = task_due(task, index)
        if due > end: break
        if due >= start: rows.append({"task_id": task.id, "occurrence_index": index, "base_date": due.isoformat()})
    return rows


def scheduled_datetime(value):
    if value in (None, ""): raise ApiError("Fecha requerida")
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            raise ApiError("Fecha de programación inválida")
    if isinstance(value, date) and not isinstance(value, datetime):
        value = datetime.combine(value, datetime.min.time())
    return timezone.make_aware(value) if timezone.is_naive(value) else value


def order_labor_hours(order):
    if not order.started_at or not order.finished_at:
        return Decimal("0.00")
    seconds = Decimal(str((order.finished_at - order.started_at).total_seconds()))
    technicians = len(set(order.participants.values_list("id", flat=True)) | ({order.technician_id} if order.technician_id else set()))
    return (seconds * technicians / Decimal("3600")).quantize(Decimal("0.01"))


def plan_snapshot(plan):
    return {"id": plan.id, "asset_id": plan.asset_id, "title": plan.title, "frequency": plan.frequency, "next_date": iso(plan.next_date), "responsible_id": plan.responsible_id, "status": plan.status, "template_code": plan.template_code, "instructions": plan.instructions, "applies_when": plan.applies_when, "version": plan.version, "tasks": [{"id": x.id, "title": x.title, "interval_unit": x.interval_unit, "interval_value": x.interval_value, "anchor_date": x.anchor_date.isoformat(), "applicability_status": x.applicability_status, "applicability_reason": x.applicability_reason} for x in plan.tasks.all()]}


def save_revision(plan, user, source, reason=""):
    return PreventivePlanRevision.objects.create(plan=plan, version=plan.version, snapshot=plan_snapshot(plan), user=user, source=source, reason=reason)


def decimal(value, label="cantidad"):
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        raise ApiError(f"{label.capitalize()} inválida")


def catalog_values(kind):
    return list(CatalogEntry.objects.filter(kind=kind, active=True).values_list("value", flat=True))


def require_catalog_value(kind, value):
    if value not in catalog_values(kind): raise ApiError(f"{kind}: selecciona un valor activo del catálogo")


def modules(user):
    return user.module_permissions or ROLE_MODULES.get(user.role, [])


def actions(user):
    return user.action_permissions or ROLE_ACTIONS.get(user.role, [])


def require(request, action=None, area=None, allow_password_change=False):
    if not request.user.is_authenticated or not request.user.is_active:
        raise ApiError("Sesión requerida", 401)
    if request.user.must_change_password and not allow_password_change:
        raise ApiError("Debes cambiar tu contraseña temporal antes de continuar", 403)
    if action and request.user.role != "Administrador" and action not in actions(request.user):
        raise ApiError("Tu usuario no tiene permiso para esta acción", 403)
    if area is not None and request.user.area_permissions and area not in request.user.area_permissions:
        raise ApiError("Tu usuario no tiene permiso para esta área", 403)
    return request.user


def public_user(user):
    return {"id": user.id, "employee_number": user.employee_number, "name": user.first_name, "last_name": user.last_name, "username": user.username, "role": user.role, "role_name": "Operador" if user.role == "Solicitante" else user.role, "permissions": modules(user), "actions": actions(user), "areas": user.area_permissions, "must_change_password": user.must_change_password}


def audit(user, entity, entity_id, action, before=None, after=None, reason=""):
    AuditLog.objects.create(user=user, entity_type=entity, entity_id=entity_id, action=action, before=before, after=after, reason=reason or "")


def asset_audit_snapshot(asset):
    fields = ["code", "original_code", "alias_codes", "name", "category", "asset_type", "area", "line", "location_detail", "brand", "model", "voltage", "serial_code", "observations", "critical", "operational_status", "operational_status_cause", "administrative_status", "operating_hours"]
    return {key: str(getattr(asset, key)) if isinstance(getattr(asset, key), Decimal) else getattr(asset, key) for key in fields}


def material_total(materials):
    net_cost = ExpressionWrapper(
        (F("quantity") - F("returned_quantity")) * F("unit_cost"),
        output_field=DecimalField(max_digits=24, decimal_places=4),
    )
    return materials.aggregate(total=Sum(net_cost))["total"] or Decimal("0")


def dashboard_orders(request, user):
    qs = order_queryset(user)
    start = parse_day(request.GET["from"], "fecha inicial") if request.GET.get("from") else None
    end = parse_day(request.GET["to"], "fecha final") if request.GET.get("to") else None
    if start and end and start > end:
        raise ApiError("La fecha inicial debe ser anterior o igual a la final")
    if start: qs = qs.filter(requested_at__date__gte=start)
    if end: qs = qs.filter(requested_at__date__lte=end)
    return qs


def dashboard_api(request):
    user = require(request, "orders.read")
    if user.role == "Solicitante": raise ApiError("Tu usuario no tiene permiso para ver el tablero", 403)
    qs = dashboard_orders(request, user)
    sync_operational_alerts(user)
    open_qs = qs.exclude(status__in=["Completada", "Cancelada"])
    assets = Asset.objects.all()
    plans = PreventivePlan.objects.all()
    if user.area_permissions:
        assets = assets.filter(area__in=user.area_permissions)
        plans = plans.filter(asset__area__in=user.area_permissions)
    recent = [order_dict(x) for x in qs.order_by("-requested_at")[:6]]
    urgent = [order_dict(x) for x in open_qs.filter(priority="Paro de máquina").order_by("-requested_at")[:6]]
    totals = qs.aggregate(labor_hours=Sum("labor_hours"))
    materials_total = material_total(MaintenanceMaterial.objects.filter(work_order__in=qs))
    by_status = [{"label": row["status"], "value": row["value"]} for row in qs.values("status").annotate(value=Count("id")).order_by("status")]
    by_classification = [{"label": row["classification"], "value": row["value"]} for row in qs.values("classification").annotate(value=Count("id")).order_by("classification")]
    start = request.GET.get("from", "")
    end = request.GET.get("to", "")
    return JsonResponse({
        "updated_at": iso(timezone.now()), "period": {"from": start, "to": end},
        "orders": {
            "total": qs.count(), "open": open_qs.count(),
            "new_orders": qs.filter(status="Abierta").count(),
            "completed": qs.filter(status="Completada").count(),
            "unassigned": open_qs.filter(technician__isnull=True).count(),
            "critical": open_qs.filter(priority="Paro de máquina").count(),
            "labor_hours": float(totals["labor_hours"] or 0), "material_cost": float(materials_total),
        },
        "byStatus": by_status, "byClassification": by_classification,
        "urgent": urgent, "recent": recent,
        "inventory": {"low_stock": InventoryItem.objects.filter(active=True, stock__lte=F("min_stock")).count()},
        "assets": {"total": assets.count(), "maintenance": assets.filter(operational_status="En mantenimiento").count(), "stopped": assets.filter(operational_status="Parada").count(), "stopped_details": [{"id": asset.id, "code": asset.code, "name": asset.name, "cause": asset.operational_status_cause} for asset in assets.filter(operational_status="Parada").order_by("code")[:10]]},
        "preventives": {"attention": plans.filter(next_date__lte=timezone.localdate()).count()},
    })


def dashboard_xlsx(request):
    user = require(request, "orders.read")
    if user.role == "Solicitante": raise ApiError("Tu usuario no tiene permiso para exportar el tablero", 403)
    dashboard_orders(request, user)
    response = orders_xlsx(request)
    response["Content-Disposition"] = 'attachment; filename="reporte-tablero.xlsx"'
    return response


def sync_operational_alerts(user):
    sources = {}
    assets = Asset.objects.filter(operational_status="Parada")
    plans = PreventivePlan.objects.filter(next_date__lte=timezone.localdate()).select_related("asset")
    orders = order_queryset(user).exclude(status__in=["Completada", "Cancelada"]).filter(priority="Paro de mÃ¡quina").select_related("asset")
    if user.area_permissions:
        assets = assets.filter(area__in=user.area_permissions)
        plans = plans.filter(asset__area__in=user.area_permissions)
    for item in assets:
        key = f"asset_stopped:{item.id}"
        sources[key] = {"kind":"asset_stopped", "source_id":item.id, "area":item.area, "title":f"Activo en parada: {item.code} Â· {item.name}", "detail":item.operational_status_cause or "Causa pendiente", "severity":"CrÃ­tica" if item.critical else "Alta"}
    for item in orders:
        key = f"critical_order:{item.id}"
        sources[key] = {"kind":"critical_order", "source_id":item.id, "area":item.asset.area if item.asset_id else "", "title":f"OT {item.folio} con prioridad Paro de mÃ¡quina", "detail":f"{item.asset.name if item.asset_id else 'Sin activo'} Â· {item.status}", "severity":"CrÃ­tica"}
    for item in plans:
        key = f"preventive_due:{item.id}"
        sources[key] = {"kind":"preventive_due", "source_id":item.id, "area":item.asset.area, "title":f"Preventivo por atender: {item.title}", "detail":f"{item.asset.code} Â· fecha: {item.next_date.isoformat()}", "severity":"Aviso"}
    for item in InventoryItem.objects.filter(active=True, stock__lte=F("min_stock")):
        key = f"low_stock:{item.id}"
        sources[key] = {"kind":"low_stock", "source_id":item.id, "area":"", "title":f"Existencia en o bajo mÃ­nimo: {item.code} Â· {item.name}", "detail":f"Existencia: {item.stock} {item.unit} · mÃ­nimo: {item.min_stock} {item.unit}", "severity":"Aviso"}
    now = timezone.now()
    current = set(sources)
    for key, data in sources.items():
        alert, created = OperationalAlert.objects.get_or_create(source_key=key, defaults=data)
        if not created:
            changed = any(getattr(alert, field) != value for field, value in data.items())
            if alert.status == "Cerrada":
                alert.status = "Abierta"
                alert.handling_note = ""
                alert.handled_by = None
                alert.handled_at = None
                changed = True
            if changed:
                for field, value in data.items(): setattr(alert, field, value)
                alert.save()
    stale = OperationalAlert.objects.filter(status__in=["Abierta", "Atendida"])
    if user.area_permissions:
        stale = stale.filter(Q(area__in=user.area_permissions) | Q(area="", kind="low_stock"))
    stale.exclude(source_key__in=current).update(status="Cerrada", updated_at=now)


def alert_dict(alert):
    return {"id":alert.id, "kind":alert.kind, "title":alert.title, "detail":alert.detail, "severity":alert.severity, "area":alert.area, "status":alert.status, "handling_note":alert.handling_note, "handled_by":alert.handled_by.first_name if alert.handled_by else None, "handled_at":iso(alert.handled_at), "updated_at":iso(alert.updated_at)}


def operational_alerts_api(request):
    user = require(request, "orders.read")
    if user.role == "Solicitante": raise ApiError("Tu usuario no tiene permiso para ver alertas", 403)
    sync_operational_alerts(user)
    qs = OperationalAlert.objects.filter(status__in=["Abierta", "Atendida"])
    if user.area_permissions:
        qs = qs.filter(Q(area__in=user.area_permissions) | Q(area="", kind="low_stock"))
    if request.method == "GET": return JsonResponse({"alerts":[alert_dict(x) for x in qs.select_related("handled_by")]})
    if request.method != "POST": raise ApiError("MÃ©todo no permitido", 405)
    data = payload(request)
    alert = get_object_or_404(qs, pk=data.get("id"))
    if alert.status == "Cerrada": raise ApiError("La condiciÃ³n de esta alerta ya no estÃ¡ activa", 409)
    note = str(data.get("note", "")).strip()
    if not note: raise ApiError("Escribe una nota breve sobre la atenciÃ³n realizada")
    if len(note) > 2000: raise ApiError("La nota no puede exceder 2000 caracteres")
    before = {"status":alert.status, "handling_note":alert.handling_note}
    alert.status = "Atendida"; alert.handling_note = note; alert.handled_by = user; alert.handled_at = timezone.now(); alert.save()
    audit(user, "operational_alert", alert.id, "attended", before=before, after={"status":alert.status, "handling_note":note}, reason=note)
    return JsonResponse(alert_dict(alert))


def operational_alerts_xlsx(request):
    user = require(request, "orders.read")
    if user.role == "Solicitante": raise ApiError("Tu usuario no tiene permiso para exportar alertas", 403)
    sync_operational_alerts(user)
    rows = OperationalAlert.objects.filter(status__in=["Abierta", "Atendida"])
    if user.area_permissions:
        rows = rows.filter(Q(area__in=user.area_permissions) | Q(area="", kind="low_stock"))
    headers = ["Severidad", "Alerta", "Detalle", "Área", "Estado", "Nota de atención", "Atendió", "Fecha de atención", "Última actualización"]
    data = []
    for alert in rows.select_related("handled_by").order_by("status", "-updated_at", "id"):
        handled_at = timezone.localtime(alert.handled_at) if alert.handled_at and timezone.is_aware(alert.handled_at) else alert.handled_at
        updated_at = timezone.localtime(alert.updated_at) if timezone.is_aware(alert.updated_at) else alert.updated_at
        data.append([alert.severity, alert.title, alert.detail, alert.area, alert.status, alert.handling_note, alert.handled_by.first_name if alert.handled_by else "", handled_at, updated_at])
    content = make_workbook("Alertas operativas", headers, data, date_columns={8, 9})
    response = HttpResponse(content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="alertas-operativas.xlsx"'
    return response


def asset_dict(a):
    return {"id": a.id, "code": a.code, "original_code": a.original_code, "alias_codes": a.alias_codes, "approved_codes": [x.code for x in a.code_equivalences.all() if x.status == "Aprobada"], "name": a.name, "category": a.category, "asset_type": a.asset_type, "area": a.area, "line": a.line, "location_detail": a.location_detail, "brand": a.brand, "model": a.model, "voltage": a.voltage, "serial_code": a.serial_code, "observations": a.observations, "operating_hours": float(a.operating_hours), "operational_status": a.operational_status, "operational_status_cause": a.operational_status_cause, "administrative_status": a.administrative_status, "critical": a.critical, "status": a.operational_status}


def equivalence_dict(item):
    return {"id": item.id, "code": item.code, "status": item.status, "source_file": item.source_file, "source_sheet": item.source_sheet, "source_row": item.source_row, "notes": item.notes, "proposed_by": item.proposed_by.first_name, "created_at": iso(item.created_at), "reviewed_by": item.reviewed_by.first_name if item.reviewed_by else None, "reviewed_at": iso(item.reviewed_at), "review_reason": item.review_reason}


def checked_asset_code(value, asset_id=None):
    code = str(value or "").strip()
    if not code or len(code) > 80: raise ApiError("Indica un código de hasta 80 caracteres")
    key = code.casefold()
    if any(existing.casefold() == key for existing in Asset.objects.exclude(pk=asset_id).values_list("code", flat=True)):
        raise ApiError("El código ya pertenece a otro activo", 409)
    if AssetCodeEquivalence.objects.filter(code_key=key, status="Aprobada").exclude(asset_id=asset_id).exists():
        raise ApiError("El código ya es una equivalencia aprobada de otro activo", 409)
    return code


def order_dict(o, detail=False, operator=False):
    row = {"id": o.id, "folio": o.folio, "requested_at": iso(o.requested_at), "requester_id": o.requester_id, "requester_name": o.requester.first_name, "requester_number": o.requester.employee_number, "priority": o.priority, "classification": o.classification, "specialty": o.specialty, "asset_id": o.asset_id, "asset": o.asset.name if o.asset else None, "asset_name": o.asset.name if o.asset else None, "asset_code": o.asset.code if o.asset else None, "location": o.location, "reported_failure": o.reported_failure, "technician_id": o.technician_id, "technician_name": o.technician.first_name if o.technician else None, "status": o.status, "validation_status": o.validation_status, "scheduled_at": iso(o.scheduled_at), "started_at": iso(o.started_at), "finished_at": iso(o.finished_at), "updated_at": iso(o.updated_at), "version": o.version}
    row.update({"actions": o.actions, "labor_hours": float(o.labor_hours)})
    if not operator:
        row.update({"material_cost": float(material_total(o.materials)), "closure_notes": o.closure_notes, "closure_document_code": o.closure_document_code, "closure_document_revision": o.closure_document_revision})
    if detail and operator: return row
    if detail:
        row["participants"] = [{"id": person.id, "name": person.first_name} for person in o.participants.all()]
        row["time_entries"] = [{"id": entry.id, "user_id": entry.user_id, "user_name": entry.user.first_name, "started_at": iso(entry.started_at), "finished_at": iso(entry.finished_at), "pause_reason": entry.pause_reason, "source": entry.source} for entry in o.time_entries.select_related("user").order_by("started_at", "id")]
        row.update({"asset_brand": o.asset.brand if o.asset else None, "asset_model": o.asset.model if o.asset else None, "asset_voltage": o.asset.voltage if o.asset else None, "validator_name": o.validator.first_name if o.validator else None, "validated_at": iso(o.validated_at)})
        row["events"] = [{"id": e.id, "event": e.event, "details": e.details, "created_at": iso(e.created_at), "user_name": e.user.first_name if e.user else "Sistema"} for e in o.events.select_related("user").order_by("created_at")]
        row["materials"] = [{"id": m.id, "inventory_item_id": m.item_id, "code": m.code, "description": m.description, "quantity": float(m.quantity), "returned_quantity": float(m.returned_quantity), "unit_cost": float(m.unit_cost), "total": float((m.quantity-m.returned_quantity)*m.unit_cost), "movement_id": m.movement_id} for m in o.materials.all()]
        occurrences = list(o.preventive_occurrences.select_related("task").prefetch_related("execution_events"))
        if occurrences:
            def execution(item):
                events = list(item.execution_events.order_by("recorded_at")); terminated = next((x for x in reversed(events) if x.event == "terminated"), None); validated = next((x for x in reversed(events) if x.event == "validated"), None)
                return {"occurrence_id": item.id, "task_id": item.task_id, "task_title": item.task.title, "base_date": item.base_date.isoformat(), "state": events[-1].event if events else "Sin ejecución registrada", "executed_at": iso(terminated.recorded_at) if terminated else None, "validated_at": iso(validated.recorded_at) if validated else None, "events": [{"event": x.event, "user_id": x.user_id, "notes": x.notes, "reason": x.reason, "recorded_at": iso(x.recorded_at)} for x in events]}
            items = [execution(x) for x in occurrences]; row["preventive_execution"] = items[0] | {"items": items}
        else: row["preventive_execution"] = None
    return row


def health(request):
    return JsonResponse({"status": "ok"})


def csrf_failure(request, reason=""):
    return JsonResponse({"error": "La sesión de seguridad venció. Recarga la página e inténtalo de nuevo."}, status=403)


def static_app(request, path=""):
    get_token(request)
    target = Path(settings.BASE_DIR / "static" / (path or "index.html")).resolve()
    root = (settings.BASE_DIR / "static").resolve()
    if root not in target.parents and target != root:
        return JsonResponse({"error": "Acceso denegado"}, status=403)
    if not target.exists() or target.is_dir():
        target = root / "index.html"
    if target.name == "index.html":
        content = target.read_text(encoding="utf-8")
        version = hashlib.sha256((root / "app.js").read_bytes()).hexdigest()[:12]
        content = content.replace("__APP_JS_VERSION__", version)
        response = HttpResponse(content, content_type="text/html; charset=utf-8")
        response["Cache-Control"] = "no-cache"
        return response
    return FileResponse(open(target, "rb"))


def api(request, path):
    try:
        return dispatch(request, "/api/" + path.strip("/"))
    except ApiError as error:
        return JsonResponse({"error": error.message}, status=error.status)
    except IntegrityError:
        return JsonResponse({"error": "El registro ya existe"}, status=409)
    except Http404:
        return JsonResponse({"error": "Registro no encontrado"}, status=404)


def dispatch(request, path):
    method = request.method
    if path == "/api/auth/login" and method == "POST":
        data = payload(request)
        user = authenticate(request, username=str(data.get("username", "")).strip(), password=str(data.get("password", "")))
        if not user or not user.is_active:
            raise ApiError("Usuario o contraseña incorrectos", 401)
        login(request, user)
        return JsonResponse(public_user(user))
    if path == "/api/auth/logout" and method == "POST":
        logout(request)
        return JsonResponse({"ok": True})
    if path == "/api/auth/me" and method == "GET":
        return JsonResponse(public_user(require(request, allow_password_change=True)))
    if path == "/api/auth/change-password" and method == "POST":
        user = require(request, allow_password_change=True); data = payload(request)
        if not user.check_password(str(data.get("current_password", ""))): raise ApiError("La contraseña actual no es correcta", 403)
        if len(str(data.get("new_password", ""))) < 8: raise ApiError("La contraseña debe tener al menos 8 caracteres")
        user.set_password(data["new_password"]); user.must_change_password = False; user.save(); update_session_auth_hash(request, user); audit(user, "user", user.id, "password_changed")
        return JsonResponse({"ok": True})
    if path == "/api/catalogs" and method == "GET":
        user = require(request)
        users = [public_user(x) | {"name": x.first_name} for x in User.objects.filter(is_active=True)] if user.role != "Solicitante" else [public_user(user) | {"name": user.first_name}]
        assets = [asset_dict(x) for x in Asset.objects.filter(administrative_status="Activo") if not user.area_permissions or x.area in user.area_permissions]
        return JsonResponse({"users": users, "assets": assets, "priorities": catalog_values("priority"), "classifications": catalog_values("classification"), "specialties": catalog_values("specialty"), "areas": catalog_values("area"), "lines": catalog_values("line"), "shifts": catalog_values("shift")})
    if path == "/api/catalog-entries": return catalog_entries_api(request)
    if path.startswith("/api/catalog-entries/"): return catalog_entry_api(request, int(path.rsplit("/", 1)[1]))
    if path == "/api/alerts/export.xlsx": return operational_alerts_xlsx(request)
    if path == "/api/alerts": return operational_alerts_api(request)
    if path == "/api/dashboard/export.xlsx" and method == "GET": return dashboard_xlsx(request)
    if path == "/api/dashboard" and method == "GET": return dashboard_api(request)
    if path == "/api/imports/preview": return import_preview_api(request)
    if path == "/api/imports": return import_batches_api(request)
    if path.startswith("/api/imports/") and "/rows/" in path:
        return import_row_review_api(request, int(path.split("/")[3]), int(path.split("/")[5]))
    if path.startswith("/api/imports/") and path.endswith("/incidents"):
        return import_incidents_api(request, int(path.split("/")[3]))
    if path.startswith("/api/imports/") and path.endswith("/readiness/export.xlsx"):
        return import_readiness_xlsx_api(request, int(path.split("/")[3]))
    if path.startswith("/api/imports/") and path.endswith("/readiness"):
        return import_readiness_api(request, int(path.split("/")[3]))
    if path.startswith("/api/imports/") and path.endswith("/reconciliation/references"):
        return import_reference_reconciliation_api(request, int(path.split("/")[3]))
    if path.startswith("/api/imports/") and path.endswith("/reconciliation"):
        return import_reconciliation_api(request, int(path.split("/")[3]))
    if path.startswith("/api/imports/") and path.endswith("/rows"):
        return import_rows_api(request, int(path.split("/")[3]))
    if path.startswith("/api/imports/"): return import_batch_api(request, int(path.rsplit("/", 1)[1]))
    if path == "/api/users": return users_api(request)
    if path.startswith("/api/users/"): return user_api(request, int(path.rsplit("/", 1)[1]))
    if path == "/api/assets/export.xlsx": return assets_xlsx(request)
    if path == "/api/assets": return assets_api(request)
    if path.startswith("/api/assets/") and "/equivalences/" in path:
        parts = path.split("/")
        return asset_equivalence_review_api(request, int(parts[3]), int(parts[5]))
    if path.startswith("/api/assets/") and path.endswith("/equivalences"):
        return asset_equivalences_api(request, int(path.split("/")[3]))
    if path.startswith("/api/assets/") and path.endswith("/meter-readings"): return meter_api(request, int(path.split("/")[3]))
    if path.startswith("/api/assets/"): return asset_api(request, int(path.rsplit("/", 1)[1]))
    if path == "/api/inventory/template.csv": return inventory_template(request)
    if path == "/api/inventory/export.csv": return inventory_export(request)
    if path == "/api/inventory/export.xlsx": return inventory_xlsx(request)
    if path == "/api/inventory/preview-import": return inventory_import(request, preview=True)
    if path == "/api/inventory/import": return inventory_import(request, preview=False)
    if path == "/api/inventory/bulk-create": return inventory_bulk_create(request)
    if path == "/api/inventory": return inventory_api(request)
    if path.endswith("/movements") and path.startswith("/api/inventory/"): return movements_api(request, int(path.split("/")[3]))
    if path.endswith("/movement") and path.startswith("/api/inventory/"): return movement_api(request, int(path.split("/")[3]))
    if path.startswith("/api/inventory/") and path.split("/")[-1].isdigit(): return inventory_item_api(request, int(path.rsplit("/", 1)[1]))
    if path == "/api/orders": return orders_api(request)
    if path == "/api/orders/export.csv": return orders_csv(request)
    if path == "/api/orders/export.xlsx": return orders_xlsx(request)
    if path.startswith("/api/orders/") and "/documents/" in path:
        parts = path.split("/")
        return work_order_document_download_api(request, int(parts[3]), int(parts[5]))
    if path.startswith("/api/orders/") and path.endswith("/documents"):
        return work_order_documents_api(request, int(path.split("/")[3]))
    if path.endswith("/time-entries/actions"): return time_action_api(request, int(path.split("/")[3]))
    if path.endswith("/time-entries"): return time_api(request, int(path.split("/")[3]))
    if "/time-entries/" in path: return time_correction_api(request, int(path.split("/")[3]), int(path.split("/")[5]))
    if path.endswith("/transitions") or path.endswith("/validate"): return transition_api(request, int(path.split("/")[3]), path.endswith("/validate"))
    if path.startswith("/api/orders/"): return order_api(request, int(path.rsplit("/", 1)[1]))
    if path == "/api/preventive-templates": return templates_api(request)
    if path == "/api/preventive-calendar": return preventive_calendar_api(request)
    if path == "/api/preventives/export.xlsx": return preventives_xlsx(request)
    if path == "/api/preventives": return preventives_api(request)
    if path.endswith("/apply-template"): return apply_template_api(request, int(path.split("/")[3]))
    if path.endswith("/occurrences/group"): return occurrence_group_api(request, int(path.split("/")[3]))
    if "/tasks/" in path and path.endswith("/checklist"): return task_checklist_api(request, int(path.split("/")[3]), int(path.split("/")[5]))
    if "/occurrences/" in path and path.endswith("/checklist"): return occurrence_checklist_api(request, int(path.split("/")[3]), int(path.split("/")[5]))
    if "/occurrences/" in path and path.endswith("/reschedule"): return reschedule_api(request, int(path.split("/")[3]), int(path.split("/")[5]))
    if path.endswith("/tasks"): return tasks_api(request, int(path.split("/")[3]))
    if "/tasks/" in path and path.endswith("/applicability"): return task_applicability_api(request, int(path.split("/")[3]), int(path.split("/")[5]))
    if path.endswith("/calendar"): return calendar_api(request, int(path.split("/")[3]))
    if path.endswith("/occurrences"): return occurrences_api(request, int(path.split("/")[3]))
    if path.endswith("/compliance"): return compliance_api(request, int(path.split("/")[3]))
    if path.endswith("/upcoming"): return upcoming_api(request, int(path.split("/")[3]))
    if path.endswith("/revisions"): return revisions_api(request, int(path.split("/")[3]))
    if path.endswith("/order"): return preventive_order_api(request, int(path.split("/")[3]))
    if path.startswith("/api/preventives/"): return preventive_api(request, int(path.rsplit("/", 1)[1]))
    if path == "/api/downtime-events/export.xlsx": return downtime_xlsx(request)
    if path == "/api/downtime-events": return downtime_api(request)
    if path.startswith("/api/downtime-events/"): return downtime_item_api(request, int(path.rsplit("/", 1)[1]))
    if path == "/api/agenda": return agenda_api(request)
    if path == "/api/audit/export.xlsx": return audit_xlsx(request)
    if path == "/api/audit": return audit_api(request)
    raise ApiError("Ruta no encontrada", 404)


def import_preview_api(request):
    user = require(request, "users.manage")
    if request.method != "POST":
        raise ApiError("Método no permitido", 405)
    upload = request.FILES.get("file")
    if not upload:
        raise ApiError("Selecciona un libro Excel")
    digest = hashlib.sha256()
    for chunk in upload.chunks():
        digest.update(chunk)
    upload.seek(0)
    existing_codes = {
        value.casefold() for value in
        list(Asset.objects.values_list("code", flat=True))
        + list(InventoryItem.objects.values_list("code", flat=True))
        + list(WorkOrder.objects.values_list("folio", flat=True))
    }
    try:
        result = preview_workbook(upload, existing_codes)
    except ValueError as error:
        raise ApiError(str(error))
    staged_rows = result.pop("staged_rows")
    with transaction.atomic():
        batch, created = ImportBatch.objects.get_or_create(
            content_hash=digest.hexdigest(),
            defaults={"filename": upload.name[:250], "preview": result, "uploaded_by": user},
        )
        batch = ImportBatch.objects.select_for_update().get(pk=batch.pk)
        if batch.status == "Revision" and not batch.source_rows.exists():
            ImportRow.objects.bulk_create(
                [ImportRow(batch=batch, **row) for row in staged_rows], batch_size=250,
            )
        elif batch.status == "Revision" and "date_system" not in batch.preview:
            by_source = {(row.sheet, row.source_row): row for row in batch.source_rows.all()}
            changed_rows = []
            for staged in staged_rows:
                row = by_source.get((staged["sheet"], staged["source_row"]))
                if row and staged["cell_details"]:
                    row.cell_details = staged["cell_details"]
                    row.issues = list(dict.fromkeys(row.issues + staged["issues"]))
                    changed_rows.append(row)
            if changed_rows:
                ImportRow.objects.bulk_update(changed_rows, ["cell_details", "issues"], batch_size=250)
            batch.preview = batch.preview | {"date_system": result["date_system"]}
            batch.save(update_fields=["preview"])
        if created:
            audit(user, "import_batch", batch.id, "preview_created", after={"filename": batch.filename, "sha256": batch.content_hash, "sheets": len(result["sheets"]), "rows": len(staged_rows)})
    return JsonResponse(result | {"batch": import_batch_dict(batch), "duplicate": not created, "operational_data_changed": False})


def import_batch_dict(batch):
    sheets = batch.preview.get("sheets", [])
    staged_count = batch.staged_count if hasattr(batch, "staged_count") else batch.source_rows.count()
    review_counts = (
        {"Pendiente": batch.pending_count, "Excluida": batch.excluded_count, "Propuesta": batch.proposed_count}
        if hasattr(batch, "pending_count") else
        {status: batch.source_rows.filter(review_status=status).count() for status in ("Pendiente", "Excluida", "Propuesta")}
    )
    return {
        "id": batch.id, "filename": batch.filename, "status": batch.status,
        "created_at": iso(batch.created_at), "uploaded_by": batch.uploaded_by.first_name,
        "content_hash": batch.content_hash,
        "sheet_count": len(sheets), "row_count": sum(sheet.get("rows", 0) for sheet in sheets),
        "staged_row_count": staged_count,
        "review_counts": review_counts,
        "visible_conflict_count": sum(len(sheet.get("conflicts", [])) for sheet in sheets),
        "discard_reason": batch.discard_reason,
    }


def import_batches_api(request):
    require(request, "users.manage")
    if request.method != "GET":
        raise ApiError("Método no permitido", 405)
    batches = ImportBatch.objects.select_related("uploaded_by").annotate(
        staged_count=Count("source_rows"),
        pending_count=Count("source_rows", filter=Q(source_rows__review_status="Pendiente")),
        excluded_count=Count("source_rows", filter=Q(source_rows__review_status="Excluida")),
        proposed_count=Count("source_rows", filter=Q(source_rows__review_status="Propuesta")),
    )[:100]
    return JsonResponse([import_batch_dict(batch) for batch in batches], safe=False)


def import_rows_api(request, batch_id):
    require(request, "users.manage")
    if request.method != "GET":
        raise ApiError("Método no permitido", 405)
    get_object_or_404(ImportBatch, pk=batch_id)
    try:
        page = int(request.GET.get("page", "1"))
    except ValueError:
        raise ApiError("Página inválida")
    if page < 1 or page > 10000:
        raise ApiError("Página inválida")
    rows = ImportRow.objects.filter(batch_id=batch_id)
    sheet = request.GET.get("sheet", "")
    if sheet:
        rows = rows.filter(sheet=sheet)
    count = rows.count()
    selected = rows.select_related("proposed_asset", "reviewed_by").order_by("sheet", "source_row", "id")[(page - 1) * 100:page * 100]
    return JsonResponse({
        "page": page, "page_size": 100, "total": count,
        "rows": [import_row_dict(row) for row in selected],
    })


def import_row_dict(row):
    return {
        "id": row.id, "sheet": row.sheet, "source_row": row.source_row,
        "cells": row.cells, "formulas": row.formulas, "cell_details": row.cell_details,
        "source_code": row.source_code, "issues": row.issues,
        "review_status": row.review_status, "proposed_asset_id": row.proposed_asset_id,
        "proposed_asset_code": row.proposed_asset.code if row.proposed_asset_id else None,
        "review_note": row.review_note,
        "reviewed_by": row.reviewed_by.first_name if row.reviewed_by_id else None,
        "reviewed_at": iso(row.reviewed_at), "version": row.version,
        "mapping": map_source_row(row.sheet, row.source_row, row.cells, row.cell_details),
    }


def import_readiness_api(request, batch_id):
    require(request, "users.manage")
    if request.method != "GET":
        raise ApiError("MÃ©todo no permitido", 405)
    batch = get_object_or_404(ImportBatch, pk=batch_id)
    reference_response = import_reference_reconciliation_api(request, batch.id)
    reference_data = json.loads(reference_response.content) if reference_response.status_code == 200 else {}
    reference_counts = {
        "maintenance_asset": reference_data.get("maintenance_asset_counts", {}),
        "material_maintenance": reference_data.get("material_maintenance_counts", {}),
        "material_item": reference_data.get("material_item_counts", {}),
    }
    unresolved_reference_count = sum(
        count for counts in reference_counts.values()
        for status, count in counts.items() if status != "Coincidencia única"
    )
    duplicate_key_count = reference_data.get("duplicate_key_count", 0)
    result = {
        "batch_id": batch.id, "batch_status": batch.status, "total_rows": 0,
        "mapped_rows": 0, "unmapped_rows": 0, "pending_review_rows": 0,
        "proposed_link_rows": 0, "excluded_rows": 0, "mapping_issue_rows": 0,
        "field_type_issue_rows": 0,
        "source_issue_rows": 0, "excel_error_cells": 0,
        "uninterpreted_temporal_cells": 0, "formula_without_value_cells": 0,
        "unresolved_reference_count": unresolved_reference_count,
        "duplicate_reference_key_count": duplicate_key_count,
        "reference_counts": reference_counts,
        "by_kind": {},
    }
    for row in ImportRow.objects.filter(batch=batch).only(
        "sheet", "source_row", "cells", "formulas", "cell_details", "issues", "review_status",
    ).iterator():
        result["total_rows"] += 1
        status_key = {"Pendiente": "pending_review_rows", "Propuesta": "proposed_link_rows", "Excluida": "excluded_rows"}[row.review_status]
        result[status_key] += 1
        mapping = map_source_row(row.sheet, row.source_row, row.cells, row.cell_details)
        kind = mapping["kind"]
        summary = result["by_kind"].setdefault(kind, {"rows": 0, "pending": 0, "proposed": 0, "excluded": 0})
        summary["rows"] += 1
        summary[{"Pendiente": "pending", "Propuesta": "proposed", "Excluida": "excluded"}[row.review_status]] += 1
        if row.review_status != "Excluida":
            if kind == "unmapped":
                result["unmapped_rows"] += 1
            else:
                result["mapped_rows"] += 1
            if mapping["issues"]:
                result["mapping_issue_rows"] += 1
            if mapping["type_issues"]:
                result["field_type_issue_rows"] += 1
            if row.issues:
                result["source_issue_rows"] += 1
            result["excel_error_cells"] += sum(detail.get("kind") == "error" for detail in row.cell_details.values())
            temporal_cells = {
                cell for cell, detail in row.cell_details.items()
                if detail.get("kind") in ("date", "datetime") and detail.get("iso") is None
            }
            temporal_cells.update(
                issue["cell"] for issue in mapping["type_issues"]
                if issue["expected"] == "fecha por interpretar"
            )
            result["uninterpreted_temporal_cells"] += len(temporal_cells)
            result["formula_without_value_cells"] += sum(cell not in row.cells for cell in row.formulas)
    blocking_counts = {
        "pending_review_rows": result["pending_review_rows"],
        "proposed_link_rows": result["proposed_link_rows"],
        "unmapped_rows": result["unmapped_rows"],
        "mapping_issue_rows": result["mapping_issue_rows"],
        "field_type_issue_rows": result["field_type_issue_rows"],
        "source_issue_rows": result["source_issue_rows"],
        "excel_error_cells": result["excel_error_cells"],
        "uninterpreted_temporal_cells": result["uninterpreted_temporal_cells"],
        "formula_without_value_cells": result["formula_without_value_cells"],
        "unresolved_reference_count": unresolved_reference_count,
        "duplicate_reference_key_count": duplicate_key_count,
        "batch_not_in_review": int(batch.status != "Revision"),
    }
    result["technical_precheck_clear"] = not any(blocking_counts.values())
    result["blocking_counts"] = blocking_counts
    result["operational_import_available"] = False
    result["operational_import_blockers"] = [
        {
            "code": "SOURCE_CLASSIFICATION_PENDING",
            "decision": "D-12",
            "message": "Confirmar si el archivo contiene datos reales o ejemplos y definir su fecha de corte.",
        },
        {
            "code": "SOURCE_MAPPING_APPROVAL_PENDING",
            "decision": "D-02 / D-04 / D-09 / D-10",
            "message": "Aprobar campos, equivalencias y reglas de conversión con Mantenimiento/Planta.",
        },
        {
            "code": "TRANSACTIONAL_WRITER_DISABLED",
            "decision": "Implementación pendiente",
            "message": "El flujo que escribe registros operativos no está habilitado.",
        },
    ]
    result["notice"] = "La prevalidaciÃ³n solo resume estructura y revisiones; no aprueba datos ni autoriza su carga operativa."
    return JsonResponse(result)


def import_readiness_xlsx_api(request, batch_id):
    """Download a privacy-safe workbook containing only readiness counts and gates."""
    response = import_readiness_api(request, batch_id)
    if response.status_code != 200:
        return response
    readiness = json.loads(response.content)
    rows = [
        ["Lote", "Filas totales", readiness["total_rows"], None],
        ["Lote", "Filas mapeadas", readiness["mapped_rows"], None],
        ["Lote", "Filas sin mapeo", readiness["unmapped_rows"], None],
        ["Lote", "Prevalidación técnica", "Sin bloqueos detectados" if readiness["technical_precheck_clear"] else "Con pendientes", None],
        ["Lote", "Importación operativa", "No disponible", None],
    ]
    rows.extend(
        ["Estado de fila", kind, status, count]
        for kind, counts in readiness["by_kind"].items()
        for status, count in counts.items()
    )
    rows.extend(
        ["Bloqueo técnico", name, "Pendiente" if count else "Sin incidencias", count]
        for name, count in readiness["blocking_counts"].items()
    )
    rows.extend(
        ["Referencia", relation, status, count]
        for relation, counts in readiness["reference_counts"].items()
        for status, count in counts.items()
    )
    rows.extend(
        ["Autorización operativa", item["decision"], item["message"], item["code"]]
        for item in readiness["operational_import_blockers"]
    )
    content = make_workbook(
        "Prevalidacion", ["Grupo", "Indicador", "Estado o detalle", "Conteo"], rows,
    )
    export = HttpResponse(
        content,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    export["Content-Disposition"] = f'attachment; filename="prevalidacion-lote-{batch_id}.xlsx"'
    export["Cache-Control"] = "no-store"
    return export


def import_incidents_api(request, batch_id):
    require(request, "users.manage")
    if request.method != "GET":
        raise ApiError("Método no permitido", 405)
    get_object_or_404(ImportBatch, pk=batch_id)
    try:
        page = int(request.GET.get("page", "1"))
    except ValueError:
        raise ApiError("Página inválida")
    if page < 1 or page > 10000:
        raise ApiError("Página inválida")
    page_size = 50
    matching = []
    error_count = 0
    invalid_temporal_count = 0
    ordered_rows = ImportRow.objects.filter(batch_id=batch_id).only(
        "id", "sheet", "source_row", "cells", "formulas", "cell_details", "review_status",
    ).order_by("sheet", "source_row", "id")
    row_number_by_sheet = {}
    for row in ordered_rows.iterator():
        row_number_by_sheet[row.sheet] = row_number_by_sheet.get(row.sheet, 0) + 1
        affected = []
        for address, detail in row.cell_details.items():
            if detail.get("kind") == "error":
                error_count += 1
                affected.append({"cell": address, "kind": "error", "raw": row.cells.get(address, detail.get("value", "")), "formula": row.formulas.get(address, "")})
            elif detail.get("kind") in ("date", "datetime") and detail.get("iso") is None:
                invalid_temporal_count += 1
                affected.append({"cell": address, "kind": "invalid_temporal", "raw": row.cells.get(address, ""), "formula": row.formulas.get(address, ""), "date_system": detail.get("date_system", "")})
        if affected:
            matching.append({
                "id": row.id, "sheet": row.sheet, "source_row": row.source_row,
                "source_page": (row_number_by_sheet[row.sheet] - 1) // 100 + 1,
                "review_status": row.review_status, "issues": row.issues, "cells": affected,
            })
    start = (page - 1) * page_size
    return JsonResponse({
        "page": page, "page_size": page_size, "total": len(matching),
        "excel_error_count": error_count, "invalid_temporal_count": invalid_temporal_count,
        "incidents": matching[start:start + page_size],
    })


def import_reconciliation_api(request, batch_id):
    require(request, "users.manage")
    if request.method != "GET":
        raise ApiError("Método no permitido", 405)
    get_object_or_404(ImportBatch, pk=batch_id)
    try:
        page = int(request.GET.get("page", "1"))
    except ValueError:
        raise ApiError("Página inválida")
    if page < 1 or page > 10000:
        raise ApiError("Página inválida")
    groups = {}
    without_code = 0
    for row in ImportRow.objects.filter(batch_id=batch_id).only(
        "id", "sheet", "source_row", "source_code", "review_status", "proposed_asset_id", "cells",
    ).iterator():
        spec = CODE_COLUMNS.get(row.sheet.upper())
        if not spec or row.sheet.upper() not in {"MAQUINAS", "BASE DE DATOS", "CALENDARIO"} or row.source_row < spec[1]:
            continue
        key = row.source_code.strip().casefold()
        if not key:
            without_code += 1
            continue
        group = groups.setdefault(key, {"code": row.source_code.strip(), "rows": [], "sheet_counts": {}, "review_counts": {status: 0 for status in ("Pendiente", "Excluida", "Propuesta")}, "_attribute_values": {}})
        group["rows"].append({"id": row.id, "sheet": row.sheet, "source_row": row.source_row, "status": row.review_status, "proposed_asset_id": row.proposed_asset_id})
        group["sheet_counts"][row.sheet] = group["sheet_counts"].get(row.sheet, 0) + 1
        group["review_counts"][row.review_status] += 1
        fields = map_source_row(row.sheet, row.source_row, row.cells)["fields"]
        for attribute in ("name", "brand", "model", "voltage"):
            value = fields.get(attribute, "")
            if value:
                group["_attribute_values"].setdefault(attribute, {}).setdefault(value.casefold(), value)
    ordered = sorted(groups.items())
    selected = ordered[(page - 1) * 50:page * 50]
    keys = {key for key, _ in selected}
    matches = {key: [] for key in keys}
    for asset in Asset.objects.only("id", "code"):
        key = asset.code.strip().casefold()
        if key in matches:
            matches[key].append({"id": asset.id, "code": asset.code, "via": "Código vigente"})
    for item in AssetCodeEquivalence.objects.filter(status="Aprobada", code_key__in=keys).select_related("asset"):
        matches[item.code_key].append({"id": item.asset_id, "code": item.asset.code, "via": "Equivalencia aprobada"})
    result = []
    for key, group in selected:
        source_rows = group["rows"]
        variants = {name: list(values.values()) for name, values in group["_attribute_values"].items() if len(values) > 1}
        result.append({name: value for name, value in group.items() if name not in ("rows", "_attribute_values")} | {
            "source_row_count": len(source_rows), "rows": source_rows[:100],
            "more_rows": max(0, len(source_rows) - 100),
            "repeated_within_sheet": any(count > 1 for count in group["sheet_counts"].values()),
            "asset_matches": matches[key],
            "attribute_variants": variants,
        })
    return JsonResponse({
        "page": page, "page_size": 50, "total": len(ordered),
        "source_rows_with_code": sum(len(group["rows"]) for group in groups.values()),
        "source_rows_without_code": without_code,
        "groups": result,
    })


def import_reference_reconciliation_api(request, batch_id):
    require(request, "users.manage")
    if request.method != "GET":
        raise ApiError("Método no permitido", 405)
    get_object_or_404(ImportBatch, pk=batch_id)
    source_rows = ImportRow.objects.filter(batch_id=batch_id).exclude(review_status="Excluida").only("id", "sheet", "source_row", "cells")
    records = {}
    for row in source_rows.iterator():
        mapped = map_source_row(row.sheet, row.source_row, row.cells)
        fields = mapped["fields"]
        if mapped["kind"] in ("asset_candidate", "maintenance_history_candidate", "material_history_candidate", "inventory_candidate", "work_order_candidate"):
            records.setdefault(mapped["kind"], []).append({
                "row_id": row.id, "sheet": row.sheet, "source_row": row.source_row,
                **fields,
            })

    def index(rows, field):
        output = {}
        for item in rows:
            value = str(item.get(field, "")).strip().casefold()
            if value:
                output.setdefault(value, []).append(item)
        return output

    machines = [item for item in records.get("asset_candidate", []) if item["sheet"].upper() == "MAQUINAS"]
    source_assets = records.get("asset_candidate", [])
    maintenance = records.get("maintenance_history_candidate", [])
    warehouse = records.get("inventory_candidate", [])
    maintenance_by_id = index(maintenance, "source_id")
    machine_by_id = index(machines, "source_id")
    asset_by_code = index(source_assets, "code")
    material_by_code = index(warehouse, "code")
    duplicate_keys = []
    duplicate_sources = [
        ("ID de origen de MAQUINAS", machines, "source_id", "MAQUINAS"),
        ("ID de origen de MANTENIMIENTOS", maintenance, "source_id", "MANTENIMIENTOS"),
        ("Código de ALMACEN", warehouse, "code", "ALMACEN"),
    ]
    duplicate_sources.extend(
        (f"Código de {sheet}", [item for item in records.get("asset_candidate", []) if item["sheet"].upper() == sheet], "code", sheet)
        for sheet in ("MAQUINAS", "BASE DE DATOS", "CALENDARIO")
    )
    duplicate_sources.append(("Folio de BASE_DATOS", [item for item in records.get("work_order_candidate", []) if item["sheet"].upper() == "BASE_DATOS"], "folio", "BASE_DATOS"))
    for label, source, field, sheet_name in duplicate_sources:
        for key, matches in index(source, field).items():
            if len(matches) > 1:
                duplicate_keys.append({
                    "kind": label, "key": matches[0].get(field, key),
                    "rows": [{"sheet": sheet_name, "source_row": match["source_row"]} for match in matches[:20]],
                    "more_rows": max(0, len(matches) - 20),
                })

    def resolve(value, lookup):
        key = str(value or "").strip().casefold()
        matches = lookup.get(key, []) if key else []
        state = "Sin valor" if not key else "Sin coincidencia" if not matches else "Coincidencia única" if len(matches) == 1 else "Ambigua"
        return {"value": str(value or ""), "status": state, "matches": [
            {"sheet": match["sheet"], "source_row": match["source_row"], "code": match.get("code", ""), "name": match.get("name", match.get("description", "")), "brand": match.get("brand", ""), "model": match.get("model", ""), "voltage": match.get("voltage", "")}
            for match in matches[:20]
        ], "more_matches": max(0, len(matches) - 20)}

    def review_asset_code(reference):
        for match in reference["matches"]:
            code_rows = asset_by_code.get(str(match.get("code", "")).strip().casefold(), [])
            counts_by_sheet = {}
            variants = {}
            for row in code_rows:
                counts_by_sheet[row["sheet"]] = counts_by_sheet.get(row["sheet"], 0) + 1
                for field in ("name", "brand", "model", "voltage"):
                    value = str(row.get(field, "")).strip()
                    if value:
                        variants.setdefault(field, {}).setdefault(value.casefold(), value)
            match["candidate_review"] = {
                "source_rows": [{"sheet": row["sheet"], "source_row": row["source_row"], "name": row.get("name", ""), "brand": row.get("brand", ""), "model": row.get("model", ""), "voltage": row.get("voltage", "")} for row in code_rows[:30]],
                "more_source_rows": max(0, len(code_rows) - 30),
                "repeated_within_sheet": any(count > 1 for count in counts_by_sheet.values()),
                "attribute_variants": {field: list(values.values()) for field, values in variants.items() if len(values) > 1},
            }
        return reference

    asset_references = []
    for item in maintenance:
        reference = review_asset_code(resolve(item.get("source_asset_id"), machine_by_id))
        asset_references.append({"source_row": item["source_row"], "source_id": item.get("source_id", ""), "source_asset_id": reference})
    maintenance_references = []
    material_references = []
    for item in records.get("material_history_candidate", []):
        maintenance_reference = resolve(item.get("source_maintenance_id"), maintenance_by_id)
        material_reference = resolve(item.get("source_item_code"), material_by_code)
        maintenance_references.append({"source_row": item["source_row"], "source_maintenance_id": maintenance_reference})
        material_references.append({"source_row": item["source_row"], "source_item_code": material_reference})

    def counts(references, key):
        values = [reference[key]["status"] for reference in references]
        return {status: values.count(status) for status in ("Coincidencia única", "Sin coincidencia", "Ambigua", "Sin valor")}

    return JsonResponse({
        "maintenance_count": len(maintenance), "material_history_count": len(records.get("material_history_candidate", [])),
        "maintenance_asset_references": asset_references,
        "maintenance_asset_counts": counts(asset_references, "source_asset_id"),
        "material_maintenance_references": maintenance_references,
        "material_maintenance_counts": counts(maintenance_references, "source_maintenance_id"),
        "material_item_references": material_references,
        "material_item_counts": counts(material_references, "source_item_code"),
        "duplicate_key_count": len(duplicate_keys), "duplicate_keys": duplicate_keys[:100],
    })


def import_row_review_api(request, batch_id, row_id):
    user = require(request, "users.manage")
    if request.method != "PATCH":
        raise ApiError("Método no permitido", 405)
    data = payload(request)
    status = str(data.get("status", "")).strip()
    reason = str(data.get("reason", "")).strip()
    if status not in dict(ImportRow.REVIEW_STATUSES):
        raise ApiError("Decisión de revisión inválida")
    if len(reason) < 5:
        raise ApiError("Explica la decisión con al menos 5 caracteres")
    try:
        version = int(data.get("version"))
    except (TypeError, ValueError):
        raise ApiError("Indica la versión de la fila")
    proposed_asset = None
    if status == "Propuesta":
        try:
            asset_id = int(data.get("asset_id"))
        except (TypeError, ValueError):
            raise ApiError("Selecciona el activo al que propones vincular la fila")
        proposed_asset = get_object_or_404(Asset, pk=asset_id)
    elif data.get("asset_id"):
        raise ApiError("Solo una propuesta puede contener un activo")
    with transaction.atomic():
        row = get_object_or_404(
            ImportRow.objects.select_for_update().select_related("batch"),
            pk=row_id, batch_id=batch_id,
        )
        if row.batch.status != "Revision":
            raise ApiError("El lote descartado no admite decisiones nuevas", 409)
        if row.version != version:
            raise ApiError("La fila cambió; actualiza la revisión antes de guardar", 409)
        if status == "Propuesta" and (row.sheet.upper() not in {"MAQUINAS", "BASE DE DATOS", "CALENDARIO"} or not row.source_code):
            raise ApiError("Esta fila no tiene un código de activo identificable")
        before = {"status": row.review_status, "asset_id": row.proposed_asset_id, "note": row.review_note, "version": row.version}
        row.review_status = status
        row.proposed_asset = proposed_asset
        row.review_note = reason
        row.reviewed_by = user
        row.reviewed_at = timezone.now()
        row.version += 1
        row.save(update_fields=["review_status", "proposed_asset", "review_note", "reviewed_by", "reviewed_at", "version"])
        audit(user, "import_row", row.id, "reviewed", before=before,
              after={"status": status, "asset_id": row.proposed_asset_id, "version": row.version}, reason=reason)
    return JsonResponse(import_row_dict(row))


def import_batch_api(request, batch_id):
    user = require(request, "users.manage")
    if request.method == "GET":
        batch = get_object_or_404(ImportBatch.objects.select_related("uploaded_by"), pk=batch_id)
        return JsonResponse({"batch": import_batch_dict(batch), "preview": batch.preview})
    if request.method != "PATCH":
        raise ApiError("Método no permitido", 405)
    data = payload(request)
    reason = str(data.get("reason", "")).strip()
    if len(reason) < 5:
        raise ApiError("Describe el motivo del descarte (al menos 5 caracteres)")
    with transaction.atomic():
        batch = get_object_or_404(ImportBatch.objects.select_for_update(), pk=batch_id)
        if batch.status != "Revision":
            raise ApiError("Solo se pueden descartar lotes que siguen en revisión", 409)
        before = {"status": batch.status}
        batch.status = "Descartado"
        batch.discarded_by = user
        batch.discarded_at = timezone.now()
        batch.discard_reason = reason
        batch.save(update_fields=["status", "discarded_by", "discarded_at", "discard_reason"])
        audit(user, "import_batch", batch.id, "discarded", before=before, after={"status": batch.status}, reason=reason)
    return JsonResponse(import_batch_dict(batch))


def catalog_entries_api(request):
    user = require(request, "catalogs.manage")
    if request.method == "GET":
        return JsonResponse([{"id": item.id, "kind": item.kind, "value": item.value, "active": item.active, "sort_order": item.sort_order} for item in CatalogEntry.objects.all()], safe=False)
    if request.method != "POST": raise ApiError("Método no permitido", 405)
    data = payload(request)
    kind = str(data.get("kind", ""))
    value = str(data.get("value", "")).strip()
    if kind not in dict(CatalogEntry.KINDS): raise ApiError("Tipo de catálogo inválido")
    if not value or len(value) > 120: raise ApiError("Indica un valor de hasta 120 caracteres")
    if any(existing.casefold() == value.casefold() for existing in CatalogEntry.objects.filter(kind=kind).values_list("value", flat=True)):
        raise ApiError("El valor ya existe en este catálogo", 409)
    try: sort_order = int(data.get("sort_order", 0))
    except (TypeError, ValueError): raise ApiError("Orden inválido")
    if sort_order < 0: raise ApiError("El orden no puede ser negativo")
    item = CatalogEntry.objects.create(kind=kind, value=value, sort_order=sort_order)
    audit(user, "catalog_entry", item.id, "created", after={"kind": kind, "value": value, "active": True})
    return JsonResponse({"id": item.id, "kind": kind, "value": value, "active": True}, status=201)


def catalog_entry_api(request, pk):
    user = require(request, "catalogs.manage")
    if request.method != "PATCH": raise ApiError("Método no permitido", 405)
    item = get_object_or_404(CatalogEntry, pk=pk)
    data = payload(request)
    if type(data.get("active")) is not bool: raise ApiError("Indica si el valor está activo")
    before = {"active": item.active}
    item.active = data["active"]
    item.save(update_fields=["active"])
    audit(user, "catalog_entry", item.id, "activated" if item.active else "deactivated", before=before, after={"active": item.active})
    return JsonResponse({"ok": True, "active": item.active})


def users_api(request):
    user = require(request, "users.manage")
    if request.method == "GET": return JsonResponse([public_user(x) | {"active": x.is_active, "created_at": iso(x.date_joined)} for x in User.objects.all()], safe=False)
    data = payload(request); password = str(data.get("password", ""))
    if len(password) < 8: raise ApiError("La contraseña debe tener al menos 8 caracteres")
    created = User.objects.create_user(username=data.get("username") or data["employee_number"], password=password, employee_number=data["employee_number"], first_name=data["name"], last_name=data["last_name"], role="Técnico" if data.get("role") == "Mantenimiento" else "Solicitante", must_change_password=True)
    audit(user, "user", created.id, "created", after={"role": created.role, "active": created.is_active, "actions": actions(created), "areas": created.area_permissions, "must_change_password": created.must_change_password}); return JsonResponse({"id": created.id, "username": created.username}, status=201)


def user_api(request, pk):
    actor = require(request, "users.manage"); target = get_object_or_404(User, pk=pk); data = payload(request)
    before = {"role": target.role, "active": target.is_active, "actions": actions(target), "areas": target.area_permissions, "must_change_password": target.must_change_password}
    password_reset = False
    if "active" in data and target.username != "administrator": target.is_active = bool(data["active"])
    if data.get("role") and target.role != "Administrador": target.role = "Técnico" if data["role"] == "Mantenimiento" else "Solicitante"
    if data.get("password"):
        if len(str(data["password"])) < 8: raise ApiError("La contraseña debe tener al menos 8 caracteres")
        target.set_password(data["password"])
        target.must_change_password = True
        password_reset = True
    if isinstance(data.get("actions"), list): target.action_permissions = data["actions"]
    if isinstance(data.get("areas"), list): target.area_permissions = data["areas"]
    target.save(); audit(actor, "user", target.id, "updated", before=before, after={"role": target.role, "active": target.is_active, "actions": actions(target), "areas": target.area_permissions, "must_change_password": target.must_change_password, "password_reset": password_reset}); return JsonResponse({"ok": True})


def assets_xlsx(request):
    user = require(request, "assets.read")
    rows = Asset.objects.all().order_by("code")
    if user.area_permissions:
        rows = rows.filter(area__in=user.area_permissions)
    query = request.GET.get("q", "").strip()
    if query:
        rows = rows.filter(Q(name__icontains=query) | Q(code__icontains=query) | Q(original_code__icontains=query) | Q(alias_codes__icontains=query) | Q(area__icontains=query) | Q(brand__icontains=query))
    headers = ["Código", "Código de origen", "Alias", "Activo", "Tipo", "Marca", "Modelo", "Voltaje", "Serie", "Área", "Línea", "Ubicación", "Estado operativo", "Causa/observaciones", "Criticidad", "Horas operación", "Estado administrativo"]
    data = [[a.code, a.original_code, a.alias_codes, a.name, a.asset_type or a.category, a.brand, a.model, a.voltage, a.serial_code, a.area, a.line, a.location_detail, a.operational_status, a.operational_status_cause or a.observations, "Crítico" if a.critical else "Normal", a.operating_hours, a.administrative_status] for a in rows]
    content = make_workbook("Activos", headers, data, decimal_columns={16})
    response = HttpResponse(content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="activos-mantenimiento.xlsx"'
    return response


def assets_api(request):
    user = require(request, "assets.read" if request.method == "GET" else "assets.edit")
    if request.method == "GET": return JsonResponse([asset_dict(a) for a in Asset.objects.prefetch_related("code_equivalences") if not user.area_permissions or a.area in user.area_permissions], safe=False)
    data = payload(request); require(request, "assets.edit", data.get("area") or "")
    data["code"] = checked_asset_code(data.get("code"))
    if catalog_values("area"): require_catalog_value("area", data.get("area"))
    if data.get("line") and catalog_values("line"): require_catalog_value("line", data["line"])
    a = Asset.objects.create(**{k: data.get(k, "") for k in ["code", "name", "category", "asset_type", "area", "line", "location_detail", "brand", "model", "voltage", "serial_code", "observations", "original_code", "alias_codes"]}, critical=bool(data.get("critical")), operational_status=data.get("operational_status", "Sin información"), operational_status_updated_at=timezone.now(), administrative_status=data.get("administrative_status", "Activo")); audit(user, "asset", a.id, "created", after=asset_audit_snapshot(a)); return JsonResponse({"id": a.id}, status=201)


def asset_api(request, pk):
    a = get_object_or_404(Asset, pk=pk); user = require(request, "assets.read" if request.method == "GET" else "assets.edit", a.area)
    if request.method == "GET":
        row = asset_dict(a)
        row["operational_status_updated_at"] = iso(a.operational_status_updated_at)
        row["equivalences"] = [equivalence_dict(x) for x in a.code_equivalences.select_related("proposed_by", "reviewed_by").order_by("-created_at")]
        orders = list(a.work_orders.select_related("requester", "technician", "asset").prefetch_related("materials").order_by("-requested_at", "-id"))
        row["maintenances"] = [order_dict(x) for x in orders]
        materials = list(MaintenanceMaterial.objects.filter(work_order__asset=a).select_related("work_order").order_by("-work_order__requested_at", "id"))
        row["material_usage"] = [{"id": x.id, "work_order_id": x.work_order_id, "folio": x.work_order.folio, "code": x.code, "description": x.description, "quantity": float(x.quantity), "returned_quantity": float(x.returned_quantity), "net_quantity": float(x.quantity - x.returned_quantity), "unit_cost": float(x.unit_cost), "net_cost": float((x.quantity - x.returned_quantity) * x.unit_cost)} for x in materials]
        material_cost = sum(((x.quantity - x.returned_quantity) * x.unit_cost for x in materials), Decimal("0"))
        row["metrics"] = {"maintenance_count": len(orders), "mttr": None, "material_cost": float(material_cost), "total_cost": float(material_cost), "last_maintenance": iso(orders[0].requested_at) if orders else None}
        row["preventive_plans"] = [{"id": p.id, "title": p.title, "frequency": p.frequency, "next_date": iso(p.next_date), "status": p.status, "responsible_name": p.responsible.first_name if p.responsible else None, "template_code": p.template_code, "work_order_id": p.work_order_id, "task_count": p.tasks.count(), "version": p.version} for p in a.preventive_plans.select_related("responsible").prefetch_related("tasks").order_by("next_date", "id")]
        row["downtime_events"] = [{"id": event.id, "cause": event.cause, "started_at": iso(event.started_at), "finished_at": iso(event.finished_at), "close_reason": event.close_reason, "work_order_ids": [order.id for order in event.work_orders.all()]} for event in a.downtime_events.prefetch_related("work_orders").order_by("-started_at", "-id")]
        row["meter_readings"] = [{"value": float(reading.value), "recorded_at": iso(reading.recorded_at), "notes": reading.notes} for reading in a.meter_readings.order_by("-recorded_at")[:10]]
        return JsonResponse(row)
    data = payload(request)
    before = asset_audit_snapshot(a)
    if "code" in data: data["code"] = checked_asset_code(data["code"], a.id)
    if "area" in data:
        require(request, "assets.edit", data["area"])
        if data["area"] != a.area and catalog_values("area"): require_catalog_value("area", data["area"])
    if "line" in data and data["line"] and data["line"] != a.line and catalog_values("line"):
        require_catalog_value("line", data["line"])
    new_status = data.get("operational_status", a.operational_status)
    new_cause = data.get("operational_status_cause", a.operational_status_cause)
    if new_status not in ("Operativa", "Parada", "En mantenimiento", "Operación restringida", "Sin información"):
        raise ApiError("Estado operativo inválido")
    if a.downtime_events.filter(finished_at__isnull=True).exists() and (new_status != "Parada" or new_cause != a.operational_status_cause):
        raise ApiError("Cierra el paro abierto antes de cambiar el estado o su causa", 409)
    status_changed = new_status != a.operational_status or new_cause != a.operational_status_cause
    for key in ["code", "name", "category", "asset_type", "area", "line", "location_detail", "brand", "model", "voltage", "serial_code", "observations", "original_code", "alias_codes", "operational_status", "operational_status_cause", "administrative_status"]:
        if key in data: setattr(a, key, data[key])
    if "critical" in data: a.critical = bool(data["critical"])
    if status_changed: a.operational_status_updated_at = timezone.now()
    a.save(); audit(user, "asset", a.id, "updated", before=before, after=asset_audit_snapshot(a)); return JsonResponse({"ok": True})


def asset_equivalences_api(request, pk):
    asset = get_object_or_404(Asset, pk=pk)
    user = require(request, "assets.read" if request.method == "GET" else "assets.edit", asset.area)
    if request.method == "GET":
        return JsonResponse([equivalence_dict(x) for x in asset.code_equivalences.select_related("proposed_by", "reviewed_by").order_by("-created_at")], safe=False)
    if request.method != "POST": raise ApiError("Método no permitido", 405)
    data = payload(request)
    code = str(data.get("code") or "").strip()
    notes = str(data.get("notes") or "").strip()
    if not code or len(code) > 80: raise ApiError("Indica un código de hasta 80 caracteres")
    if not notes: raise ApiError("Explica por qué se propone la equivalencia")
    if code.casefold() == asset.code.strip().casefold(): raise ApiError("El código propuesto ya es el código vigente de este activo", 409)
    try: source_row = int(data["source_row"]) if data.get("source_row") not in (None, "") else None
    except (TypeError, ValueError): raise ApiError("Fila de origen inválida")
    if source_row is not None and source_row < 1: raise ApiError("Fila de origen inválida")
    source_file = str(data.get("source_file") or "").strip()
    source_sheet = str(data.get("source_sheet") or "").strip()
    if len(source_file) > 250 or len(source_sheet) > 120: raise ApiError("Referencia de origen demasiado larga")
    item = AssetCodeEquivalence.objects.create(asset=asset, code=code, code_key=code.casefold(), notes=notes, source_file=source_file, source_sheet=source_sheet, source_row=source_row, proposed_by=user)
    audit(user, "asset_code_equivalence", item.id, "proposed", after={"asset_id": pk, "code": code, "status": item.status, "source_file": source_file, "source_sheet": source_sheet, "source_row": source_row, "notes": notes})
    return JsonResponse(equivalence_dict(item), status=201)


@transaction.atomic
def asset_equivalence_review_api(request, pk, item_id):
    asset = get_object_or_404(Asset, pk=pk)
    user = require(request, "assets.edit", asset.area)
    if request.method != "PATCH": raise ApiError("Método no permitido", 405)
    item = get_object_or_404(AssetCodeEquivalence.objects.select_for_update(), pk=item_id, asset=asset)
    data = payload(request)
    status = data.get("status")
    reason = str(data.get("reason") or "").strip()
    if status not in ("Aprobada", "Rechazada"): raise ApiError("Estado de revisión inválido")
    if not reason: raise ApiError("Indica el motivo de la revisión")
    if status == "Aprobada":
        checked_asset_code(item.code, asset.id)
        if item.code_key == asset.code.strip().casefold(): raise ApiError("El código ya es el vigente de este activo", 409)
    before = {"status": item.status, "review_reason": item.review_reason}
    item.status = status
    item.reviewed_by = user
    item.reviewed_at = timezone.now()
    item.review_reason = reason
    item.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_reason"])
    audit(user, "asset_code_equivalence", item.id, "reviewed", before=before, after={"status": status, "review_reason": reason}, reason=reason)
    return JsonResponse(equivalence_dict(item))


def inventory_api(request):
    user = require(request, "inventory.read" if request.method == "GET" else "inventory.move")
    if request.method == "GET":
        items = filtered_inventory(request).order_by("code")
        return JsonResponse([{**{k: getattr(i, k) for k in ["id", "code", "name", "category", "unit", "location", "active", "version"]}, "stock": float(i.stock), "min_stock": float(i.min_stock), "max_stock": float(i.max_stock), "unit_cost": float(i.unit_cost), "low_stock": i.stock <= i.min_stock} for i in items], safe=False)
    data = payload(request); item = InventoryItem.objects.create(code=data["code"], name=data["name"], category=data["category"], unit=data["unit"], stock=decimal(data.get("stock", 0)), min_stock=decimal(data.get("min_stock", 0)), max_stock=decimal(data.get("max_stock", 0)), unit_cost=decimal(data.get("unit_cost", 0)), location=data.get("location", "")); audit(user, "inventory_item", item.id, "created"); return JsonResponse({"id": item.id}, status=201)


@transaction.atomic
def inventory_bulk_create(request):
    user = require(request, "inventory.move")
    if request.method != "POST":
        raise ApiError("Método no permitido", 405)
    rows = payload(request).get("rows")
    if not isinstance(rows, list) or not rows or len(rows) > 500:
        raise ApiError("Envía de 1 a 500 renglones")
    parsed, seen = [], set()
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ApiError(f"Fila {index}: formato no válido")
        code = str(row.get("code", "")).strip().upper()
        name = str(row.get("name", "")).strip()
        category = str(row.get("category", "Refacción")).strip() or "Refacción"
        unit = str(row.get("unit", "pieza")).strip() or "pieza"
        location = str(row.get("location", "")).strip()
        if not code or len(code) > 80:
            raise ApiError(f"Fila {index}: el código es obligatorio y admite hasta 80 caracteres")
        if not name or len(name) > 250:
            raise ApiError(f"Fila {index}: la descripción es obligatoria y admite hasta 250 caracteres")
        if code.casefold() in seen or InventoryItem.objects.filter(code__iexact=code).exists():
            raise ApiError(f"Fila {index}: código duplicado ({code})", 409)
        seen.add(code.casefold())
        stock = decimal(row.get("stock", 0), f"existencia fila {index}")
        minimum = decimal(row.get("min_stock", 0), f"mínimo fila {index}")
        maximum = decimal(row.get("max_stock", 0), f"máximo fila {index}")
        unit_cost = decimal(row.get("unit_cost", 0), f"costo fila {index}")
        if min(stock, minimum, maximum, unit_cost) < 0 or maximum < minimum:
            raise ApiError(f"Fila {index}: cantidades y costos deben ser positivos y el máximo no menor que el mínimo")
        parsed.append({"code": code, "name": name, "category": category, "unit": unit,
                       "location": location, "stock": stock, "min_stock": minimum,
                       "max_stock": maximum, "unit_cost": unit_cost})
    created = []
    for row in parsed:
        item = InventoryItem.objects.create(**row)
        created.append(item)
        audit(user, "inventory_item", item.id, "created", after={
            "code": item.code, "name": item.name, "category": item.category,
            "unit": item.unit, "stock": str(item.stock), "min_stock": str(item.min_stock),
            "max_stock": str(item.max_stock), "unit_cost": str(item.unit_cost),
            "location": item.location,
        })
        if item.stock:
            InventoryMovement.objects.create(
                item=item, type="Ajuste", quantity=item.stock, unit_cost=item.unit_cost,
                user=user, notes="Existencia inicial registrada en captura tabular",
                request_key=uuid.uuid4().hex,
                request_hash=hashlib.sha256(f"bulk:{item.id}:{item.stock}".encode()).hexdigest(),
            )
    audit(user, "inventory_bulk_create", None, "created", after={"rows": len(created)})
    return JsonResponse({"ok": True, "created": len(created), "ids": [item.id for item in created]}, status=201)


def inventory_item_api(request, pk):
    user = require(request, "inventory.move"); item = get_object_or_404(InventoryItem, pk=pk); data = payload(request)
    before = {key: str(getattr(item, key)) for key in ["code", "name", "category", "unit", "location", "stock", "min_stock", "max_stock", "unit_cost", "active", "version"]}
    for key in ["code", "name", "category", "unit", "location"]:
        if key in data: setattr(item, key, data[key])
    for key in ["min_stock", "max_stock", "unit_cost"]:
        if key in data: setattr(item, key, decimal(data[key]))
    item.version += 1; item.save(); after = {key: str(getattr(item, key)) for key in ["code", "name", "category", "unit", "location", "stock", "min_stock", "max_stock", "unit_cost", "active", "version"]}; audit(user, "inventory_item", item.id, "updated", before=before, after=after); return JsonResponse({"ok": True, "version": item.version})


def movements_api(request, pk):
    require(request, "inventory.read"); rows = InventoryMovement.objects.filter(item_id=pk).select_related("user", "work_order").order_by("-created_at")
    return JsonResponse([{"id": x.id, "type": x.type, "quantity": float(x.quantity), "unit_cost": float(x.unit_cost), "work_order_id": x.work_order_id, "folio": x.work_order.folio if x.work_order else None, "user_name": x.user.first_name, "notes": x.notes, "return_of": x.return_of_id, "created_at": iso(x.created_at)} for x in rows], safe=False)


def csv_cell(value):
    text = str(value or "")
    return "'" + text if text.startswith(("=", "+", "-", "@")) else text


def filtered_inventory(request):
    items = InventoryItem.objects.filter(active=True)
    query = request.GET.get("q", "").strip()
    if query:
        items = items.filter(
            Q(code__icontains=query) | Q(name__icontains=query)
            | Q(category__icontains=query) | Q(location__icontains=query)
        )
    category = request.GET.get("category", "").strip()
    if category:
        items = items.filter(category=category)
    stock_status = request.GET.get("stock", "").strip()
    if stock_status == "low":
        items = items.filter(stock__lte=F("min_stock"))
    elif stock_status == "available":
        items = items.filter(stock__gt=F("min_stock"))
    elif stock_status:
        raise ApiError("Filtro de existencias inválido")
    return items


def inventory_template(request):
    require(request, "inventory.read"); output = io.StringIO(); writer = csv.writer(output); writer.writerow(["Código", "Descripción", "Categoría", "Unidad", "Existencia", "StockMínimo", "StockMáximo", "CostoUnitario", "Ubicación"]); writer.writerow(["MAT-101", "Tornillo Hexagonal 8mm", "Tornillería", "pieza", 50, 10, 100, "3.50", "Anaquel A-01"]); response = HttpResponse("\ufeff"+output.getvalue(), content_type="text/csv; charset=utf-8"); response["Content-Disposition"] = 'attachment; filename="plantilla-inventario.csv"'; return response


def inventory_export(request):
    require(request, "inventory.read"); output = io.StringIO(); writer = csv.writer(output); writer.writerow(["Código", "Descripción", "Categoría", "Unidad", "Existencia", "StockMínimo", "StockMáximo", "CostoUnitario", "Ubicación"])
    for x in filtered_inventory(request).order_by("code"): writer.writerow([csv_cell(v) for v in [x.code, x.name, x.category, x.unit, x.stock, x.min_stock, x.max_stock, x.unit_cost, x.location]])
    response = HttpResponse("\ufeff"+output.getvalue(), content_type="text/csv; charset=utf-8"); response["Content-Disposition"] = 'attachment; filename="base-de-datos-inventario.csv"'; return response


def inventory_xlsx(request):
    require(request, "inventory.read")
    headers = ["Código", "Descripción", "Categoría", "Unidad", "Existencia", "Stock mínimo", "Stock máximo", "Costo unitario", "Valor en existencia", "Estado", "Ubicación"]
    rows = []
    for item in filtered_inventory(request).order_by("code"):
        rows.append([
            item.code, item.name, item.category, item.unit,
            item.stock, item.min_stock, item.max_stock, item.unit_cost,
            item.stock * item.unit_cost,
            "Reabastecer" if item.stock <= item.min_stock else "Suficiente",
            item.location,
        ])
    content = make_workbook("Inventario", headers, rows, decimal_columns={9}, decimal_precision_columns={5, 6, 7, 8})
    response = HttpResponse(content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="inventario-mantenimiento.xlsx"'
    return response


def preventives_xlsx(request):
    user = require(request, "preventives.read")
    plans = PreventivePlan.objects.select_related("asset", "responsible", "work_order").order_by("next_date", "asset__code", "title")
    if user.area_permissions:
        plans = plans.filter(asset__area__in=user.area_permissions)
    headers = ["Próxima fecha", "Código activo", "Activo", "Área", "Actividad", "Código plantilla", "Aplica cuando", "Frecuencia", "Responsable", "Estado", "Versión", "Folio OT"]
    rows = [[p.next_date, p.asset.code, p.asset.name, p.asset.area, p.title, p.template_code, p.applies_when, p.frequency, p.responsible.first_name if p.responsible else "", p.status, p.version, p.work_order.folio if p.work_order_id else ""] for p in plans]
    content = make_workbook("Programa preventivo", headers, rows, date_columns={1})
    response = HttpResponse(content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="programa-preventivo.xlsx"'
    return response


@transaction.atomic
def inventory_import(request, preview):
    user = require(request, "inventory.move"); data = payload(request); items = data.get("items", [])
    if not items and data.get("csvText"):
        items = list(csv.DictReader(io.StringIO(data["csvText"].lstrip("\ufeff"))))
    parsed = []
    seen_codes = set()
    for index, row in enumerate(items, 1):
        code = str(row.get("code") or row.get("Código") or "").strip().upper()
        name = str(row.get("name") or row.get("Descripción") or "").strip()
        existing = InventoryItem.objects.filter(code__iexact=code).first() if code else None
        errors = []
        if not code: errors.append("Falta código")
        if not name: errors.append("Falta descripción")
        if code in seen_codes: errors.append("Código repetido en el archivo")
        seen_codes.add(code)
        parsed.append({"row": index, "code": code, "name": name, "action": "Actualizar" if existing else "Nuevo", "errors": errors, "source": row})
    if preview:
        return JsonResponse({"rows": parsed, "newCount": sum(x["action"] == "Nuevo" and not x["errors"] for x in parsed), "updateCount": sum(x["action"] == "Actualizar" and not x["errors"] for x in parsed), "errorCount": sum(bool(x["errors"]) for x in parsed)})
    if any(x["errors"] for x in parsed): raise ApiError("La importación contiene errores")
    mode = data.get("mode", "replace")
    if mode not in ["replace", "add"]: raise ApiError("Modo de importación inválido")
    for row in parsed:
        source = row["source"]
        defaults = {
            "name": row["name"], "category": source.get("category") or source.get("Categoría") or "Sin categoría",
            "unit": source.get("unit") or source.get("Unidad") or "pieza",
            "min_stock": decimal(source.get("min_stock") or source.get("StockMínimo") or 0),
            "max_stock": decimal(source.get("max_stock") or source.get("StockMáximo") or 0),
            "unit_cost": decimal(source.get("unit_cost") or source.get("CostoUnitario") or 0),
            "location": source.get("location") or source.get("Ubicación") or "",
        }
        stock = decimal(source.get("stock") or source.get("Existencia") or 0)
        if stock < 0 or defaults["min_stock"] < 0 or defaults["max_stock"] < defaults["min_stock"] or defaults["unit_cost"] < 0:
            raise ApiError(f"Valores de inventario inválidos en la fila {row['row']}")
        item = InventoryItem.objects.select_for_update().filter(code__iexact=row["code"]).first()
        created = item is None
        if created:
            item = InventoryItem.objects.create(code=row["code"], stock=stock, **defaults)
        else:
            old_stock = item.stock
            for field, value in defaults.items(): setattr(item, field, value)
            item.stock = old_stock + stock if mode == "add" else stock
            item.version += 1
            item.save()
        if created or item.stock != old_stock:
            fingerprint = hashlib.sha256(f"{item.id}:{item.stock}:{row['row']}".encode()).hexdigest()
            movement = InventoryMovement.objects.create(
                item=item, type="Ajuste", quantity=item.stock, unit_cost=item.unit_cost,
                user=user, notes=f"Importación CSV, fila {row['row']}, modo {mode}",
                request_key=uuid.uuid4().hex, request_hash=fingerprint,
            )
            audit(user, "inventory_item", item.id, "import-adjustment",
                  after={"stock": float(item.stock), "movement_id": movement.id}, reason=movement.notes)

    audit(user, "inventory_import", None, "imported", after={"rows": len(parsed), "mode": mode}); return JsonResponse({"ok": True, "rows": len(parsed)})


@transaction.atomic
def movement_api(request, pk):
    user = require(request, "inventory.move"); data = payload(request); item = get_object_or_404(InventoryItem.objects.select_for_update(), pk=pk)
    key = str(data.get("request_key", "")).strip()
    if not key: raise ApiError("La clave de petición es obligatoria")
    fingerprint = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest(); replay = InventoryMovement.objects.filter(user=user, request_key=key).first()
    if replay:
        if replay.request_hash != fingerprint: raise ApiError("La clave de petición ya fue utilizada con otros datos", 409)
        return JsonResponse({"id": replay.id, "stock": float(item.stock), "version": item.version, "replayed": True})
    if int(data.get("version", -1)) != item.version: raise ApiError("El inventario cambió en otra sesión", 409)
    quantity = decimal(data.get("quantity")); kind = data.get("type"); order = WorkOrder.objects.select_for_update().filter(pk=data.get("work_order_id")).first(); origin = None
    if quantity <= 0: raise ApiError("La cantidad debe ser mayor que cero")
    if kind == "Salida": next_stock = item.stock - quantity; cost = item.unit_cost
    elif kind == "Entrada": next_stock = item.stock + quantity; cost = decimal(data.get("unit_cost", item.unit_cost)); item.unit_cost = ((item.stock*item.unit_cost)+(quantity*cost))/next_stock if next_stock else cost
    elif kind == "Ajuste": require(request, "inventory.adjust"); next_stock = quantity; cost = item.unit_cost
    elif kind == "Devolución":
        origin = get_object_or_404(InventoryMovement, pk=data.get("return_of"), item=item, type="Salida"); returned = origin.returns.aggregate(v=Sum("quantity"))["v"] or 0
        if returned + quantity > origin.quantity: raise ApiError("La devolución supera la salida original")
        next_stock = item.stock + quantity; cost = origin.unit_cost; order = origin.work_order
    else: raise ApiError("Tipo de movimiento inválido")
    if next_stock < 0: raise ApiError("Existencia insuficiente", 409)
    if order: require(request, None, order.asset.area if order.asset else order.location)
    if order and kind == "Salida" and order.status in ("Pendiente de validación", "Completada", "Cancelada"):
        raise ApiError("Reabre o devuelve la orden a trabajo antes de agregar materiales")
    movement = InventoryMovement.objects.create(item=item, type=kind, quantity=quantity, unit_cost=cost, work_order=order, user=user, notes=data.get("notes", ""), return_of=origin, request_key=key, request_hash=fingerprint)
    item.stock = next_stock; item.version += 1; item.save()
    if kind == "Salida" and order: MaintenanceMaterial.objects.create(work_order=order, item=item, code=item.code, description=item.name, quantity=quantity, unit_cost=cost, movement=movement)
    if kind == "Devolución" and origin: MaintenanceMaterial.objects.filter(movement=origin).update(returned_quantity=F("returned_quantity") + quantity)
    if order:
        WorkOrder.objects.filter(pk=order.pk).update(material_cost=material_total(MaintenanceMaterial.objects.filter(work_order=order)))
    audit(user, "inventory_item", item.id, kind, after={"stock": float(item.stock), "movement_id": movement.id}); return JsonResponse({"id": movement.id, "stock": float(item.stock), "version": item.version})


def order_queryset(user):
    qs = WorkOrder.objects.select_related("requester", "technician", "asset")
    if user.role == "Solicitante": return qs.filter(requester=user)
    if user.area_permissions: return qs.filter(Q(asset__area__in=user.area_permissions) | Q(asset__isnull=True, location__in=user.area_permissions))
    return qs


def filtered_orders(request, user):
    qs = order_queryset(user)
    for key, field in [
        ("status", "status"), ("priority", "priority"), ("area", "asset__area"),
        ("technician_id", "technician_id"), ("asset_id", "asset_id"),
        ("classification", "classification"),
    ]:
        if request.GET.get(key):
            qs = qs.filter(**{field: request.GET[key]})
    if request.GET.get("q"):
        q = request.GET["q"].strip()
        qs = qs.filter(
            Q(folio__icontains=q) | Q(reported_failure__icontains=q)
            | Q(asset__code__icontains=q) | Q(asset__name__icontains=q)
            | Q(requester__first_name__icontains=q)
        )
    if request.GET.get("from"):
        qs = qs.filter(requested_at__date__gte=parse_day(request.GET["from"], "fecha inicial"))
    if request.GET.get("to"):
        qs = qs.filter(requested_at__date__lte=parse_day(request.GET["to"], "fecha final"))
    return qs


@transaction.atomic
def next_folio():
    year = timezone.localdate().year
    sequence, _ = FolioSequence.objects.select_for_update().get_or_create(year=year, defaults={"next_number": 1})
    number = sequence.next_number; sequence.next_number += 1; sequence.save(update_fields=["next_number"])
    return f"OT-{year}-{number:04d}"


@transaction.atomic
def orders_api(request):
    user = require(request, "orders.read" if request.method == "GET" else "orders.create")
    if request.method == "GET":
        qs = filtered_orders(request, user).order_by("-requested_at")
        return JsonResponse([order_dict(o, operator=user.role == "Solicitante") for o in qs], safe=False)
    data = payload(request)
    requester = user if user.role == "Solicitante" else get_object_or_404(User, pk=data.get("requester_id"))
    key = request.headers.get("Idempotency-Key") or data.get("idempotency_key")
    request_data = {name: value for name, value in data.items() if name != "idempotency_key"}
    request_hash = hashlib.sha256(json.dumps(request_data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    if key:
        requester = User.objects.select_for_update().get(pk=requester.pk)
    replay = WorkOrder.objects.filter(requester=requester, idempotency_key=key).first() if key else None
    if replay:
        if replay.idempotency_hash and replay.idempotency_hash != request_hash:
            raise ApiError("La clave de petición ya fue utilizada con otros datos", 409)
        return JsonResponse({"id": replay.id, "folio": replay.folio, "replayed": True})
    asset_id = data.get("asset_id") or None
    asset = get_object_or_404(Asset, pk=asset_id) if asset_id else None
    require(request, "orders.create", asset.area if asset else data.get("location") or "")
    if data.get("priority") == "Paro de máquina":
        if data.get("machine_stopped") not in ("yes", "no"):
            raise ApiError("Confirma si la máquina realmente está parada")
        if data["machine_stopped"] == "yes" and not asset:
            raise ApiError("Selecciona el activo para registrar el paro")
        if data["machine_stopped"] == "yes" and not str(data.get("downtime_cause", "")).strip():
            raise ApiError("Indica la causa del paro")
    technician_id = None
    if user.role != "Solicitante" and data.get("technician_id"):
        require(request, "orders.assign")
        technician_id = data["technician_id"]
        if not User.objects.filter(pk=technician_id, is_active=True, role__in=["Técnico", "Jefatura"]).exists():
            raise ApiError("El responsable no es un técnico activo")
    if user.role != "Solicitante" and data.get("status", "Abierta") != "Abierta":
        raise ApiError("Las órdenes nuevas deben iniciar abiertas; cambia el estado después de crearlas")
    require_catalog_value("priority", data.get("priority"))
    require_catalog_value("classification", data.get("classification"))
    if data.get("classification") == "Mantenimiento Preventivo":
        raise ApiError("Programa la OT preventiva desde una tarea y fecha del plan", 409)
    if user.role != "Solicitante" and data.get("specialty"):
        require_catalog_value("specialty", data["specialty"])
    order = WorkOrder.objects.create(
        folio=next_folio(),
        requested_at=timezone.now() if user.role == "Solicitante" else data.get("requested_at") or timezone.now(),
        requester=requester, priority=data["priority"], classification=data["classification"],
        specialty=data.get("specialty", "") if user.role != "Solicitante" else "",
        asset=asset, location=data.get("location", ""), reported_failure=data["reported_failure"],
        technician_id=technician_id, scheduled_at=scheduled_datetime(data["scheduled_at"]) if data.get("scheduled_at") else None,
        status="Abierta", idempotency_key=key,
        idempotency_hash=request_hash if key else "",
        autonomous_checklist=data.get("autonomous_checklist", ""),
    )
    WorkOrderEvent.objects.create(work_order=order, user=user, event="Creada")
    if data.get("priority") == "Paro de máquina" and data["machine_stopped"] == "yes":
        asset = Asset.objects.select_for_update().get(pk=asset.pk)
        downtime = DowntimeEvent.objects.filter(asset=asset, finished_at__isnull=True).order_by("-started_at").first()
        if not downtime:
            downtime = DowntimeEvent.objects.create(asset=asset, cause=str(data["downtime_cause"]).strip(), started_at=timezone.now(), created_by=user)
            asset.operational_status = "Parada"; asset.operational_status_cause = downtime.cause; asset.operational_status_updated_at = timezone.now()
            asset.save(update_fields=["operational_status", "operational_status_cause", "operational_status_updated_at"])
        downtime.work_orders.add(order)
        WorkOrderEvent.objects.create(work_order=order, user=user, event="Paro confirmado", details=f"Evento #{downtime.id}: {downtime.cause}")
        audit(user, "downtime", downtime.id, "order_linked", after={"work_order_id": order.id})
    audit(user, "work_order", order.id, "created", after={"folio": order.folio})
    return JsonResponse({"id": order.id, "folio": order.folio}, status=201)

@transaction.atomic
def order_api(request, pk):
    user = require(request, "orders.read" if request.method == "GET" else "orders.edit")
    qs = order_queryset(user)
    if request.method != "GET": qs = qs.select_for_update(of=("self",))
    order = get_object_or_404(qs, pk=pk)
    if request.method == "GET": return JsonResponse(order_dict(order, True, user.role == "Solicitante"))
    if user.role == "Técnico" and order.technician_id != user.id: raise ApiError("Solo puedes editar órdenes asignadas a ti", 403)
    data = payload(request)
    if int(data.get("version", -1)) != order.version: raise ApiError("La orden cambió en otra sesión", 409)
    before = order_dict(order)
    before["participant_ids"] = list(order.participants.values_list("id", flat=True))
    if "priority" in data and data["priority"] != order.priority: require_catalog_value("priority", data["priority"])
    if "specialty" in data and data["specialty"] and data["specialty"] != order.specialty: require_catalog_value("specialty", data["specialty"])
    if not order.asset_id and "location" in data: require(request, None, data["location"])
    for key in ["location", "priority", "specialty", "reported_failure", "actions", "closure_notes", "closure_document_code", "closure_document_revision"]:
        if key in data: setattr(order, key, data[key])
    technician_changed = False
    if "technician_id" in data:
        try:
            technician_id = int(data["technician_id"]) if data["technician_id"] not in (None, "") else None
        except (TypeError, ValueError):
            raise ApiError("Selecciona un tecnico valido")
        technician_changed = technician_id != order.technician_id
        if technician_changed:
            require(request, "orders.assign")
        if technician_id and not User.objects.filter(pk=technician_id, is_active=True, role__in=["Técnico", "Jefatura"]).exists():
            raise ApiError("El responsable no es un técnico activo")
        if technician_changed: order.technician_id = technician_id
    participant_ids = None
    participant_changed = False
    if "participant_ids" in data:
        require(request, "orders.assign")
        try:
            participant_ids = {int(value) for value in data["participant_ids"]}
        except (TypeError, ValueError):
            raise ApiError("Colaboradores inválidos")
        valid = set(User.objects.filter(pk__in=participant_ids, is_active=True, role__in=["Técnico", "Jefatura"]).values_list("id", flat=True))
        if valid != participant_ids: raise ApiError("Selecciona colaboradores activos de Mantenimiento")
        previous_ids = set(order.participants.values_list("id", flat=True))
        participant_changed = (participant_ids - {order.technician_id}) != previous_ids
        removed = previous_ids - participant_ids
        if removed and order.time_entries.filter(user_id__in=removed).exists():
            raise ApiError("No puedes quitar colaboradores con tiempo registrado")
    for key in ["requested_at", "scheduled_at"]:
        if key in data:
            if key == "requested_at" and not data[key]: raise ApiError("Indica la fecha de solicitud")
            value = scheduled_datetime(data[key]) if data[key] else None
            if value != getattr(order, key):
                require(request, "orders.edit_dates")
                setattr(order, key, value)
    work_dates_changed = False
    for key in ["started_at", "finished_at"]:
        if key in data:
            value = scheduled_datetime(data[key]) if data[key] else None
            if value != getattr(order, key):
                setattr(order, key, value)
                work_dates_changed = True
    if order.finished_at and not order.started_at: raise ApiError("Indica la fecha y hora de inicio")
    if order.started_at and order.finished_at and order.finished_at <= order.started_at:
        raise ApiError("El termino debe ser posterior al inicio")
    order.version += 1; order.save()
    if participant_changed: order.participants.set(participant_ids - {order.technician_id})
    if work_dates_changed or ((technician_changed or participant_changed) and not order.time_entries.exists()):
        order.labor_hours = order_labor_hours(order)
        order.save(update_fields=["labor_hours", "updated_at"])
    after = order_dict(order)
    after["participant_ids"] = list(order.participants.values_list("id", flat=True))
    WorkOrderEvent.objects.create(work_order=order, user=user, event="Actualizada", details=data.get("date_change_reason", "")); audit(user, "work_order", order.id, "updated", before, after, data.get("date_change_reason", "")); return JsonResponse({"ok": True, "version": order.version})


def time_target(user, order, data):
    allowed_ids = set(order.participants.values_list("id", flat=True))
    if order.technician_id: allowed_ids.add(order.technician_id)
    if user.role == "Técnico":
        if user.id not in allowed_ids: raise ApiError("No participas en esta orden", 403)
        return user
    target_id = data.get("user_id") or order.technician_id
    try: target_id = int(target_id)
    except (TypeError, ValueError): raise ApiError("Selecciona un técnico asignado")
    if target_id not in allowed_ids: raise ApiError("El técnico no está asignado a esta orden", 403)
    return get_object_or_404(User, pk=target_id, is_active=True)


def recalculate_labor(order):
    seconds = sum((entry.finished_at - entry.started_at).total_seconds() for entry in order.time_entries.all() if entry.finished_at)
    order.labor_hours = Decimal(str(round(seconds / 3600, 2)))
    order.version += 1
    order.save(update_fields=["labor_hours", "version", "updated_at"])


def time_rows(order):
    return [{"id": entry.id, "user_id": entry.user_id, "user_name": entry.user.first_name, "started_at": iso(entry.started_at), "finished_at": iso(entry.finished_at), "pause_reason": entry.pause_reason, "source": entry.source} for entry in order.time_entries.select_related("user").order_by("started_at", "id")]


@transaction.atomic
def time_api(request, pk):
    user = require(request, "orders.time")
    order = get_object_or_404(WorkOrder.objects.select_for_update(), pk=pk)
    require(request, None, order.asset.area if order.asset else order.location)
    if user.role == "Técnico" and user.id not in ({order.technician_id} | set(order.participants.values_list("id", flat=True))):
        raise ApiError("No participas en esta orden", 403)
    if request.method == "GET": return JsonResponse(time_rows(order), safe=False)
    if request.method != "POST": raise ApiError("Método no permitido", 405)
    if order.status in ("Completada", "Cancelada", "Pendiente de validación"):
        raise ApiError("Reabre o devuelve la orden a trabajo antes de registrar tiempo")
    data = payload(request); target = time_target(user, order, data)
    User.objects.select_for_update().get(pk=target.pk)
    if "version" in data and int(data["version"]) != order.version: raise ApiError("La orden cambió en otra sesión", 409)
    try:
        start = datetime.fromisoformat(data["started_at"])
        finish = datetime.fromisoformat(data["finished_at"])
    except (KeyError, TypeError, ValueError): raise ApiError("Indica inicio y fin válidos")
    if timezone.is_naive(start): start = timezone.make_aware(start)
    if timezone.is_naive(finish): finish = timezone.make_aware(finish)
    if finish <= start: raise ApiError("El fin debe ser posterior al inicio")
    overlap = TimeEntry.objects.filter(user=target, started_at__lt=finish).filter(Q(finished_at__isnull=True) | Q(finished_at__gt=start)).exists()
    if overlap: raise ApiError("El intervalo se traslapa con otra sesión", 409)
    entry = TimeEntry.objects.create(work_order=order, user=target, started_at=start, finished_at=finish, pause_reason=data.get("pause_reason", ""), source="manual")
    recalculate_labor(order)
    WorkOrderEvent.objects.create(work_order=order, user=user, event="Tiempo manual registrado", details=f"{target.first_name}: {iso(start)} - {iso(finish)}")
    audit(user, "time_entry", entry.id, "manual_created", after={"work_order_id": order.id, "user_id": target.id, "started_at": iso(start), "finished_at": iso(finish)})
    return JsonResponse({"id": entry.id, "labor_hours": float(order.labor_hours), "version": order.version}, status=201)


@transaction.atomic
def time_action_api(request, pk):
    user = require(request, "orders.time")
    if request.method != "POST": raise ApiError("Método no permitido", 405)
    order = get_object_or_404(WorkOrder.objects.select_for_update(), pk=pk)
    require(request, None, order.asset.area if order.asset else order.location)
    data = payload(request)
    action = data.get("action")
    if action not in ("start", "pause", "finish"): raise ApiError("Acción de sesión inválida")
    target = time_target(user, order, data)
    User.objects.select_for_update().get(pk=target.pk)
    if int(data.get("version", -1)) != order.version: raise ApiError("La orden cambió en otra sesión", 409)
    if order.status != "En proceso": raise ApiError("La orden debe estar en proceso")
    open_entry = TimeEntry.objects.filter(user=target, finished_at__isnull=True).first()
    if action == "start":
        if open_entry: raise ApiError("El técnico ya tiene una sesión activa", 409)
        entry = TimeEntry.objects.create(work_order=order, user=target, started_at=timezone.now(), source="timer")
        event = "Sesión iniciada"
    else:
        if not open_entry or open_entry.work_order_id != order.id: raise ApiError("No hay sesión activa de este técnico en la orden", 409)
        entry = open_entry
        entry.finished_at = timezone.now()
        entry.pause_reason = str(data.get("reason", "")).strip() if action == "pause" else ""
        if action == "pause" and not entry.pause_reason: raise ApiError("Indica el motivo de la pausa")
        entry.save(update_fields=["finished_at", "pause_reason"])
        event = "Sesión pausada" if action == "pause" else "Sesión terminada"
    recalculate_labor(order)
    WorkOrderEvent.objects.create(work_order=order, user=user, event=event, details=f"{target.first_name}: {iso(entry.started_at)} - {iso(entry.finished_at) or 'activa'}" + (f"; {entry.pause_reason}" if entry.pause_reason else ""))
    audit(user, "time_entry", entry.id, action, after={"work_order_id": order.id, "user_id": target.id, "started_at": iso(entry.started_at), "finished_at": iso(entry.finished_at), "reason": entry.pause_reason})
    return JsonResponse({"id": entry.id, "action": action, "labor_hours": float(order.labor_hours), "version": order.version})


@transaction.atomic
def time_correction_api(request, pk, entry_pk):
    user = require(request, "orders.edit_dates")
    if request.method != "PATCH": raise ApiError("Método no permitido", 405)
    order = get_object_or_404(WorkOrder.objects.select_for_update(), pk=pk)
    require(request, None, order.asset.area if order.asset else order.location)
    entry = get_object_or_404(TimeEntry, pk=entry_pk, work_order=order)
    if not entry.finished_at: raise ApiError("Termina la sesión antes de corregirla")
    data = payload(request)
    if int(data.get("version", -1)) != order.version: raise ApiError("La orden cambió en otra sesión", 409)
    reason = str(data.get("reason", "")).strip()
    if not reason: raise ApiError("Indica el motivo de la corrección")
    try:
        start = datetime.fromisoformat(data["started_at"])
        finish = datetime.fromisoformat(data["finished_at"])
    except (KeyError, TypeError, ValueError): raise ApiError("Indica inicio y fin válidos")
    if timezone.is_naive(start): start = timezone.make_aware(start)
    if timezone.is_naive(finish): finish = timezone.make_aware(finish)
    if finish <= start: raise ApiError("El fin debe ser posterior al inicio")
    User.objects.select_for_update().get(pk=entry.user_id)
    overlap = TimeEntry.objects.filter(user_id=entry.user_id, started_at__lt=finish).filter(Q(finished_at__isnull=True) | Q(finished_at__gt=start)).exclude(pk=entry.pk).exists()
    if overlap: raise ApiError("El intervalo se traslapa con otra sesión", 409)
    before = {"started_at": iso(entry.started_at), "finished_at": iso(entry.finished_at)}
    entry.started_at = start; entry.finished_at = finish
    entry.save(update_fields=["started_at", "finished_at"])
    recalculate_labor(order)
    after = {"started_at": iso(start), "finished_at": iso(finish)}
    WorkOrderEvent.objects.create(work_order=order, user=user, event="Tiempo corregido", details=f"{entry.user.first_name}: {before} → {after}; motivo: {reason}")
    audit(user, "time_entry", entry.id, "corrected", before, after, reason)
    return JsonResponse({"ok": True, "labor_hours": float(order.labor_hours), "version": order.version})


@transaction.atomic
def transition_api(request, pk, validate):
    user = require(request, "orders.validate" if validate else "orders.transition"); order = get_object_or_404(WorkOrder.objects.select_for_update(), pk=pk); require(request, None, order.asset.area if order.asset else order.location)
    if user.role == "Técnico" and order.technician_id != user.id:
        raise ApiError("Solo puedes cambiar órdenes asignadas a ti", 403)
    data = payload(request)
    if int(data.get("version", -1)) != order.version: raise ApiError("La orden cambió en otra sesión", 409)
    target = "Completada" if validate else data.get("to"); allowed = {"Abierta": ["Programada", "En proceso", "Cancelada"], "Programada": ["En proceso", "Abierta", "Cancelada"], "En proceso": ["Pausada", "Espera de material", "Pendiente de validación", "Cancelada"], "Pausada": ["En proceso", "Cancelada"], "Espera de material": ["En proceso", "Cancelada"], "Pendiente de validación": ["Completada", "En proceso"], "Completada": ["Abierta"], "Cancelada": ["Abierta"]}
    if target not in allowed.get(order.status, []) or (target == "Completada" and not validate): raise ApiError("Usa la acción correspondiente al estado actual de la orden")
    if target == "Cancelada":
        require(request, "orders.validate")
        if not str(data.get("reason", "")).strip(): raise ApiError("Indica el motivo de cancelación")
        if order.materials.exists() and not str(data.get("material_disposition", "")).strip():
            raise ApiError("Indica el tratamiento de los materiales consumidos")
    if target in ("Pausada", "Espera de material", "Pendiente de validación", "Cancelada") and order.time_entries.filter(finished_at__isnull=True).exists():
        raise ApiError("Pausa o termina las sesiones activas antes de cambiar el estado")
    if target == "Pendiente de validación":
        if not order.actions or not order.technician_id or not order.closure_notes:
            raise ApiError("Registra acciones, tecnicos y notas de cierre antes de terminar")
        if not order.time_entries.exists() and (not order.started_at or not order.finished_at):
            raise ApiError("Indica inicio y fin del trabajo antes de terminar")
        if not order.labor_hours:
            raise ApiError("Las horas hombre deben ser mayores que cero")
        for occurrence in order.preventive_occurrences.select_related("task"):
            required_ids = set(occurrence.task.checklist_items.filter(required=True).values_list("id", flat=True))
            answered_ids = set(occurrence.checklist_answers.filter(item_id__in=required_ids).values_list("item_id", flat=True))
            if required_ids - answered_ids:
                raise ApiError("Faltan respuestas obligatorias del preventivo")
    if target == "Abierta" and order.status in ("Completada", "Cancelada"):
        require(request, "orders.validate")
        if not str(data.get("reason", "")).strip(): raise ApiError("Indica el motivo de reapertura")
    previous = order.status; order.status = target; order.version += 1
    if target == "En proceso" and not order.started_at: order.started_at = timezone.now()
    if target == "Pendiente de validación":
        if not order.finished_at: order.finished_at = timezone.now()
        if order.finished_at <= order.started_at: raise ApiError("El termino debe ser posterior al inicio")
        if not order.time_entries.exists(): order.labor_hours = order_labor_hours(order)
        order.validation_status = "Pendiente"
    if target == "Completada": order.validator = user; order.validated_at = timezone.now(); order.validation_status = "Validada"; order.closed_at = timezone.now()
    if target == "Abierta" and previous in ("Completada", "Cancelada"):
        order.validation_status = "No aplica"; order.close_reason = data.get("reason", "")
        order.validator = None; order.validated_at = None; order.closed_at = None; order.finished_at = None
    if target == "Cancelada": order.close_reason = str(data["reason"]).strip(); order.closed_at = timezone.now()
    order.save(); WorkOrderEvent.objects.create(work_order=order, user=user, event=f"{previous} → {target}", details="; ".join(part for part in [data.get("reason") or data.get("comment", ""), data.get("material_disposition", "")] if part))
    event_name = {"Pendiente de validación": "terminated", "Completada": "validated", "En proceso": "returned" if previous == "Pendiente de validación" else None, "Cancelada": "cancelled", "Abierta": "reopened"}.get(target)
    if event_name:
        for occurrence in order.preventive_occurrences.all(): PreventiveExecutionEvent.objects.create(occurrence=occurrence, event=event_name, user=user, notes=data.get("closure_notes") or data.get("comment", ""), reason=data.get("reason", ""))
    audit(user, "work_order", order.id, "transition", {"status": previous}, {"status": target}, data.get("reason", "")); return JsonResponse({"ok": True, "status": target, "version": order.version})


def orders_csv(request):
    user = require(request, "orders.read"); output = io.StringIO(); writer = csv.writer(output); writer.writerow(["Folio", "Fecha", "Activo", "Prioridad", "Clasificación", "Estado", "Técnico"])
    for o in filtered_orders(request, user).order_by("-requested_at"): writer.writerow([csv_cell(v) for v in [o.folio, iso(o.requested_at), o.asset.name if o.asset else "", o.priority, o.classification, o.status, o.technician.first_name if o.technician else ""]])
    response = HttpResponse("\ufeff" + output.getvalue(), content_type="text/csv; charset=utf-8"); response["Content-Disposition"] = 'attachment; filename="ordenes-mantenimiento.csv"'; return response


def orders_xlsx(request):
    user = require(request, "orders.read")
    headers = ["Folio", "Fecha de solicitud", "Activo", "Código de activo", "Área", "Prioridad", "Clasificación", "Estado", "Solicitante", "Técnico", "Fecha programada", "Inicio", "Fin", "Horas hombre", "Falla reportada", "Acciones realizadas"]
    if user.role != "Solicitante":
        headers += ["Costo de materiales", "Notas de cierre"]
    rows = []
    orders = filtered_orders(request, user).order_by("-requested_at").iterator()
    for order in orders:
        requested = timezone.localtime(order.requested_at) if timezone.is_aware(order.requested_at) else order.requested_at
        scheduled = timezone.localtime(order.scheduled_at) if order.scheduled_at and timezone.is_aware(order.scheduled_at) else order.scheduled_at
        started = timezone.localtime(order.started_at) if order.started_at and timezone.is_aware(order.started_at) else order.started_at
        finished = timezone.localtime(order.finished_at) if order.finished_at and timezone.is_aware(order.finished_at) else order.finished_at
        row = [
            order.folio, requested, order.asset.name if order.asset else "", order.asset.code if order.asset else "",
            order.asset.area if order.asset else order.location, order.priority, order.classification, order.status,
            order.requester.first_name, order.technician.first_name if order.technician else "",
            scheduled, started, finished, order.labor_hours, order.reported_failure, order.actions,
        ]
        if user.role != "Solicitante":
            row += [material_total(order.materials), order.closure_notes]
        rows.append(row)
    decimal_columns = {14} if user.role == "Solicitante" else {14, 17}
    content = make_workbook("Órdenes de trabajo", headers, rows, date_columns={2, 11, 12, 13}, decimal_columns=decimal_columns)
    response = HttpResponse(content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="ordenes-mantenimiento.xlsx"'
    return response


def work_order_document_dict(document):
    return {
        "id": document.id,
        "version": document.version,
        "document_number": document.document_number,
        "source_order_version": document.source_order_version,
        "status": document.snapshot.get("status"),
        "document_code": document.snapshot.get("closure_document_code", ""),
        "document_revision": document.snapshot.get("closure_document_revision", ""),
        "sha256": document.sha256,
        "created_at": iso(document.created_at),
        "created_by_name": document.created_by.first_name,
    }


@transaction.atomic
def work_order_documents_api(request, order_pk):
    if request.method == "GET":
        user = require(request, "orders.read")
        if user.role == "Solicitante":
            raise ApiError("Las copias versionadas están disponibles para personal de Mantenimiento", 403)
        order = get_object_or_404(order_queryset(user).select_related("requester", "technician", "validator", "asset"), pk=order_pk)
        rows = WorkOrderDocument.objects.filter(work_order=order).select_related("created_by").order_by("-version")
        return JsonResponse([work_order_document_dict(document) for document in rows], safe=False)

    if request.method != "POST":
        raise ApiError("Método no permitido", 405)
    user = require(request, "orders.edit")
    order = get_object_or_404(
        order_queryset(user).select_for_update(of=("self",)).select_related("requester", "technician", "validator", "asset"),
        pk=order_pk,
    )
    if user.role == "Técnico" and order.technician_id != user.id:
        raise ApiError("Solo puedes generar documentos de órdenes asignadas a ti", 403)

    record = work_order_snapshot(order)
    latest = WorkOrderDocument.objects.filter(work_order=order).select_related("created_by").first()
    created = latest is None or latest.snapshot.get("record") != record
    if created:
        version = latest.version + 1 if latest else 1
        document_number = f"{order.folio}-PDF-v{version:03d}"
        generated_at = timezone.localtime(timezone.now())
        canonical_record = json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        snapshot = {
            **record,
            "version": version,
            "document_number": document_number,
            "generated_at": generated_at.isoformat(),
            "snapshot_sha256": hashlib.sha256(canonical_record.encode("utf-8")).hexdigest(),
            "record": record,
        }
        pdf_content = render_work_order_pdf(snapshot)
        checksum = hashlib.sha256(pdf_content).hexdigest()
        document = WorkOrderDocument.objects.create(
            work_order=order,
            version=version,
            document_number=document_number,
            source_order_version=order.version,
            snapshot=snapshot,
            sha256=checksum,
            pdf_content=pdf_content,
            created_by=user,
        )
        WorkOrderEvent.objects.create(
            work_order=order,
            user=user,
            event="PDF versionado generado",
            details=f"{document_number}; versión de OT {order.version}; SHA-256 {checksum}",
        )
        audit(user, "work_order_document", document.id, "generated", after={
            "work_order_id": order.id,
            "folio": order.folio,
            "document_number": document_number,
            "version": version,
            "source_order_version": order.version,
            "sha256": checksum,
        })
    else:
        document = latest

    body = work_order_document_dict(document)
    body["url"] = f"/api/orders/{order.id}/documents/{document.id}"
    body["created"] = created
    return JsonResponse(body, status=201 if created else 200)


def work_order_document_download_api(request, order_pk, document_pk):
    if request.method != "GET":
        raise ApiError("Método no permitido", 405)
    user = require(request, "orders.read")
    if user.role == "Solicitante":
        raise ApiError("Las copias versionadas están disponibles para personal de Mantenimiento", 403)
    order = get_object_or_404(order_queryset(user), pk=order_pk)
    document = get_object_or_404(WorkOrderDocument, pk=document_pk, work_order=order)
    response = HttpResponse(bytes(document.pdf_content), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{document.document_number}.pdf"'
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    response["ETag"] = f'"{document.sha256}"'
    return response


def preventives_api(request):
    user = require(request, "preventives.read" if request.method == "GET" else "preventives.edit")
    if request.method == "GET":
        rows = PreventivePlan.objects.select_related("asset", "responsible")
        return JsonResponse([{"id": p.id, "asset_id": p.asset_id, "asset_name": p.asset.name, "asset_code": p.asset.code, "asset_area": p.asset.area, "title": p.title, "frequency": p.frequency, "next_date": p.next_date.isoformat(), "responsible_id": p.responsible_id, "responsible_name": p.responsible.first_name if p.responsible else None, "status": p.status, "work_order_id": p.work_order_id, "version": p.version, "template_code": p.template_code, "instructions": p.instructions, "applies_when": p.applies_when} for p in rows if not user.area_permissions or p.asset.area in user.area_permissions], safe=False)
    data = payload(request); asset = get_object_or_404(Asset, pk=data["asset_id"]); require(request, "preventives.edit", asset.area); plan = PreventivePlan.objects.create(asset=asset, title=data["title"], frequency=data["frequency"], next_date=data["next_date"], responsible_id=data.get("responsible_id") or None, status=data.get("status", "Programado"), template_code=data.get("template_code", ""), instructions=data.get("instructions", ""), applies_when=data.get("applies_when", "")); save_revision(plan, user, "created"); audit(user, "preventive_plan", plan.id, "created"); return JsonResponse({"id": plan.id, "version": 1}, status=201)


def plan_for(request, pk, action):
    plan = get_object_or_404(PreventivePlan.objects.select_related("asset"), pk=pk); require(request, action, plan.asset.area); return plan


@transaction.atomic
def tasks_api(request, pk):
    plan = plan_for(request, pk, "preventives.read" if request.method == "GET" else "preventives.edit")
    if request.method == "GET": return JsonResponse([{"id": x.id, "plan_id": x.plan_id, "title": x.title, "interval_unit": x.interval_unit, "interval_value": x.interval_value, "anchor_date": x.anchor_date.isoformat(), "applicability_status": x.applicability_status, "applicability_reason": x.applicability_reason, "validated_by": x.validated_by_id, "validated_at": iso(x.validated_at)} for x in plan.tasks.order_by("id")], safe=False)
    data = payload(request)
    if int(data.get("version", -1)) != plan.version: raise ApiError("El preventivo cambió en otra sesión", 409)
    if plan.occurrences.exists() or plan.work_order_id: raise ApiError("No puedes cambiar tareas después de generar una OT", 409)
    unit, value, anchor = data.get("interval_unit"), int(data.get("interval_value", 0)), parse_day(data.get("anchor_date"), "fecha ancla")
    if unit not in ["days", "months"] or value < 1 or value > 1200: raise ApiError("Recurrencia inválida")
    task = PreventiveTask.objects.create(plan=plan, title=str(data.get("title", "")).strip(), interval_unit=unit, interval_value=value, anchor_date=anchor, created_by=request.user); plan.version += 1; plan.save(update_fields=["version"]); save_revision(plan, request.user, "task-added"); audit(request.user, "preventive_plan", plan.id, "task-added"); return JsonResponse({"id": task.id, "version": plan.version}, status=201)


@transaction.atomic
def task_applicability_api(request, plan_pk, task_pk):
    plan = plan_for(request, plan_pk, "preventives.edit")
    if request.method != "PATCH": raise ApiError("Método no permitido", 405)
    plan = PreventivePlan.objects.select_for_update().get(pk=plan.pk)
    task = get_object_or_404(plan.tasks.select_for_update(), pk=task_pk)
    data = payload(request)
    if int(data.get("version", -1)) != plan.version: raise ApiError("El preventivo cambió en otra sesión", 409)
    status = data.get("status")
    reason = str(data.get("reason") or "").strip()
    if status not in ("Interna", "Externa", "No aplica"): raise ApiError("Selecciona una decisión de aplicabilidad")
    if not reason: raise ApiError("Explica la decisión de aplicabilidad")
    before = {"status": task.applicability_status, "reason": task.applicability_reason}
    task.applicability_status = status
    task.applicability_reason = reason
    task.validated_by = request.user
    task.validated_at = timezone.now()
    task.save(update_fields=["applicability_status", "applicability_reason", "validated_by", "validated_at"])
    plan.version += 1
    plan.save(update_fields=["version"])
    save_revision(plan, request.user, "applicability-reviewed", reason)
    audit(request.user, "preventive_task", task.id, "applicability-reviewed", before=before, after={"status": status, "reason": reason}, reason=reason)
    return JsonResponse({"id": task.id, "status": status, "version": plan.version, "validated_at": iso(task.validated_at)})


def calendar_api(request, pk):
    plan = plan_for(request, pk, "preventives.read"); start, end = parse_day(request.GET.get("from"), "fecha inicial"), parse_day(request.GET.get("to"), "fecha final")
    if end < start or (end-start).days > 366: raise ApiError("El período es inválido o supera 366 días")
    tasks = list(plan.tasks.all())
    saved_keys = set(plan.occurrences.values_list("task_id", "occurrence_index"))
    rows = [item for task in tasks for item in task_projection(task, start, end) if task.applicability_status in ("Interna", "Externa") or (task.id, item["occurrence_index"]) in saved_keys]
    return JsonResponse({"plan_id": plan.id, "configuration_pending": not any(task.applicability_status in ("Interna", "Externa") for task in tasks) or any(task.applicability_status == "Pendiente" for task in tasks), "projection_only": True, "occurrences": rows})


def revisions_api(request, pk):
    plan = plan_for(request, pk, "preventives.read")
    return JsonResponse([{"id": x.id, "version": x.version, "snapshot": x.snapshot, "user_id": x.user_id, "source": x.source, "reason": x.reason, "recorded_at": iso(x.recorded_at)} for x in plan.revisions.order_by("-version")], safe=False)


@transaction.atomic
def make_occurrence(plan, task, index, user, shared_order=None, source="manual"):
    PreventivePlan.objects.select_for_update().get(pk=plan.pk)
    task = PreventiveTask.objects.get(pk=task.pk)
    existing = PreventiveOccurrence.objects.filter(task=task, occurrence_index=index).select_related("work_order").first()
    if existing: return existing, True
    if task.applicability_status not in ("Interna", "Externa"):
        raise ApiError("Valida la aplicabilidad de la tarea antes de generar su OT", 409)
    revision = plan.revisions.filter(version=plan.version).first() or save_revision(plan, user, "occurrence-baseline")
    due = task_due(task, index); order = shared_order or WorkOrder.objects.create(folio=next_folio(), requested_at=timezone.now(), scheduled_at=scheduled_datetime(due), requester=user, priority="Media", classification="Mantenimiento Preventivo", asset=plan.asset, location=plan.asset.area, reported_failure=task.title, actions="", technician=plan.responsible, status="Programada")
    occurrence = PreventiveOccurrence.objects.create(plan=plan, task=task, occurrence_index=index, base_date=due, work_order=order, revision=revision, created_by=user)
    WorkOrderEvent.objects.create(work_order=order, user=user, event="OT preventiva generada", details=f"Origen: {source}; tarea #{task.id}; fecha base {due}")
    audit(user, "preventive_occurrence", occurrence.id, "created", after={"plan_id": plan.id, "task_id": task.id, "work_order_id": order.id, "base_date": due.isoformat(), "source": source})
    return occurrence, False


@transaction.atomic
def occurrences_api(request, pk):
    plan = plan_for(request, pk, "preventives.read" if request.method == "GET" else "preventives.edit")
    if request.method == "GET": return JsonResponse([{"id": x.id, "task_id": x.task_id, "occurrence_index": x.occurrence_index, "base_date": x.base_date.isoformat(), "work_order_id": x.work_order_id, "folio": x.work_order.folio, "status": x.work_order.status, "order_status": x.work_order.status, "scheduled_at": iso(x.work_order.scheduled_at)} for x in plan.occurrences.select_related("work_order")], safe=False)
    plan = PreventivePlan.objects.select_for_update().get(pk=plan.pk)
    require(request, "orders.create", plan.asset.area); data = payload(request)
    if int(data.get("version", -1)) != plan.version: raise ApiError("El preventivo cambió en otra sesión", 409)
    task = get_object_or_404(plan.tasks, pk=data.get("task_id")); occurrence, replay = make_occurrence(plan, task, int(data.get("occurrence_index")), request.user); return JsonResponse({"id": occurrence.id, "work_order_id": occurrence.work_order_id, "folio": occurrence.work_order.folio, "replayed": replay}, status=200 if replay else 201)


@transaction.atomic
def occurrence_group_api(request, pk):
    plan = plan_for(request, pk, "preventives.edit"); require(request, "orders.create", plan.asset.area); data = payload(request)
    PreventivePlan.objects.select_for_update().get(pk=plan.pk)
    if int(data.get("version", -1)) != plan.version: raise ApiError("El preventivo cambió en otra sesión", 409)
    requested = data.get("occurrences", [])
    if len(requested) < 2: raise ApiError("Selecciona al menos dos tareas")
    tasks = [(get_object_or_404(plan.tasks, pk=x["task_id"]), int(x["occurrence_index"])) for x in requested]; dates = {task_due(t, i) for t, i in tasks}
    if any(task.applicability_status not in ("Interna", "Externa") for task, _ in tasks): raise ApiError("Valida la aplicabilidad de todas las tareas", 409)
    if len(dates) != 1: raise ApiError("Las tareas agrupadas deben compartir fecha base")
    existing = [PreventiveOccurrence.objects.filter(task=t, occurrence_index=i).first() for t, i in tasks]
    if any(existing):
        ids = {x.work_order_id for x in existing if x}
        if len(ids) == 1 and all(existing): return JsonResponse({"work_order_id": ids.pop(), "replayed": True})
        raise ApiError("Una tarea ya pertenece a otra OT", 409)
    title = " · ".join(t.title for t, _ in tasks); order = WorkOrder.objects.create(folio=next_folio(), requested_at=timezone.now(), scheduled_at=scheduled_datetime(dates.pop()), requester=request.user, priority="Media", classification="Mantenimiento Preventivo", asset=plan.asset, location=plan.asset.area, reported_failure=title, technician=plan.responsible, status="Programada")
    rows = [make_occurrence(plan, t, i, request.user, order)[0] for t, i in tasks]; return JsonResponse({"work_order_id": order.id, "folio": order.folio, "occurrences": [x.id for x in rows]}, status=201)


def preventive_status_rows(plan, start, end, as_of):
    saved = {
        (item.task_id, item.occurrence_index): item
        for item in plan.occurrences.filter(base_date__range=(start, end)).select_related("work_order").prefetch_related("execution_events")
    }
    rows = []
    for task in plan.tasks.all():
        for projected in task_projection(task, start, end):
            occurrence = saved.get((task.id, projected["occurrence_index"]))
            if task.applicability_status not in ("Interna", "Externa") and not occurrence: continue
            events = list(occurrence.execution_events.order_by("recorded_at", "pk")) if occurrence else []
            executed = next((event for event in reversed(events) if event.event == "terminated"), None)
            cancelled = any(event.event == "cancelled" for event in events)
            reprogrammed = any(event.event == "rescheduled" for event in events)
            base_date = date.fromisoformat(projected["base_date"])
            executed_date = timezone.localdate(executed.recorded_at) if executed else None
            if cancelled:
                status, reason = "Cancelada", "Cancelada o excluida"
            elif executed_date:
                status, reason = ("T", "Ejecutada en fecha") if executed_date <= base_date else ("D", "Ejecutada después de la fecha base")
            elif base_date < as_of:
                status, reason = "V", "Vencida sin ejecución"
            else:
                status, reason = "P", "Pendiente"
            rows.append({
                "id": occurrence.id if occurrence else None,
                "plan_id": plan.id,
                "task_id": task.id,
                "task_title": task.title,
                "occurrence_index": projected["occurrence_index"],
                "base_date": projected["base_date"],
                "work_order_id": occurrence.work_order_id if occurrence else None,
                "folio": occurrence.work_order.folio if occurrence else None,
                "order_status": occurrence.work_order.status if occurrence else None,
                "scheduled_at": iso(occurrence.work_order.scheduled_at) if occurrence else None,
                "status": status,
                "reason": reason,
                "reprogrammed": reprogrammed,
                "executed_date": executed_date.isoformat() if executed_date else None,
            })
    return rows


def compliance_api(request, pk):
    plan = plan_for(request, pk, "preventives.read")
    start = parse_day(request.GET.get("from"), "fecha inicial")
    end = parse_day(request.GET.get("to"), "fecha final")
    as_of = parse_day(request.GET.get("as_of") or timezone.localdate())
    if end < start or (end - start).days > 366:
        raise ApiError("El período es inválido o supera 366 días")
    rows = preventive_status_rows(plan, start, end, as_of)
    counts = {key: sum(row["status"] == key for row in rows) for key in "PTDV"}
    counts["R"] = sum(row["reprogrammed"] for row in rows)
    counts["Cancelada"] = sum(row["status"] == "Cancelada" for row in rows)
    eligible = len(rows) - counts["Cancelada"]
    percentage = round(counts["T"] * 100 / eligible, 2) if eligible else None
    return JsonResponse({
        "plan_id": plan.id,
        "configuration_pending": not plan.tasks.filter(applicability_status__in=("Interna", "Externa")).exists() or plan.tasks.filter(applicability_status="Pendiente").exists(),
        "counts": counts,
        "eligible": eligible,
        "percentage": percentage,
        "compliance_percent": percentage,
        "occurrences": rows,
    })


def preventive_calendar_api(request):
    user = require(request, "preventives.read")
    if request.method != "GET": raise ApiError("Método no permitido", 405)
    start = parse_day(request.GET.get("from") or timezone.localdate(), "fecha inicial")
    end = parse_day(request.GET.get("to") or start + timedelta(days=30), "fecha final")
    as_of = parse_day(request.GET.get("as_of") or timezone.localdate())
    if end < start or (end - start).days > 366:
        raise ApiError("El período es inválido o supera 366 días")
    plans = PreventivePlan.objects.select_related("asset").prefetch_related("tasks", "occurrences__work_order", "occurrences__execution_events")
    assets = Asset.objects.filter(administrative_status="Activo")
    if user.area_permissions:
        plans = plans.filter(asset__area__in=user.area_permissions)
        assets = assets.filter(area__in=user.area_permissions)
    rows = []
    configured_asset_ids = set()
    incomplete = []
    for plan in plans:
        eligible_tasks = [task for task in plan.tasks.all() if task.applicability_status in ("Interna", "Externa")]
        pending_tasks = [task for task in plan.tasks.all() if task.applicability_status == "Pendiente"]
        if not eligible_tasks or pending_tasks:
            incomplete.append({"plan_id": plan.id, "asset_id": plan.asset_id, "asset_code": plan.asset.code, "title": plan.title, "reason": "Sin tareas que apliquen al activo" if not eligible_tasks else f"{len(pending_tasks)} tareas pendientes de revisión"})
        if not eligible_tasks and not plan.occurrences.exists():
            continue
        if eligible_tasks: configured_asset_ids.add(plan.asset_id)
        for row in preventive_status_rows(plan, start, end, as_of):
            rows.append(row | {"asset_id": plan.asset_id, "asset_code": plan.asset.code, "asset_name": plan.asset.name, "asset_area": plan.asset.area, "plan_title": plan.title, "plan_version": plan.version})
    rows.sort(key=lambda row: (row["base_date"], row["asset_code"], row["plan_id"], row["task_id"]))
    uncovered = [{"asset_id": asset.id, "asset_code": asset.code, "asset_name": asset.name, "area": asset.area} for asset in assets.exclude(pk__in=configured_asset_ids).order_by("code")]
    counts = {key: sum(row["status"] == key for row in rows) for key in "PTDV"}
    counts["R"] = sum(row["reprogrammed"] for row in rows)
    counts["Cancelada"] = sum(row["status"] == "Cancelada" for row in rows)
    return JsonResponse({"from": start.isoformat(), "to": end.isoformat(), "as_of": as_of.isoformat(), "occurrences": rows, "counts": counts, "coverage": {"assets_without_configured_plan": uncovered, "incomplete_plans": incomplete}})

def upcoming_api(request, pk):
    plan = plan_for(request, pk, "preventives.read"); start = parse_day(request.GET.get("from") or timezone.localdate()); end = parse_day(request.GET.get("to") or start+timedelta(days=30)); saved = {(x.task_id, x.occurrence_index): x for x in plan.occurrences.all()}; rows = []
    for task in plan.tasks.all():
        for row in task_projection(task, start, end):
            found = saved.get((task.id, row["occurrence_index"]))
            if task.applicability_status not in ("Interna", "Externa") and not found: continue
            rows.append(row | {"persisted": bool(found), "work_order_id": found.work_order_id if found else None})
    return JsonResponse({"plan_id": plan.id, "from": start.isoformat(), "to": end.isoformat(), "projection_only": True, "occurrences": rows})


@transaction.atomic
def task_checklist_api(request, plan_pk, task_pk):
    plan = plan_for(request, plan_pk, "preventives.read" if request.method == "GET" else "preventives.edit"); task = get_object_or_404(plan.tasks, pk=task_pk)
    if request.method == "GET": return JsonResponse([{"id": x.id, "task_id": x.task_id, "position": x.position, "prompt": x.prompt, "required": x.required} for x in task.checklist_items.order_by("position")], safe=False)
    data = payload(request); row = ChecklistItem.objects.create(task=task, position=int(data["position"]), prompt=str(data["prompt"]).strip(), required=data.get("required", True), created_by=request.user); audit(request.user, "preventive_checklist_item", row.id, "created", after={"plan_id": plan.id, "task_id": task.id, "position": row.position, "prompt": row.prompt, "required": row.required}); return JsonResponse({"id": row.id, "task_id": task.id, "position": row.position, "prompt": row.prompt, "required": row.required}, status=201)


@transaction.atomic
def occurrence_checklist_api(request, plan_pk, occurrence_pk):
    plan = plan_for(request, plan_pk, "preventives.read" if request.method == "GET" else "preventives.edit"); occurrence = get_object_or_404(plan.occurrences, pk=occurrence_pk); items = occurrence.task.checklist_items.order_by("position")
    if request.method == "GET":
        answers = {x.item_id: x for x in occurrence.checklist_answers.all()}; return JsonResponse({"occurrence_id": occurrence.id, "items": [{"id": x.id, "prompt": x.prompt, "position": x.position, "required": x.required, "answer": answers[x.id].answer if x.id in answers else None, "notes": answers[x.id].notes if x.id in answers else ""} for x in items]})
    rows = payload(request).get("answers", []); supplied = {int(x["item_id"]): x for x in rows}
    if any(x.required and x.id not in supplied for x in items): raise ApiError("Faltan respuestas obligatorias del checklist")
    for item in items:
        if item.id not in supplied: continue
        value = supplied[item.id]
        if value.get("answer") not in ["Sí", "No", "N/A"]: raise ApiError("La respuesta debe ser Sí, No o N/A")
        if value["answer"] == "N/A" and not str(value.get("notes", "")).strip(): raise ApiError("Explica por qué el punto no aplica")
        answer_row = ChecklistAnswer.objects.filter(occurrence=occurrence, item=item).first()
        before = {"answer": answer_row.answer, "notes": answer_row.notes} if answer_row else None
        answer_row, created = ChecklistAnswer.objects.update_or_create(occurrence=occurrence, item=item, defaults={"answer": value["answer"], "notes": value.get("notes", ""), "recorded_by": request.user})
        audit(request.user, "preventive_checklist_answer", answer_row.id, "recorded" if created else "updated", before=before, after={"occurrence_id": occurrence.id, "item_id": item.id, "answer": answer_row.answer, "notes": answer_row.notes})
    return JsonResponse({"occurrence_id": occurrence.id, "complete": True})


@transaction.atomic
def apply_template_api(request, pk):
    plan = plan_for(request, pk, "preventives.edit"); data = payload(request); template = get_object_or_404(PreventiveTemplate, pk=data.get("template_id"), active=True)
    if int(data.get("version", -1)) != plan.version: raise ApiError("El preventivo cambió en otra sesión", 409)
    if template.family not in [plan.asset.asset_type, plan.asset.category]: raise ApiError("La plantilla no corresponde a la familia del activo", 409)
    if plan.tasks.exists() or plan.occurrences.exists(): raise ApiError("Solo puedes aplicar la plantilla a un preventivo vacío", 409)
    plan.title, plan.instructions, plan.template_code, plan.version = template.title, template.instructions, template.code, plan.version+1; plan.save()
    for row in template.tasks: PreventiveTask.objects.create(plan=plan, title=row["title"], interval_unit=row["interval_unit"], interval_value=int(row["interval_value"]), anchor_date=row["anchor_date"], created_by=request.user)
    save_revision(plan, request.user, "template-applied"); audit(request.user, "preventive_plan", plan.id, "template-applied"); return JsonResponse({"ok": True, "version": plan.version, "template_id": template.id, "tasks": len(template.tasks)})


@transaction.atomic
def reschedule_api(request, plan_pk, occurrence_pk):
    plan = plan_for(request, plan_pk, "preventives.edit"); occurrence = get_object_or_404(plan.occurrences.select_related("work_order"), pk=occurrence_pk); data = payload(request); order = WorkOrder.objects.select_for_update().get(pk=occurrence.work_order_id)
    if int(data.get("version", -1)) != order.version: raise ApiError("La orden cambió en otra sesión", 409)
    if not str(data.get("reason", "")).strip(): raise ApiError("Indica el motivo de reprogramación")
    previous_date = iso(order.scheduled_at)
    order.scheduled_at = scheduled_datetime(data["scheduled_at"]); order.version += 1; order.save()
    WorkOrderEvent.objects.create(work_order=order, user=request.user, event="Reprogramada", details=data["reason"])
    for related in order.preventive_occurrences.all():
        PreventiveExecutionEvent.objects.create(occurrence=related, event="rescheduled", user=request.user, reason=data["reason"], notes=f"{previous_date} → {iso(order.scheduled_at)}")
    audit(request.user, "work_order", order.id, "rescheduled", before={"scheduled_at": previous_date}, after={"scheduled_at": iso(order.scheduled_at)}, reason=data["reason"])
    return JsonResponse({"ok": True, "base_date": occurrence.base_date.isoformat(), "scheduled_at": iso(order.scheduled_at), "version": order.version})


@transaction.atomic
def preventive_order_api(request, pk):
    plan = plan_for(request, pk, "preventives.edit"); require(request, "orders.create", plan.asset.area)
    if plan.work_order: return JsonResponse({"id": plan.work_order_id, "folio": plan.work_order.folio, "replayed": True})
    raise ApiError("Selecciona una tarea y fecha del plan para generar su OT", 409)


@transaction.atomic
def preventive_api(request, pk):
    plan = plan_for(request, pk, "preventives.edit"); data = payload(request)
    if int(data.get("version", -1)) != plan.version: raise ApiError("El preventivo cambió en otra sesión", 409)
    if plan.occurrences.exists(): raise ApiError("No puedes editar un preventivo con ocurrencias", 409)
    for key in ["title", "frequency", "next_date", "status", "template_code", "instructions", "applies_when"]:
        if key in data: setattr(plan, key, data[key])
    if "responsible_id" in data: plan.responsible_id = data.get("responsible_id") or None
    plan.version += 1; plan.save(); save_revision(plan, request.user, "updated"); audit(request.user, "preventive_plan", plan.id, "updated"); return JsonResponse({"ok": True, "version": plan.version})


def templates_api(request):
    user = require(request, "preventives.read" if request.method == "GET" else "preventives.edit")
    if request.method == "GET": return JsonResponse([{"id": x.id, "code": x.code, "family": x.family, "title": x.title, "instructions": x.instructions, "tasks": x.tasks} for x in PreventiveTemplate.objects.filter(active=True)], safe=False)
    data = payload(request); row = PreventiveTemplate.objects.create(code=data["code"].upper(), family=data["family"], title=data["title"], instructions=data.get("instructions", ""), tasks=data["tasks"], created_by=user); audit(user, "preventive_template", row.id, "created", after={"code": row.code, "family": row.family, "title": row.title, "instructions": row.instructions, "tasks": row.tasks}); return JsonResponse({"id": row.id}, status=201)


@transaction.atomic
def meter_api(request, pk):
    asset = get_object_or_404(Asset, pk=pk); user = require(request, "assets.read" if request.method == "GET" else "assets.edit", asset.area)
    if request.method == "GET": return JsonResponse([{"id": x.id, "value": float(x.value), "notes": x.notes, "recorded_by": x.recorded_by_id, "recorded_at": iso(x.recorded_at)} for x in asset.meter_readings.order_by("-recorded_at")], safe=False)
    data = payload(request); value = decimal(data.get("value"), "lectura")
    if value < asset.operating_hours: raise ApiError("La lectura no puede ser menor que el horómetro actual")
    previous_hours = str(asset.operating_hours)
    row = MeterReading.objects.create(asset=asset, value=value, notes=data.get("notes", ""), recorded_by=user); asset.operating_hours = value; asset.save(update_fields=["operating_hours"]); audit(user, "meter_reading", row.id, "recorded", before={"asset_operating_hours": previous_hours}, after={"asset_id": asset.id, "value": str(row.value), "asset_operating_hours": str(asset.operating_hours), "notes": row.notes}); return JsonResponse({"id": row.id, "value": float(value)}, status=201)


@transaction.atomic
def downtime_api(request):
    user = require(request, "orders.read" if request.method == "GET" else "orders.transition")
    if request.method == "GET": return JsonResponse([{"id": x.id, "asset_id": x.asset_id, "asset_name": x.asset.name, "asset_code": x.asset.code, "cause": x.cause, "started_at": iso(x.started_at), "finished_at": iso(x.finished_at), "order_count": x.work_orders.count(), "work_order_ids": list(x.work_orders.values_list("id", flat=True))} for x in DowntimeEvent.objects.select_related("asset") if not user.area_permissions or x.asset.area in user.area_permissions], safe=False)
    if request.method != "POST": raise ApiError("Método no permitido", 405)
    data = payload(request)
    asset = get_object_or_404(Asset.objects.select_for_update(), pk=data.get("asset_id"))
    require(request, "orders.transition", asset.area)
    cause = str(data.get("cause", "")).strip()
    if not cause: raise ApiError("Indica la causa del paro")
    start = scheduled_datetime(data.get("started_at"))
    finish = scheduled_datetime(data["finished_at"]) if data.get("finished_at") else None
    if finish and finish <= start: raise ApiError("El fin del paro debe ser posterior al inicio")
    try: order_ids = {int(value) for value in data.get("work_order_ids", [])}
    except (TypeError, ValueError): raise ApiError("Órdenes relacionadas inválidas")
    orders = list(WorkOrder.objects.filter(pk__in=order_ids, asset=asset))
    if len(orders) != len(order_ids): raise ApiError("Todas las OT relacionadas deben pertenecer al activo")
    row = DowntimeEvent.objects.create(asset=asset, cause=cause, started_at=start, finished_at=finish, created_by=user)
    row.work_orders.set(orders)
    if not finish:
        asset.operational_status = "Parada"; asset.operational_status_cause = cause; asset.operational_status_updated_at = timezone.now()
        asset.save(update_fields=["operational_status", "operational_status_cause", "operational_status_updated_at"])
    audit(user, "downtime", row.id, "created", after={"asset_id": asset.id, "work_order_ids": list(order_ids), "started_at": iso(start), "finished_at": iso(finish)})
    return JsonResponse({"id": row.id}, status=201)


def downtime_xlsx(request):
    user = require(request, "orders.read")
    events = DowntimeEvent.objects.select_related("asset", "created_by", "closed_by").prefetch_related("work_orders").order_by("-started_at", "-id")
    if user.area_permissions:
        events = events.filter(asset__area__in=user.area_permissions)
    headers = ["Activo", "Código", "Área", "Causa", "Inicio", "Fin", "Estado", "OT relacionadas", "Registró", "Cerró", "Motivo de cierre"]
    rows = []
    for event in events:
        start = timezone.localtime(event.started_at) if timezone.is_aware(event.started_at) else event.started_at
        finish = timezone.localtime(event.finished_at) if event.finished_at and timezone.is_aware(event.finished_at) else event.finished_at
        folios = ", ".join(sorted(order.folio for order in event.work_orders.all()))
        rows.append([event.asset.name, event.asset.code, event.asset.area, event.cause, start, finish, "Abierto" if not event.finished_at else "Cerrado", folios, event.created_by.first_name, event.closed_by.first_name if event.closed_by else "", event.close_reason])
    content = make_workbook("Historial de paros", headers, rows, date_columns={5, 6})
    response = HttpResponse(content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="historial-paros.xlsx"'
    return response


@transaction.atomic
def downtime_item_api(request, pk):
    user = require(request, "orders.transition")
    if request.method != "PATCH": raise ApiError("Método no permitido", 405)
    row = get_object_or_404(DowntimeEvent.objects.select_for_update().select_related("asset"), pk=pk)
    require(request, None, row.asset.area)
    if row.finished_at: raise ApiError("El paro ya está cerrado", 409)
    data = payload(request)
    if not data.get("reason") or len(str(data["reason"]).strip()) < 5: raise ApiError("Indica el motivo del cierre")
    finish = scheduled_datetime(data["finished_at"]) if data.get("finished_at") else timezone.now()
    if finish <= row.started_at: raise ApiError("El fin del paro debe ser posterior al inicio")
    row.finished_at = finish; row.closed_by = user; row.close_reason = data["reason"]; row.save()
    asset = Asset.objects.select_for_update().get(pk=row.asset_id)
    other_open = DowntimeEvent.objects.filter(asset=asset, finished_at__isnull=True).exclude(pk=row.pk).order_by("-started_at").first()
    asset.operational_status = "Parada" if other_open else "Operativa"
    asset.operational_status_cause = other_open.cause if other_open else ""
    asset.operational_status_updated_at = timezone.now()
    asset.save(update_fields=["operational_status", "operational_status_cause", "operational_status_updated_at"])
    audit(user, "downtime", row.id, "closed", before={"finished_at": None}, after={"finished_at": iso(finish), "operational_status": asset.operational_status}, reason=data["reason"])
    return JsonResponse({"ok": True, "asset_status": asset.operational_status})


def agenda_api(request):
    user = require(request, "orders.read"); orders = order_queryset(user).exclude(status__in=["Completada", "Cancelada"]); technicians = User.objects.filter(role__in=["Técnico", "Jefatura"], is_active=True)
    return JsonResponse({"orders": [order_dict(x) for x in orders], "technicians": [public_user(x) for x in technicians]})


def audit_queryset(request, user):
    rows = AuditLog.objects.select_related("user")
    if user.area_permissions:
        areas = user.area_permissions
        assets = Asset.objects.filter(area__in=areas).values("id")
        orders = WorkOrder.objects.filter(Q(asset__area__in=areas) | Q(asset__isnull=True, location__in=areas)).values("id")
        plans = PreventivePlan.objects.filter(asset__area__in=areas).values("id")
        checklist_items = ChecklistItem.objects.filter(task__plan_id__in=plans).values("id")
        checklist_answers = ChecklistAnswer.objects.filter(occurrence__plan_id__in=plans).values("id")
        meter_readings = MeterReading.objects.filter(asset__area__in=areas).values("id")
        downtime = DowntimeEvent.objects.filter(asset__area__in=areas).values("id")
        alerts = OperationalAlert.objects.filter(area__in=areas).values("id")
        rows = rows.filter(
            Q(entity_type="asset", entity_id__in=assets)
            | Q(entity_type="asset_code_equivalence", entity_id__in=AssetCodeEquivalence.objects.filter(asset__area__in=areas).values("id"))
            | Q(entity_type="work_order", entity_id__in=orders)
            | Q(entity_type="work_order_document", entity_id__in=WorkOrderDocument.objects.filter(work_order_id__in=orders).values("id"))
            | Q(entity_type="time_entry", entity_id__in=TimeEntry.objects.filter(work_order_id__in=orders).values("id"))
            | Q(entity_type="preventive_plan", entity_id__in=plans)
            | Q(entity_type="preventive_task", entity_id__in=PreventiveTask.objects.filter(plan_id__in=plans).values("id"))
            | Q(entity_type="preventive_checklist_item", entity_id__in=checklist_items)
            | Q(entity_type="preventive_checklist_answer", entity_id__in=checklist_answers)
            | Q(entity_type="preventive_occurrence", entity_id__in=PreventiveOccurrence.objects.filter(plan_id__in=plans).values("id"))
            | Q(entity_type="meter_reading", entity_id__in=meter_readings)
            | Q(entity_type="downtime", entity_id__in=downtime)
            | Q(entity_type="operational_alert", entity_id__in=alerts)
            | Q(entity_type__in=["inventory_item", "inventory_import"])
        )
    start = parse_day(request.GET["from"], "fecha inicial") if request.GET.get("from") else None
    end = parse_day(request.GET["to"], "fecha final") if request.GET.get("to") else None
    if start and end and start > end:
        raise ApiError("La fecha inicial debe ser anterior o igual a la final")
    if start: rows = rows.filter(created_at__date__gte=start)
    if end: rows = rows.filter(created_at__date__lte=end)
    if request.GET.get("entity_type"):
        rows = rows.filter(entity_type=request.GET["entity_type"][:80])
    if request.GET.get("entity_id"):
        try: entity_id = int(request.GET["entity_id"])
        except ValueError: raise ApiError("ID de entidad inválido")
        if entity_id < 1: raise ApiError("ID de entidad inválido")
        rows = rows.filter(entity_id=entity_id)
    if request.GET.get("action"):
        rows = rows.filter(action=request.GET["action"][:100])
    if request.GET.get("q"):
        query = request.GET["q"].strip()[:200]
        rows = rows.filter(Q(entity_type__icontains=query) | Q(action__icontains=query) | Q(reason__icontains=query) | Q(user__first_name__icontains=query) | Q(user__last_name__icontains=query) | Q(user__username__icontains=query))
    return rows.order_by("-created_at", "-id")


def audit_dict(row):
    return {"id":row.id, "user_id":row.user_id, "user_name":row.user.first_name if row.user else "Sistema", "entity_type":row.entity_type, "entity_id":row.entity_id, "action":row.action, "before":row.before, "after":row.after, "reason":row.reason, "created_at":iso(row.created_at)}


def audit_api(request):
    user = require(request, "audit.read")
    if request.method != "GET": raise ApiError("Método no permitido", 405)
    rows = audit_queryset(request, user)
    try: page = int(request.GET.get("page", "1"))
    except ValueError: raise ApiError("Página inválida")
    if page < 1 or page > 100000: raise ApiError("Página inválida")
    page_size = 50
    total = rows.count()
    items = [audit_dict(x) for x in rows[(page-1)*page_size:page*page_size]]
    return JsonResponse({"items":items, "page":page, "page_size":page_size, "total":total})


def audit_xlsx(request):
    user = require(request, "audit.read")
    if request.method != "GET": raise ApiError("Método no permitido", 405)
    rows = audit_queryset(request, user).iterator()
    headers = ["Fecha", "Usuario", "Entidad", "ID entidad", "Acción", "Motivo", "Antes", "Después"]
    data = []
    for row in rows:
        created = timezone.localtime(row.created_at) if timezone.is_aware(row.created_at) else row.created_at
        data.append([created, row.user.first_name if row.user else "Sistema", row.entity_type, row.entity_id, row.action, row.reason, json.dumps(row.before, ensure_ascii=False, default=str) if row.before is not None else "", json.dumps(row.after, ensure_ascii=False, default=str) if row.after is not None else ""])
    content = make_workbook("Auditoría", headers, data, date_columns={1})
    response = HttpResponse(content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="auditoria-mantenimiento.xlsx"'
    return response
