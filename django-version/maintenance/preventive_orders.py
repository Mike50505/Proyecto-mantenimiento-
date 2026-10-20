"""Schedule preventive work as ordinary future work orders."""
import hashlib
import json
from datetime import timedelta

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import Asset, PreventivePlan, PreventiveTask, TimeEntry, User, WorkOrder
from .views import (ApiError, actions, audit, effective_areas, iso, make_occurrence, modules,
                    order_queryset, payload, require, save_revision, scheduled_datetime,
                    task_projection)


HORIZON_DAYS = 90


def record_id(value, label):
    try: number = int(value)
    except (TypeError, ValueError): raise ApiError(f"Selecciona {label}")
    if number < 1: raise ApiError(f"Selecciona {label}")
    return number


def may_generate(plan):
    actor = plan.schedule_user
    if not actor or not actor.is_active or actor.deleted_at or actor.must_change_password:
        return False
    allowed = set(actions(actor))
    if not {"preventives.edit", "orders.create"}.issubset(allowed): return False
    if actor.custom_permissions and not {"preventives", "orders"}.issubset(modules(actor)): return False
    if plan.responsible_id and "orders.assign" not in allowed: return False
    if plan.responsible_id and (not plan.responsible.is_active or plan.responsible.deleted_at): return False
    return not effective_areas(actor) or plan.asset.area in effective_areas(actor)


@transaction.atomic
def extend_schedule(plan, *, today=None):
    if plan.schedule_user_id:
        User.all_objects.select_for_update(no_key=True).get(pk=plan.schedule_user_id)
    Asset.all_objects.select_for_update(no_key=True).get(pk=plan.asset_id)
    plan = PreventivePlan.objects.select_for_update(of=("self",)).select_related("asset", "schedule_user", "responsible").get(pk=plan.pk)
    if not plan.simple_schedule or plan.status != "Programado" or plan.asset.deleted_at or plan.asset.administrative_status != "Activo" or not may_generate(plan):
        return []
    task = plan.tasks.get()
    today = today or timezone.localdate()
    projected = task_projection(task, today, today + timedelta(days=HORIZON_DAYS))
    created = []
    for item in projected:
        occurrence, replayed = make_occurrence(plan, task, item["occurrence_index"], plan.schedule_user, source="scheduled")
        if not replayed: created.append(occurrence.work_order_id)
    return created


def refresh_schedules(*, today=None):
    created = 0
    for plan in PreventivePlan.objects.filter(simple_schedule=True, schedule_repeat=True, status="Programado", asset__deleted_at__isnull=True, asset__administrative_status="Activo").iterator():
        created += len(extend_schedule(plan, today=today))
    return created


def schedule_result(plan, *, replayed=False, created=None):
    first = plan.occurrences.select_related("work_order").order_by("occurrence_index").first()
    return {"plan_id":plan.pk, "work_order_id":first.work_order_id if first else None,
            "folio":first.work_order.folio if first else None, "replayed":replayed, "created":len(created or [])}


