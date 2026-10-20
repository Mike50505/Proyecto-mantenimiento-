import json
from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from .models import Asset, AuditLog, FolioSequence, PreventivePlan, User, WorkOrder
from .preventive_orders import extend_schedule, refresh_schedules
from .views import task_projection


class SimplePreventiveOrderTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="simple-scheduler", employee_number="SPO-A", role="Administrador")
        self.tech = User.objects.create_user(username="simple-technician", employee_number="SPO-T", role="Técnico")
        self.asset = Asset.objects.create(code="SPO-ASSET", name="Prensa", area="Corte")
        self.first_date = timezone.localdate() + timedelta(days=1)
        self.client.force_login(self.admin)

    def schedule(self, key=None, **data):
        body = {"title":"Lubricar prensa", "asset_id":self.asset.pk, "scheduled_at":f"{self.first_date}T09:30", "repeat":"none", **data}
        headers = {"HTTP_IDEMPOTENCY_KEY":key} if key else {}
        return self.client.post("/api/preventive-orders/schedule", json.dumps(body), content_type="application/json", **headers)

    def plan(self, response):
        self.assertEqual(response.status_code, 201, response.content)
        return PreventivePlan.objects.get(pk=response.json()["plan_id"])

    def test_single_preventive_is_a_real_scheduled_order(self):
        response = self.schedule(technician_id=self.tech.pk)
        plan = self.plan(response)
        order = WorkOrder.objects.get(pk=response.json()["work_order_id"])
        self.assertEqual(order.classification, "Mantenimiento Preventivo")
        self.assertEqual(order.status, "Programada")
        self.assertEqual(order.technician, self.tech)
        self.assertEqual(timezone.localtime(order.scheduled_at).strftime("%Y-%m-%dT%H:%M"), f"{self.first_date}T09:30")
        self.assertEqual(plan.tasks.get().applicability_status, "Interna")
        self.assertEqual(task_projection(plan.tasks.get(), self.first_date, self.first_date+timedelta(days=365)),
                         [{"task_id":plan.tasks.get().pk,"occurrence_index":0,"base_date":self.first_date.isoformat()}])
        self.assertEqual(self.client.get("/api/orders").json()[0]["id"], order.pk)
        self.assertEqual(self.client.get("/api/preventive-orders").json()["orders"][0]["id"], order.pk)
        self.assertTrue(AuditLog.objects.filter(entity_type="preventive_plan", action="ot-scheduled").exists())

    def test_daily_repetition_creates_future_orders_and_refresh_is_idempotent(self):
        plan = self.plan(self.schedule(repeat="days", interval=1))
        before = WorkOrder.objects.count()
        self.assertGreater(before, 1)
        self.assertEqual(refresh_schedules(), 0)
        self.assertEqual(WorkOrder.objects.count(), before)
        self.assertGreater(refresh_schedules(today=self.first_date+timedelta(days=30)), 0)
        self.assertEqual(plan.occurrences.count(), len(set(plan.occurrences.values_list("base_date", flat=True))))
        self.assertTrue(all(order.status == "Programada" for order in WorkOrder.objects.all()))

    def test_repeat_end_limits_generated_dates(self):
        end = self.first_date + timedelta(days=7)
        plan = self.plan(self.schedule(repeat="days", interval=2, repeat_until=end.isoformat()))
        self.assertEqual(list(plan.occurrences.order_by("base_date").values_list("base_date", flat=True)),
                         [self.first_date+timedelta(days=offset) for offset in (0,2,4,6)])
        self.assertEqual(refresh_schedules(today=end+timedelta(days=1)), 0)

    def test_weekly_and_yearly_intervals_are_stored_correctly(self):
        for repeat, unit, value in [("weeks","days",14),("years","months",24)]:
            plan = self.plan(self.schedule(repeat=repeat, interval=2))
            task = plan.tasks.get()
            self.assertEqual((task.interval_unit, task.interval_value), (unit, value))

    def test_monthly_repetition_keeps_anchor_and_time_at_month_end(self):
        year = timezone.localdate().year + 1
        plan = self.plan(self.schedule(scheduled_at=f"{year}-01-31T15:45", repeat="months", interval=1))
        extend_schedule(plan, today=date(year,1,1))
        dates = list(plan.occurrences.order_by("base_date").values_list("base_date", flat=True))
        import calendar
        self.assertEqual(dates[:3], [date(year,1,31), date(year,2,calendar.monthrange(year,2)[1]), date(year,3,31)])
        self.assertTrue(all(timezone.localtime(order.scheduled_at).strftime("%H:%M") == "15:45" for order in WorkOrder.objects.all()))

    def test_repeated_request_does_not_duplicate_orders_and_changed_payload_conflicts(self):
        first = self.schedule(key="same-schedule", repeat="weeks")
        self.assertEqual(first.status_code, 201)
        count = WorkOrder.objects.count()
        repeated = self.schedule(key="same-schedule", repeat="weeks")
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.json()["work_order_id"], first.json()["work_order_id"])
        self.assertEqual(WorkOrder.objects.count(), count)
        self.assertEqual(self.schedule(key="same-schedule", title="Otro trabajo").status_code, 409)

    def test_stop_repetition_preserves_existing_orders_and_audit(self):
        plan = self.plan(self.schedule(repeat="weeks"))
        count = WorkOrder.objects.count()
        response = self.client.post(f"/api/preventive-orders/{plan.pk}/stop", '{"reason":"Fin de programa"}', content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(refresh_schedules(today=self.first_date+timedelta(days=80)), 0)
        self.assertEqual(WorkOrder.objects.count(), count)
        self.assertTrue(AuditLog.objects.filter(entity_type="preventive_plan", action="repetition-stopped").exists())

    def test_calendar_contains_actual_order_ids_only_for_simple_schedules(self):
        year = timezone.localdate().year+1
        response = self.schedule(scheduled_at=f"{year}-07-01T09:00", repeat="months")
        self.plan(response)
        calendar = self.client.get("/api/preventive-calendar", {"from":f"{year}-07-01","to":f"{year}-12-31"}).json()
        self.assertEqual(len(calendar["occurrences"]), 1)
        self.assertEqual(calendar["occurrences"][0]["work_order_id"], response.json()["work_order_id"])

    def test_can_convert_an_empty_legacy_plan_without_duplicate_plan(self):
        legacy = PreventivePlan.objects.create(asset=self.asset, title="Anterior", frequency="Mensual", next_date=self.first_date)
        response = self.schedule(plan_id=legacy.pk, version=1)
        plan = self.plan(response)
        self.assertEqual(plan.pk, legacy.pk)
        self.assertEqual(PreventivePlan.objects.count(), 1)
        self.assertEqual(WorkOrder.objects.count(), 1)

    def test_conversion_rejects_stale_version(self):
        legacy = PreventivePlan.objects.create(asset=self.asset, title="Anterior", frequency="Mensual", next_date=self.first_date)
        self.assertEqual(self.schedule(plan_id=legacy.pk, version=99).status_code, 409)
        self.assertEqual(WorkOrder.objects.count(), 0)

    def test_schedule_requires_actions_and_area_permissions(self):
        self.tech.custom_permissions = True
        self.tech.module_permissions = ["preventives","orders"]
        self.tech.action_permissions = ["preventives.edit"]
        self.tech.save()
        self.client.force_login(self.tech)
        self.assertEqual(self.schedule().status_code, 403)
        self.tech.action_permissions = ["preventives.edit","orders.create"]
        self.tech.area_permissions = ["Otra"]
        self.tech.save()
        self.assertEqual(self.schedule().status_code, 403)
        self.tech.area_permissions = ["Corte"]
        self.tech.save()
        self.assertEqual(self.schedule(technician_id=self.tech.pk).status_code, 403)
        self.assertEqual(self.schedule().status_code, 201)

    def test_scheduler_stops_if_permissions_are_revoked(self):
        self.tech.custom_permissions = True
        self.tech.module_permissions = ["preventives","orders"]
        self.tech.action_permissions = ["preventives.edit","orders.create"]
        self.tech.save()
        self.client.force_login(self.tech)
        plan = self.plan(self.schedule(repeat="weeks"))
        count = WorkOrder.objects.count()
        self.tech.action_permissions = []
        self.tech.save()
        self.assertEqual(refresh_schedules(today=self.first_date+timedelta(days=90)), 0)
        self.assertEqual(WorkOrder.objects.count(), count)

    def test_invalid_schedule_does_not_create_records(self):
        for fields in [{"asset_id":"bad"}, {"scheduled_at":"bad"}, {"scheduled_at":None}, {"title":""},
                       {"repeat":"invalid"}, {"interval":0}, {"interval":"bad"},
                       {"repeat":"months", "repeat_until":"2020-01-01"}, {"scheduled_at":"2020-01-01T09:00"}]:
            with self.subTest(fields=fields): self.assertEqual(self.schedule(**fields).status_code, 400)
        self.assertEqual(PreventivePlan.objects.count(), 0)
        self.assertEqual(WorkOrder.objects.count(), 0)

    def test_failed_generation_rolls_back_plan_and_folios(self):
        with patch("maintenance.preventive_orders.extend_schedule", side_effect=RuntimeError("Unavailable")):
            with self.assertRaises(RuntimeError): self.schedule(repeat="weeks")
        self.assertEqual(PreventivePlan.objects.count(), 0)
        self.assertEqual(WorkOrder.objects.count(), 0)
        self.assertEqual(FolioSequence.objects.count(), 0)

    def test_order_inbox_shows_nearest_but_calendar_keeps_all_repetitions(self):
        plan = self.plan(self.schedule(repeat="days"))
        self.assertGreater(plan.occurrences.count(), 1)
        expected = plan.occurrences.order_by("base_date").first().work_order_id
        rows = self.client.get("/api/orders?next_preventive=1&status=Programada").json()
        self.assertEqual([row["id"] for row in rows], [expected])
        calendar = self.client.get("/api/preventive-calendar", {"from":self.first_date.isoformat(), "to":(self.first_date+timedelta(days=89)).isoformat()}).json()
        self.assertEqual({row["work_order_id"] for row in calendar["occurrences"]}, set(plan.occurrences.values_list("work_order_id", flat=True)))
        self.assertEqual(sum(calendar["counts"][key] for key in "PTDV"), plan.occurrences.count())

    def test_next_order_appears_after_previous_is_completed_or_cancelled(self):
        plan = self.plan(self.schedule(repeat="weeks"))
        occurrences = list(plan.occurrences.order_by("base_date"))
        for index, status in enumerate(["Completada", "Cancelada"]):
            order = WorkOrder.objects.get(pk=occurrences[index].work_order_id)
            order.status = status
            order.save(update_fields=["status"])
            visible = self.client.get("/api/orders?next_preventive=1&status=Programada").json()
            self.assertEqual([row["id"] for row in visible], [occurrences[index+1].work_order_id])

    def test_each_series_and_single_order_remains_visible(self):
        first = self.plan(self.schedule(repeat="weeks"))
        second = self.plan(self.schedule(title="Revisar", repeat="months"))
        single = self.plan(self.schedule(title="Una vez"))
        rows = self.client.get("/api/orders?next_preventive=1&status=Programada").json()
        self.assertEqual({row["id"] for row in rows}, {plan.occurrences.order_by("base_date").first().work_order_id for plan in [first, second, single]})
        self.assertEqual(len(rows), 3)

    def test_calendar_keeps_future_weeks_visible(self):
        self.plan(self.schedule(repeat="days"))
        later = self.first_date+timedelta(days=20)
        result = self.client.get("/api/preventive-calendar", {"from":later.isoformat(), "to":(later+timedelta(days=20)).isoformat()}).json()
        self.assertGreater(len(result["occurrences"]), 1)

    def test_rescheduling_changes_which_pending_order_is_nearest(self):
        plan = self.plan(self.schedule(repeat="weeks"))
        occurrences = list(plan.occurrences.order_by("base_date"))
        first = WorkOrder.objects.get(pk=occurrences[0].work_order_id)
        first.scheduled_at += timedelta(days=20)
        first.save(update_fields=["scheduled_at"])
        rows = self.client.get("/api/orders?next_preventive=1&status=Programada").json()
        self.assertEqual([row["id"] for row in rows], [occurrences[1].work_order_id])

    def test_repetition_can_still_be_stopped_when_no_near_order_is_pending(self):
        plan = self.plan(self.schedule(repeat="years"))
        WorkOrder.objects.update(status="Completada")
        result = self.client.get("/api/preventive-orders").json()
        self.assertEqual(result["orders"], [])
        self.assertEqual([series["plan_id"] for series in result["active_series"]], [plan.pk])

    def test_inbox_filter_preserves_correctives_in_progress_work_and_history(self):
        plan = self.plan(self.schedule(repeat="weeks"))
        occurrences = list(plan.occurrences.order_by("base_date"))
        working = WorkOrder.objects.get(pk=occurrences[1].work_order_id)
        working.status = "En proceso"
        working.save(update_fields=["status"])
        completed = WorkOrder.objects.get(pk=occurrences[2].work_order_id)
        completed.status = "Completada"
        completed.save(update_fields=["status"])
        corrective = WorkOrder.objects.create(folio="CORRECTIVE", requested_at=timezone.now(), requester=self.admin,
                                               priority="Media", classification="Correctivo", reported_failure="Reparar", asset=self.asset)
        visible = self.client.get("/api/orders?next_preventive=1").json()
        self.assertEqual({row["id"] for row in visible}, {occurrences[0].work_order_id, working.pk, completed.pk, corrective.pk})

    def test_inbox_exports_match_nearest_filter_without_hiding_calendar_orders(self):
        import csv
        import io
        import zipfile
        plan = self.plan(self.schedule(repeat="weeks"))
        orders = list(WorkOrder.objects.order_by("scheduled_at"))
        exported = self.client.get("/api/orders/export.csv?next_preventive=1")
        rows = list(csv.DictReader(io.StringIO(exported.content.decode("utf-8-sig"))))
        self.assertEqual([row["Folio"] for row in rows], [orders[0].folio])
        xlsx = self.client.get("/api/orders/export.xlsx?next_preventive=1")
        with zipfile.ZipFile(io.BytesIO(xlsx.content)) as archive:
            sheet = archive.read("xl/worksheets/sheet1.xml").decode()
        self.assertIn(orders[0].folio, sheet)
        self.assertNotIn(orders[1].folio, sheet)
        self.assertEqual(len(self.client.get("/api/preventive-orders").json()["orders"]), plan.occurrences.count())
