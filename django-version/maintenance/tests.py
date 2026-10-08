import json
from datetime import date
from io import StringIO
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.db import close_old_connections, connections
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, TransactionTestCase
from django.utils import timezone
from .models import Asset, AssetCodeEquivalence, AuditLog, CatalogEntry, DowntimeEvent, ImportBatch, ImportRow, InventoryItem, InventoryMovement, MaintenanceMaterial, MeterReading, PreventiveOccurrence, PreventivePlan, PreventiveTask, User, WorkOrder


class PreventivePlannerTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="planner-manager", password="Password123!", employee_number="PLN-M", first_name="Jefa", role="Jefatura")
        asset = Asset.objects.create(code="PLN-01", name="Cortadora", area="Corte")
        self.plan = PreventivePlan.objects.create(asset=asset, title="Revisión", frequency="Por tarea", next_date=date(2026, 1, 1))
        self.monthly = PreventiveTask.objects.create(plan=self.plan, title="Mensual", interval_unit="months", interval_value=1, anchor_date=date(2026, 1, 1), created_by=self.manager, applicability_status="Interna", applicability_reason="Aplica", validated_by=self.manager, validated_at=timezone.now())
        self.quarterly = PreventiveTask.objects.create(plan=self.plan, title="Trimestral", interval_unit="months", interval_value=3, anchor_date=date(2026, 1, 1), created_by=self.manager, applicability_status="Interna", applicability_reason="Aplica", validated_by=self.manager, validated_at=timezone.now())

    def run_planner(self, as_of, *, apply=False, ahead=0, behind=0):
        args = ["plan_preventives", "--as-of", as_of, "--lookback-days", str(behind), "--lookahead-days", str(ahead)]
        if apply: args += ["--apply", "--user", self.manager.username]
        output = StringIO()
        call_command(*args, stdout=output)
        return output.getvalue()

    def test_dry_run_repeat_and_independent_task_dates(self):
        preview = self.run_planner("2026-01-01", ahead=90)
        self.assertIn("'ready': 2", preview)
        self.assertEqual(WorkOrder.objects.count(), 0)
        self.run_planner("2026-01-01", apply=True, ahead=90)
        self.assertEqual(WorkOrder.objects.count(), 2)
        self.run_planner("2026-01-01", apply=True, ahead=90)
        self.assertEqual(WorkOrder.objects.count(), 2)
        monthly_first = PreventiveOccurrence.objects.get(task=self.monthly, occurrence_index=0)
        quarterly_first = PreventiveOccurrence.objects.get(task=self.quarterly, occurrence_index=0)
        monthly_first.work_order.status = "Completada"
        monthly_first.work_order.save(update_fields=["status"])
        self.run_planner("2026-02-01", apply=True)
        self.assertTrue(PreventiveOccurrence.objects.filter(task=self.monthly, occurrence_index=1).exists())
        self.assertFalse(PreventiveOccurrence.objects.filter(task=self.quarterly, occurrence_index=1).exists())
        quarterly_first.work_order.status = "Completada"
        quarterly_first.work_order.save(update_fields=["status"])
        self.run_planner("2026-04-01", apply=True)
        self.assertTrue(PreventiveOccurrence.objects.filter(task=self.quarterly, occurrence_index=1).exists())
        self.assertFalse(PreventiveOccurrence.objects.filter(task=self.monthly, occurrence_index=3).exists())
        self.assertEqual(WorkOrder.objects.count(), 4)

    def test_apply_requires_actor_and_bounded_window(self):
        with self.assertRaises(CommandError):
            call_command("plan_preventives", "--as-of", "2026-01-01", "--lookback-days", "0", "--lookahead-days", "0", "--apply", stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("plan_preventives", "--as-of", "2026-01-01", "--lookback-days", "0", "--lookahead-days", "367", stdout=StringIO())
        self.assertEqual(WorkOrder.objects.count(), 0)

    def test_apply_respects_area_and_maximum_batch(self):
        self.manager.area_permissions = ["Corte"]
        self.manager.save(update_fields=["area_permissions"])
        other_asset = Asset.objects.create(code="PLN-OTHER", name="Prensa", area="Prensas")
        other_plan = PreventivePlan.objects.create(asset=other_asset, title="Otro plan", frequency="1 mes", next_date=date(2026, 1, 1))
        PreventiveTask.objects.create(plan=other_plan, title="Otra tarea", interval_unit="months", interval_value=1, anchor_date=date(2026, 1, 1), created_by=self.manager, applicability_status="Interna", applicability_reason="Aplica", validated_by=self.manager, validated_at=timezone.now())
        with self.assertRaises(CommandError):
            call_command("plan_preventives", "--as-of", "2026-01-01", "--lookback-days", "0", "--lookahead-days", "0", "--apply", "--user", self.manager.username, "--max-new-orders", "1", stdout=StringIO())
        self.assertEqual(WorkOrder.objects.count(), 0)
        self.run_planner("2026-01-01", apply=True)
        self.assertEqual(WorkOrder.objects.count(), 2)
        self.assertFalse(PreventiveOccurrence.objects.filter(plan=other_plan).exists())


class AssetDossierTests(TestCase):
    def test_dossier_collects_related_history_and_net_cost_once(self):
        manager = User.objects.create_user(username="dossier-manager", password="Password123!", employee_number="DOS-M", first_name="Jefa", role="Jefatura")
        asset = Asset.objects.create(code="DOS-01", name="Cortadora", area="Corte", operational_status="Parada", operational_status_cause="Motor")
        other = Asset.objects.create(code="DOS-02", name="Prensa", area="Prensas")
        now = timezone.now()
        order = WorkOrder.objects.create(folio="DOS-OT-1", requested_at=now, requester=manager, priority="Alta", classification="Mantenimiento Correctivo", asset=asset, reported_failure="Motor", labor_cost=Decimal("25.00"))
        WorkOrder.objects.create(folio="DOS-OT-2", requested_at=now, requester=manager, priority="Alta", classification="Mantenimiento Correctivo", asset=other, reported_failure="Otro", labor_cost=Decimal("99.00"))
        item = InventoryItem.objects.create(code="MAT-DOS", name="Banda", category="Refacción", unit="pieza")
        movement = InventoryMovement.objects.create(item=item, type="Salida", quantity=2, unit_cost=Decimal("10.00"), work_order=order, user=manager, request_key="dossier-1", request_hash="hash")
        MaintenanceMaterial.objects.create(work_order=order, item=item, code=item.code, description=item.name, quantity=2, returned_quantity=1, unit_cost=Decimal("10.00"), movement=movement)
        plan = PreventivePlan.objects.create(asset=asset, title="Revisión mensual", frequency="1 mes", next_date=timezone.localdate(), responsible=manager)
        stop = DowntimeEvent.objects.create(asset=asset, cause="Motor", started_at=now, created_by=manager)
        stop.work_orders.add(order)
        MeterReading.objects.create(asset=asset, value=120, recorded_by=manager)
        self.client.force_login(manager)
        response = self.client.get(f"/api/assets/{asset.id}")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["metrics"]["maintenance_count"], 1)
        self.assertNotIn("labor_cost", body["metrics"])
        self.assertEqual(body["metrics"]["material_cost"], 10)
        self.assertEqual(body["metrics"]["total_cost"], 10)
        self.assertEqual(body["material_usage"][0]["net_quantity"], 1)
        self.assertEqual(body["preventive_plans"][0]["id"], plan.id)
        self.assertEqual(body["downtime_events"][0]["work_order_ids"], [order.id])
        self.assertEqual(body["meter_readings"][0]["value"], 120)

    def test_area_restriction_applies_to_entire_dossier(self):
        manager = User.objects.create_user(username="dossier-limited", password="Password123!", employee_number="DOS-L", first_name="Jefa", role="Jefatura", area_permissions=["Corte"])
        asset = Asset.objects.create(code="DOS-RESTRICT", name="Prensa", area="Prensas")
        self.client.force_login(manager)
        self.assertEqual(self.client.get(f"/api/assets/{asset.id}").status_code, 403)

    def test_open_downtime_blocks_manual_release_and_status_date_updates(self):
        manager = User.objects.create_user(username="dossier-status", password="Password123!", employee_number="DOS-S", first_name="Jefa", role="Jefatura")
        asset = Asset.objects.create(code="DOS-STATUS", name="Prensa", area="Prensas", operational_status="Parada", operational_status_cause="Motor")
        DowntimeEvent.objects.create(asset=asset, cause="Motor", started_at=timezone.now(), created_by=manager)
        self.client.force_login(manager)
        denied = self.client.patch(f"/api/assets/{asset.id}", json.dumps({"operational_status": "Operativa"}), content_type="application/json")
        self.assertEqual(denied.status_code, 409)
        asset.refresh_from_db()
        self.assertEqual(asset.operational_status, "Parada")
        open_stop = asset.downtime_events.get()
        open_stop.finished_at = timezone.now()
        open_stop.save(update_fields=["finished_at"])
        changed = self.client.patch(f"/api/assets/{asset.id}", json.dumps({"operational_status": "Operativa", "operational_status_cause": ""}), content_type="application/json")
        self.assertEqual(changed.status_code, 200)
        asset.refresh_from_db()
        self.assertIsNotNone(asset.operational_status_updated_at)


class PreventiveCalendarTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="calendar-manager", password="Password123!", employee_number="CAL-M", first_name="Jefa", role="Jefatura", area_permissions=["Corte"])
        self.asset = Asset.objects.create(code="CAL-01", name="Cortadora", area="Corte")
        self.uncovered = Asset.objects.create(code="CAL-02", name="Sierra", area="Corte")
        self.hidden = Asset.objects.create(code="CAL-03", name="Prensa", area="Prensas")
        self.client.force_login(self.manager)
        self.plan = self.client.post("/api/preventives", json.dumps({"asset_id":self.asset.id,"title":"Inspección","frequency":"1 mes","next_date":"2026-01-01"}), content_type="application/json").json()
        self.task = self.client.post(f"/api/preventives/{self.plan['id']}/tasks", json.dumps({"title":"Lubricar","interval_unit":"months","interval_value":1,"anchor_date":"2026-01-01","version":1}), content_type="application/json").json()
        reviewed = self.client.patch(f"/api/preventives/{self.plan['id']}/tasks/{self.task['id']}/applicability", json.dumps({"status":"Interna","reason":"Validada para esta cortadora","version":2}), content_type="application/json")
        assert reviewed.status_code == 200, reviewed.content

    def test_global_calendar_matches_plan_and_reports_coverage(self):
        query = "from=2026-01-01&to=2026-02-28&as_of=2026-03-01"
        global_response = self.client.get(f"/api/preventive-calendar?{query}")
        self.assertEqual(global_response.status_code, 200)
        body = global_response.json()
        individual = self.client.get(f"/api/preventives/{self.plan['id']}/compliance?{query}").json()
        self.assertEqual(body["counts"], individual["counts"])
        self.assertEqual(body["counts"]["V"], 2)
        self.assertEqual([row["asset_code"] for row in body["occurrences"]], ["CAL-01", "CAL-01"])
        self.assertEqual([row["asset_code"] for row in body["coverage"]["assets_without_configured_plan"]], ["CAL-02"])
        self.assertEqual(body["occurrences"][0]["task_title"], "Lubricar")

    def test_calendar_and_task_route_return_same_order(self):
        endpoint = f"/api/preventives/{self.plan['id']}/occurrences"
        data = {"task_id":self.task["id"], "occurrence_index":0, "version":3}
        first = self.client.post(endpoint, json.dumps(data), content_type="application/json")
        second = self.client.post(endpoint, json.dumps(data), content_type="application/json")
        self.assertEqual([first.status_code, second.status_code], [201, 200])
        self.assertEqual(first.json()["work_order_id"], second.json()["work_order_id"])
        self.assertEqual(WorkOrder.objects.count(), 1)
        global_row = self.client.get("/api/preventive-calendar?from=2026-01-01&to=2026-01-31&as_of=2026-01-01").json()["occurrences"][0]
        self.assertEqual(global_row["work_order_id"], first.json()["work_order_id"])
        self.assertEqual(global_row["folio"], first.json()["folio"])

    def test_generic_order_and_legacy_plan_route_cannot_create_orphan_preventive(self):
        CatalogEntry.objects.get_or_create(kind="priority", value="Media")
        CatalogEntry.objects.get_or_create(kind="classification", value="Mantenimiento Preventivo")
        generic = self.client.post("/api/orders", json.dumps({"requester_id":self.manager.id,"priority":"Media","classification":"Mantenimiento Preventivo","asset_id":self.asset.id,"reported_failure":"Lubricar"}), content_type="application/json")
        self.assertEqual(generic.status_code, 409)
        legacy = self.client.post(f"/api/preventives/{self.plan['id']}/order", json.dumps({}), content_type="application/json")
        self.assertEqual(legacy.status_code, 409)
        self.assertEqual(WorkOrder.objects.count(), 0)

    def test_calendar_rejects_large_range(self):
        response = self.client.get("/api/preventive-calendar?from=2026-01-01&to=2028-01-01")
        self.assertEqual(response.status_code, 400)

    def test_agenda_feed_has_schedule_fields_for_calendar_view(self):
        CatalogEntry.objects.get_or_create(kind="priority", value="Media")
        CatalogEntry.objects.get_or_create(kind="classification", value="Correctivo")
        order = self.client.post("/api/orders", json.dumps({
            "requester_id": self.manager.id, "priority": "Media", "classification": "Correctivo",
            "asset_id": self.asset.id, "reported_failure": "Vibración", "technician_id": self.manager.id,
            "scheduled_at": "2026-01-15T10:00",
        }), content_type="application/json")
        self.assertEqual(order.status_code, 201)
        feed = self.client.get("/api/agenda").json()
        row = next(item for item in feed["orders"] if item["id"] == order.json()["id"])
        self.assertEqual(row["asset_name"], "Cortadora")
        self.assertEqual(row["technician_id"], self.manager.id)
        self.assertIsNotNone(row["scheduled_at"])

    def test_pending_and_not_applicable_tasks_do_not_create_due_work(self):
        task = self.client.post(f"/api/preventives/{self.plan['id']}/tasks", json.dumps({"title":"Revisar línea externa","interval_unit":"months","interval_value":1,"anchor_date":"2026-01-01","version":3}), content_type="application/json").json()
        calendar = self.client.get("/api/preventive-calendar?from=2026-01-01&to=2026-01-31&as_of=2026-02-01").json()
        self.assertEqual(len(calendar["occurrences"]), 1)
        self.assertEqual(len(calendar["coverage"]["incomplete_plans"]), 1)
        blocked = self.client.post(f"/api/preventives/{self.plan['id']}/occurrences", json.dumps({"task_id":task["id"],"occurrence_index":0,"version":4}), content_type="application/json")
        self.assertEqual(blocked.status_code, 409)
        reviewed = self.client.patch(f"/api/preventives/{self.plan['id']}/tasks/{task['id']}/applicability", json.dumps({"status":"No aplica","reason":"No existe esa línea en el activo","version":4}), content_type="application/json")
        self.assertEqual(reviewed.status_code, 200)
        after = self.client.get("/api/preventive-calendar?from=2026-01-01&to=2026-01-31&as_of=2026-02-01").json()
        self.assertEqual(len(after["occurrences"]), 1)
        self.assertEqual(len(after["coverage"]["incomplete_plans"]), 0)

    def test_review_requires_reason_and_keeps_existing_order(self):
        no_reason = self.client.patch(f"/api/preventives/{self.plan['id']}/tasks/{self.task['id']}/applicability", json.dumps({"status":"Externa","version":3}), content_type="application/json")
        self.assertEqual(no_reason.status_code, 400)
        created = self.client.post(f"/api/preventives/{self.plan['id']}/occurrences", json.dumps({"task_id":self.task["id"],"occurrence_index":0,"version":3}), content_type="application/json").json()
        task = PreventiveTask.objects.get(pk=self.task["id"])
        task.applicability_status = "Pendiente"
        task.save(update_fields=["applicability_status"])
        historical = self.client.get("/api/preventive-calendar?from=2026-01-01&to=2026-02-28&as_of=2026-03-01").json()["occurrences"]
        self.assertEqual([row["work_order_id"] for row in historical], [created["work_order_id"]])
        reviewed = self.client.patch(f"/api/preventives/{self.plan['id']}/tasks/{self.task['id']}/applicability", json.dumps({"status":"Externa","reason":"Proveedor externo","version":3}), content_type="application/json")
        self.assertEqual(reviewed.status_code, 200)
        self.assertEqual(WorkOrder.objects.count(), 1)
        row = self.client.get("/api/preventive-calendar?from=2026-01-01&to=2026-01-31&as_of=2026-02-01").json()["occurrences"][0]
        self.assertEqual(row["work_order_id"], created["work_order_id"])


class AssetEquivalenceTests(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user(username="alias-manager", password="Password123!", employee_number="ALIAS-M", first_name="Jefa", role="Jefatura")
        self.technician = User.objects.create_user(username="alias-technician", password="Password123!", employee_number="ALIAS-T", first_name="Técnica", role="Técnico")
        self.first = Asset.objects.create(code="MAQ-01", name="Prensa uno", area="Prensas")
        self.second = Asset.objects.create(code="MAQ-02", name="Prensa dos", area="Prensas")
        self.client.force_login(self.manager)

    def propose(self, asset, code):
        return self.client.post(f"/api/assets/{asset.id}/equivalences", json.dumps({"code": code, "notes": "Placa y archivo cotejados", "source_file": "maquinas.xlsx", "source_sheet": "MAQUINAS", "source_row": 74}), content_type="application/json")

    def review(self, asset, item_id, status, reason="Cotejo físico"):
        return self.client.patch(f"/api/assets/{asset.id}/equivalences/{item_id}", json.dumps({"status": status, "reason": reason}), content_type="application/json")

    def test_proposal_preserves_code_and_requires_approval(self):
        response = self.propose(self.first, "  00-ABC  ")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["code"], "00-ABC")
        self.assertEqual(response.json()["source_row"], 74)
        self.assertEqual(self.client.get("/api/assets").json()[0]["approved_codes"], [])
        item_id = response.json()["id"]
        self.assertEqual(self.review(self.first, item_id, "Aprobada").status_code, 200)
        detail = self.client.get(f"/api/assets/{self.first.id}").json()
        self.assertEqual(detail["approved_codes"], ["00-ABC"])
        self.assertEqual(detail["equivalences"][0]["review_reason"], "Cotejo físico")
        self.assertTrue(AuditLog.objects.filter(entity_type="asset_code_equivalence", entity_id=item_id, action="reviewed").exists())

    def test_cross_asset_conflict_and_revocation(self):
        first = self.propose(self.first, "00-Z").json()["id"]
        second = self.propose(self.second, "00-z").json()["id"]
        self.assertEqual(self.review(self.first, first, "Aprobada").status_code, 200)
        self.assertEqual(self.review(self.second, second, "Aprobada").status_code, 409)
        self.assertEqual(self.review(self.first, first, "Rechazada", "Revisión corrigió la placa").status_code, 200)
        self.assertEqual(self.review(self.second, second, "Aprobada").status_code, 200)
        self.assertEqual(AssetCodeEquivalence.objects.get(pk=first).status, "Rechazada")

    def test_primary_code_collision_and_role_restriction(self):
        item_id = self.propose(self.first, "MAQ-02").json()["id"]
        self.assertEqual(self.review(self.first, item_id, "Aprobada").status_code, 409)
        self.client.force_login(self.technician)
        self.assertEqual(self.review(self.first, item_id, "Aprobada").status_code, 403)
        self.assertEqual(self.propose(self.first, "00-X").status_code, 403)

    def test_primary_code_cannot_take_approved_equivalence(self):
        item_id = self.propose(self.first, "00-Y").json()["id"]
        self.assertEqual(self.review(self.first, item_id, "Aprobada").status_code, 200)
        response = self.client.patch(f"/api/assets/{self.second.id}", json.dumps({"code": "00-y"}), content_type="application/json")
        self.assertEqual(response.status_code, 409)


class ConcurrentFolioTests(TransactionTestCase):
    def setUp(self):
        CatalogEntry.objects.get_or_create(kind="priority", value="Alta", defaults={"sort_order": 1})
        CatalogEntry.objects.get_or_create(kind="classification", value="Mantenimiento Correctivo", defaults={"sort_order": 1})

    def test_two_simultaneous_requests_get_distinct_folios(self):
        operator = User.objects.create_user(
            username="concurrent-operator", password="Password123!",
            employee_number="OP-CONCURRENT", first_name="Operador", role="Solicitante",
        )
        asset = Asset.objects.create(code="MAQ-CONCURRENT", name="Prensa", area="Prensas")
        barrier = Barrier(2)

        def create(index):
            close_old_connections()
            try:
                client = Client()
                client.force_login(User.objects.get(pk=operator.pk))
                barrier.wait(timeout=10)
                response = client.post("/api/orders", json.dumps({
                    "priority": "Alta", "classification": "Mantenimiento Correctivo",
                    "asset_id": asset.id, "reported_failure": f"Falla {index}",
                }), content_type="application/json", HTTP_IDEMPOTENCY_KEY=f"concurrent-{index}")
                return response.status_code, response.json()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(create, (1, 2)))
        self.assertEqual([status for status, _ in results], [201, 201])
        self.assertEqual(len({body["folio"] for _, body in results}), 2)

    def test_two_simultaneous_requests_for_same_occurrence_share_order(self):
        manager = User.objects.create_user(username="concurrent-plan-manager", password="Password123!", employee_number="PM-CONCURRENT", first_name="Jefa", role="Jefatura")
        asset = Asset.objects.create(code="PM-CONCURRENT", name="Prensa", area="Prensas")
        plan = PreventivePlan.objects.create(asset=asset, title="Mensual", frequency="1 mes", next_date=timezone.localdate())
        task = PreventiveTask.objects.create(plan=plan, title="Lubricar", interval_unit="months", interval_value=1, anchor_date=timezone.localdate(), created_by=manager, applicability_status="Interna", applicability_reason="Validada por Jefatura", validated_by=manager, validated_at=timezone.now())
        barrier = Barrier(2)

        def create(_):
            close_old_connections()
            try:
                client = Client()
                client.force_login(User.objects.get(pk=manager.pk))
                barrier.wait(timeout=10)
                response = client.post(f"/api/preventives/{plan.id}/occurrences", json.dumps({"task_id":task.id,"occurrence_index":0,"version":1}), content_type="application/json")
                return response.status_code, response.json()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(create, (1, 2)))
        self.assertEqual(sorted(status for status, _ in results), [200, 201])
        self.assertEqual(len({body["work_order_id"] for _, body in results}), 1)
        self.assertEqual(WorkOrder.objects.count(), 1)

    def test_simultaneous_retry_with_same_key_creates_one_order(self):
        operator = User.objects.create_user(
            username="same-key-operator", password="Password123!",
            employee_number="OP-SAME", first_name="Operador", role="Solicitante",
        )
        asset = Asset.objects.create(code="MAQ-SAME", name="Prensa", area="Prensas")
        barrier = Barrier(2)
        body = json.dumps({
            "priority": "Alta", "classification": "Mantenimiento Correctivo",
            "asset_id": asset.id, "reported_failure": "Motor detenido",
        })

        def create(_):
            close_old_connections()
            try:
                client = Client()
                client.force_login(User.objects.get(pk=operator.pk))
                barrier.wait(timeout=10)
                response = client.post("/api/orders", body, content_type="application/json",
                                       HTTP_IDEMPOTENCY_KEY="same-key")
                return response.status_code, response.json()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(create, (1, 2)))
        self.assertEqual(sorted(status for status, _ in results), [200, 201])
        self.assertEqual(len({result["id"] for _, result in results}), 1)
        self.assertEqual(WorkOrder.objects.count(), 1)

    def test_same_technician_cannot_start_two_orders_simultaneously(self):
        operator = User.objects.create_user(
            username="session-operator", password="Password123!",
            employee_number="OP-SESSION", first_name="Operador", role="Solicitante",
        )
        technician = User.objects.create_user(
            username="session-concurrent-tech", password="Password123!",
            employee_number="T-CONCURRENT", first_name="Técnico", role="Técnico",
        )
        admin = User.objects.create_user(
            username="session-admin", password="Password123!",
            employee_number="ADMIN-CONCURRENT", first_name="Admin", role="Administrador",
        )
        asset = Asset.objects.create(code="MAQ-SESSION", name="Prensa", area="Prensas")
        operator_client, admin_client = Client(), Client()
        operator_client.force_login(operator)
        admin_client.force_login(admin)
        orders = []
        for index in (1, 2):
            created = operator_client.post("/api/orders", json.dumps({
                "priority": "Alta", "classification": "Mantenimiento Correctivo",
                "asset_id": asset.id, "reported_failure": f"Falla {index}",
            }), content_type="application/json").json()
            assigned = admin_client.patch(f"/api/orders/{created['id']}", json.dumps({
                "technician_id": technician.id, "version": 1,
            }), content_type="application/json").json()
            started = admin_client.post(f"/api/orders/{created['id']}/transitions", json.dumps({
                "to": "En proceso", "version": assigned["version"],
            }), content_type="application/json").json()
            orders.append((created["id"], started["version"]))
        barrier = Barrier(2)

        def start(order):
            close_old_connections()
            try:
                client = Client()
                client.force_login(User.objects.get(pk=technician.pk))
                barrier.wait(timeout=10)
                response = client.post(f"/api/orders/{order[0]}/time-entries/actions", json.dumps({
                    "action": "start", "version": order[1],
                }), content_type="application/json")
                return response.status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(start, orders))
        self.assertEqual(sorted(statuses), [200, 409])


