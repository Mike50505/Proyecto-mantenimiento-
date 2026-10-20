import json

from django.test import TestCase

from .models import Asset, PreventivePlan, PreventiveTask, PreventiveTemplate, User, WorkOrder


class PreventiveScheduleVisibilityTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="schedule-manager", employee_number="SCH-M", role="Jefatura", area_permissions=["Corte"])
        self.asset = Asset.objects.create(code="SCH-ASSET", name="Cortadora", area="Corte", asset_type="Maquinaria")
        self.client.force_login(self.manager)

    def create_plan(self, **fields):
        response = self.client.post("/api/preventives", json.dumps({"asset_id":self.asset.pk, "title":"Revisar equipo", "frequency":"1 mes", "next_date":"2026-10-15", **fields}), content_type="application/json")
        self.assertEqual(response.status_code, 201, response.content)
        return PreventivePlan.objects.get(pk=response.json()["id"])

    def calendar(self, start="2026-10-01", end="2026-10-31"):
        response = self.client.get("/api/preventive-calendar", {"from":start, "to":end, "as_of":"2026-10-01"})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_new_plan_appears_on_its_scheduled_date_without_tasks_or_orders(self):
        plan = self.create_plan()
        result = self.calendar()
        self.assertEqual(len(result["occurrences"]), 1)
        entry = result["occurrences"][0]
        self.assertEqual(entry["plan_id"], plan.pk)
        self.assertEqual(entry["base_date"], "2026-10-15")
        self.assertEqual(entry["task_title"], plan.title)
        self.assertEqual(entry["asset_name"], self.asset.name)
        self.assertEqual(entry["status"], "configuration_pending")
        self.assertTrue(entry["is_plan_schedule"])
        self.assertIsNone(entry["task_id"])
        self.assertIsNone(entry["work_order_id"])
        self.assertEqual(PreventiveTask.objects.count(), 0)
        self.assertEqual(WorkOrder.objects.count(), 0)
        self.assertTrue(any(row["id"] == plan.pk for row in self.client.get("/api/preventives").json()))

    def test_plan_markers_do_not_count_as_task_compliance_or_recur(self):
        self.create_plan()
        result = self.calendar(end="2026-12-31")
        self.assertEqual(len(result["occurrences"]), 1)
        self.assertTrue(all(count == 0 for count in result["counts"].values()))
        self.assertEqual(len(result["coverage"]["incomplete_plans"]), 1)

    def test_plan_is_only_shown_in_the_scheduled_period(self):
        self.create_plan(next_date="2026-11-05")
        self.assertEqual(self.calendar()["occurrences"], [])
        self.assertEqual(self.calendar("2026-11-01", "2026-11-30")["occurrences"][0]["base_date"], "2026-11-05")

    def test_pending_task_plan_is_visible_until_review_then_uses_task_dates(self):
        plan = self.create_plan()
        added = self.client.post(f"/api/preventives/{plan.pk}/tasks", json.dumps({"title":"Lubricar", "interval_unit":"months", "interval_value":1, "anchor_date":"2026-10-20", "version":1}), content_type="application/json")
        self.assertEqual(added.status_code, 201)
        self.assertTrue(self.calendar()["occurrences"][0]["is_plan_schedule"])
        reviewed = self.client.patch(f"/api/preventives/{plan.pk}/tasks/{added.json()['id']}/applicability", json.dumps({"status":"Interna", "reason":"Aplica a este equipo", "version":2}), content_type="application/json")
        self.assertEqual(reviewed.status_code, 200)
        rows = self.calendar()["occurrences"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["base_date"], "2026-10-20")
        self.assertEqual(rows[0]["task_title"], "Lubricar")
        self.assertFalse(rows[0].get("is_plan_schedule", False))

    def test_not_applicable_tasks_do_not_create_plan_markers(self):
        plan = self.create_plan()
        PreventiveTask.objects.create(plan=plan, title="No aplica", interval_unit="months", interval_value=1,
                                      anchor_date=plan.next_date, created_by=self.manager, applicability_status="No aplica")
        self.assertEqual(self.calendar()["occurrences"], [])

    def test_template_plan_is_visible_while_its_tasks_await_review(self):
        template = PreventiveTemplate.objects.create(code="SCH-TEMPLATE", family="Maquinaria", title="Inspección", created_by=self.manager,
                                                    tasks=[{"title":"Inspeccionar", "interval_unit":"months", "interval_value":1, "anchor_date":"2026-10-15"}])
        plan = self.create_plan()
        response = self.client.post(f"/api/preventives/{plan.pk}/apply-template", json.dumps({"template_id":template.pk,"version":1}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.calendar()["occurrences"][0]["is_plan_schedule"])
        self.assertEqual(WorkOrder.objects.count(), 0)

    def test_rescheduling_an_empty_plan_moves_its_calendar_entry(self):
        plan = self.create_plan()
        response = self.client.patch(f"/api/preventives/{plan.pk}", json.dumps({"next_date":"2026-11-10", "version":1}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.calendar()["occurrences"], [])
        self.assertEqual(self.calendar("2026-11-01", "2026-11-30")["occurrences"][0]["base_date"], "2026-11-10")

    def test_plan_markers_respect_area_permissions(self):
        hidden = Asset.objects.create(code="SCH-HIDDEN", name="Prensa", area="Prensas")
        PreventivePlan.objects.create(asset=hidden, title="Fuera de área", frequency="1 mes", next_date="2026-10-15")
        visible = self.create_plan()
        self.assertEqual([row["plan_id"] for row in self.calendar()["occurrences"]], [visible.pk])
