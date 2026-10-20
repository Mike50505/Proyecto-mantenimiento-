import json
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from .models import (Asset, AuditLog, InventoryItem, InventoryMovement, MaintenanceMaterial,
                     PreventivePlan, TimeEntry, User, WorkOrder)
from .planner import plan_preventive_window


class AuditedDeletionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="delete-admin", employee_number="DEL-A", role="Administrador")
        self.member = User.objects.create_user(username="delete-member", employee_number="DEL-M", role="Técnico")
        self.asset = Asset.objects.create(code="DEL-ASSET", name="Equipo", area="Prensas")
        self.item = InventoryItem.objects.create(code="DEL-ITEM", name="Refacción", category="Refacción", unit="pieza", stock=5)
        self.order = WorkOrder.objects.create(folio="DEL-OT", requester=self.admin, requested_at=timezone.now(),
                                             asset=self.asset, priority="Media", classification="Correctivo", reported_failure="Falla")
        self.client.force_login(self.admin)

    def delete(self, kind, record, **data):
        body = {"reason": "Registro duplicado", **data}
        if hasattr(record, "version") and "version" not in data: body["version"] = record.version
        return self.client.delete(f"/api/{kind}/{record.pk}", json.dumps(body), content_type="application/json")

    def restrict(self, module, action, areas=None):
        self.member.custom_permissions = True
        self.member.module_permissions = [module]
        self.member.action_permissions = [action]
        self.member.area_permissions = areas or []
        self.member.save()
        self.client.force_login(self.member)

    def test_delete_permissions_are_separate_from_edit_permissions(self):
        for kind, record, edit in [("orders", self.order, "orders.edit"), ("assets", self.asset, "assets.edit"),
                                   ("inventory", self.item, "inventory.adjust"), ("users", self.admin, "users.manage")]:
            with self.subTest(kind=kind):
                self.restrict(kind, edit)
                self.assertEqual(self.delete(kind, record).status_code, 403)
                self.assertIsNone(type(record).all_objects.get(pk=record.pk).deleted_at)

    def test_hidden_module_blocks_delete_even_with_delete_permission(self):
        self.restrict("inventory", "orders.delete")
        self.assertEqual(self.delete("orders", self.order).status_code, 403)

    def test_deleted_order_is_hidden_and_history_is_preserved(self):
        self.assertEqual(self.delete("orders", self.order).status_code, 200)
        self.assertFalse(WorkOrder.objects.filter(pk=self.order.pk).exists())
        row = WorkOrder.all_objects.get(pk=self.order.pk)
        self.assertEqual(row.status, "Cancelada")
        self.assertEqual(row.deleted_by, self.admin)
        self.assertTrue(row.events.filter(event="Borrada").exists())
        self.assertEqual(self.client.get(f"/api/orders/{row.pk}").status_code, 404)
        self.assertEqual(self.client.get("/api/orders").json(), [])
        self.assertNotIn(row.folio, self.client.get("/api/orders/export.csv").content.decode())
        event = AuditLog.objects.get(entity_type="work_order", entity_id=row.pk, action="deleted")
        self.assertEqual(event.before["folio"], row.folio)
        self.assertEqual(event.before["status"], "Abierta")
        self.assertTrue(event.after["deleted"])
        self.assertEqual(event.reason, "Registro duplicado")

    def test_inventory_deletion_retains_stock_and_movements(self):
        movement = InventoryMovement.objects.create(item=self.item, type="Ajuste", quantity=5, user=self.admin,
                                                    request_key="delete-ledger", request_hash="hash")
        self.assertEqual(self.delete("inventory", self.item).status_code, 200)
        archived = InventoryItem.all_objects.get(pk=self.item.pk)
        self.assertEqual(archived.stock, Decimal("5"))
        self.assertFalse(archived.active)
        self.assertTrue(InventoryMovement.objects.filter(pk=movement.pk).exists())
        self.assertEqual(self.client.get("/api/inventory").json(), [])
        self.assertEqual(self.client.post(f"/api/inventory/{self.item.pk}/movement", "{}", content_type="application/json").status_code, 404)
        self.assertTrue(AuditLog.objects.filter(entity_type="inventory_item", action="deleted").exists())

    def test_material_history_survives_order_and_inventory_deletion(self):
        movement = InventoryMovement.objects.create(item=self.item, type="Salida", quantity=1, user=self.admin,
                                                    work_order=self.order, request_key="delete-material", request_hash="hash")
        material = MaintenanceMaterial.objects.create(work_order=self.order, item=self.item, code=self.item.code,
                                                      description=self.item.name, quantity=1, unit_cost=2, movement=movement)
        self.assertEqual(self.delete("orders", self.order).status_code, 200)
        self.assertEqual(self.delete("inventory", self.item).status_code, 200)
        material.refresh_from_db()
        self.assertEqual(material.work_order.folio, "DEL-OT")
        self.assertEqual(material.item.code, "DEL-ITEM")

    def test_user_deletion_disables_existing_sessions_and_retains_history(self):
        historical = WorkOrder.objects.create(folio="DEL-HISTORY", requester=self.member, requested_at=timezone.now(),
                                              priority="Media", classification="Correctivo", reported_failure="Falla", status="Completada")
        from django.test import Client
        previous_session = Client()
        previous_session.force_login(self.member)
        self.assertEqual(self.delete("users", self.member).status_code, 200)
        self.assertFalse(User.objects.filter(pk=self.member.pk).exists())
        archived = User.all_objects.get(pk=self.member.pk)
        self.assertFalse(archived.is_active)
        self.assertEqual(previous_session.get("/api/auth/me").status_code, 401)
        historical.refresh_from_db()
        self.assertEqual(historical.requester.employee_number, "DEL-M")
        self.assertTrue(AuditLog.objects.filter(entity_type="user", entity_id=self.member.pk, action="deleted").exists())

    def test_cannot_delete_self_or_administrator(self):
        self.assertEqual(self.delete("users", self.admin).status_code, 409)
        chief = User.objects.create_user(username="delete-chief", employee_number="DEL-C", role="Jefe de mantenimiento")
        self.client.force_login(chief)
        self.assertEqual(self.delete("users", self.admin).status_code, 409)

    def test_cannot_delete_user_with_outstanding_assignments(self):
        self.order.technician = self.member
        self.order.save()
        self.assertEqual(self.delete("users", self.member).status_code, 409)
        self.assertIsNone(User.objects.get(pk=self.member.pk).deleted_at)

    def test_cannot_delete_order_with_running_session(self):
        TimeEntry.objects.create(work_order=self.order, user=self.member, started_at=timezone.now())
        self.assertEqual(self.delete("orders", self.order).status_code, 409)

    def test_asset_deletion_requires_resolving_open_work(self):
        self.assertEqual(self.delete("assets", self.asset).status_code, 409)
        self.delete("orders", self.order)
        self.assertEqual(self.delete("assets", self.asset).status_code, 200)
        self.assertFalse(Asset.objects.filter(pk=self.asset.pk).exists())
        self.assertEqual(self.client.get("/api/assets").json(), [])
        archived_order = WorkOrder.all_objects.get(pk=self.order.pk)
        self.assertEqual(archived_order.asset.code, "DEL-ASSET")

    def test_asset_deletion_excludes_preventives_and_planner(self):
        self.delete("orders", self.order)
        plan = PreventivePlan.objects.create(asset=self.asset, title="Plan", frequency="Mensual", next_date=date.today())
        self.assertEqual(self.delete("assets", self.asset).status_code, 200)
        self.assertTrue(PreventivePlan.objects.filter(pk=plan.pk).exists())
        self.assertEqual(self.client.get("/api/preventives").json(), [])
        self.assertEqual(self.client.get(f"/api/preventives/{plan.pk}/tasks").status_code, 404)
        self.assertEqual(plan_preventive_window(date.today(), date.today())["plans"], 0)

    def test_area_permissions_apply_to_deletion_and_deleted_audit(self):
        self.restrict("orders", "orders.delete", ["Corte"])
        self.assertEqual(self.delete("orders", self.order).status_code, 403)
        self.member.area_permissions = ["Prensas"]
        self.member.save()
        self.assertEqual(self.delete("orders", self.order).status_code, 200)
        self.member.module_permissions = ["audit"]
        self.member.action_permissions = ["audit.read"]
        self.member.save()
        response = self.client.get("/api/audit?action=deleted")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)
        self.member.area_permissions = ["Corte"]
        self.member.save()
        self.assertEqual(self.client.get("/api/audit?action=deleted").json()["total"], 0)

    def test_requester_cannot_delete_another_request_even_when_granted_permission(self):
        self.member.role = "Solicitante"
        self.member.save()
        self.restrict("orders", "orders.delete")
        self.assertEqual(self.delete("orders", self.order).status_code, 403)

    def test_reason_is_required_and_stale_versions_are_rejected(self):
        self.assertEqual(self.delete("orders", self.order, reason=" ").status_code, 400)
        self.assertEqual(self.delete("orders", self.order, version=99).status_code, 409)
        self.assertEqual(self.delete("inventory", self.item, version=99).status_code, 409)
        self.assertEqual(AuditLog.objects.filter(action="deleted").count(), 0)

    def test_retry_does_not_create_duplicate_audit(self):
        self.assertEqual(self.delete("orders", self.order).status_code, 200)
        self.assertEqual(self.delete("orders", self.order).status_code, 200)
        self.assertEqual(AuditLog.objects.filter(action="deleted").count(), 1)

    def test_audit_failure_rolls_back_the_deletion(self):
        with patch("maintenance.views.audit", side_effect=RuntimeError("Audit unavailable")):
            with self.assertRaises(RuntimeError): self.delete("orders", self.order)
        self.order.refresh_from_db()
        self.assertIsNone(self.order.deleted_at)
        self.assertEqual(self.order.status, "Abierta")
        self.assertFalse(self.order.events.filter(event="Borrada").exists())

    def test_employee_number_can_be_changed_and_is_audited(self):
        response = self.client.patch(f"/api/users/{self.member.pk}", json.dumps({"employee_number": "DEL-NEW"}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.member.refresh_from_db()
        self.assertEqual(self.member.employee_number, "DEL-NEW")
        self.assertEqual(self.member.username, "delete-member")
        event = AuditLog.objects.get(entity_type="user", entity_id=self.member.pk, action="updated")
        self.assertEqual(event.before["employee_number"], "DEL-M")
        self.assertEqual(event.after["employee_number"], "DEL-NEW")
        self.assertNotIn("password", event.after)

    def test_employee_number_validates_duplicates_and_permissions(self):
        for value, status in [("", 400), (" " * 2, 400), ("x" * 51, 400), ("DEL-A", 409)]:
            response = self.client.patch(f"/api/users/{self.member.pk}", json.dumps({"employee_number": value}), content_type="application/json")
            self.assertEqual(response.status_code, status)
        self.client.force_login(self.member)
        response = self.client.patch(f"/api/users/{self.admin.pk}", '{"employee_number":"CHANGED"}', content_type="application/json")
        self.assertEqual(response.status_code, 403)