@transaction.atomic
def schedule_api(request):
    actor = require(request, "preventives.edit")
    require(request, "orders.create")
    if "orders" not in modules(actor): raise ApiError("Necesitas acceso a Órdenes para programar una OT", 403)
    if request.method != "POST": raise ApiError("Método no permitido", 405)
    data = payload(request)
    if not isinstance(data, dict): raise ApiError("Datos de programación inválidos")
    key = request.headers.get("Idempotency-Key")
    if key and len(key) > 120: raise ApiError("Clave de solicitud inválida")
    # Serialize retries for the same account, including concurrent requests.
    actor = User.objects.select_for_update().get(pk=actor.pk)
    digest = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if key:
        existing = PreventivePlan.objects.filter(schedule_user=actor, schedule_key=key).first()
        if existing:
            if existing.schedule_hash != digest: raise ApiError("La solicitud ya fue utilizada con otros datos", 409)
            return JsonResponse(schedule_result(existing, replayed=True))
    asset = get_object_or_404(Asset.objects.select_for_update(), pk=record_id(data.get("asset_id"), "un activo"))
    require(request, "orders.create", asset.area)
    require(request, "preventives.edit", asset.area)
    if asset.administrative_status != "Activo": raise ApiError("Selecciona un activo disponible para programar")
    title = data.get("title")
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 250:
        raise ApiError("Describe el trabajo (hasta 250 caracteres)")
    if not isinstance(data.get("scheduled_at"), str): raise ApiError("Selecciona una fecha y hora futura")
    scheduled = scheduled_datetime(data["scheduled_at"])
    if scheduled <= timezone.now(): raise ApiError("Selecciona una fecha y hora futura")
    local = timezone.localtime(scheduled)
    repeat = data.get("repeat", "none")
    if repeat not in ("none", "days", "weeks", "months", "years"): raise ApiError("Repetición inválida")
    try: interval = int(data.get("interval", 1))
    except (TypeError, ValueError): raise ApiError("Intervalo inválido")
    if interval < 1 or interval > 100: raise ApiError("El intervalo debe estar entre 1 y 100")
    unit = "months" if repeat in ("months", "years") else "days"
    amount = interval * (7 if repeat == "weeks" else 12 if repeat == "years" else 1)
    from .views import parse_day
    end = parse_day(data["repeat_until"]) if repeat != "none" and data.get("repeat_until") else None
    if end and end < local.date(): raise ApiError("La fecha final debe ser posterior o igual a la primera OT")
    responsible = None
    if data.get("technician_id"):
        require(request, "orders.assign", asset.area)
        responsible = get_object_or_404(User.objects.select_for_update(), pk=record_id(data["technician_id"], "un responsable"), is_active=True, role__in=["Técnico", "Jefatura", "Jefe de mantenimiento"])
    if data.get("plan_id"):
        plan = get_object_or_404(PreventivePlan.objects.select_for_update(), pk=record_id(data["plan_id"], "una programación"))
        require(request, "preventives.edit", plan.asset.area)
        try: version = int(data.get("version", -1))
        except (TypeError, ValueError): raise ApiError("Versión inválida")
        if version != plan.version or plan.simple_schedule or plan.tasks.exists() or plan.occurrences.exists() or plan.work_order_id:
            raise ApiError("La programación anterior cambió o ya tiene tareas y OT", 409)
        plan.version += 1
    else:
        plan = PreventivePlan()
    labels = {"days":"día(s)", "weeks":"semana(s)", "months":"mes(es)", "years":"año(s)"}
    plan.asset, plan.title, plan.next_date = asset, title.strip(), local.date()
    plan.frequency = "Una sola vez" if repeat == "none" else f"Cada {interval} {labels[repeat]}"
    plan.responsible, plan.status = responsible, "Programado"
    plan.simple_schedule, plan.schedule_repeat = True, repeat != "none"
    plan.schedule_time, plan.schedule_end, plan.schedule_user = local.time().replace(tzinfo=None), end, actor
    plan.schedule_key, plan.schedule_hash = key, digest
    plan.save()
    task = PreventiveTask.objects.create(plan=plan, title=plan.title, interval_unit=unit, interval_value=amount,
                                        anchor_date=local.date(), created_by=actor, applicability_status="Interna",
                                        applicability_reason="Programada como OT preventiva", validated_by=actor, validated_at=timezone.now())
    save_revision(plan, actor, "ot-scheduled")
    first, _ = make_occurrence(plan, task, 0, actor, source="scheduled")
    created = [first.work_order_id, *extend_schedule(plan)]
    audit(actor, "preventive_plan", plan.pk, "ot-scheduled", after={"title":plan.title, "scheduled_at":iso(scheduled), "frequency":plan.frequency, "repeat_until":iso(end), "work_order_ids":created})
    return JsonResponse(schedule_result(plan, created=created), status=201)


def nearest_scheduled_order_ids(user):
    """One earliest unresolved OT per simple schedule, across all calendar periods."""
    orders = order_queryset(user).filter(preventive_occurrences__plan__simple_schedule=True).exclude(status__in=["Completada", "Cancelada"]).order_by("scheduled_at", "pk")
    selected = {}
    for order_id, plan_id in orders.values_list("pk", "preventive_occurrences__plan_id"):
        selected.setdefault(plan_id, order_id)
    return set(selected.values())


def scheduled_orders_api(request):
    user = require(request, "preventives.read")
    if request.method != "GET": raise ApiError("Método no permitido", 405)
    orders = order_queryset(user).filter(classification="Mantenimiento Preventivo").prefetch_related("preventive_occurrences__plan").order_by("scheduled_at", "pk")
    rows = []
    for order in orders:
        occurrence = next(iter(order.preventive_occurrences.all()), None)
        plan = occurrence.plan if occurrence else None
        if order.status in ("Completada", "Cancelada"): continue
        rows.append({"id":order.pk, "folio":order.folio, "asset_name":order.asset.name if order.asset_id else order.location,
                     "title":order.reported_failure, "scheduled_at":iso(order.scheduled_at), "status":order.status, "version":order.version,
                     "technician_name":order.technician.first_name if order.technician_id else None, "plan_id":plan.pk if plan else None,
                     "frequency":plan.frequency if plan else "Una sola vez", "repeating":bool(plan and plan.simple_schedule and plan.schedule_repeat),
                     "repetition_active":bool(plan and plan.status == "Programado"),
                     "recurrent_plan_id":plan.pk if plan and plan.simple_schedule and plan.schedule_repeat else None})
    legacy = PreventivePlan.objects.filter(simple_schedule=False, asset__deleted_at__isnull=True).exclude(status="Borrado").select_related("asset", "responsible").prefetch_related("tasks", "occurrences")
    if effective_areas(user): legacy = legacy.filter(asset__area__in=effective_areas(user))
    series = PreventivePlan.objects.filter(simple_schedule=True, schedule_repeat=True, status="Programado", asset__deleted_at__isnull=True).select_related("asset")
    if effective_areas(user): series = series.filter(asset__area__in=effective_areas(user))
    if user.role == "Solicitante": series = series.filter(schedule_user=user)
    return JsonResponse({"orders":rows, "active_series":[{"plan_id":p.pk,"title":p.title,"asset_name":p.asset.name,"frequency":p.frequency} for p in series], "legacy_plans":[{"id":p.pk, "title":p.title, "asset_id":p.asset_id, "asset_name":p.asset.name, "next_date":iso(p.next_date), "frequency":p.frequency,
                           "responsible_id":p.responsible_id, "version":p.version, "can_convert":not p.tasks.exists() and not p.occurrences.exists() and not p.work_order_id} for p in legacy]})


