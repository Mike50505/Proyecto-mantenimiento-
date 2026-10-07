from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    ROLES = [(x, x) for x in ("Administrador", "Jefatura", "Técnico", "Solicitante")]
    employee_number = models.CharField(max_length=50, unique=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=20, choices=ROLES, default="Solicitante")
    must_change_password = models.BooleanField(default=False)
    module_permissions = models.JSONField(default=list, blank=True)
    action_permissions = models.JSONField(default=list, blank=True)
    area_permissions = models.JSONField(default=list, blank=True)

    @property
    def name(self):
        return self.first_name


class CatalogEntry(models.Model):
    KINDS = [(value, value) for value in ("priority", "classification", "specialty", "area", "line", "shift")]
    kind = models.CharField(max_length=30, choices=KINDS)
    value = models.CharField(max_length=120)
    active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["kind", "value"], name="unique_catalog_value")]
        ordering = ["kind", "sort_order", "value"]


class Asset(models.Model):
    code = models.CharField(max_length=80, unique=True)
    original_code = models.CharField(max_length=80, blank=True)
    alias_codes = models.TextField(blank=True)
    name = models.CharField(max_length=250)
    category = models.CharField(max_length=80, default="Maquinaria")
    asset_type = models.CharField(max_length=80, default="Maquinaria")
    area = models.CharField(max_length=120)
    line = models.CharField(max_length=120, blank=True)
    location_detail = models.CharField(max_length=250, blank=True)
    brand = models.CharField(max_length=120, blank=True)
    model = models.CharField(max_length=120, blank=True)
    voltage = models.CharField(max_length=80, blank=True)
    serial_code = models.CharField(max_length=120, blank=True)
    observations = models.TextField(blank=True)
    operating_hours = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    operational_status = models.CharField(max_length=40, default="Sin información")
    operational_status_cause = models.TextField(blank=True)
    operational_status_updated_at = models.DateTimeField(null=True, blank=True)
    administrative_status = models.CharField(max_length=40, default="Activo")
    critical = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class AssetCodeEquivalence(models.Model):
    STATUSES = [(value, value) for value in ("Pendiente", "Aprobada", "Rechazada")]
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="code_equivalences")
    code = models.CharField(max_length=80)
    code_key = models.CharField(max_length=80)
    status = models.CharField(max_length=12, choices=STATUSES, default="Pendiente")
    source_file = models.CharField(max_length=250, blank=True)
    source_sheet = models.CharField(max_length=120, blank=True)
    source_row = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField()
    proposed_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="proposed_asset_codes")
    reviewed_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="reviewed_asset_codes")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["asset", "code_key"], name="unique_asset_code_candidate"),
            models.UniqueConstraint(fields=["code_key"], condition=models.Q(status="Aprobada"), name="unique_approved_asset_code"),
        ]


class FolioSequence(models.Model):
    year = models.PositiveIntegerField(primary_key=True)
    next_number = models.PositiveIntegerField(default=1)


class WorkOrder(models.Model):
    folio = models.CharField(max_length=40, unique=True)
    original_folio = models.CharField(max_length=80, blank=True)
    requested_at = models.DateTimeField()
    requester = models.ForeignKey(User, on_delete=models.PROTECT, related_name="requested_orders")
    priority = models.CharField(max_length=40)
    classification = models.CharField(max_length=80)
    specialty = models.CharField(max_length=80, blank=True)
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, null=True, blank=True, related_name="work_orders")
    location = models.CharField(max_length=250, blank=True)
    reported_failure = models.TextField()
    actions = models.TextField(blank=True)
    technician = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="assigned_orders")
    participants = models.ManyToManyField(User, related_name="participating_orders", blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    labor_hours = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    labor_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    material_cost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=40, default="Abierta", db_index=True)
    validation_status = models.CharField(max_length=40, default="No aplica")
    validator = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="validated_orders")
    validated_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    close_reason = models.TextField(blank=True)
    closure_notes = models.TextField(blank=True)
    closure_document_code = models.CharField(max_length=80, blank=True)
    closure_document_revision = models.CharField(max_length=40, blank=True)
    autonomous_checklist = models.TextField(blank=True)
    version = models.PositiveIntegerField(default=1)
    idempotency_key = models.CharField(max_length=120, null=True, blank=True)
    idempotency_hash = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["requester", "idempotency_key"], name="unique_order_request")]
        indexes = [models.Index(fields=["status", "requested_at"]), models.Index(fields=["asset", "status"])]


