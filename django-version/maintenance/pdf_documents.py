"""Immutable PDF snapshots for maintenance work orders."""

from decimal import Decimal, InvalidOperation
from xml.sax.saxutils import escape

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


NAVY = colors.HexColor("#17324D")
BLUE = colors.HexColor("#287A9B")
PALE = colors.HexColor("#EAF1F5")
MUTED = colors.HexColor("#5D6872")
GRID = colors.HexColor("#C6D0D8")


def _text(value):
    raw = "-" if value in (None, "") else str(value)
    return escape(raw).replace("\n", "<br/>")


def _decimal(value):
    try:
        return Decimal(str(value or "0"))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _money(value):
    return f"${_decimal(value):,.2f} MXN"


def _date(value):
    if not value:
        return "-"
    try:
        from datetime import datetime
        parsed = datetime.fromisoformat(str(value))
        return parsed.strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return str(value)


def work_order_snapshot(order):
    """Capture every value that appears in the printable maintenance record."""
    materials = []
    net_material_cost = Decimal("0")
    for material in order.materials.order_by("id"):
        quantity = Decimal(material.quantity)
        returned = Decimal(material.returned_quantity)
        unit_cost = Decimal(material.unit_cost)
        total = (quantity - returned) * unit_cost
        net_material_cost += total
        materials.append({
            "code": material.code,
            "description": material.description,
            "quantity": str(quantity),
            "returned_quantity": str(returned),
            "unit_cost": str(unit_cost),
            "total": str(total),
        })

    def local_iso(value):
        return timezone.localtime(value).isoformat() if value and timezone.is_aware(value) else value.isoformat() if value else None

    preventives = []
    occurrences = order.preventive_occurrences.select_related("plan", "plan__asset", "task", "revision").prefetch_related(
        "task__checklist_items", "checklist_answers__item", "execution_events__user"
    ).order_by("base_date", "id")
    for occurrence in occurrences:
        answers = {answer.item_id: answer for answer in occurrence.checklist_answers.all()}
        checklist = [{
            "prompt": item.prompt,
            "required": item.required,
            "answer": answers[item.id].answer if item.id in answers else "",
            "notes": answers[item.id].notes if item.id in answers else "",
        } for item in sorted(occurrence.task.checklist_items.all(), key=lambda item: item.position)]
        execution_events = [{
            "event": event.event,
            "user": event.user.first_name,
            "notes": event.notes,
            "reason": event.reason,
            "recorded_at": local_iso(event.recorded_at),
        } for event in sorted(occurrence.execution_events.all(), key=lambda event: event.recorded_at)]
        preventives.append({
            "plan_title": occurrence.plan.title,
            "plan_asset": occurrence.plan.asset.name,
            "template_code": occurrence.plan.template_code,
            "revision_version": occurrence.revision.version,
            "task_title": occurrence.task.title,
            "interval_unit": "días" if occurrence.task.interval_unit == "days" else "meses",
            "interval_value": occurrence.task.interval_value,
            "anchor_date": occurrence.task.anchor_date.isoformat(),
            "base_date": occurrence.base_date.isoformat(),
            "checklist": checklist,
            "execution_events": execution_events,
            "execution_state": execution_events[-1]["event"] if execution_events else "pending",
        })

    asset = order.asset
    return {
        "folio": order.folio, "source_order_version": order.version,
        "status": order.status, "validation_status": order.validation_status,
        "requested_at": local_iso(order.requested_at), "scheduled_at": local_iso(order.scheduled_at),
        "started_at": local_iso(order.started_at), "finished_at": local_iso(order.finished_at),
        "priority": order.priority, "classification": order.classification, "specialty": order.specialty,
        "asset_name": asset.name if asset else "", "asset_code": asset.code if asset else "",
        "area": asset.area if asset else order.location,
        "asset_brand": asset.brand if asset else "", "asset_model": asset.model if asset else "",
        "asset_voltage": asset.voltage if asset else "", "location": order.location,
        "requester_name": order.requester.get_full_name() or order.requester.first_name,
        "technician_name": (order.technician.get_full_name() or order.technician.first_name) if order.technician else "",
        "validator_name": (order.validator.get_full_name() or order.validator.first_name) if order.validator else "",
        "validated_at": local_iso(order.validated_at),
        "reported_failure": order.reported_failure, "actions": order.actions,
        "autonomous_checklist": order.autonomous_checklist,
        "closure_notes": order.closure_notes,
        "closure_document_code": order.closure_document_code,
        "closure_document_revision": order.closure_document_revision,
        "labor_hours": str(order.labor_hours),
        "material_cost": str(net_material_cost), "materials": materials,
        "preventive_occurrences": preventives,
    }


