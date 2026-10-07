"""Deterministic, repeatable preventive work-order planning."""

from datetime import date

from django.db import transaction

from .models import PreventivePlan
from .views import make_occurrence, task_projection


TERMINAL_ORDER_STATES = {"Completada", "Cancelada"}
APPLICABLE_STATES = {"Interna", "Externa"}


def plan_preventive_window(start, end, *, actor=None, apply=False, allow_overlap=False):
    """Project or persist due tasks; one task/date maps to one canonical OT.

    Fixed task anchor dates stay unchanged. By default a prior unfinished OT
    prevents a new OT for the same task until staff resolve it.
    """
    if apply and actor is None:
        raise ValueError("An actor is required to create work orders")
    result = {"due": 0, "ready": 0, "created": 0, "existing": 0, "blocked_open": 0, "skipped_unvalidated": 0, "skipped_area": 0, "plans": 0}
    plan_ids = list(PreventivePlan.objects.filter(asset__administrative_status="Activo").exclude(status__in=("Inactivo", "Cancelado")).order_by("pk").values_list("pk", flat=True))

    def process(plan):
        if actor and actor.area_permissions and plan.asset.area not in actor.area_permissions:
            result["skipped_area"] += 1
            return
        result["plans"] += 1
        for task in plan.tasks.order_by("pk"):
            projected = task_projection(task, start, end)
            if task.applicability_status not in APPLICABLE_STATES:
                result["skipped_unvalidated"] += len(projected)
                continue
            existing = {occurrence.occurrence_index: occurrence for occurrence in task.occurrences.select_related("work_order")}
            open_dates = [occurrence.base_date for occurrence in existing.values() if occurrence.work_order.status not in TERMINAL_ORDER_STATES]
            for item in projected:
                result["due"] += 1
                index = item["occurrence_index"]
                due = date.fromisoformat(item["base_date"])
                if index in existing:
                    result["existing"] += 1
                    continue
                if not allow_overlap and any(open_date < due for open_date in open_dates):
                    result["blocked_open"] += 1
                    continue
                result["ready"] += 1
                if apply:
                    occurrence, replayed = make_occurrence(plan, task, index, actor, source="planner")
                    if replayed:
                        result["existing"] += 1
                        result["ready"] -= 1
                    else:
                        result["created"] += 1
                        open_dates.append(occurrence.base_date)
                else:
                    open_dates.append(due)

    for plan_id in plan_ids:
        if apply:
            with transaction.atomic():
                plan = PreventivePlan.objects.select_for_update().select_related("asset").get(pk=plan_id)
                process(plan)
        else:
            process(PreventivePlan.objects.select_related("asset").get(pk=plan_id))
    return result
