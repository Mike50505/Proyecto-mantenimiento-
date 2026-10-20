import io
import json
import hashlib
import random
from datetime import timedelta
from unittest.mock import patch

from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.deletion import ProtectedError
from django.test import Client, TestCase
from django.test.client import BOUNDARY, MULTIPART_CONTENT, encode_multipart
from django.utils import timezone

from .models import Asset, AuditLog, CatalogEntry, User, WorkOrder, WorkOrderImage
from .order_images import ImageUploadError, TARGET_IMAGE_BYTES, prepare_image


def photo(color='red', format='PNG'):
    stream = io.BytesIO()
    Image.new('RGB', (24, 16), color).save(stream, format=format)
    return SimpleUploadedFile('foto.' + format.lower(), stream.getvalue(), content_type='image/' + format.lower())


class OrderImagesTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user(username='image-operator', employee_number='IMG-O', first_name='Operador', role='Solicitante')
        self.tech = User.objects.create_user(username='image-tech', employee_number='IMG-T', first_name='Técnico', role='Técnico')
        self.other = User.objects.create_user(username='image-other', employee_number='IMG-X', first_name='Otro', role='Solicitante')
        self.asset = Asset.objects.create(code='IMG-ASSET', name='Prensa', area='Corte')
        CatalogEntry.objects.get_or_create(kind='priority', value='Normal')
        CatalogEntry.objects.get_or_create(kind='classification', value='Mantenimiento Correctivo')
        self.client.force_login(self.operator)

    def create(self, upload=None, **extra):
        data = {'priority': 'Normal', 'classification': 'Mantenimiento Correctivo',
                'asset_id': self.asset.pk, 'reported_failure': 'Fuga de aceite'}
        if upload is None:
            return self.client.post('/api/orders', json.dumps(data), content_type='application/json', **extra)
        return self.client.post('/api/orders', {'data': json.dumps(data), 'report_image': upload}, **extra)

    def work_order(self):
        return WorkOrder.objects.create(folio='IMG-OLD', requester=self.operator, asset=self.asset,
            requested_at=timezone.now(), priority='Normal', classification='Mantenimiento Correctivo',
            reported_failure='Fuga de aceite', technician=self.tech, status='En proceso',
            actions='Cambiar sello', closure_notes='Pruebas correctas',
            started_at=timezone.now() - timedelta(hours=1), finished_at=timezone.now(), labor_hours=1)

    def update(self, order, upload=None, **fields):
        data = {'version': order.version, **fields}
        if upload is None:
            return self.client.patch(f'/api/orders/{order.pk}', json.dumps(data), content_type='application/json')
        body = encode_multipart(BOUNDARY, {'data': json.dumps(data), 'completion_image': upload})
        return self.client.patch(f'/api/orders/{order.pk}', body, content_type=MULTIPART_CONTENT)

    def test_operator_attaches_image_atomically_and_only_detail_has_metadata(self):
        response = self.create(photo())
        self.assertEqual(response.status_code, 201, response.content)
        order = WorkOrder.objects.get(pk=response.json()['id'])
        image = order.images.get()
        self.assertEqual(image.kind, 'report')
        self.assertEqual(image.created_by, self.operator)
        detail = self.client.get(f'/api/orders/{order.pk}').json()
        self.assertEqual(detail['images'][0]['id'], image.pk)
        self.assertEqual(detail['images'][0]['created_by'], self.operator.first_name)
        self.assertNotIn('image_content', detail['images'][0])
        self.assertNotIn('images', self.client.get('/api/orders').json()[0])
        download = self.client.get(detail['images'][0]['url'])
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download['Content-Type'], 'image/webp')
        self.assertEqual(download['X-Content-Type-Options'], 'nosniff')
        self.assertIn('no-store', download['Cache-Control'])
        self.assertEqual(Image.open(io.BytesIO(download.content)).format, 'WEBP')
        self.assertTrue(AuditLog.objects.filter(entity_type='work_order_image', entity_id=image.pk).exists())

    def test_optional_images_preserve_existing_order_creation(self):
        response = self.create()
        self.assertEqual(response.status_code, 201)
        self.assertFalse(WorkOrderImage.objects.exists())
        self.assertEqual(self.client.get(f"/api/orders/{response.json()['id']}").json()['images'], [])

    def test_technician_adds_completion_image_and_can_finish_order(self):
        order = self.work_order()
        before = (order.pk, order.folio, order.requester_id, order.started_at, order.labor_hours)
        self.client.force_login(self.tech)
        response = self.update(order, photo('green'), actions='Sello cambiado y verificado')
        self.assertEqual(response.status_code, 200, response.content)
        order.refresh_from_db()
        self.assertEqual((order.pk, order.folio, order.requester_id, order.started_at, order.labor_hours), before)
        self.assertEqual(order.images.get().kind, 'completion')
        self.assertEqual(order.images.get().created_by, self.tech)
        response = self.client.post(f'/api/orders/{order.pk}/transitions',
            json.dumps({'to': 'Pendiente de validación', 'version': order.version}), content_type='application/json')
        self.assertEqual(response.status_code, 200, response.content)
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get(f'/api/orders/{order.pk}').json()['images'][0]['kind'], 'completion')

    def test_completion_images_preserve_previous_evidence_and_deduplicate_retries(self):
        order = self.work_order()
        self.client.force_login(self.tech)
        for color in ('green', 'green', 'blue'):
            response = self.update(order, photo(color))
            self.assertEqual(response.status_code, 200, response.content)
            order.refresh_from_db()
        self.assertEqual(order.images.count(), 2)
        self.assertEqual(AuditLog.objects.filter(entity_type='work_order_image').count(), 2)

    def test_report_retry_is_idempotent_and_a_different_photo_conflicts(self):
        first = self.create(photo(), HTTP_IDEMPOTENCY_KEY='photo-request')
        repeat = self.create(photo(), HTTP_IDEMPOTENCY_KEY='photo-request')
        self.assertEqual(first.status_code, 201)
        self.assertEqual(repeat.status_code, 200)
        self.assertEqual(first.json()['id'], repeat.json()['id'])
        self.assertEqual(WorkOrderImage.objects.count(), 1)
        changed = self.create(photo('green'), HTTP_IDEMPOTENCY_KEY='photo-request')
        self.assertEqual(changed.status_code, 409)
        self.assertEqual(WorkOrder.objects.count(), 1)

    def test_fake_image_and_oversized_image_do_not_create_orders(self):
        for upload in (
            SimpleUploadedFile('fake.jpg', b'<svg><script>bad</script></svg>', content_type='image/jpeg'),
            SimpleUploadedFile('big.jpg', b'x' * (8 * 1024 * 1024 + 1), content_type='image/jpeg'),
        ):
            response = self.create(upload)
            self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(WorkOrder.objects.exists())
        self.assertFalse(WorkOrderImage.objects.exists())

    def test_invalid_completion_image_and_stale_version_roll_back_changes(self):
        order = self.work_order()
        self.client.force_login(self.tech)
        original = WorkOrder.objects.values().get(pk=order.pk)
        response = self.update(order, SimpleUploadedFile('bad.png', b'not an image'), actions='Should not save')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(WorkOrder.objects.values().get(pk=order.pk), original)
        response = self.update(order, photo(), version=0)
        self.assertEqual(response.status_code, 409)
        self.assertFalse(order.images.exists())

    def test_unassigned_technician_and_operator_cannot_upload_completion(self):
        order = self.work_order()
        self.client.force_login(self.operator)
        self.assertEqual(self.update(order, photo()).status_code, 403)
        order.technician = None
        order.save()
        self.client.force_login(self.tech)
        self.assertEqual(self.update(order, photo()).status_code, 403)
        self.assertFalse(order.images.exists())

    def test_images_obey_authentication_requester_and_area_permissions(self):
        response = self.create(photo())
        order = WorkOrder.objects.get(pk=response.json()['id'])
        url = f'/api/orders/{order.pk}/images/{order.images.get().pk}'
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.tech)
        self.tech.area_permissions = ['Otra área']
        self.tech.save()
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 401)

    def test_image_is_unavailable_after_soft_delete_but_still_preserved(self):
        response = self.create(photo())
        order = WorkOrder.objects.get(pk=response.json()['id'])
        image = order.images.get()
        order.deleted_at = timezone.now()
        order.save()
        self.assertEqual(self.client.get(f'/api/orders/{order.pk}/images/{image.pk}').status_code, 404)
        self.assertTrue(WorkOrderImage.objects.filter(pk=image.pk).exists())
        with self.assertRaises(ProtectedError):
            WorkOrder.all_objects.filter(pk=order.pk).delete()

    def test_database_failure_does_not_leave_an_image_or_partial_order(self):
        with patch('maintenance.views.audit', side_effect=RuntimeError('Simulated failure')):
            with self.assertRaises(RuntimeError):
                self.create(photo())
        self.assertFalse(WorkOrderImage.objects.exists())
        self.assertFalse(WorkOrder.objects.exists())

    def test_image_content_cannot_be_requested_under_another_order(self):
        response = self.create(photo())
        image = WorkOrderImage.objects.get()
        another = self.work_order()
        self.assertNotEqual(another.pk, response.json()['id'])
        self.assertEqual(self.client.get(f'/api/orders/{another.pk}/images/{image.pk}').status_code, 404)

    def test_completion_after_validation_is_rejected_without_changing_history(self):
        order = self.work_order()
        order.status = 'Completada'
        order.save()
        before = WorkOrder.objects.values().get(pk=order.pk)
        self.client.force_login(self.tech)
        self.assertEqual(self.update(order, photo()).status_code, 409)
        self.assertEqual(WorkOrder.objects.values().get(pk=order.pk), before)
        self.assertFalse(order.images.exists())

    def test_upload_needs_csrf_protection(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.operator)
        self.assertEqual(client.post('/api/orders', {'data': '{}', 'report_image': photo()}).status_code, 403)

    def test_previous_jpeg_evidence_is_served_without_reencoding_or_changing_hash(self):
        order = self.work_order()
        stream = io.BytesIO()
        Image.new('RGB', (80, 60), 'blue').save(stream, format='JPEG')
        original = stream.getvalue()
        image = WorkOrderImage.objects.create(work_order=order, kind='report', image_content=original,
            sha256=hashlib.sha256(original).hexdigest(), width=80, height=60, created_by=self.operator)
        response = self.client.get(f'/api/orders/{order.pk}/images/{image.pk}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/jpeg')
        self.assertIn('.jpg', response['Content-Disposition'])
        self.assertEqual(response.content, original)
        image.refresh_from_db()
        self.assertEqual(hashlib.sha256(bytes(image.image_content)).hexdigest(), image.sha256)