class WorkOrderEvent(models.Model):
    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name="events")
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=True)
    event = models.CharField(max_length=100)
    details = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class WorkOrderDocument(models.Model):
    work_order = models.ForeignKey(WorkOrder, on_delete=models.PROTECT, related_name="documents")
    version = models.PositiveIntegerField()
    document_number = models.CharField(max_length=120)
    source_order_version = models.PositiveIntegerField()
    snapshot = models.JSONField()
    sha256 = models.CharField(max_length=64)
    pdf_content = models.BinaryField()
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="generated_work_order_documents")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version"]
        constraints = [models.UniqueConstraint(fields=["work_order", "version"], name="unique_work_order_document_version")]


class TimeEntry(models.Model):
    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name="time_entries")
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    pause_reason = models.TextField(blank=True)
    source = models.CharField(max_length=40, default="manual")
    created_at = models.DateTimeField(auto_now_add=True)


class InventoryItem(models.Model):
    code = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=250)
    category = models.CharField(max_length=120)
    unit = models.CharField(max_length=40)
    stock = models.DecimalField(max_digits=16, decimal_places=4, default=0)
    min_stock = models.DecimalField(max_digits=16, decimal_places=4, default=0)
    max_stock = models.DecimalField(max_digits=16, decimal_places=4, default=0)
    unit_cost = models.DecimalField(max_digits=16, decimal_places=4, default=0)
    location = models.CharField(max_length=250, blank=True)
    active = models.BooleanField(default=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)


class InventoryMovement(models.Model):
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT, related_name="movements")
    type = models.CharField(max_length=30)
    quantity = models.DecimalField(max_digits=16, decimal_places=4)
    unit_cost = models.DecimalField(max_digits=16, decimal_places=4, default=0)
    work_order = models.ForeignKey(WorkOrder, on_delete=models.PROTECT, null=True, blank=True, related_name="inventory_movements")
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    notes = models.TextField(blank=True)
    return_of = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="returns")
    request_key = models.CharField(max_length=120)
    request_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "request_key"], name="unique_stock_request")]


class MaintenanceMaterial(models.Model):
    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name="materials")
    item = models.ForeignKey(InventoryItem, on_delete=models.PROTECT)
    code = models.CharField(max_length=80)
    description = models.CharField(max_length=250)
    quantity = models.DecimalField(max_digits=16, decimal_places=4)
    returned_quantity = models.DecimalField(max_digits=16, decimal_places=4, default=0)
    unit_cost = models.DecimalField(max_digits=16, decimal_places=4)
    movement = models.OneToOneField(InventoryMovement, on_delete=models.PROTECT)


class PreventivePlan(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="preventive_plans")
    title = models.CharField(max_length=250)
    frequency = models.CharField(max_length=120)
    next_date = models.DateField()
    responsible = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True)
    status = models.CharField(max_length=40, default="Programado")
    work_order = models.ForeignKey(WorkOrder, on_delete=models.PROTECT, null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    template_code = models.CharField(max_length=80, blank=True)
    instructions = models.TextField(blank=True)
    applies_when = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class PreventiveTask(models.Model):
    plan = models.ForeignKey(PreventivePlan, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=250)
    interval_unit = models.CharField(max_length=10)
    interval_value = models.PositiveIntegerField()
    anchor_date = models.DateField()
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    applicability_status = models.CharField(max_length=12, default="Pendiente", choices=[(value, value) for value in ("Pendiente", "Interna", "Externa", "No aplica")])
    applicability_reason = models.TextField(blank=True)
    validated_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="validated_preventive_tasks")
    validated_at = models.DateTimeField(null=True, blank=True)


class PreventivePlanRevision(models.Model):
    plan = models.ForeignKey(PreventivePlan, on_delete=models.CASCADE, related_name="revisions")
    version = models.PositiveIntegerField()
    snapshot = models.JSONField()
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=True)
    source = models.CharField(max_length=80)
    reason = models.TextField(blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["plan", "version"], name="unique_plan_revision")]


class PreventiveOccurrence(models.Model):
    plan = models.ForeignKey(PreventivePlan, on_delete=models.PROTECT, related_name="occurrences")
    task = models.ForeignKey(PreventiveTask, on_delete=models.PROTECT, related_name="occurrences")
    occurrence_index = models.PositiveIntegerField()
    base_date = models.DateField()
    work_order = models.ForeignKey(WorkOrder, on_delete=models.PROTECT, related_name="preventive_occurrences")
    revision = models.ForeignKey(PreventivePlanRevision, on_delete=models.PROTECT)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["task", "occurrence_index"], name="unique_occurrence")]


