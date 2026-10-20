import importlib
import json
from types import SimpleNamespace

from django.apps import apps
from django.test import TestCase
from django.utils import timezone

from .models import Asset, AuditLog, User


class SimplifiedAssetTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="simple-admin", employee_number="SIM-A", role="Administrador")
        self.client.force_login(self.admin)

    def create(self, **fields):
        data = {"name": "Prensa", "area": "Producción", "asset_type": "Maquinaria", **fields}
        return self.client.post("/api/assets", json.dumps(data), content_type="application/json")

    def test_create_without_codes_and_legacy_fields(self):
        response = self.create(criticality="B")
        self.assertEqual(response.status_code, 201, response.content)
        asset = Asset.objects.get(pk=response.json()["id"])
        self.assertTrue(asset.code.startswith("MESA-AUTO-"))
        self.assertEqual(asset.criticality, "B")
        self.assertFalse(asset.critical)
        self.assertEqual(asset.category, "Maquinaria")
        self.assertEqual(asset.original_code, "")
        self.assertEqual(asset.alias_codes, "")
        self.assertEqual(asset.location_detail, "")
        event = AuditLog.objects.get(entity_type="asset", entity_id=asset.pk, action="created")
        self.assertEqual(event.after["criticality"], "B")

    def test_internal_identifiers_are_unique_for_equal_names(self):
        first = self.create()
        second = self.create()
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertNotEqual(Asset.objects.get(pk=first.json()["id"]).code, Asset.objects.get(pk=second.json()["id"]).code)

    def test_all_three_criticality_grades_round_trip(self):
        for grade in ("A", "B", "C"):
            with self.subTest(grade=grade):
                response = self.create(criticality=grade)
                self.assertEqual(response.status_code, 201)
                record = self.client.get(f"/api/assets/{response.json()['id']}").json()
                self.assertEqual(record["criticality"], grade)
                self.assertEqual(record["critical"], grade == "A")

    def test_edit_retains_omitted_historical_fields_and_audits_criticality(self):
        asset = Asset.objects.create(code="OLD-01", name="Antiguo", area="Producción", category="Categoría anterior",
                                     original_code="SOURCE-01", alias_codes="Alias", line="Línea 1", location_detail="Nave 1")
        response = self.client.patch(f"/api/assets/{asset.pk}", json.dumps({"name": "Nuevo", "criticality": "A"}), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        asset.refresh_from_db()
        self.assertEqual(asset.criticality, "A")
        self.assertTrue(asset.critical)
        self.assertEqual((asset.code, asset.original_code, asset.alias_codes, asset.category, asset.line, asset.location_detail),
                         ("OLD-01", "SOURCE-01", "Alias", "Categoría anterior", "Línea 1", "Nave 1"))
        event = AuditLog.objects.get(entity_type="asset", entity_id=asset.pk, action="updated")
        self.assertEqual(event.before["criticality"], "C")
        self.assertEqual(event.after["criticality"], "A")

    def test_invalid_criticality_and_missing_essential_data_are_rejected(self):
        for fields in [{"criticality": "D"}, {"criticality": ""}, {"name": " "}, {"area": ""}]:
            with self.subTest(fields=fields): self.assertEqual(self.create(**fields).status_code, 400)
        self.assertEqual(Asset.objects.count(), 0)

    def test_edit_invalid_grade_is_atomic(self):
        asset = Asset.objects.create(code="INVALID", name="Original", area="Producción")
        response = self.client.patch(f"/api/assets/{asset.pk}", json.dumps({"name":"Changed", "criticality":"D"}), content_type="application/json")
        self.assertEqual(response.status_code, 400)
        asset.refresh_from_db()
        self.assertEqual(asset.name, "Original")

    def test_legacy_boolean_requests_remain_compatible(self):
        response = self.create(code="OLD-API", critical=True)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Asset.objects.get(pk=response.json()["id"]).criticality, "A")

    def test_migration_preserves_former_criticality_including_archived_assets(self):
        critical = Asset.objects.create(code="MIG-A", name="Crítico", area="Producción", critical=True)
        normal = Asset.objects.create(code="MIG-C", name="Normal", area="Producción", critical=False)
        archived = Asset.all_objects.create(code="MIG-ARCHIVED", name="Anterior", area="Producción", critical=True, deleted_at=timezone.now())
        migration = importlib.import_module("maintenance.migrations.0016_asset_criticality")
        migration.migrate_criticality(apps, SimpleNamespace(connection=SimpleNamespace(alias="default")))
        for record, grade in [(critical, "A"), (normal, "C"), (archived, "A")]:
            self.assertEqual(Asset.all_objects.get(pk=record.pk).criticality, grade)

    def test_simplified_export_uses_letters_and_omits_unused_columns(self):
        import io
        import zipfile
        self.create(criticality="B")
        response = self.client.get("/api/assets/export.xlsx")
        self.assertEqual(response.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            content = "".join(archive.read(name).decode() for name in archive.namelist() if name.endswith(".xml"))
        self.assertIn("Criticidad", content)
        self.assertIn(">B<", content)
        for removed in ("Código de origen", "Alias", "Categoría histórica", "Línea"):
            self.assertNotIn(removed, content)