class ImageNormalizationTests(TestCase):
    def test_rotates_exif_strips_metadata_and_limits_dimensions(self):
        original = Image.new('RGB', (2000, 1000), 'red')
        exif = Image.Exif()
        exif[274] = 6
        exif[315] = 'Private camera owner'
        stream = io.BytesIO()
        original.save(stream, format='JPEG', exif=exif)
        prepared = prepare_image(SimpleUploadedFile('camera.jpg', stream.getvalue()))
        image = Image.open(io.BytesIO(prepared.content))
        self.assertEqual(image.size, (800, 1600))
        self.assertFalse(dict(image.getexif()))

    def test_resolution_limit_rejects_image_before_decode(self):
        with patch('maintenance.order_images.MAX_PIXELS', 10):
            with self.assertRaises(ImageUploadError):
                prepare_image(photo())

    def test_small_photos_are_not_upscaled_and_webp_uses_less_than_previous_jpeg(self):
        prepared = prepare_image(photo())
        old = io.BytesIO()
        Image.new('RGB', (24, 16), 'red').save(old, format='JPEG', quality=85, optimize=True)
        self.assertEqual((prepared.width, prepared.height), (24, 16))
        self.assertEqual(prepared.content_type, 'image/webp')
        self.assertLess(len(prepared.content), len(old.getvalue()))

    def test_adaptive_compression_reduces_complex_photo_and_keeps_useful_resolution(self):
        original = Image.frombytes('RGB', (1800, 1200), random.Random(17).randbytes(1800 * 1200 * 3))
        stream = io.BytesIO()
        original.save(stream, format='PNG')
        prepared = prepare_image(SimpleUploadedFile('detail.png', stream.getvalue()))
        self.assertLessEqual(len(prepared.content), TARGET_IMAGE_BYTES)
        self.assertGreaterEqual(max(prepared.width, prepared.height), 1024)
        self.assertLessEqual(max(prepared.width, prepared.height), 1600)
        self.assertEqual(Image.open(io.BytesIO(prepared.content)).size, (prepared.width, prepared.height))
        normalized = original.copy()
        normalized.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
        old = io.BytesIO()
        normalized.save(old, format='JPEG', quality=85, optimize=True)
        self.assertLessEqual(len(prepared.content), len(old.getvalue()))

    def test_unreachable_size_target_does_not_destroy_evidence_resolution(self):
        stream = io.BytesIO()
        Image.new('RGB', (1600, 1200), 'green').save(stream, format='PNG')
        with patch('maintenance.order_images.TARGET_IMAGE_BYTES', 1):
            prepared = prepare_image(SimpleUploadedFile('detail.png', stream.getvalue()))
        self.assertGreater(len(prepared.content), 1)
        self.assertGreaterEqual(max(prepared.width, prepared.height), 1024)