class InterfaceModeContractTests(TestCase):
    def test_inventory_grid_is_a_real_tabular_paste_workflow(self):
        from pathlib import Path

        script = (Path(__file__).resolve().parent.parent / "static" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("data-form-mode", script)
        self.assertIn("function openInventoryGrid()", script)
        self.assertIn("body.addEventListener('paste'", script)
        self.assertIn("api('/api/inventory/bulk-create'", script)
        self.assertIn("data-sheet-add", script)
        self.assertIn("data-sheet-save", script)

    def test_agenda_calendar_is_month_grid_with_navigation_and_events(self):
        from pathlib import Path

        script = (Path(__file__).resolve().parent.parent / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("data-agenda-mode=\"calendar\"", script)
        self.assertIn("data-agenda-mode=\"list\"", script)
        self.assertIn("class=\"month-grid\"", script)
        self.assertIn("Array.from({length:42}", script)
        self.assertIn("id=\"month-prev\"", script)
        self.assertIn("class=\"month-event", script)

    def test_order_close_flow_and_work_time_have_explanations(self):
        from pathlib import Path

        script = (Path(__file__).resolve().parent.parent / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Terminar trabajo", script)
        self.assertIn("Validar y cerrar OT", script)
        self.assertIn("Terminar una sesión no cierra la OT", script)
        self.assertIn("Se registra al enviar el trabajo a validación", script)
        self.assertIn("Código documental (opcional)", script)
        self.assertIn("no es la versión del PDF generado", script)

    def test_pending_order_validation_stays_visible_for_admin(self):
        from pathlib import Path

        script = (Path(__file__).resolve().parent.parent / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("o.status==='Pendiente de validación'&&['Administrador','Jefatura','Jefe de mantenimiento'].includes(state.user.role)", script)
        self.assertIn('class="btn btn-primary validate-order"', script)
        self.assertIn("wrap.querySelector('form .form-actions .btn-primary')", script)
        self.assertNotIn("wrap.querySelector('form .btn-primary').hidden=true", script)
        self.assertIn("'Revisar y validar'", script)

    def test_order_history_is_collapsible_and_labor_cost_is_absent(self):
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent / "static"
        script = (root / "app.js").read_text(encoding="utf-8")
        print_script = (root / "print.js").read_text(encoding="utf-8")
        self.assertIn('<details class="detail-box order-history"><summary>Historial de la orden', script)
        self.assertNotIn('name="labor_cost"', script)
        self.assertNotIn("Costo M.O.", print_script)

    def test_request_information_is_grouped_first_and_locked_until_enabled(self):
        from pathlib import Path

        script = (Path(__file__).resolve().parent.parent / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn("overview.replaceWith(requestPanel)", script)
        self.assertIn("Información proporcionada al levantar la OT", script)
        self.assertIn("['requested_at','priority','location','reported_failure']", script)
        self.assertIn("input.disabled=true", script)
        self.assertIn("edit-request-origin", script)
        self.assertIn("orders.edit_dates", script)

    def test_agenda_and_inventory_labels_keep_spanish_accents(self):
        from pathlib import Path

        script = (Path(__file__).resolve().parent.parent / "static" / "app.js").read_text(encoding="utf-8")
        for correct in ("Código", "Descripción", "Categoría", "Técnico", "Miércoles", "Sábado", "Paro de máquina"):
            self.assertIn(correct, script)
        for broken in ("C?digo", "Descripci?n", "T?cnico", "Mi?rcoles", "Paro de m?quina"):
            self.assertNotIn(broken, script)

    def test_technician_selector_is_compact_and_keeps_multiple_assignments(self):
        from pathlib import Path

        script = (Path(__file__).resolve().parent.parent / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('class="technician-picker"', script)
        self.assertIn('class="technician-option"', script)
        self.assertIn('aria-expanded="false"', script)
        self.assertIn(".technician-option[aria-pressed=\"true\"]", script)
        self.assertIn("data.participant_ids=ids.filter(id=>id!==primary)", script)
        self.assertNotIn("technician-choice-grid", script)

    def test_preventives_offer_month_grid_and_existing_list(self):
        from pathlib import Path

        script = (Path(__file__).resolve().parent.parent / "static" / "preventive-calendar.js").read_text(encoding="utf-8")
        self.assertIn('data-preventive-mode="calendar"', script)
        self.assertIn('data-preventive-mode="list"', script)
        self.assertIn('class="month-grid"', script)
        self.assertIn('data-calendar-open=', script)
        self.assertIn("calendarSection.hidden=mode!=='calendar'", script)
        self.assertIn("planList.hidden=mode!=='list'", script)


class DemoTextRepairTests(TestCase):
    def test_repair_text_changes_only_tagged_demo_records(self):
        from django.core.management import call_command

        demo = Asset.objects.create(code="PRUEBA-MESA-TEST", name="Prensa hidr?ulica DEMO", area="PRUEBA-MESA-L?nea 1")
        real = Asset.objects.create(code="REAL-TEST", name="Prensa hidr?ulica", area="L?nea 1")
        CatalogEntry.objects.get_or_create(kind="specialty", value="Mecánica")
        CatalogEntry.objects.create(kind="specialty", value="Mec?nica")
        call_command("demo_data", "repair-text", verbosity=0)
        demo.refresh_from_db()
        real.refresh_from_db()
        self.assertEqual(demo.name, "Prensa hidráulica DEMO")
        self.assertEqual(real.name, "Prensa hidr?ulica")
        self.assertEqual(CatalogEntry.objects.filter(kind="specialty", value="Mecánica").count(), 1)
        self.assertFalse(CatalogEntry.objects.filter(kind="specialty", value="Mec?nica").exists())


class ApiWorkflowTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="administrator", password="Password123!", employee_number="ADMIN", first_name="Admin", role="Administrador")
        self.operator = User.objects.create_user(username="operator", password="Password123!", employee_number="OP-1", first_name="Operador", role="Solicitante")
        self.asset = Asset.objects.create(code="MAQ-001", name="Prensa", category="Maquinaria", asset_type="Maquinaria", area="Prensas")

    def post(self, url, data, **headers):
        return self.client.post(url, json.dumps(data), content_type="application/json", **headers)

    def test_health_and_session(self):
        self.assertEqual(Client().get("/api/health").json(), {"status": "ok"})
        response = self.post("/api/auth/login", {"username": "administrator", "password": "Password123!"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get("/api/auth/me").json()["role"], "Administrador")

    def test_manual_order_hours_with_two_technicians_and_direct_close(self):
        technicians = [User.objects.create_user(
            username=f"direct-close-{index}", password="Password123!",
            employee_number=f"DIRECT-{index}", first_name=f"Tecnico {index}", role="Técnico",
        ) for index in (1, 2)]
        self.client.force_login(self.operator)
        order_id = self.post("/api/orders", {
            "priority": "Media", "classification": "Mantenimiento Correctivo",
            "asset_id": self.asset.id, "reported_failure": "Ajuste de prueba",
        }).json()["id"]
        self.client.force_login(self.admin)
        assigned = self.client.patch(f"/api/orders/{order_id}", json.dumps({
            "technician_id": technicians[0].id, "participant_ids": [technicians[1].id],
            "scheduled_at": "2026-10-02T08:00", "date_change_reason": "", "version": 1,
        }), content_type="application/json")
        self.assertEqual(assigned.status_code, 200)
        self.client.force_login(technicians[0])
        started = self.post(f"/api/orders/{order_id}/transitions", {
            "to": "En proceso", "version": assigned.json()["version"],
        })
        self.assertEqual(started.status_code, 200)
        detail = self.client.get(f"/api/orders/{order_id}").json()
        saved = self.client.patch(f"/api/orders/{order_id}", json.dumps({
            "technician_id": str(technicians[0].id),
            "requested_at": detail["requested_at"],
            "scheduled_at": detail["scheduled_at"],
            "started_at": "2026-10-02T08:00", "finished_at": "2026-10-02T11:00",
            "actions": "Ajuste y prueba", "closure_notes": "Equipo funcionando",
            "version": started.json()["version"],
        }), content_type="application/json")
        self.assertEqual(saved.status_code, 200)
        detail = self.client.get(f"/api/orders/{order_id}").json()
        self.assertEqual(detail["labor_hours"], 6.0)
        self.assertEqual(len(detail["participants"]), 1)
        finished = self.post(f"/api/orders/{order_id}/transitions", {
            "to": "Pendiente de validación", "version": saved.json()["version"],
        })
        self.assertEqual(finished.status_code, 200)
        self.assertEqual(self.client.get(f"/api/orders/{order_id}").json()["finished_at"], detail["finished_at"])
        self.client.force_login(self.admin)
        validated = self.post(f"/api/orders/{order_id}/validate", {"version": finished.json()["version"]})
        self.assertEqual(validated.status_code, 200)
        self.assertEqual(self.client.get(f"/api/orders/{order_id}").json()["status"], "Completada")

    def test_order_idempotency_and_operator_scope(self):
        self.client.force_login(self.operator)
        data = {"requested_at": timezone.now().isoformat(), "priority": "Alta", "classification": "Mantenimiento Correctivo", "asset_id": self.asset.id, "reported_failure": "No arranca"}
        first = self.post("/api/orders", data, HTTP_IDEMPOTENCY_KEY="request-1")
        second = self.post("/api/orders", data, HTTP_IDEMPOTENCY_KEY="request-1")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.json()["id"], second.json()["id"])
        changed = self.post("/api/orders", data | {"reported_failure": "Otro problema"}, HTTP_IDEMPOTENCY_KEY="request-1")
        self.assertEqual(changed.status_code, 409)
        self.assertNotIn("labor_cost", self.client.get(f"/api/orders/{first.json()['id']}").json())

    def test_catalog_deactivation_preserves_history_and_blocks_new_use(self):
        self.client.force_login(self.admin)
        self.assertIn("Seguimiento", self.client.get("/api/catalogs").json()["priorities"])
        created = self.post("/api/catalog-entries", {
            "kind": "priority", "value": "Revisión especial", "sort_order": 10,
        })
        self.assertEqual(created.status_code, 201)
        self.client.force_login(self.operator)
        order_data = {
            "priority": "Revisión especial", "classification": "Mantenimiento Correctivo",
            "asset_id": self.asset.id, "reported_failure": "Verificación",
        }
        order = self.post("/api/orders", order_data)
        self.assertEqual(order.status_code, 201)
        self.client.force_login(self.admin)
        disabled = self.client.patch(f"/api/catalog-entries/{created.json()['id']}",
                                     json.dumps({"active": False}), content_type="application/json")
        self.assertEqual(disabled.status_code, 200)
        self.assertNotIn("Revisión especial", self.client.get("/api/catalogs").json()["priorities"])
        self.assertEqual(self.client.get(f"/api/orders/{order.json()['id']}").json()["priority"], "Revisión especial")
        self.client.force_login(self.operator)
        self.assertEqual(self.post("/api/orders", order_data).status_code, 400)
        self.assertEqual(self.post("/api/catalog-entries", {
            "kind": "priority", "value": "No autorizado",
        }).status_code, 403)
        self.assertEqual(CatalogEntry.objects.filter(kind="priority", value="Revisión especial").count(), 1)

    def test_asset_line_uses_catalog_and_keeps_inactive_historical_value(self):
        self.client.force_login(self.admin)
        line = self.post("/api/catalog-entries", {"kind": "line", "value": "Línea A"}).json()
        base = {"code": "MAQ-LINE", "name": "Prensa 2", "area": "Prensas",
                "location_detail": "Nave 2, celda 4"}
        self.assertEqual(self.post("/api/assets", base | {"line": "No catalogada"}).status_code, 400)
        created = self.post("/api/assets", base | {"line": "Línea A"})
        self.assertEqual(created.status_code, 201)
        self.assertEqual(self.client.get(f"/api/assets/{created.json()['id']}").json()["line"], "Línea A")
        self.client.patch(f"/api/catalog-entries/{line['id']}", json.dumps({"active": False}),
                          content_type="application/json")
        saved = self.client.patch(f"/api/assets/{created.json()['id']}", json.dumps({
            "line": "Línea A", "observations": "Revisado",
        }), content_type="application/json")
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(self.client.get(f"/api/assets/{created.json()['id']}").json()["location_detail"], "Nave 2, celda 4")

    def test_atomic_stock_exit(self):
        self.client.force_login(self.admin)
        item = InventoryItem.objects.create(code="MAT-1", name="Tornillo", category="Refacción", unit="pieza", stock=10, min_stock=2, max_stock=20, unit_cost=3)
        response = self.post(f"/api/inventory/{item.id}/movement", {"type": "Salida", "quantity": 3, "version": 1, "request_key": "stock-1"})
        self.assertEqual(response.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.stock, 7)
        replay = self.post(f"/api/inventory/{item.id}/movement", {"type": "Salida", "quantity": 3, "version": 1, "request_key": "stock-1"})
        self.assertTrue(replay.json()["replayed"])

    def test_inventory_filters_match_csv_and_xlsx_exports(self):
        from io import BytesIO
        from zipfile import ZipFile

        self.client.force_login(self.admin)
        low = InventoryItem.objects.create(
            code="MAT-FILTER-LOW", name="Filtro de prensa", category="Filtración",
            unit="pieza", stock=1, min_stock=2, max_stock=8, unit_cost=12,
            location="Anaquel A",
        )
        InventoryItem.objects.create(
            code="MAT-FILTER-OK", name="Banda transportadora", category="Transmisión",
            unit="pieza", stock=8, min_stock=2, max_stock=12, unit_cost=30,
            location="Anaquel B",
        )

        filtered = self.client.get("/api/inventory?stock=low&q=filtro")
        csv_response = self.client.get("/api/inventory/export.csv?stock=low&q=filtro")
        xlsx_response = self.client.get("/api/inventory/export.xlsx?stock=low&q=filtro")

        self.assertEqual([row["id"] for row in filtered.json()], [low.id])
        self.assertIn("MAT-FILTER-LOW", csv_response.content.decode("utf-8-sig"))
        self.assertNotIn("MAT-FILTER-OK", csv_response.content.decode("utf-8-sig"))
        with ZipFile(BytesIO(xlsx_response.content)) as workbook:
            sheet = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
        self.assertIn("MAT-FILTER-LOW", sheet)
        self.assertNotIn("MAT-FILTER-OK", sheet)

    def test_inventory_bulk_create_is_atomic_audited_and_records_opening_stock(self):
        self.client.force_login(self.admin)
        rows = [
            {"code": "MAT-PASTE-1", "name": "Banda", "category": "Transmisión", "unit": "pieza", "stock": "8", "min_stock": "2", "max_stock": "20", "unit_cost": "15.50", "location": "A-01"},
            {"code": "MAT-PASTE-2", "name": "Rodamiento", "category": "Refacción", "unit": "pieza", "stock": "4", "min_stock": "1", "max_stock": "10", "unit_cost": "8", "location": "A-02"},
        ]
        response = self.post("/api/inventory/bulk-create", {"rows": rows})
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["created"], 2)
        self.assertEqual(InventoryItem.objects.get(code="MAT-PASTE-1").stock, Decimal("8"))
        self.assertTrue(InventoryMovement.objects.filter(item__code="MAT-PASTE-1", type="Ajuste", quantity=8).exists())
        self.assertEqual(AuditLog.objects.filter(entity_type="inventory_bulk_create", action="created").count(), 1)

        invalid = rows + [rows[0] | {"code": "MAT-INVALID", "name": "Duplicado"}]
        rejected = self.post("/api/inventory/bulk-create", {"rows": invalid})
        self.assertEqual(rejected.status_code, 409)
        self.assertFalse(InventoryItem.objects.filter(code="MAT-INVALID").exists())

    def test_inventory_bulk_create_denies_requester(self):
        self.client.force_login(self.operator)
        response = self.post("/api/inventory/bulk-create", {"rows": [{"code": "MAT-X", "name": "No autorizado"}]})
        self.assertEqual(response.status_code, 403)

    def test_inventory_history_is_visible_to_readers_and_denied_to_requesters(self):
        manager = User.objects.create_user(
            username="inventory-history-manager", password="Password123!",
            employee_number="INV-H-M", first_name="Almacén", role="Jefatura",
        )
        requester = User.objects.create_user(
            username="inventory-history-requester", password="Password123!",
            employee_number="INV-H-R", first_name="Solicitante", role="Solicitante",
        )
        item = InventoryItem.objects.create(
            code="MAT-HISTORY", name="Rodamiento", category="Refacción", unit="pieza",
            stock=5, min_stock=1, max_stock=10,
        )
        InventoryMovement.objects.create(
            item=item, type="Entrada", quantity=5, unit_cost=10, user=manager,
            request_key="history-entry", request_hash="a" * 64,
        )
        self.client.force_login(manager)
        response = self.client.get(f"/api/inventory/{item.id}/movements")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()[0]["type"], "Entrada")
        self.client.force_login(requester)
        self.assertEqual(self.client.get(f"/api/inventory/{item.id}/movements").status_code, 403)

    def test_preventive_recurrence_occurrence_and_checklist(self):
        self.client.force_login(self.admin)
        plan = self.post("/api/preventives", {"asset_id": self.asset.id, "title": "Mensual", "frequency": "1 mes", "next_date": "2026-01-31", "status": "Programado"}).json()
        task = self.post(f"/api/preventives/{plan['id']}/tasks", {"title": "Lubricar", "interval_unit": "months", "interval_value": 1, "anchor_date": "2026-01-31", "version": 1}).json()
        self.client.patch(f"/api/preventives/{plan['id']}/tasks/{task['id']}/applicability", json.dumps({"status":"Interna","reason":"Aplica a este activo","version":2}), content_type="application/json")
        projected = self.client.get(f"/api/preventives/{plan['id']}/calendar?from=2026-02-01&to=2026-03-31").json()["occurrences"]
        self.assertEqual([x["base_date"] for x in projected], ["2026-02-28", "2026-03-31"])
        item = self.post(f"/api/preventives/{plan['id']}/tasks/{task['id']}/checklist", {"position": 1, "prompt": "Nivel correcto", "required": True}).json()
        occurrence = self.post(f"/api/preventives/{plan['id']}/occurrences", {"task_id": task["id"], "occurrence_index": 1, "version": 3}).json()
        saved = self.post(f"/api/preventives/{plan['id']}/occurrences/{occurrence['id']}/checklist", {"answers": [{"item_id": item["id"], "answer": "Sí", "notes": "Correcto"}]})
        self.assertTrue(saved.json()["complete"])


class ImportReadinessTests(TestCase):
    def test_readiness_xlsx_contains_only_aggregate_review_data(self):
        from io import BytesIO
        from zipfile import ZipFile

        admin = User.objects.create_user(
            username="import-report-admin", password="Password123!",
            employee_number="IMP-XLSX", first_name="Admin", role="Administrador",
        )
        batch = ImportBatch.objects.create(
            content_hash="e" * 64, filename="private-source-filename.xlsx", uploaded_by=admin,
        )
        ImportRow.objects.create(
            batch=batch, sheet="MAQUINAS", source_row=2,
            cells={"B2": "PRIVATE_CELL_VALUE_4872"}, source_code="PRIVATE_CELL_VALUE_4872",
        )
        self.client.force_login(admin)

        response = self.client.get(f"/api/imports/{batch.id}/readiness/export.xlsx")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn(f"prevalidacion-lote-{batch.id}.xlsx", response["Content-Disposition"])
        with ZipFile(BytesIO(response.content)) as workbook:
            sheet = workbook.read("xl/worksheets/sheet1.xml").decode("utf-8")
        self.assertIn("PRIVATE_CELL_VALUE_4872", "") if False else None
        self.assertNotIn("PRIVATE_CELL_VALUE_4872", sheet)
        self.assertNotIn("private-source-filename.xlsx", sheet)
        self.assertIn("TRANSACTIONAL_WRITER_DISABLED", sheet)
        self.assertIn("No disponible", sheet)

    def test_readiness_xlsx_keeps_users_manage_permission(self):
        requester = User.objects.create_user(
            username="import-report-requester", password="Password123!",
            employee_number="IMP-XLSX-R", first_name="Requester", role="Solicitante",
        )
        batch = ImportBatch.objects.create(
            content_hash="f" * 64, filename="source.xlsx", uploaded_by=requester,
        )
        self.client.force_login(requester)

        response = self.client.get(f"/api/imports/{batch.id}/readiness/export.xlsx")

        self.assertEqual(response.status_code, 403)

    def test_readiness_counts_blockers_and_never_authorizes_operational_import(self):
        admin = User.objects.create_user(
            username="import-readiness-admin", password="Password123!",
            employee_number="IMP-RDY", first_name="Admin", role="Administrador",
        )
        batch = ImportBatch.objects.create(
            content_hash="a" * 64, filename="review.xlsx", uploaded_by=admin,
        )
        ImportRow.objects.create(
            batch=batch, sheet="MAQUINAS", source_row=2,
            cells={"B2": "ASSET-01"}, source_code="ASSET-01",
        )
        ImportRow.objects.create(
            batch=batch, sheet="HOJA_NO_MAPEADA", source_row=2,
            cells={"A2": "valor"}, source_code="valor", review_status="Propuesta",
        )
        ImportRow.objects.create(
            batch=batch, sheet="HOJA_NO_MAPEADA", source_row=3,
            cells={"A3": "error"}, cell_details={"A3": {"kind": "error"}},
            review_status="Excluida",
        )
        self.client.force_login(admin)

        response = self.client.get(f"/api/imports/{batch.id}/readiness")

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["total_rows"], 3)
        self.assertEqual(result["pending_review_rows"], 1)
        self.assertEqual(result["proposed_link_rows"], 1)
        self.assertEqual(result["excluded_rows"], 1)
        self.assertEqual(result["unmapped_rows"], 1)
        self.assertEqual(result["excel_error_cells"], 0)
        self.assertFalse(result["technical_precheck_clear"])
        self.assertFalse(result["operational_import_available"])

    def test_readiness_flags_uninterpreted_dates_and_exposes_provisional_types(self):
        admin = User.objects.create_user(
            username="import-types-admin", password="Password123!",
            employee_number="IMP-TYPE", first_name="Admin", role="Administrador",
        )
        batch = ImportBatch.objects.create(
            content_hash="b" * 64, filename="dates.xlsx", uploaded_by=admin,
        )
        row = ImportRow.objects.create(
            batch=batch, sheet="MANTENIMIENTOS", source_row=2,
            cells={"A2": "1", "C2": "28/08/2026", "M2": "125.50"},
            cell_details={"C2": {"kind": "date_text", "value": "28/08/2026"}, "M2": {"kind": "number"}},
        )
        self.client.force_login(admin)

        readiness = self.client.get(f"/api/imports/{batch.id}/readiness").json()
        mapping = self.client.get(f"/api/imports/{batch.id}/rows?sheet=MANTENIMIENTOS").json()["rows"][0]["mapping"]

        self.assertEqual(readiness["field_type_issue_rows"], 1)
        self.assertEqual(readiness["uninterpreted_temporal_cells"], 1)
        self.assertEqual(mapping["field_types"]["event_date_raw"], "date_candidate")
        self.assertEqual(mapping["fields"]["event_date_raw"], "28/08/2026")
        self.assertEqual(mapping["type_issues"][0]["cell"], "C2")
        self.assertFalse(readiness["operational_import_available"])

    def test_readiness_counts_unresolved_references_and_ignores_excluded_rows(self):
        admin = User.objects.create_user(
            username="import-refs-admin", password="Password123!",
            employee_number="IMP-REF", first_name="Admin", role="Administrador",
        )
        batch = ImportBatch.objects.create(
            content_hash="c" * 64, filename="references.xlsx", uploaded_by=admin,
        )
        rows = [
            ImportRow(batch=batch, sheet="MAQUINAS", source_row=2, cells={"A2": "1", "B2": "MAQ-1"}, source_code="MAQ-1"),
            ImportRow(batch=batch, sheet="MANTENIMIENTOS", source_row=2, cells={"A2": "20", "B2": "999"}),
            ImportRow(batch=batch, sheet="PM", source_row=2, cells={"A2": "404", "C2": "PART-1"}),
            ImportRow(batch=batch, sheet="ALMACEN", source_row=2, cells={"A2": "DUP-1"}),
            ImportRow(batch=batch, sheet="ALMACEN", source_row=3, cells={"A3": "DUP-1"}),
            ImportRow(batch=batch, sheet="MANTENIMIENTOS", source_row=3, cells={"A3": "20", "B3": "1"}, review_status="Excluida"),
            ImportRow(batch=batch, sheet="PM", source_row=3, cells={"A3": "999", "C3": "MISSING"}, review_status="Excluida"),
        ]
        ImportRow.objects.bulk_create(rows)
        self.client.force_login(admin)

        result = self.client.get(f"/api/imports/{batch.id}/readiness").json()

        self.assertEqual(result["unresolved_reference_count"], 3)
        self.assertEqual(result["duplicate_reference_key_count"], 1)
        self.assertEqual(result["reference_counts"]["maintenance_asset"]["Sin coincidencia"], 1)
        self.assertEqual(result["reference_counts"]["material_maintenance"]["Sin coincidencia"], 1)
        self.assertEqual(result["excluded_rows"], 2)
        self.assertFalse(result["technical_precheck_clear"])
        self.assertFalse(result["operational_import_available"])

    def test_missing_technical_key_blocks_until_row_is_excluded(self):
        admin = User.objects.create_user(
            username="import-required-admin", password="Password123!",
            employee_number="IMP-REQ", first_name="Admin", role="Administrador",
        )
        batch = ImportBatch.objects.create(
            content_hash="d" * 64, filename="inventory.xlsx", uploaded_by=admin,
        )
        row = ImportRow.objects.create(
            batch=batch, sheet="ALMACEN", source_row=2, cells={"B2": "Aceite"},
        )
        self.client.force_login(admin)

        blocked = self.client.get(f"/api/imports/{batch.id}/readiness").json()
        self.assertEqual(blocked["mapping_issue_rows"], 1)
        row.review_status = "Excluida"
        row.save(update_fields=["review_status"])
        excluded = self.client.get(f"/api/imports/{batch.id}/readiness").json()
        self.assertEqual(excluded["mapping_issue_rows"], 0)
        self.assertTrue(excluded["technical_precheck_clear"])
        self.assertFalse(excluded["operational_import_available"])
        self.assertEqual(
            [item["code"] for item in excluded["operational_import_blockers"]],
            ["SOURCE_CLASSIFICATION_PENDING", "SOURCE_MAPPING_APPROVAL_PENDING", "TRANSACTIONAL_WRITER_DISABLED"],
        )


class OperationalAlertExportTests(TestCase):
    def test_xlsx_respects_area_scope_and_denies_requester(self):
        from zipfile import ZipFile
        from io import BytesIO

        from .models import OperationalAlert

        manager = User.objects.create_user(
            username="alert-export-manager", password="Password123!",
            employee_number="ALERT-M", first_name="Mantenimiento", role="Jefatura",
            area_permissions=["Prensas"],
        )
        requester = User.objects.create_user(
            username="alert-export-requester", password="Password123!",
            employee_number="ALERT-R", first_name="Solicitante", role="Solicitante",
        )
        visible = Asset.objects.create(
            code="ALERT-01", name="Prensa", area="Prensas",
            operational_status="Parada", operational_status_cause="Falla detectada",
        )
        hidden = Asset.objects.create(
            code="ALERT-02", name="Torno", area="Maquinado",
            operational_status="Parada", operational_status_cause="Falla detectada",
        )
        OperationalAlert.objects.create(
            source_key=f"asset_stopped:{visible.id}", kind="asset_stopped",
            source_id=visible.id, area="Prensas", title="Alerta visible", detail="Detalle",
        )
        OperationalAlert.objects.create(
            source_key=f"asset_stopped:{hidden.id}", kind="asset_stopped",
            source_id=hidden.id, area="Maquinado", title="Alerta restringida", detail="Detalle",
        )

        self.client.force_login(manager)
        response = self.client.get("/api/alerts/export.xlsx")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        with ZipFile(BytesIO(response.content)) as workbook:
            sheet = workbook.read("xl/worksheets/sheet1.xml").decode()
        self.assertIn("ALERT-01", sheet)
        self.assertNotIn("ALERT-02", sheet)

        self.client.force_login(requester)
        self.assertEqual(self.client.get("/api/alerts/export.xlsx").status_code, 403)


class SecurityAndContractTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="administrator", password="Password123!",
            employee_number="ADMIN", first_name="Admin", role="Administrador",
        )
        self.operator = User.objects.create_user(
            username="operator", password="Password123!",
            employee_number="OP-1", first_name="Operador", role="Solicitante",
        )
        self.asset = Asset.objects.create(
            code="MAQ-001", name="Prensa", area="Prensas",
        )

    def post(self, url, data, **headers):
        return self.client.post(url, json.dumps(data), content_type="application/json", **headers)

    def test_app_page_requests_current_import_readiness_script(self):
        from hashlib import sha256
        from pathlib import Path

        page = self.client.get("/")
        script = self.client.get("/app.js")
        script_path = Path(__file__).resolve().parent.parent / "static" / "app.js"
        expected_version = sha256(script_path.read_bytes()).hexdigest()[:12]
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, f"/app.js?v={expected_version}")
        self.assertNotContains(page, "__APP_JS_VERSION__")
        self.assertEqual(script.status_code, 200)
        self.assertContains(script, "Condiciones pendientes para autorizar una importación")

    def test_dashboard_contract_and_area_scope(self):
        other = Asset.objects.create(code="MAQ-002", name="Torno", area="Maquinado")
        for asset in (self.asset, other):
            self.client.force_login(self.operator)
            self.post("/api/orders", {
                "priority": "Alta", "classification": "Mantenimiento Correctivo",
                "asset_id": asset.id, "reported_failure": "No arranca",
            }, HTTP_IDEMPOTENCY_KEY=f"order-{asset.id}")
        self.post("/api/orders", {
            "priority": "Alta", "classification": "Mantenimiento Correctivo",
            "location": "Maquinado", "reported_failure": "Sin activo",
        }, HTTP_IDEMPOTENCY_KEY="order-without-asset")
        technician = User.objects.create_user(
            username="tech", password="Password123!", employee_number="T-1",
            first_name="Técnico", role="Técnico", area_permissions=["Prensas"],
        )
        self.client.force_login(technician)
        response = self.client.get("/api/dashboard")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["orders"]["total"], 1)
        self.assertEqual(data["assets"]["total"], 1)
        self.assertIn("byStatus", data)
        self.assertIn("byClassification", data)
        self.assertIn("preventives", data)
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get("/api/dashboard").status_code, 403)

    def test_operator_cannot_choose_initial_status_or_technician(self):
        self.client.force_login(self.operator)
        response = self.post("/api/orders", {
            "priority": "Alta", "classification": "Mantenimiento Correctivo",
            "asset_id": self.asset.id, "reported_failure": "No arranca",
            "status": "Completada", "technician_id": self.admin.id,
        }, HTTP_IDEMPOTENCY_KEY="operator-status")
        self.assertEqual(response.status_code, 201)
        from .models import WorkOrder
        order = WorkOrder.objects.get(pk=response.json()["id"])
        self.assertEqual(order.status, "Abierta")
        self.assertIsNone(order.technician_id)
        detail = self.client.get(f"/api/orders/{order.id}").json()
        self.assertNotIn("materials", detail)
        self.assertNotIn("material_cost", detail)

    def test_technician_cannot_transition_another_order(self):
        tech = User.objects.create_user(
            username="tech", password="Password123!", employee_number="T-1",
            first_name="Técnico", role="Técnico",
        )
        self.client.force_login(self.operator)
        created = self.post("/api/orders", {
            "priority": "Alta", "classification": "Mantenimiento Correctivo",
            "asset_id": self.asset.id, "reported_failure": "No arranca",
        }, HTTP_IDEMPOTENCY_KEY="unassigned-order")
        self.client.force_login(tech)
        response = self.post(
            f"/api/orders/{created.json()['id']}/transitions",
            {"to": "Cancelada", "version": 1},
        )
        self.assertEqual(response.status_code, 403)
        self.client.force_login(self.admin)
        assigned = self.client.patch(
            f"/api/orders/{created.json()['id']}",
            json.dumps({"technician_id": tech.id, "version": 1}),
            content_type="application/json",
        )
        self.assertEqual(assigned.status_code, 200)
        self.client.force_login(tech)
        transition = self.post(
            f"/api/orders/{created.json()['id']}/transitions",
            {"to": "Programada", "version": 2},
        )
        self.assertEqual(transition.status_code, 200)

    def test_password_change_is_required_and_keeps_session(self):
        self.admin.must_change_password = True
        self.admin.save(update_fields=["must_change_password"])
        self.client.force_login(self.admin)
        self.assertTrue(self.client.get("/api/auth/me").json()["must_change_password"])
        self.assertEqual(self.client.get("/api/dashboard").status_code, 403)
        changed = self.post("/api/auth/change-password", {
            "current_password": "Password123!", "new_password": "DifferentPassword123!",
        })
        self.assertEqual(changed.status_code, 200)
        self.assertFalse(self.client.get("/api/auth/me").json()["must_change_password"])
        self.assertEqual(self.client.get("/api/dashboard").status_code, 200)

    def test_csrf_cookie_and_header_are_required(self):
        client = Client(enforce_csrf_checks=True)
        page = client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("csrftoken", client.cookies)
        credentials = json.dumps({"username": "administrator", "password": "Password123!"})
        blocked = client.post("/api/auth/login", credentials, content_type="application/json")
        self.assertEqual(blocked.status_code, 403)
        allowed = client.post(
            "/api/auth/login", credentials, content_type="application/json",
            HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
        )
        self.assertEqual(allowed.status_code, 200)

    def test_import_records_each_stock_change(self):
        from .models import InventoryMovement
        self.client.force_login(self.admin)
        first = self.post("/api/inventory/import", {
            "items": [{"code": "MAT-1", "name": "Tornillo", "stock": 5}],
        })
        self.assertEqual(first.status_code, 200)
        second = self.post("/api/inventory/import", {
            "items": [{"code": "MAT-1", "name": "Tornillo", "stock": 7}],
        })
        self.assertEqual(second.status_code, 200)
        item = InventoryItem.objects.get(code="MAT-1")
        self.assertEqual(item.stock, 7)
        self.assertEqual(list(InventoryMovement.objects.filter(item=item).order_by("id").values_list("quantity", flat=True)), [5, 7])



    def test_time_entry_requires_assigned_technician(self):
        tech = User.objects.create_user(
            username="tech-time", password="Password123!", employee_number="T-2",
            first_name="Tech", role="T\u00e9cnico",
        )
        self.client.force_login(self.operator)
        created = self.post("/api/orders", {
            "priority": "Alta", "classification": "Mantenimiento Correctivo",
            "asset_id": self.asset.id, "reported_failure": "No arranca",
        }, HTTP_IDEMPOTENCY_KEY="time-order")
        self.client.force_login(tech)
        response = self.post(f"/api/orders/{created.json()['id']}/time-entries", {
            "started_at": "2026-09-22T08:00", "finished_at": "2026-09-22T09:00",
        })
        self.assertEqual(response.status_code, 403)
        self.client.force_login(self.admin)
        assigned = self.client.patch(
            f"/api/orders/{created.json()['id']}",
            json.dumps({"technician_id": tech.id, "version": 1}),
            content_type="application/json",
        )
        self.assertEqual(assigned.status_code, 200)
        self.client.force_login(tech)
        saved = self.post(f"/api/orders/{created.json()['id']}/time-entries", {
            "started_at": "2026-09-22T08:00", "finished_at": "2026-09-22T09:00",
        })
        self.assertEqual(saved.status_code, 201)
        self.assertEqual(saved.json()["labor_hours"], 1.0)

    def test_order_csv_escapes_spreadsheet_formulas(self):
        self.asset.name = "=2+2"
        self.asset.save(update_fields=["name"])
        self.client.force_login(self.operator)
        self.post("/api/orders", {
            "priority": "Alta", "classification": "Mantenimiento Correctivo",
            "asset_id": self.asset.id, "reported_failure": "No arranca",
        }, HTTP_IDEMPOTENCY_KEY="csv-order")
        self.client.force_login(self.admin)
        response = self.client.get("/api/orders/export.csv")
        self.assertEqual(response.status_code, 200)
        self.assertIn("'=2+2", response.content.decode("utf-8"))



    def test_restricted_manager_cannot_move_asset_to_other_area(self):
        manager = User.objects.create_user(
            username="manager", password="Password123!", employee_number="J-1",
            first_name="Manager", role="Jefatura", area_permissions=["Prensas"],
        )
        self.client.force_login(manager)
        response = self.post("/api/assets", {
            "code": "MAQ-002", "name": "Torno", "area": "Maquinado",
        })
        self.assertEqual(response.status_code, 403)
        changed = self.client.patch(
            f"/api/assets/{self.asset.id}",
            json.dumps({"area": "Maquinado"}), content_type="application/json",
        )
        self.assertEqual(changed.status_code, 403)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.area, "Prensas")


    def test_material_cost_tracks_exit_return_and_dashboard(self):
        from .models import WorkOrder
        self.client.force_login(self.operator)
        created = self.post("/api/orders", {
            "priority": "Alta", "classification": "Mantenimiento Correctivo",
            "asset_id": self.asset.id, "reported_failure": "No arranca",
        }, HTTP_IDEMPOTENCY_KEY="cost-order")
        order = WorkOrder.objects.get(pk=created.json()["id"])
        self.client.force_login(self.admin)
        item = InventoryItem.objects.create(
            code="MAT-COST", name="Refacción", category="Refacción",
            unit="pieza", stock=10, min_stock=2, max_stock=20, unit_cost=7,
        )
        issued = self.post(f"/api/inventory/{item.id}/movement", {
            "type": "Salida", "quantity": 3, "version": 1,
            "request_key": "cost-exit", "work_order_id": order.id,
        })
        self.assertEqual(issued.status_code, 200)
        self.assertEqual(self.client.get(f"/api/orders/{order.id}").json()["material_cost"], 21.0)
        self.assertEqual(self.client.get("/api/dashboard").json()["orders"]["material_cost"], 21.0)
        self.assertEqual(self.client.get(f"/api/assets/{self.asset.id}").json()["metrics"]["total_cost"], 21.0)
        returned = self.post(f"/api/inventory/{item.id}/movement", {
            "type": "Devolución", "quantity": 1, "version": 2,
            "request_key": "cost-return", "return_of": issued.json()["id"],
        })
        self.assertEqual(returned.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(float(order.material_cost), 14.0)
        detail = self.client.get(f"/api/orders/{order.id}").json()
        self.assertEqual(detail["material_cost"], 14.0)
        self.assertEqual(detail["materials"][0]["total"], 14.0)
        self.assertEqual(self.client.get("/api/dashboard").json()["orders"]["material_cost"], 14.0)
        self.assertEqual(self.client.get(f"/api/assets/{self.asset.id}").json()["metrics"]["total_cost"], 14.0)

    def test_preventive_compliance_includes_unscheduled_due_dates_and_reschedule(self):
        self.client.force_login(self.admin)
        plan = self.post("/api/preventives", {
            "asset_id": self.asset.id, "title": "Mensual",
            "frequency": "1 mes", "next_date": "2026-01-31",
        }).json()
        task = self.post(f"/api/preventives/{plan['id']}/tasks", {
            "title": "Lubricar", "interval_unit": "months",
            "interval_value": 1, "anchor_date": "2026-01-31", "version": 1,
        }).json()
        self.client.patch(f"/api/preventives/{plan['id']}/tasks/{task['id']}/applicability", json.dumps({"status":"Interna","reason":"Aplica a este activo","version":2}), content_type="application/json")
        url = f"/api/preventives/{plan['id']}/compliance?from=2026-02-01&to=2026-03-31&as_of=2026-04-01"
        before = self.client.get(url).json()
        self.assertEqual(before["counts"]["V"], 2)
        self.assertEqual(before["eligible"], 2)
        self.assertEqual(before["percentage"], 0.0)
        occurrence = self.post(f"/api/preventives/{plan['id']}/occurrences", {
            "task_id": task["id"], "occurrence_index": 1, "version": 3,
        }).json()
        moved = self.post(f"/api/preventives/{plan['id']}/occurrences/{occurrence['id']}/reschedule", {
            "scheduled_at": "2026-04-15", "reason": "Paro de producción",
            "version": 1,
        })
        self.assertEqual(moved.status_code, 200)
        after = self.client.get(url).json()
        self.assertEqual(after["counts"]["V"], 2)
        self.assertEqual(after["counts"]["R"], 1)
        self.assertEqual(after["occurrences"][0]["base_date"], "2026-02-28")
        self.assertTrue(after["occurrences"][0]["reprogrammed"])
        self.assertEqual(after["compliance_percent"], 0.0)
    def test_order_csv_respects_search_filter(self):
        self.client.force_login(self.operator)
        for marker in ("FILTRO-UNO", "FILTRO-DOS"):
            self.post("/api/orders", {
                "priority": "Media", "classification": "Mantenimiento Correctivo",
                "asset_id": self.asset.id, "reported_failure": marker,
            }, HTTP_IDEMPOTENCY_KEY=marker)
        self.client.force_login(self.admin)
        response = self.client.get("/api/orders/export.csv?q=FILTRO-UNO")
        body = response.content.decode("utf-8")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(body.count("OT-"), 1)
        self.assertNotIn("FILTRO-DOS", body)

    def test_time_entries_reject_overlap_between_orders_for_same_person(self):
        technician = User.objects.create_user(
            username="overlap-tech", password="Password123!",
            employee_number="T-OVERLAP", first_name="Técnico", role="Técnico",
        )
        self.client.force_login(self.operator)
        ids = []
        for marker in ("A", "B"):
            response = self.post("/api/orders", {
                "priority": "Media", "classification": "Mantenimiento Correctivo",
                "asset_id": self.asset.id, "reported_failure": marker,
            }, HTTP_IDEMPOTENCY_KEY=f"overlap-{marker}")
            ids.append(response.json()["id"])
        self.client.force_login(self.admin)
        self.client.patch(
            f"/api/orders/{ids[0]}",
            json.dumps({"technician_id": technician.id, "version": 1}),
            content_type="application/json",
        )
        self.client.patch(
            f"/api/orders/{ids[1]}",
            json.dumps({"technician_id": technician.id, "version": 1}),
            content_type="application/json",
        )
        first = self.post(f"/api/orders/{ids[0]}/time-entries", {
            "user_id": technician.id,
            "started_at": "2026-09-22T07:00", "finished_at": "2026-09-22T09:00",
        })
        self.assertEqual(first.status_code, 201)
        second = self.post(f"/api/orders/{ids[1]}/time-entries", {
            "user_id": technician.id,
            "started_at": "2026-09-22T08:00", "finished_at": "2026-09-22T10:00",
        })
        self.assertEqual(second.status_code, 409)
    def test_excel_preview_is_read_only_and_restricted(self):
        from io import BytesIO
        from zipfile import ZipFile
        from django.core.files.uploadedfile import SimpleUploadedFile
        stream = BytesIO()
        with ZipFile(stream, "w") as archive:
            archive.writestr(
                "xl/workbook.xml",
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="MAQUINAS" sheetId="1" r:id="rId1"/></sheets></workbook>',
            )
            archive.writestr(
                "xl/_rels/workbook.xml.rels",
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>',
            )
            archive.writestr(
                "xl/worksheets/sheet1.xml",
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="1"><c r="B1" t="inlineStr"><is><t>MAQUINA</t></is></c></row><row r="2"><c r="B2" t="inlineStr"><is><t>MAQ-001</t></is></c></row><row r="3"><c r="B3" t="inlineStr"><is><t>MAQ-001</t></is></c></row>'
                + ''.join(f'<row r="{number}"><c r="B{number}" t="inlineStr"><is><t>MAQ-{number:03}</t></is></c></row>' for number in range(4, 8))
                + '<row r="8"><c r="B8" t="inlineStr"><is><t>MAQ-008</t></is></c><c r="C8"><f>1+1</f><v>2</v></c></row></sheetData></worksheet>',
            )
        content = stream.getvalue()
        self.client.force_login(self.operator)
        blocked = self.client.post("/api/imports/preview", {
            "file": SimpleUploadedFile("fuente.xlsm", content),
        })
        self.assertEqual(blocked.status_code, 403)
        self.client.force_login(self.admin)
        response = self.client.post("/api/imports/preview", {
            "file": SimpleUploadedFile("fuente.xlsm", content),
        })
        self.assertEqual(response.status_code, 200)
        sheet = response.json()["sheets"][0]
        self.assertEqual(sheet["rows"], 8)
        self.assertEqual(len(sheet["conflicts"]), 2)
        self.assertEqual(len(sheet["preview"]), 6)
        self.assertEqual(Asset.objects.count(), 1)
        batch_id = response.json()["batch"]["id"]
        listing = self.client.get("/api/imports")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()[0]["row_count"], 8)
        self.assertEqual(listing.json()[0]["staged_row_count"], 8)
        detail = self.client.get(f"/api/imports/{batch_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["preview"]["sheets"][0]["conflicts"], sheet["conflicts"])
        all_rows = self.client.get(f"/api/imports/{batch_id}/rows?sheet=MAQUINAS")
        self.assertEqual(all_rows.status_code, 200)
        self.assertEqual(all_rows.json()["total"], 8)
        self.assertEqual(all_rows.json()["rows"][-1]["cells"]["B8"], "MAQ-008")
        self.assertEqual(all_rows.json()["rows"][-1]["formulas"]["C8"], "1+1")
        self.assertEqual(all_rows.json()["rows"][-1]["cell_details"]["C8"], {"kind": "number"})
        legacy_batch = ImportBatch.objects.get(pk=batch_id)
        legacy_batch.preview.pop("date_system")
        legacy_batch.save(update_fields=["preview"])
        ImportRow.objects.filter(batch_id=batch_id).update(cell_details={})
        repeated = self.client.post("/api/imports/preview", {
            "file": SimpleUploadedFile("otra-copia.xlsm", content),
        })
        self.assertTrue(repeated.json()["duplicate"])
        self.assertEqual(repeated.json()["batch"]["id"], batch_id)
        self.assertEqual(repeated.json()["batch"]["staged_row_count"], 8)
        self.assertEqual(ImportBatch.objects.get(pk=batch_id).preview["date_system"], "1900")
        self.assertEqual(self.client.get(f"/api/imports/{batch_id}/rows?sheet=MAQUINAS").json()["rows"][-1]["cell_details"]["C8"], {"kind": "number"})
        row_id = all_rows.json()["rows"][1]["id"]
        review_url = f"/api/imports/{batch_id}/rows/{row_id}"
        missing_asset = self.client.patch(review_url, json.dumps({
            "status": "Propuesta", "asset_id": "inválido", "reason": "Mismo equipo", "version": 1,
        }), content_type="application/json")
        self.assertEqual(missing_asset.status_code, 400)
        proposed = self.client.patch(review_url, json.dumps({
            "status": "Propuesta", "asset_id": self.asset.id, "reason": "Código confirmado", "version": 1,
        }), content_type="application/json")
        self.assertEqual(proposed.status_code, 200)
        self.assertEqual(proposed.json()["review_status"], "Propuesta")
        self.assertEqual(proposed.json()["proposed_asset_code"], "MAQ-001")
        stale = self.client.patch(review_url, json.dumps({
            "status": "Excluida", "reason": "Registro duplicado", "version": 1,
        }), content_type="application/json")
        self.assertEqual(stale.status_code, 409)
        excluded = self.client.patch(review_url, json.dumps({
            "status": "Excluida", "reason": "Registro duplicado", "version": 2,
        }), content_type="application/json")
        self.assertEqual(excluded.status_code, 200)
        self.assertIsNone(excluded.json()["proposed_asset_id"])
        self.assertEqual(self.client.get(f"/api/imports/{batch_id}").json()["batch"]["review_counts"],
                         {"Pendiente": 7, "Excluida": 1, "Propuesta": 0})
        self.assertEqual(AuditLog.objects.filter(entity_type="import_row", entity_id=row_id, action="reviewed").count(), 2)
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get("/api/imports").status_code, 403)
        self.assertEqual(self.client.get(f"/api/imports/{batch_id}").status_code, 403)
        self.assertEqual(self.client.get(f"/api/imports/{batch_id}/rows").status_code, 403)
        self.assertEqual(self.client.patch(review_url, json.dumps({
            "status": "Pendiente", "reason": "Revisar de nuevo", "version": 3,
        }), content_type="application/json").status_code, 403)
        self.client.force_login(self.admin)
        short_reason = self.client.patch(f"/api/imports/{batch_id}", json.dumps({"reason": "No"}), content_type="application/json")
        self.assertEqual(short_reason.status_code, 400)
        discarded = self.client.patch(f"/api/imports/{batch_id}", json.dumps({"reason": "Archivo de ejemplo"}), content_type="application/json")
        self.assertEqual(discarded.status_code, 200)
        self.assertEqual(discarded.json()["status"], "Descartado")
        self.assertEqual(self.client.get(f"/api/imports/{batch_id}").json()["batch"]["discard_reason"], "Archivo de ejemplo")
        self.assertEqual(self.client.patch(review_url, json.dumps({
            "status": "Pendiente", "reason": "Revisar de nuevo", "version": 3,
        }), content_type="application/json").status_code, 409)
        self.assertEqual(Asset.objects.count(), 1)
    def test_calendar_codes_start_after_header(self):
        from io import BytesIO
        from zipfile import ZipFile
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .workbook_preview import preview_workbook
        stream = BytesIO()
        with ZipFile(stream, "w") as archive:
            archive.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="CALENDARIO" sheetId="1" r:id="rId1"/></sheets></workbook>')
            archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
            archive.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="12"><c r="B12" t="inlineStr"><is><t>MAQ-001</t></is></c></row><row r="13"><c r="B13" t="inlineStr"><is><t>MAQ-001</t></is></c></row><row r="14"><c r="B14" t="inlineStr"><is><t>MAQ-001</t></is></c></row></sheetData></worksheet>')
        source = SimpleUploadedFile("calendario.xlsx", stream.getvalue())
        result = preview_workbook(source, {"maq-001"})
        self.assertEqual([row["source_code"] for row in result["staged_rows"]], ["", "MAQ-001", "MAQ-001"])
        self.assertEqual([row["issues"] for row in result["staged_rows"]], [[], ["Ya existe en Django"], ["Repetido en esta hoja"]])
    def test_import_reconciliation_groups_sources_and_approved_equivalences(self):
        batch = ImportBatch.objects.create(content_hash="a" * 64, filename="fuente.xlsx", uploaded_by=self.admin)
        for sheet, number, code in [
            ("MAQUINAS", 2, "MAQ-001"), ("MAQUINAS", 3, "maq-001"),
            ("BASE DE DATOS", 2, "MAQ-001"), ("CALENDARIO", 13, "OLD-001"),
            ("CALENDARIO", 14, ""),
        ]:
            brand_column = "C" if sheet == "MAQUINAS" else "D" if sheet == "BASE DE DATOS" else "F"
            brand = "OAK" if number != 3 else "Healing"
            ImportRow.objects.create(batch=batch, sheet=sheet, source_row=number,
                                     source_code=code, cells={f"{brand_column}{number}": brand})
        AssetCodeEquivalence.objects.create(
            asset=self.asset, code="OLD-001", code_key="old-001", status="Aprobada",
            notes="Código histórico validado", proposed_by=self.admin, reviewed_by=self.admin,
        )
        self.client.force_login(self.admin)
        response = self.client.get(f"/api/imports/{batch.id}/reconciliation")
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["source_rows_with_code"], 4)
        self.assertEqual(result["source_rows_without_code"], 1)
        current, historical = result["groups"]
        self.assertEqual(current["source_row_count"], 3)
        self.assertTrue(current["repeated_within_sheet"])
        self.assertEqual(current["sheet_counts"], {"MAQUINAS": 2, "BASE DE DATOS": 1})
        self.assertEqual(current["asset_matches"][0]["via"], "Código vigente")
        self.assertEqual(current["attribute_variants"], {"brand": ["OAK", "Healing"]})
        self.assertEqual(historical["asset_matches"][0]["via"], "Equivalencia aprobada")
        self.assertEqual(self.client.get(f"/api/imports/{batch.id}/reconciliation?page=0").status_code, 400)
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(f"/api/imports/{batch.id}/reconciliation").status_code, 403)
    def test_source_mapping_uses_sheet_specific_columns_without_inventing_status(self):
        from .import_mapping import map_source_row
        machine = map_source_row("MAQUINAS", 2, {"A2": "6", "B2": "ALENM008", "C2": "OAK", "K2": "CORTE"})
        calendar = map_source_row("CALENDARIO", 13, {"B13": "ALENM008", "C13": "REBABEO", "D13": "1"})
        database = map_source_row("BASE DE DATOS", 2, {"A2": "ALENM008", "B2": "REBABEO", "D2": "OAK", "G2": "APLICA"})
        self.assertEqual(machine["fields"], {"source_id": "6", "code": "ALENM008", "brand": "OAK", "area": "CORTE", "code_key": "alenm008"})
        self.assertEqual(calendar["fields"]["name"], "REBABEO")
        self.assertEqual(database["fields"]["brand"], "OAK")
        self.assertNotIn("review_points", database["fields"])
        self.assertEqual(map_source_row("CALENDARIO", 12, {"B12": "CODIGO"})["kind"], "unmapped")
        history = map_source_row("MANTENIMIENTOS", 2, {"A2": "1", "B2": "6", "C2": "46224", "I2": "1"})
        self.assertEqual(history["fields"]["event_date_raw"], "46224")
        self.assertEqual(history["fields"]["performed_raw"], "1")
        self.assertNotIn("event_date", history["fields"])
        kaizen = map_source_row("CELDA AUTOMATIZACION", 6, {"A6": "1", "B6": "Pendiente", "C6": "25", "G6": "Comentario"})
        self.assertEqual(kaizen["fields"], {"source_item": "1", "description": "Pendiente", "comments": "Comentario"})
        missing_inventory_code = map_source_row("ALMACEN", 2, {"B2": "Aceite"})
        self.assertEqual(missing_inventory_code["issues"], ["Falta código de insumo; revisar la fila antes de conciliar"])
    def test_workbook_preserves_raw_cells_and_marks_excel_dates_and_errors(self):
        from io import BytesIO
        from zipfile import ZipFile
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .workbook_preview import excel_temporal_value, preview_workbook
        self.assertEqual(excel_temporal_value("61", "date", False), "1900-03-01")
        self.assertIsNone(excel_temporal_value("60", "date", False))
        self.assertEqual(excel_temporal_value("0", "date", True), "1904-01-01")
        stream = BytesIO()
        with ZipFile(stream, "w") as archive:
            archive.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><workbookPr date1904="0"/><sheets><sheet name="MANTENIMIENTOS" sheetId="1" r:id="rId1"/></sheets></workbook>')
            archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
            archive.writestr("xl/styles.xml", '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><cellXfs count="2"><xf numFmtId="0"/><xf numFmtId="14"/></cellXfs></styleSheet>')
            archive.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row r="2"><c r="A2"><v>1</v></c><c r="C2" s="1"><v>61</v></c><c r="J2" t="e"><v>#DIV/0!</v></c><c r="I2" t="b"><v>1</v></c></row></sheetData></worksheet>')
        source = SimpleUploadedFile("historial.xlsx", stream.getvalue())
        result = preview_workbook(source, set())
        row = result["staged_rows"][0]
        self.assertEqual(result["date_system"], "1900")
        self.assertEqual(row["cells"]["C2"], "61")
        self.assertEqual(row["cell_details"]["C2"], {"kind": "date", "iso": "1900-03-01", "date_system": "1900"})
        self.assertEqual(row["cell_details"]["J2"], {"kind": "error", "value": "#DIV/0!"})
        self.assertEqual(row["cell_details"]["I2"], {"kind": "boolean", "value": True})
        self.assertTrue(any("J2" in issue for issue in row["issues"]))
    def test_preventive_order_requires_checklist_before_validation(self):
        technician = User.objects.create_user(
            username="preventive-tech", password="Password123!",
            employee_number="T-PM", first_name="Técnico", role="Técnico",
        )
        self.client.force_login(self.admin)
        plan = self.post("/api/preventives", {
            "asset_id": self.asset.id, "title": "Revisión",
            "frequency": "1 mes", "next_date": "2026-09-22",
            "responsible_id": technician.id,
        }).json()
        task = self.post(f"/api/preventives/{plan['id']}/tasks", {
            "title": "Revisar aceite", "interval_unit": "months",
            "interval_value": 1, "anchor_date": "2026-09-22", "version": 1,
        }).json()
        self.client.patch(f"/api/preventives/{plan['id']}/tasks/{task['id']}/applicability", json.dumps({"status":"Interna","reason":"Aplica al activo","version":2}), content_type="application/json")
        item = self.post(f"/api/preventives/{plan['id']}/tasks/{task['id']}/checklist", {
            "position": 1, "prompt": "Nivel correcto", "required": True,
        }).json()
        occurrence = self.post(f"/api/preventives/{plan['id']}/occurrences", {
            "task_id": task["id"], "occurrence_index": 0, "version": 3,
        }).json()
        order_id = occurrence["work_order_id"]
        changed = self.client.patch(f"/api/orders/{order_id}", json.dumps({
            "actions": "Aceite revisado", "closure_notes": "Prueba correcta", "version": 1,
        }), content_type="application/json")
        self.assertEqual(changed.status_code, 200)
        time = self.post(f"/api/orders/{order_id}/time-entries", {
            "user_id": technician.id,
            "started_at": "2026-09-22T07:00", "finished_at": "2026-09-22T08:00",
        })
        self.assertEqual(time.status_code, 201)
        started = self.post(f"/api/orders/{order_id}/transitions", {
            "to": "En proceso", "version": time.json()["version"],
        })
        self.assertEqual(started.status_code, 200)
        blocked = self.post(f"/api/orders/{order_id}/transitions", {
            "to": "Pendiente de validación", "version": started.json()["version"],
        })
        self.assertEqual(blocked.status_code, 400)
        no_reason = self.post(f"/api/preventives/{plan['id']}/occurrences/{occurrence['id']}/checklist", {
            "answers": [{"item_id": item["id"], "answer": "N/A"}],
        })
        self.assertEqual(no_reason.status_code, 400)
        answered = self.post(f"/api/preventives/{plan['id']}/occurrences/{occurrence['id']}/checklist", {
            "answers": [{"item_id": item["id"], "answer": "Sí"}],
        })
        self.assertEqual(answered.status_code, 200)
        finished = self.post(f"/api/orders/{order_id}/transitions", {
            "to": "Pendiente de validación", "version": started.json()["version"],
        })
        self.assertEqual(finished.status_code, 200)
        validated = self.post(f"/api/orders/{order_id}/validate", {"version": finished.json()["version"]})
        self.assertEqual(validated.status_code, 200)

    def test_work_sessions_pause_and_reject_state_change_while_running(self):
        technician = User.objects.create_user(
            username="session-tech", password="Password123!", employee_number="T-SESSION",
            first_name="Técnico", role="Técnico",
        )
        self.client.force_login(self.operator)
        order_id = self.post("/api/orders", {
            "priority": "Alta", "classification": "Mantenimiento Correctivo",
            "asset_id": self.asset.id, "reported_failure": "Falla de prueba",
        }).json()["id"]
        self.client.force_login(self.admin)
        assigned = self.client.patch(f"/api/orders/{order_id}", json.dumps({
            "technician_id": technician.id, "version": 1,
        }), content_type="application/json").json()
        started_order = self.post(f"/api/orders/{order_id}/transitions", {
            "to": "En proceso", "version": assigned["version"],
        }).json()
        self.client.force_login(technician)
        first = self.post(f"/api/orders/{order_id}/time-entries/actions", {
            "action": "start", "version": started_order["version"],
        })
        self.assertEqual(first.status_code, 200)
        duplicate = self.post(f"/api/orders/{order_id}/time-entries/actions", {
            "action": "start", "version": first.json()["version"],
        })
        self.assertEqual(duplicate.status_code, 409)
        blocked = self.post(f"/api/orders/{order_id}/transitions", {
            "to": "Pausada", "version": first.json()["version"],
        })
        self.assertEqual(blocked.status_code, 400)
        missing_reason = self.post(f"/api/orders/{order_id}/time-entries/actions", {
            "action": "pause", "version": first.json()["version"],
        })
        self.assertEqual(missing_reason.status_code, 400)
        paused = self.post(f"/api/orders/{order_id}/time-entries/actions", {
            "action": "pause", "reason": "Espera de material", "version": first.json()["version"],
        })
        self.assertEqual(paused.status_code, 200)
        resumed = self.post(f"/api/orders/{order_id}/time-entries/actions", {
            "action": "start", "version": paused.json()["version"],
        })
        self.assertEqual(resumed.status_code, 200)
        ended = self.post(f"/api/orders/{order_id}/time-entries/actions", {
            "action": "finish", "version": resumed.json()["version"],
        })
        self.assertEqual(ended.status_code, 200)
        entries = self.client.get(f"/api/orders/{order_id}/time-entries").json()
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["pause_reason"], "Espera de material")
        self.assertTrue(all(entry["finished_at"] for entry in entries))

    def test_two_participants_and_midnight_manual_hours(self):
        technicians = [User.objects.create_user(
            username=f"manual-tech-{index}", password="Password123!",
            employee_number=f"T-MAN-{index}", first_name=f"Técnico {index}", role="Técnico",
        ) for index in (1, 2)]
        self.client.force_login(self.operator)
        order_id = self.post("/api/orders", {
            "priority": "Media", "classification": "Mantenimiento Correctivo",
            "asset_id": self.asset.id, "reported_failure": "Reparación nocturna",
        }).json()["id"]
        self.client.force_login(self.admin)
        assigned = self.client.patch(f"/api/orders/{order_id}", json.dumps({
            "technician_id": technicians[0].id, "participant_ids": [technicians[1].id],
            "version": 1,
        }), content_type="application/json")
        self.assertEqual(assigned.status_code, 200)
        for technician in technicians:
            saved = self.post(f"/api/orders/{order_id}/time-entries", {
                "user_id": technician.id, "started_at": "2026-09-22T23:00",
                "finished_at": "2026-09-23T01:00",
            })
            self.assertEqual(saved.status_code, 201)
        self.assertEqual(saved.json()["labor_hours"], 4.0)
        detail = self.client.get(f"/api/orders/{order_id}").json()
        self.assertEqual(len(detail["participants"]), 1)
        self.assertEqual(len(detail["time_entries"]), 2)
        first_entry_id = detail["time_entries"][0]["id"]
        missing_reason = self.client.patch(f"/api/orders/{order_id}/time-entries/{first_entry_id}", json.dumps({
            "started_at": "2026-09-22T22:00", "finished_at": "2026-09-23T01:00",
            "version": saved.json()["version"],
        }), content_type="application/json")
        self.assertEqual(missing_reason.status_code, 400)
        corrected = self.client.patch(f"/api/orders/{order_id}/time-entries/{first_entry_id}", json.dumps({
            "started_at": "2026-09-22T22:00", "finished_at": "2026-09-23T01:00",
            "reason": "Captura tardía revisada", "version": saved.json()["version"],
        }), content_type="application/json")
        self.assertEqual(corrected.status_code, 200)
        self.assertEqual(corrected.json()["labor_hours"], 5.0)
        from .models import AuditLog
        correction = AuditLog.objects.get(entity_type="time_entry", entity_id=first_entry_id, action="corrected")
        self.assertEqual(correction.reason, "Captura tardía revisada")
        self.assertNotEqual(correction.before["started_at"], correction.after["started_at"])
        new_hours = self.client.patch(f"/api/orders/{order_id}", json.dumps({
            "started_at": "2026-09-22T22:00", "finished_at": "2026-09-23T01:00",
            "version": corrected.json()["version"],
        }), content_type="application/json")
        self.assertEqual(new_hours.status_code, 200)
        self.assertEqual(self.client.get(f"/api/orders/{order_id}").json()["labor_hours"], 6.0)
        self.client.force_login(self.operator)
        forbidden = self.post(f"/api/orders/{order_id}/time-entries/actions", {
            "action": "start", "version": corrected.json()["version"],
        })
        self.assertEqual(forbidden.status_code, 403)

    def test_cancel_requires_manager_and_reason(self):
        technician = User.objects.create_user(
            username="cancel-tech", password="Password123!", employee_number="T-CANCEL",
            first_name="Técnico", role="Técnico",
        )
        self.client.force_login(self.operator)
        order_id = self.post("/api/orders", {
            "priority": "Media", "classification": "Mantenimiento Correctivo",
            "asset_id": self.asset.id, "reported_failure": "Solicitud cancelable",
        }).json()["id"]
        self.client.force_login(self.admin)
        assigned = self.client.patch(f"/api/orders/{order_id}", json.dumps({
            "technician_id": technician.id, "version": 1,
        }), content_type="application/json").json()
        self.client.force_login(technician)
        forbidden = self.post(f"/api/orders/{order_id}/transitions", {
            "to": "Cancelada", "reason": "Duplicada", "version": assigned["version"],
        })
        self.assertEqual(forbidden.status_code, 403)
        self.client.force_login(self.admin)
        missing_reason = self.post(f"/api/orders/{order_id}/transitions", {
            "to": "Cancelada", "version": assigned["version"],
        })
        self.assertEqual(missing_reason.status_code, 400)
        cancelled = self.post(f"/api/orders/{order_id}/transitions", {
            "to": "Cancelada", "reason": "Solicitud duplicada", "version": assigned["version"],
        })
        self.assertEqual(cancelled.status_code, 200)
        reopened = self.post(f"/api/orders/{order_id}/transitions", {
            "to": "Abierta", "reason": "Se requiere trabajo", "version": cancelled.json()["version"],
        })
        self.assertEqual(reopened.status_code, 200)
        detail = self.client.get(f"/api/orders/{order_id}").json()
        self.assertEqual(detail["status"], "Abierta")
        self.assertTrue(any(event["event"] == "Cancelada → Abierta" for event in detail["events"]))

    def test_one_downtime_can_link_two_orders_without_releasing_asset_on_order_close(self):
        self.client.force_login(self.operator)
        ids = [self.post("/api/orders", {
            "priority": "Paro de máquina", "classification": "Mantenimiento Correctivo",
            "asset_id": self.asset.id, "reported_failure": f"Falla {index}",
            "machine_stopped": "no",
        }).json()["id"] for index in (1, 2)]
        self.client.force_login(self.admin)
        created = self.post("/api/downtime-events", {
            "asset_id": self.asset.id, "cause": "Motor detenido",
            "started_at": "2026-09-22T07:00", "work_order_ids": ids,
        })
        self.assertEqual(created.status_code, 201)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.operational_status, "Parada")
        events = self.client.get("/api/downtime-events").json()
        self.assertEqual(events[0]["order_count"], 2)
        self.assertEqual(set(events[0]["work_order_ids"]), set(ids))
        cancelled = self.post(f"/api/orders/{ids[0]}/transitions", {
            "to": "Cancelada", "reason": "OT duplicada", "version": 1,
        })
        self.assertEqual(cancelled.status_code, 200)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.operational_status, "Parada")
        closed = self.client.patch(f"/api/downtime-events/{created.json()['id']}", json.dumps({
            "finished_at": "2026-09-22T09:00", "reason": "Equipo liberado",
        }), content_type="application/json")
        self.assertEqual(closed.status_code, 200)
        self.assertEqual(closed.json()["asset_status"], "Operativa")
        self.assertEqual(self.client.get("/api/downtime-events").json()[0]["order_count"], 2)

    def test_critical_priority_requires_confirmation_and_links_existing_downtime(self):
        self.client.force_login(self.operator)
        data = {"priority": "Paro de máquina", "classification": "Mantenimiento Correctivo",
                "asset_id": self.asset.id, "reported_failure": "Equipo detenido"}
        self.assertEqual(self.post("/api/orders", data).status_code, 400)
        first = self.post("/api/orders", data | {
            "machine_stopped": "yes", "downtime_cause": "Motor sin movimiento",
        })
        self.assertEqual(first.status_code, 201)
        second = self.post("/api/orders", data | {
            "machine_stopped": "yes", "downtime_cause": "Motor sin movimiento",
        })
        self.assertEqual(second.status_code, 201)
        self.client.force_login(self.admin)
        events = self.client.get("/api/downtime-events").json()
        self.assertEqual(len(events), 1)
        self.assertEqual(set(events[0]["work_order_ids"]), {first.json()["id"], second.json()["id"]})
        dashboard = self.client.get("/api/dashboard").json()
        self.assertEqual(dashboard["assets"]["stopped"], 1)
        self.assertEqual(dashboard["orders"]["critical"], 2)
        self.assertEqual(dashboard["assets"]["stopped_details"][0]["cause"], "Motor sin movimiento")

    def test_cancel_and_reopen_keep_material_consumption_once(self):
        self.client.force_login(self.operator)
        order_id = self.post("/api/orders", {
            "priority": "Alta", "classification": "Mantenimiento Correctivo",
            "asset_id": self.asset.id, "reported_failure": "Reparar fixture",
        }).json()["id"]
        self.client.force_login(self.admin)
        item = InventoryItem.objects.create(
            code="MAT-CANCEL", name="Pieza", category="Refacción", unit="pieza",
            stock=10, min_stock=0, max_stock=20, unit_cost=25,
        )
        issued = self.post(f"/api/inventory/{item.id}/movement", {
            "type": "Salida", "quantity": 3, "version": 1,
            "request_key": "cancel-material", "work_order_id": order_id,
        })
        self.assertEqual(issued.status_code, 200)
        no_disposition = self.post(f"/api/orders/{order_id}/transitions", {
            "to": "Cancelada", "reason": "Orden duplicada", "version": 1,
        })
        self.assertEqual(no_disposition.status_code, 400)
        cancelled = self.post(f"/api/orders/{order_id}/transitions", {
            "to": "Cancelada", "reason": "Orden duplicada",
            "material_disposition": "Consumo conservado; revisar devolución", "version": 1,
        })
        self.assertEqual(cancelled.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.stock, 7)
        rejected = self.post(f"/api/inventory/{item.id}/movement", {
            "type": "Salida", "quantity": 1, "version": item.version,
            "request_key": "after-cancel", "work_order_id": order_id,
        })
        self.assertEqual(rejected.status_code, 400)
        reopened = self.post(f"/api/orders/{order_id}/transitions", {
            "to": "Abierta", "reason": "Trabajo necesario", "version": cancelled.json()["version"],
        })
        self.assertEqual(reopened.status_code, 200)
        replay = self.post(f"/api/inventory/{item.id}/movement", {
            "type": "Salida", "quantity": 3, "version": 1,
            "request_key": "cancel-material", "work_order_id": order_id,
        })
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()["replayed"])
        item.refresh_from_db()
        self.assertEqual(item.stock, 7)
        self.assertEqual(self.client.get(f"/api/orders/{order_id}").json()["material_cost"], 75.0)
