from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from maintenance.models import User
from maintenance.planner import plan_preventive_window
from maintenance.views import actions


class Command(BaseCommand):
    help = "Preview or create due preventive OTs in a bounded date window. Re-running is safe."

    def add_arguments(self, parser):
        parser.add_argument("--as-of", help="Operational date YYYY-MM-DD; defaults to today")
        parser.add_argument("--lookback-days", type=int, required=True)
        parser.add_argument("--lookahead-days", type=int, required=True)
        parser.add_argument("--user", help="Active administrator or maintenance manager used as the actor")
        parser.add_argument("--apply", action="store_true", help="Persist work orders; without it, preview only")
        parser.add_argument("--allow-overlap", action="store_true", help="Allow a new date while this task has an earlier open OT")
        parser.add_argument("--max-new-orders", type=int, default=100)

    def handle(self, *args, **options):
        try:
            as_of = date.fromisoformat(options["as_of"]) if options["as_of"] else timezone.localdate()
        except ValueError as error:
            raise CommandError("--as-of debe ser YYYY-MM-DD") from error
        behind, ahead = options["lookback_days"], options["lookahead_days"]
        if behind < 0 or ahead < 0 or behind + ahead > 366:
            raise CommandError("La ventana debe estar entre 0 y 366 días")
        if options["max_new_orders"] < 1:
            raise CommandError("--max-new-orders debe ser positivo")
        start, end = as_of - timedelta(days=behind), as_of + timedelta(days=ahead)
        actor = None
        if options["apply"]:
            if not options["user"]:
                raise CommandError("--apply requiere --user")
            actor = User.objects.filter(username=options["user"], is_active=True).first()
            if not actor or actor.role not in ("Administrador", "Jefatura", "Jefe de mantenimiento") or (actor.role != "Administrador" and not {"preventives.edit", "orders.create"}.issubset(set(actions(actor)))):
                raise CommandError("El usuario debe ser Administrador o Jefatura activa con permisos preventivos y de OT")
            if actor.must_change_password:
                raise CommandError("El usuario debe cambiar su contraseña temporal antes de operar")
        preview = plan_preventive_window(start, end, actor=actor, allow_overlap=options["allow_overlap"])
        self.stdout.write(f"Ventana {start} a {end}: {preview}")
        if not options["apply"]:
            self.stdout.write("Vista previa; no se crearon OT")
            return
        if preview["ready"] > options["max_new_orders"]:
            raise CommandError(f"Hay {preview['ready']} OT propuestas; supera --max-new-orders={options['max_new_orders']}")
        result = plan_preventive_window(start, end, actor=actor, apply=True, allow_overlap=options["allow_overlap"])
        self.stdout.write(self.style.SUCCESS(f"Aplicado: {result}"))