@transaction.atomic
def stop_schedule_api(request, pk):
    actor = require(request, "preventives.edit")
    if request.method != "POST": raise ApiError("Método no permitido", 405)
    plan = get_object_or_404(PreventivePlan.objects.exclude(status="Borrado").select_for_update(), pk=pk, simple_schedule=True)
    require(request, "preventives.edit", plan.asset.area)
    data = payload(request)
    if not isinstance(data, dict) or not isinstance(data.get("reason"), str) or not data["reason"].strip() or len(data["reason"]) > 2000:
        raise ApiError("Indica el motivo para detener la repetición")
    if plan.status != "Inactivo":
        plan.status = "Inactivo"
        plan.version += 1
        plan.save(update_fields=["status", "version"])
        save_revision(plan, actor, "repetition-stopped", data["reason"].strip())
        audit(actor, "preventive_plan", plan.pk, "repetition-stopped", before={"status":"Programado"}, after={"status":"Inactivo"}, reason=data["reason"].strip())
    return JsonResponse({"ok":True})


def series_confirmation(plan, orders, scope):
    value = [plan.pk, plan.version, plan.status, scope, [(order.pk, order.version) for order in orders]]
    return hashlib.sha256(json.dumps(value).encode()).hexdigest()


@transaction.atomic
def delete_series_api(request, pk):
    actor = require(request, "orders.delete")
    require(request, "preventives.edit")
    if "orders" not in modules(actor): raise ApiError("Necesitas acceso a Órdenes", 403)
    if request.method not in ("GET", "POST"): raise ApiError("Método no permitido", 405)
    plans = PreventivePlan.objects.select_for_update() if request.method == "POST" else PreventivePlan.objects.all()
    plan = get_object_or_404(plans, pk=pk, simple_schedule=True, schedule_repeat=True)
    require(request, "orders.delete", plan.asset.area)
    require(request, "preventives.edit", plan.asset.area)
    data = request.GET if request.method == "GET" else payload(request)
    if not isinstance(data, (dict, type(request.GET))): raise ApiError("Datos de borrado inválidos")
    scope = data.get("scope", "all")
    if scope not in ("all", "pending"): raise ApiError("Selecciona qué órdenes quieres borrar")
    targets = WorkOrder.objects.filter(preventive_occurrences__plan=plan)
    if scope == "pending": targets = targets.exclude(status__in=["Completada", "Cancelada"])
    if request.method == "POST": targets = targets.select_for_update(of=("self",))
    orders = list(targets.order_by("pk"))
    if actor.role == "Solicitante" and any(order.requester_id != actor.pk for order in orders):
        raise ApiError("Solo puedes borrar tus propias solicitudes", 403)
    confirmation = series_confirmation(plan, orders, scope)
    if request.method == "GET":
        return JsonResponse({"plan_id":plan.pk, "title":plan.title, "count":len(orders), "scope":scope,
                             "completed":sum(order.status in ("Completada", "Cancelada") for order in orders),
                             "confirmation":confirmation})
    reason = data.get("reason")
    if not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 2000:
        raise ApiError("Indica el motivo del borrado de la repetición")
    if data.get("confirmation") != confirmation:
        raise ApiError("Las órdenes cambiaron. Cierra y vuelve a abrir la confirmación de borrado", 409)
    if TimeEntry.objects.filter(work_order_id__in=[order.pk for order in orders], finished_at__isnull=True).exists():
        raise ApiError("Termina las sesiones abiertas de esta repetición antes de borrarla", 409)
    from .views import delete_record_api, plan_snapshot
    before = plan_snapshot(plan)
    for order in orders:
        delete_record_api(request, "orders", order.pk, deletion_data={"reason":reason.strip(), "version":order.version})
    if plan.status != "Borrado" or orders:
        plan.status = "Borrado"
        plan.version += 1
        plan.save(update_fields=["status", "version"])
        save_revision(plan, actor, "series-deleted", reason.strip())
        audit(actor, "preventive_plan", plan.pk, "deleted", before=before,
              after={"deleted":True,"label":plan.title,"scope":scope,"work_order_ids":[order.pk for order in orders],"count":len(orders)}, reason=reason.strip())
    return JsonResponse({"ok":True,"deleted":len(orders),"repetition_stopped":True})