class PreventiveExecutionEvent(models.Model):
    occurrence = models.ForeignKey(PreventiveOccurrence, on_delete=models.PROTECT, related_name="execution_events")
    event = models.CharField(max_length=30)
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    notes = models.TextField(blank=True)
    reason = models.TextField(blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)


class PreventiveTemplate(models.Model):
    code = models.CharField(max_length=80, unique=True)
    family = models.CharField(max_length=80)
    title = models.CharField(max_length=250)
    instructions = models.TextField(blank=True)
    tasks = models.JSONField(default=list)
    active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class MeterReading(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="meter_readings")
    value = models.DecimalField(max_digits=14, decimal_places=2)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(User, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now_add=True)


class DowntimeEvent(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.PROTECT, related_name="downtime_events")
    cause = models.TextField()
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    work_orders = models.ManyToManyField(WorkOrder, related_name="downtime_events", blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="created_downtime_events")
    closed_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="closed_downtime_events")
    close_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ChecklistItem(models.Model):
    task = models.ForeignKey(PreventiveTask, on_delete=models.CASCADE, related_name="checklist_items")
    position = models.PositiveIntegerField()
    prompt = models.CharField(max_length=500)
    required = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["task", "position"], name="unique_check_position")]


class ChecklistAnswer(models.Model):
    occurrence = models.ForeignKey(PreventiveOccurrence, on_delete=models.PROTECT, related_name="checklist_answers")
    item = models.ForeignKey(ChecklistItem, on_delete=models.PROTECT)
    answer = models.CharField(max_length=4)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(User, on_delete=models.PROTECT)
    recorded_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["occurrence", "item"], name="unique_check_answer")]


class AuditLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=True)
    entity_type = models.CharField(max_length=80)
    entity_id = models.BigIntegerField(null=True)
    action = models.CharField(max_length=100)
    before = models.JSONField(null=True)
    after = models.JSONField(null=True)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class OperationalAlert(models.Model):
    STATUSES = [(value, value) for value in ("Abierta", "Atendida", "Cerrada")]
    source_key = models.CharField(max_length=160, unique=True)
    kind = models.CharField(max_length=40)
    source_id = models.PositiveBigIntegerField()
    area = models.CharField(max_length=120, blank=True)
    title = models.CharField(max_length=250)
    detail = models.TextField(blank=True)
    severity = models.CharField(max_length=20, default="Aviso")
    status = models.CharField(max_length=12, choices=STATUSES, default="Abierta", db_index=True)
    handling_note = models.TextField(blank=True)
    handled_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="handled_operational_alerts")
    handled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["status", "-updated_at", "id"]


class ImportBatch(models.Model):
    STATUSES = [("Revision", "En revisión"), ("Descartado", "Descartado")]
    content_hash = models.CharField(max_length=64, unique=True)
    filename = models.CharField(max_length=250)
    status = models.CharField(max_length=12, choices=STATUSES, default="Revision")
    preview = models.JSONField(default=dict)
    uploaded_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="import_batches")
    discarded_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="discarded_import_batches")
    discarded_at = models.DateTimeField(null=True, blank=True)
    discard_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["status", "created_at"], name="maintenance_status_8ac840_idx")]


class ImportRow(models.Model):
    REVIEW_STATUSES = [(value, value) for value in ("Pendiente", "Excluida", "Propuesta")]
    batch = models.ForeignKey(ImportBatch, on_delete=models.CASCADE, related_name="source_rows")
    sheet = models.CharField(max_length=120)
    source_row = models.PositiveIntegerField()
    cells = models.JSONField(default=dict)
    formulas = models.JSONField(default=dict)
    cell_details = models.JSONField(default=dict)
    source_code = models.CharField(max_length=300, blank=True)
    issues = models.JSONField(default=list)
    review_status = models.CharField(max_length=12, choices=REVIEW_STATUSES, default="Pendiente")
    proposed_asset = models.ForeignKey(Asset, on_delete=models.PROTECT, null=True, blank=True, related_name="import_row_proposals")
    review_note = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="reviewed_import_rows")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["sheet", "source_row", "id"]
        constraints = [models.UniqueConstraint(fields=["batch", "sheet", "source_row"], name="unique_import_source_row")]
        indexes = [models.Index(fields=["batch", "sheet", "source_row"], name="maintenance_import_rows_idx")]