def render_work_order_pdf(snapshot):
    """Render a stored snapshot; never query mutable operational records here."""
    from io import BytesIO

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15 * mm,
        leftMargin=15 * mm,
        topMargin=25 * mm,
        bottomMargin=18 * mm,
        title=f"Orden {snapshot['folio']} - {snapshot['document_number']}",
        author="MESA Mantenimiento",
        subject="Copia versionada de una orden de trabajo",
    )
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("MesaTitle", parent=base["Title"], fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=NAVY, alignment=TA_LEFT, spaceAfter=2 * mm),
        "subtitle": ParagraphStyle("MesaSubtitle", parent=base["Normal"], fontName="Helvetica", fontSize=8, leading=11, textColor=MUTED, spaceAfter=4 * mm),
        "section": ParagraphStyle("MesaSection", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=9, leading=12, textColor=colors.white, backColor=NAVY, borderPadding=(5, 7, 5, 7), spaceBefore=4 * mm, spaceAfter=2 * mm),
        "label": ParagraphStyle("MesaLabel", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=7.4, leading=10, textColor=NAVY),
        "value": ParagraphStyle("MesaValue", parent=base["Normal"], fontName="Helvetica", fontSize=8, leading=11, textColor=colors.HexColor("#1D252C")),
        "cell": ParagraphStyle("MesaCell", parent=base["Normal"], fontName="Helvetica", fontSize=7, leading=9, textColor=colors.HexColor("#1D252C")),
        "cell_head": ParagraphStyle("MesaCellHead", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=7, leading=9, textColor=colors.white),
        "center": ParagraphStyle("MesaCenter", parent=base["Normal"], fontName="Helvetica", fontSize=8, leading=11, alignment=TA_CENTER),
        "right": ParagraphStyle("MesaRight", parent=base["Normal"], fontName="Helvetica", fontSize=8, leading=11, alignment=TA_RIGHT),
        "notice": ParagraphStyle("MesaNotice", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=8, leading=11, textColor=BLUE, backColor=PALE, borderPadding=7, spaceBefore=2 * mm, spaceAfter=2 * mm),
    }

    def para(value, style="value"):
        return Paragraph(_text(value), styles[style])

    story = [
        Paragraph("MESA <font color='#287A9B'>/</font> MANTENIMIENTO", styles["title"]),
        Paragraph("MANUFACTURAS ESPECIALIZADAS S.A. - PLANTA RAMOS", styles["subtitle"]),
        para(f"COPIA VERSIONADA EN MESA | {snapshot['document_number']} | Versión {snapshot['version']}", "notice"),
        para(f"Captura del folio {snapshot['folio']} al { _date(snapshot['generated_at']) }. Esta copia refleja la versión de OT {snapshot['source_order_version']}.", "subtitle"),
    ]

    def section(title):
        story.append(Paragraph(escape(title.upper()), styles["section"]))

    def key_value_table(pairs):
        cells = []
        for left_label, left_value, right_label, right_value in pairs:
            cells.append([para(left_label, "label"), para(left_value), para(right_label, "label"), para(right_value)])
        table = Table(cells, colWidths=[28 * mm, 58 * mm, 28 * mm, 66 * mm], hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), PALE), ("BACKGROUND", (2, 0), (2, -1), PALE),
            ("GRID", (0, 0), (-1, -1), 0.45, GRID), ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(table)

    section("Datos generales")
    key_value_table([
        ("Folio OT", snapshot["folio"], "Estado", snapshot["status"]),
        ("Fecha de solicitud", _date(snapshot["requested_at"]), "Prioridad", snapshot["priority"]),
        ("Clasificación", snapshot["classification"], "Especialidad", snapshot["specialty"] or "-"),
        ("Activo", snapshot["asset_name"] or "Sin activo asociado", "Código", snapshot["asset_code"] or "-"),
        ("Área", snapshot["area"] or "-", "Ubicación", snapshot["location"] or "-"),
        ("Marca / modelo", " / ".join(x for x in (snapshot["asset_brand"], snapshot["asset_model"]) if x) or "-", "Voltaje", snapshot["asset_voltage"] or "-"),
        ("Solicitante", snapshot["requester_name"], "Responsable", snapshot["technician_name"] or "Sin asignar"),
        ("Inicio", _date(snapshot["started_at"] or snapshot["requested_at"]), "Fin", _date(snapshot["finished_at"])),
        ("Horas hombre", f"{_decimal(snapshot['labor_hours']):.2f} h", "Fecha programada", _date(snapshot["scheduled_at"])),
    ])

    section("Falla reportada")
    story.append(para(snapshot["reported_failure"]))
    section("Trabajo realizado")
    story.append(para(snapshot["actions"] or "Sin acciones registradas."))
    if snapshot.get("autonomous_checklist"):
        section("Revisión autónoma")
        story.append(para(snapshot["autonomous_checklist"]))
    if snapshot.get("closure_notes"):
        section("Notas de cierre")
        story.append(para(snapshot["closure_notes"]))

    section("Materiales e insumos")
    material_rows = [[para(x, "cell_head") for x in ("Código", "Descripción", "Cantidad", "Devuelto", "Costo unitario", "Total neto")]]
    for item in snapshot["materials"]:
        material_rows.append([
            para(item["code"] or "-", "cell"), para(item["description"], "cell"),
            para(item["quantity"], "right"), para(item["returned_quantity"], "right"),
            para(_money(item["unit_cost"]), "right"), para(_money(item["total"]), "right"),
        ])
    if len(material_rows) == 1:
        material_rows.append([para("Sin materiales registrados.", "cell"), "", "", "", "", ""])
    material_table = LongTable(material_rows, colWidths=[22 * mm, 54 * mm, 20 * mm, 20 * mm, 28 * mm, 36 * mm], repeatRows=1, hAlign="LEFT")
    material_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("GRID", (0, 0), (-1, -1), 0.45, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(material_table)

    if snapshot.get("preventive_occurrences"):
        section("Ejecución preventiva")
        event_labels = {
            "terminated": "Terminada", "validated": "Validada", "returned": "Devuelta a trabajo",
            "cancelled": "Cancelada", "reopened": "Reabierta",
        }
        for occurrence in snapshot["preventive_occurrences"]:
            key_value_table([
                ("Plan", occurrence["plan_title"], "Activo del plan", occurrence["plan_asset"]),
                ("Tarea", occurrence["task_title"], "Vencimiento base", occurrence["base_date"]),
            ("Plantilla", occurrence["template_code"] or "-", "Revisión del plan", occurrence["revision_version"]),
            ("Ancla de recurrencia", occurrence["anchor_date"], "Intervalo", f"Cada {occurrence['interval_value']} {occurrence['interval_unit']}"),
            ("Estado de ejecución", event_labels.get(occurrence["execution_state"], "Sin ejecución registrada" if occurrence["execution_state"] == "pending" else occurrence["execution_state"]), "Eventos", len(occurrence["execution_events"])),
        ])
            if occurrence["checklist"]:
                checklist_rows = [[para(text, "cell_head") for text in ("Punto de revisión", "Obligatorio", "Respuesta", "Notas")]]
                checklist_rows.extend([
                    [para(item["prompt"], "cell"), para("Sí" if item["required"] else "No", "center"),
                     para(item["answer"] or "Sin respuesta", "center"), para(item["notes"], "cell")]
                    for item in occurrence["checklist"]
                ])
                checklist_table = LongTable(checklist_rows, colWidths=[76 * mm, 24 * mm, 30 * mm, 50 * mm], repeatRows=1, hAlign="LEFT")
                checklist_table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), BLUE), ("GRID", (0, 0), (-1, -1), 0.45, GRID),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]))
                story.append(checklist_table)
            if occurrence["execution_events"]:
                event_rows = [[para(text, "cell_head") for text in ("Evento", "Fecha", "Usuario", "Notas / motivo")]]
                event_rows.extend([
                    [para(event_labels.get(event["event"], event["event"]), "cell"), para(_date(event["recorded_at"]), "cell"),
                     para(event["user"], "cell"), para("; ".join(part for part in (event["notes"], event["reason"]) if part), "cell")]
                    for event in occurrence["execution_events"]
                ])
                event_table = LongTable(event_rows, colWidths=[30 * mm, 33 * mm, 31 * mm, 86 * mm], repeatRows=1, hAlign="LEFT")
                event_table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), BLUE), ("GRID", (0, 0), (-1, -1), 0.45, GRID),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]))
                story.append(event_table)

    section("Validación y control documental")
    key_value_table([
        ("Validó", snapshot["validator_name"] or "Pendiente", "Fecha de validación", _date(snapshot["validated_at"])),
        ("Código documental", snapshot["closure_document_code"] or "Pendiente de configurar", "Revisión de formato", snapshot["closure_document_revision"] or "Pendiente de configurar"),
        ("Horas hombre", f"{_decimal(snapshot['labor_hours']):.2f} h", "Costo neto de materiales", _money(snapshot["material_cost"])),
        ("Hash de contenido", snapshot["snapshot_sha256"][:16], "", ""),
    ])
    story.append(Spacer(1, 4 * mm))
    story.append(para("La versión archivada en MESA conserva el contenido de esta captura. La aprobación del código y revisión del formato oficial corresponde al control documental de planta.", "subtitle"))

    def page_marks(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(GRID)
        canvas.line(doc.leftMargin, A4[1] - 14 * mm, A4[0] - doc.rightMargin, A4[1] - 14 * mm)
        canvas.setFont("Helvetica-Bold", 7)
        canvas.setFillColor(NAVY)
        canvas.drawString(doc.leftMargin, A4[1] - 11 * mm, "MESA - MANTENIMIENTO PLANTA RAMOS")
        canvas.setStrokeColor(GRID)
        canvas.line(doc.leftMargin, 12 * mm, A4[0] - doc.rightMargin, 12 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(MUTED)
        canvas.drawString(doc.leftMargin, 8 * mm, f"{snapshot['folio']} | {snapshot['document_number']} | Copia versionada en MESA")
        canvas.drawRightString(A4[0] - doc.rightMargin, 8 * mm, f"Página {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=page_marks, onLaterPages=page_marks)
    return buffer.getvalue()
