import os
from django.core.management.base import BaseCommand, CommandError
from maintenance.models import User

class Command(BaseCommand):
    def handle(self, *args, **options):
        password = os.environ.get("MESA_ADMIN_PASSWORD")
        if not password or len(password) < 12:
            raise CommandError("MESA_ADMIN_PASSWORD debe tener al menos 12 caracteres")
        user, created = User.objects.get_or_create(
            username="administrator",
            defaults={"employee_number": "ADMIN", "first_name": "Administrator", "last_name": "MESA", "role": "Administrador", "is_staff": True, "is_superuser": True, "must_change_password": True},
        )
        if created:
            user.set_password(password)
            user.save(update_fields=["password", "must_change_password"])
            self.stdout.write("Administrador inicial creado")
