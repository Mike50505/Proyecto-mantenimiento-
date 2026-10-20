import json
from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from .models import Asset, AuditLog, PreventivePlan, TimeEntry, User, WorkOrder
from .preventive_orders import extend_schedule


class RecurrentSeriesDeletionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="series-admin", employee_number="SER-A", role="Administrador")
        self.member = User.objects.create_user(username="series-member", employee_number="SER-M", role="Técnico")
        self.asset = Asset.objects.create(code="SER-ASSET", name="Prensa", area="Corte")
        self.client.force_login(self.admin)
        first = timezone.localdate()+timedelta(days=1)
        response = self.client.post("/api/preventive-orders/schedule", json.dumps({"asset_id":self.asset.pk,"title":"Lubricar","scheduled_at":f"{first}T09:00","repeat":"weeks","interval":1,"repeat_until":str(first+timedelta(days=21))}), content_type="application/json")
        self.assertEqual(response.status_code, 201, response.content)
        self.plan = PreventivePlan.objects.get(pk=response.json()["plan_id"])
        self.orders = list(WorkOrder.objects.order_by("pk"))
        self.url = f"/api/preventive-orders/{self.plan.pk}/delete-series"

    def preview(self, scope="all"):
        response = self.client.get(self.url, {"scope":scope})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def delete(self, preview=None, **fields):
        preview = preview or self.preview()
        return self.client.post(self.url, json.dumps({"scope":preview["scope"],"confirmation":preview["confirmation"],"reason":"Repetición creada por error",**fields}), content_type="application/json")

    def test_preview_counts_orders_without_changing_any_record(self):
        self.orders[0].status="Completada"
        self.orders[0].save(update_fields=["status"])
        self.assertEqual(self.preview()["count"], 4)
        self.assertEqual(self.preview()["completed"], 1)
        self.assertEqual(self.preview("pending")["count"], 3)
        self.assertEqual(WorkOrder.objects.count(), 4)
        self.assertFalse(AuditLog.objects.filter(action="deleted").exists())

    def test_deletes_all_series_orders_and_stops_future_generation(self):
        unrelated = WorkOrder.objects.create(folio="UNRELATED", requested_at=timezone.now(),requester=self.admin,priority="Media",classification="Correctivo",reported_failure="Otro trabajo")
        self.orders[0].status="Completada"
        self.orders[0].save(update_fields=["status"])
        response = self.delete()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["deleted"], 4)
        self.assertEqual(list(WorkOrder.objects.values_list("pk",flat=True)), [unrelated.pk])
        self.assertEqual(WorkOrder.all_objects.filter(pk__in=[order.pk for order in self.orders],deleted_by=self.admin).count(), 4)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status,"Borrado")
        self.assertEqual(extend_schedule(self.plan), [])
        self.assertEqual(self.client.get(f"/api/preventives/{self.plan.pk}/tasks").status_code, 404)
        self.assertFalse(any(plan["id"]==self.plan.pk for plan in self.client.get("/api/preventives").json()))
        self.assertEqual(AuditLog.objects.filter(entity_type="work_order",action="deleted").count(),4)
        event=AuditLog.objects.get(entity_type="preventive_plan",entity_id=self.plan.pk,action="deleted")
        self.assertEqual(event.after["count"],4)
        self.assertEqual(event.after["scope"],"all")
        self.assertEqual(self.client.get("/api/audit?action=deleted").json()["total"],5)

    def test_pending_scope_retains_completed_history(self):
        completed=self.orders[0]
        completed.status="Completada"
        completed.save(update_fields=["status"])
        response=self.delete(self.preview("pending"))
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()["deleted"],3)
        self.assertTrue(WorkOrder.objects.filter(pk=completed.pk).exists())
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status,"Borrado")

    def test_requires_delete_and_preventive_permissions_and_area_scope(self):
        self.member.custom_permissions=True
        self.member.module_permissions=["orders","preventives"]
        self.member.save()
        self.client.force_login(self.member)
        for allowed, areas in [(["preventives.edit"],[]),(["orders.delete"],[]),(["orders.delete","preventives.edit"],["Otra área"])]:
            self.member.action_permissions=allowed
            self.member.area_permissions=areas
            self.member.save()
            self.assertEqual(self.client.get(self.url).status_code,403)
            self.assertEqual(self.client.post(self.url,"{}",content_type="application/json").status_code,403)
        self.assertEqual(WorkOrder.objects.count(),4)

    def test_missing_reason_and_stale_confirmation_do_not_delete_anything(self):
        preview=self.preview()
        self.assertEqual(self.delete(preview,reason=" ").status_code,400)
        self.orders[0].version+=1
        self.orders[0].save(update_fields=["version"])
        self.assertEqual(self.delete(preview).status_code,409)
        self.assertEqual(WorkOrder.objects.count(),4)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status,"Programado")

    def test_running_session_blocks_entire_batch(self):
        TimeEntry.objects.create(work_order=self.orders[1],user=self.member,started_at=timezone.now())
        self.assertEqual(self.delete().status_code,409)
        self.assertEqual(WorkOrder.objects.count(),4)
        self.assertFalse(AuditLog.objects.filter(action="deleted").exists())

    def test_mid_batch_audit_failure_rolls_back_every_deletion(self):
        preview=self.preview()
        with patch("maintenance.views.audit",side_effect=[None,RuntimeError("Audit unavailable")]):
            with self.assertRaises(RuntimeError):self.delete(preview)
        self.assertEqual(WorkOrder.objects.count(),4)
        self.assertFalse(WorkOrder.all_objects.filter(deleted_at__isnull=False).exists())
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status,"Programado")

    def test_requester_cannot_bulk_delete_other_peoples_orders(self):
        self.member.role="Solicitante"
        self.member.custom_permissions=True
        self.member.module_permissions=["orders","preventives"]
        self.member.action_permissions=["orders.delete","preventives.edit"]
        self.member.save()
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(self.url).status_code,403)

    def test_order_payload_exposes_series_action_in_both_lists(self):
        row=self.client.get(f"/api/orders/{self.orders[0].pk}").json()
        self.assertEqual(row["recurrent_plan_id"],self.plan.pk)
        rows=self.client.get("/api/preventive-orders").json()["orders"]
        self.assertTrue(all(row["recurrent_plan_id"]==self.plan.pk for row in rows))

    def test_deleted_series_cannot_be_reactivated_by_stop_endpoint(self):
        self.assertEqual(self.delete().status_code,200)
        response=self.client.post(f"/api/preventive-orders/{self.plan.pk}/stop",'{"reason":"Otro motivo"}',content_type="application/json")
        self.assertEqual(response.status_code,404)

    def test_deleted_legacy_programs_are_hidden_without_erasing_their_history(self):
        legacy=PreventivePlan.objects.create(asset=self.asset,title="Anterior",frequency="Mensual",next_date=timezone.localdate(),status="Borrado")
        result=self.client.get("/api/preventive-orders").json()
        self.assertFalse(any(plan["id"]==legacy.pk for plan in result["legacy_plans"]))
        self.assertTrue(PreventivePlan.objects.filter(pk=legacy.pk).exists())
