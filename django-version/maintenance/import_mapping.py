"""Named, provisional fields for source rows. Original cells remain authoritative."""

SOURCE_MAPS = {
    "MAQUINAS": (2, "asset_candidate", {
        "source_id": "A", "code": "B", "brand": "C", "model": "D",
        "voltage": "E", "serial_code": "F", "observations": "G", "area": "K",
    }),
    "BASE DE DATOS": (2, "asset_candidate", {
        "code": "A", "name": "B", "material": "C", "brand": "D",
        "model": "E", "voltage": "F",
    }),
    "CALENDARIO": (13, "asset_candidate", {
        "code": "B", "name": "C", "line": "D", "brand": "F",
        "model": "G", "voltage": "H",
    }),
    "ALMACEN": (2, "inventory_candidate", {
        "code": "A", "description": "B", "unit": "C", "stock_raw": "D",
        "unit_cost_raw": "E",
    }),
    "MANTENIMIENTOS": (2, "maintenance_history_candidate", {
        "source_id": "A", "source_asset_id": "B", "event_date_raw": "C",
        "event_time_raw": "D", "classification_raw": "E", "description": "F",
        "responsible_raw": "G", "observations": "H", "performed_raw": "I",
        "repair_time_raw": "J", "delivery_date_raw": "K", "labor_cost_raw": "M",
        "material_cost_raw": "N", "asset_name_raw": "O",
    }),
    "PM": (2, "material_history_candidate", {
        "source_maintenance_id": "A", "event_date_raw": "B", "source_item_code": "C",
        "description": "D", "quantity_raw": "E", "cost_raw": "F",
    }),
    "BASE_DATOS": (2, "work_order_candidate", {
        "folio": "A", "event_date_raw": "B", "requester_raw": "C",
        "priority_raw": "D", "classification_raw": "E", "specialty_raw": "F",
        "location_raw": "G", "reported_failure": "H", "actions": "I",
        "technician_raw": "J", "start_time_raw": "K", "end_time_raw": "L",
        "labor_hours_raw": "M", "material_cost_raw": "N", "status_raw": "O",
        "validator_raw": "P",
    }),
    "CELDA AUTOMATIZACION": (6, "kaizen_candidate", {
        "source_item": "A", "description": "B", "comments": "G",
    }),
}


SOURCE_FIELD_TYPES = {
    "ALMACEN": {"stock_raw": "decimal_candidate", "unit_cost_raw": "decimal_candidate"},
    "MANTENIMIENTOS": {
        "event_date_raw": "date_candidate", "event_time_raw": "time_candidate",
        "delivery_date_raw": "date_candidate", "repair_time_raw": "decimal_candidate",
        "labor_cost_raw": "decimal_candidate", "material_cost_raw": "decimal_candidate",
    },
    "PM": {"event_date_raw": "date_candidate", "quantity_raw": "decimal_candidate", "cost_raw": "decimal_candidate"},
    "BASE_DATOS": {
        "event_date_raw": "date_candidate", "start_time_raw": "time_candidate",
        "end_time_raw": "time_candidate", "labor_hours_raw": "decimal_candidate",
        "material_cost_raw": "decimal_candidate",
    },
}

SOURCE_REQUIRED_FIELDS = {
    "ALMACEN": {"code": "código de insumo"},
    "MANTENIMIENTOS": {"source_id": "ID de mantenimiento de origen"},
    "PM": {
        "source_maintenance_id": "ID de mantenimiento relacionado",
        "source_item_code": "código de insumo relacionado",
    },
    "BASE_DATOS": {"folio": "folio de OT"},
}

TYPE_LABELS = {
    "text": "texto conservado",
    "date_candidate": "fecha por interpretar",
    "time_candidate": "hora por interpretar",
    "decimal_candidate": "número por validar",
}


def map_source_row(sheet, source_row, cells, cell_details=None):
    spec = SOURCE_MAPS.get(sheet.upper())
    if not spec or source_row < spec[0]:
        return {"kind": "unmapped", "fields": {}, "field_types": {}, "type_issues": [], "issues": []}
    _, kind, columns = spec
    cell_details = cell_details or {}
    fields = {}
    for name, column in columns.items():
        value = str(cells.get(f"{column}{source_row}", "")).strip()
        if value:
            fields[name] = value
    issues = []
    if kind == "asset_candidate" and fields and not fields.get("code"):
        issues.append("Candidato de activo sin código; revisar la fila")
    if kind == "asset_candidate" and fields.get("code"):
        fields["code_key"] = fields["code"].casefold()
    declared_types = SOURCE_FIELD_TYPES.get(sheet.upper(), {})
    field_types = {name: declared_types.get(name, "text") for name in fields if name != "code_key"}
    type_issues = []
    allowed_kinds = {
        "date_candidate": {"date", "datetime"},
        "time_candidate": {"time", "datetime"},
        "decimal_candidate": {"number"},
    }
    for name, expected in field_types.items():
        if expected == "text":
            continue
        column = columns[name]
        detail = cell_details.get(f"{column}{source_row}", {})
        actual = detail.get("kind")
        if actual not in allowed_kinds[expected]:
            type_issues.append({
                "field": name, "cell": f"{column}{source_row}",
                "expected": TYPE_LABELS[expected],
                "observed": actual or "texto o tipo sin evidencia",
                "message": f"{name}: confirmar tipo/formato de origen antes de interpretar el valor",
            })
        elif expected == "date_candidate" and not detail.get("iso"):
            type_issues.append({
                "field": name, "cell": f"{column}{source_row}",
                "expected": TYPE_LABELS[expected],
                "observed": "fecha sin interpretación",
                "message": f"{name}: fecha de Excel sin interpretación disponible",
            })
    if not fields:
        kind = "unmapped"
    else:
        for field, label in SOURCE_REQUIRED_FIELDS.get(sheet.upper(), {}).items():
            if not fields.get(field):
                issues.append(f"Falta {label}; revisar la fila antes de conciliar")
        issues = list(dict.fromkeys(issues))
    return {"kind": kind, "fields": fields, "field_types": field_types, "type_issues": type_issues, "issues": issues}
