import json

from django.test import TestCase

from .models import Asset, AuditLog, CatalogEntry, User
from .views import ACTIONS, MODULES, actions, modules


class AccountPermissionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='permission-admin', employee_number='PERM-A', first_name='Admin', role='Administrador')
        self.chief = User.objects.create_user(username='permission-chief', employee_number='PERM-J', first_name='Jefe', role='Jefe de mantenimiento')
        self.operator = User.objects.create_user(username='permission-operator', employee_number='PERM-O', first_name='Operador')
        self.client.force_login(self.admin)

    def update(self, user, data):
        return self.client.patch(f'/api/users/{user.pk}', json.dumps(data), content_type='application/json')

    def restrict(self, user, windows, allowed, areas=None):
        response = self.update(user, {'custom_permissions': True, 'permissions': windows, 'actions': allowed, 'areas': areas or []})
        self.assertEqual(response.status_code, 200, response.content)
        user.refresh_from_db()

    def test_chief_can_have_individual_windows_actions_and_areas(self):
        Asset.objects.create(code='P-A', name='Prensa', area='Prensas')
        Asset.objects.create(code='P-B', name='Corte', area='Corte')
        self.restrict(self.chief, ['assets'], ['assets.read'], ['Prensas'])
        self.client.force_login(self.chief)
        profile = self.client.get('/api/auth/me').json()
        self.assertEqual(profile['permissions'], ['assets'])
        self.assertEqual(profile['actions'], ['assets.read'])
        self.assertEqual(profile['areas'], ['Prensas'])
        self.assertEqual(len(self.client.get('/api/assets').json()), 1)
        self.assertEqual(self.client.post('/api/assets', '{}', content_type='application/json').status_code, 403)
        for url in ('/api/users', '/api/orders', '/api/dashboard', '/api/inventory', '/api/agenda', '/api/imports'):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_hidden_window_blocks_api_even_with_the_action(self):
        self.restrict(self.operator, ['orders'], ['orders.read', 'assets.read'])
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get('/api/orders').status_code, 200)
        self.assertEqual(self.client.get('/api/assets').status_code, 403)

    def test_empty_selection_does_not_restore_role_permissions(self):
        self.restrict(self.chief, [], [])
        self.assertEqual(modules(self.chief), [])
        self.assertEqual(actions(self.chief), [])
        self.client.force_login(self.chief)
        self.assertEqual(self.client.get('/api/users').status_code, 403)
        self.assertEqual(self.client.get('/api/orders').status_code, 403)

    def test_can_restore_defaults_explicitly(self):
        self.restrict(self.chief, ['orders'], ['orders.read'], ['Prensas'])
        self.assertEqual(self.update(self.chief, {'custom_permissions': False}).status_code, 200)
        self.chief.refresh_from_db()
        self.assertFalse(self.chief.custom_permissions)
        self.assertEqual(modules(self.chief), MODULES)
        self.assertEqual(actions(self.chief), ACTIONS)
        self.assertEqual(self.chief.area_permissions, [])

    def test_creates_account_with_selected_permissions(self):
        response = self.client.post('/api/users', json.dumps({
            'name':'Nueva', 'last_name':'Cuenta', 'employee_number':'PERM-N', 'username':'permission-new',
            'password':'Temporary123!', 'role':'Mantenimiento', 'custom_permissions':True,
            'permissions':['inventory'], 'actions':['inventory.read'], 'areas':['Prensas'],
        }), content_type='application/json')
        self.assertEqual(response.status_code, 201, response.content)
        user = User.objects.get(pk=response.json()['id'])
        self.assertTrue(user.custom_permissions)
        self.assertTrue(user.must_change_password)
        self.assertEqual(user.module_permissions, ['inventory'])
        self.assertEqual(user.action_permissions, ['inventory.read'])
        self.assertEqual(user.area_permissions, ['Prensas'])

    def test_invalid_selection_rolls_back_role_and_permissions(self):
        self.restrict(self.operator, ['orders'], ['orders.read'])
        for data in ({'permissions':['invented']}, {'actions':['invented']}, {'permissions':'orders'}, {'custom_permissions':'false'}, {'areas':[5]}):
            with self.subTest(data=data):
                response = self.update(self.operator, {'role':'Jefe de mantenimiento', **data})
                self.assertEqual(response.status_code, 400)
                self.operator.refresh_from_db()
                self.assertEqual(self.operator.role, 'Solicitante')
                self.assertEqual(self.operator.module_permissions, ['orders'])

    def test_primary_administrator_retains_access(self):
        self.assertEqual(self.update(self.admin, {'custom_permissions':True, 'permissions':[], 'actions':[]}).status_code, 400)
        self.admin.refresh_from_db()
        self.assertEqual(modules(self.admin), MODULES)

    def test_permission_options_are_selected_from_catalogs(self):
        CatalogEntry.objects.create(kind='area', value='Prensas')
        Asset.objects.create(code='AREA-PERM', name='Equipo', area='Corte')
        self.operator.area_permissions = ['Área histórica']
        self.operator.save()
        response = self.client.get('/api/user-permission-options')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()['areas']), {'Prensas', 'Corte', 'Área histórica'})
        self.assertIn('downtime', response.json()['modules'])
        self.client.force_login(self.operator)
        self.assertEqual(self.client.get('/api/user-permission-options').status_code, 403)

    def test_customized_role_change_preserves_selections(self):
        self.restrict(self.operator, ['assets'], ['assets.read'])
        self.assertEqual(self.update(self.operator, {'role':'Jefe de mantenimiento'}).status_code, 200)
        self.operator.refresh_from_db()
        self.assertEqual(self.operator.role, 'Jefe de mantenimiento')
        self.assertEqual(modules(self.operator), ['assets'])
        self.assertEqual(actions(self.operator), ['assets.read'])

    def test_permission_change_is_audited(self):
        self.restrict(self.operator, ['orders'], ['orders.read'])
        event = AuditLog.objects.filter(entity_type='user', entity_id=str(self.operator.pk), action='updated').latest('id')
        self.assertEqual(event.user, self.admin)
        self.assertTrue(event.after['custom_permissions'])
        self.assertEqual(event.after['permissions'], ['orders'])
        self.assertEqual(event.after['actions'], ['orders.read'])

    def test_paros_can_be_configured_separately_from_orders(self):
        self.restrict(self.chief, ['downtime'], ['orders.read'])
        self.client.force_login(self.chief)
        self.assertEqual(self.client.get('/api/agenda').status_code, 200)
        self.assertEqual(self.client.get('/api/orders').status_code, 403)
