from django.core.management.base import BaseCommand
from maintenance.preventive_orders import refresh_schedules


class Command(BaseCommand):
    help = "Mantiene las OT preventivas recurrentes de los próximos 90 días, sin duplicarlas."

    def handle(self, *args, **options):
        created = refresh_schedules()
        self.stdout.write(f"OT preventivas futuras creadas: {created}")
