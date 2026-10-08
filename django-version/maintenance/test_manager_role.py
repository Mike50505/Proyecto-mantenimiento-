import json

from django.test import TestCase

from .models import Asset, User
from .views import ACTIONS, MODULES


class MaintenanceManagerRoleTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username="role-admin", employee_number="ROLE-A", first_name="Admin", role="Administrador")
        self.manager = User.objects.create_user(username="role-chief", employee_number="ROLE-J", first_name="Jefe", role="Jefe de mantenimiento")
        self.operator = User.objects.create_user(username="role-operator", employee_number="ROLE-O", first_name="Operador", role="Solicitante")

    def create_user(self, role):
        return self.client.post('/api/users', json.dumps({
            'name': 'Nuevo', 'last_name': 'Usuario', 'employee_number': 'NEW-ROLE',
            'password': 'Temporary123!', 'role': role,
        }), content_type='application/json')

    def test_manager_has_all_modules_actions_and_areas(self):
        self.manager.module_permissions = ['orders']
        self.manager.action_permissions = ['orders.read']
        self.manager.area_permissions = ['Prensas']
        self.manager.save()
        Asset.objects.create(code='ROLE-ASSET', name='Equipo', area='Corte')
        self.client.force_login(self.manager)
        user = self.client.get('/api/auth/me').json()
        self.assertEqual(user['role_name'], 'Jefe de mantenimiento')
        self.assertEqual(user['permissions'], MODULES)
        self.assertEqual(user['actions'], ACTIONS)
        self.assertEqual(user['areas'], [])
        self.assertEqual(len(self.client.get('/api/assets').json()), 1)
        for endpoint in ('/api/users', '/api/dashboard', '/api/inventory', '/api/preventives', '/api/audit', '/api/catalogs', '/api/imports'):
            with self.subTest(endpoint=endpoint):
                self.assertEqual(self.client.get(endpoint).status_code, 200)

    def test_admin_creates_manager_with_temporary_password(self):
        self.client.force_login(self.admin)
        response = self.create_user('Jefe de mantenimiento')
        self.assertEqual(response.status_code, 201)
        created = User.objects.get(pk=response.json()['id'])
        self.assertEqual(created.role, 'Jefe de mantenimiento')
        self.assertTrue(created.must_change_password)
        self.client.force_login(created)
        self.assertEqual(self.client.get('/api/users').status_code, 403)

    def test_manager_can_promote_and_demote_users(self):
        self.operator.action_permissions = ['orders.read']
        self.operator.area_permissions = ['Prensas']
        self.operator.save()
        self.client.force_login(self.manager)
        url = f'/api/users/{self.operator.pk}'
        response = self.client.patch(url, json.dumps({'role': 'Jefe de mantenimiento'}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.operator.refresh_from_db()
        self.assertEqual(self.operator.role, 'Jefe de mantenimiento')
        self.assertEqual(self.operator.action_permissions, [])
        self.assertEqual(self.operator.area_permissions, [])
        response = self.client.patch(url, json.dumps({'role': 'Mantenimiento'}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.operator.refresh_from_db()
        self.assertEqual(self.operator.role, 'Técnico')
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get('/api/users').status_code, 403)

    def test_operator_and_technician_cannot_grant_manager_access(self):
        for role in ('Solicitante', 'Técnico'):
            self.operator.role = role
            self.operator.save()
            self.client.force_login(self.operator)
            self.assertEqual(self.create_user('Jefe de mantenimiento').status_code, 403)
            self.assertEqual(self.client.patch(f'/api/users/{self.operator.pk}', json.dumps({'role': 'Jefe de mantenimiento'}), content_type='application/json').status_code, 403)

    def test_unknown_role_is_rejected(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.create_user('Rol inexistente').status_code, 400)
        self.assertFalse(User.objects.filter(employee_number='NEW-ROLE').exists())
