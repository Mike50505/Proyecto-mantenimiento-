"""Read-only inspection of OOXML workbooks; VBA parts are never opened."""
import posixpath
import re
import zipfile
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree as ET

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
MAX_XML_BYTES = 25 * 1024 * 1024
MAX_TOTAL_XML_BYTES = 80 * 1024 * 1024
MAX_STAGED_ROWS = 10000
MAX_STAGED_CHARACTERS = 5_000_000
CODE_COLUMNS = {
    "MAQUINAS": ("B", 2), "BASE DE DATOS": ("A", 2),
    "CALENDARIO": ("B", 13), "ALMACEN": ("A", 2), "BASE_DATOS": ("A", 2),
}
DATE_FORMAT_IDS = {14, 15, 16, 17}
TIME_FORMAT_IDS = {18, 19, 20, 21, 45, 46, 47}
DATETIME_FORMAT_IDS = {22}


def cell_style_kinds(styles):
    if styles is None:
        return []
    custom = {int(node.get("numFmtId")): node.get("formatCode", "") for node in styles.findall(f".//{{{MAIN}}}numFmt")}
    result = []
    for xf in styles.findall(f".//{{{MAIN}}}cellXfs/{{{MAIN}}}xf"):
        format_id = int(xf.get("numFmtId", "0"))
        if format_id in DATE_FORMAT_IDS:
            kind = "date"
        elif format_id in TIME_FORMAT_IDS:
            kind = "time"
        elif format_id in DATETIME_FORMAT_IDS:
            kind = "datetime"
        else:
            pattern = custom.get(format_id, "")
            pattern = re.sub(r'"[^"]*"|\\.|\[[^]]*\]', "", pattern).lower()
            has_date = bool(re.search(r"[yd]", pattern))
            has_time = bool(re.search(r"[hs]", pattern))
            kind = "datetime" if has_date and has_time else "date" if has_date else "time" if has_time else "number"
        result.append(kind)
    return result


def excel_temporal_value(raw, kind, date1904):
    try:
        serial = Decimal(raw)
        if not serial.is_finite() or serial < 0 or serial > 2958465:
            return None
        if kind == "time":
            seconds = int((serial % 1) * 86400)
            return (datetime.min + timedelta(seconds=seconds)).time().isoformat()
        days = int(serial)
        if not date1904 and (days == 60 or days < 1):
            return None
        base = datetime(1904, 1, 1) if date1904 else datetime(1899, 12, 30) if days > 60 else datetime(1899, 12, 31)
        moment = base + timedelta(days=days, seconds=int((serial % 1) * 86400))
        return moment.date().isoformat() if kind == "date" else moment.isoformat(sep=" ")
    except (InvalidOperation, OverflowError, ValueError):
        return None


def preview_workbook(upload, existing_codes):
    if not upload.name.lower().endswith((".xlsx", ".xlsm")):
        raise ValueError("Selecciona un archivo .xlsx o .xlsm")
    if upload.size > 15 * 1024 * 1024:
        raise ValueError("El libro supera el límite de 15 MB")
    try:
        with zipfile.ZipFile(upload) as archive:
            total_read = 0

            def read_xml(name):
                nonlocal total_read
                info = archive.getinfo(name)
                total_read += info.file_size
                if info.file_size > MAX_XML_BYTES or total_read > MAX_TOTAL_XML_BYTES:
                    raise ValueError("El libro contiene hojas demasiado grandes para la vista previa")
                return ET.fromstring(archive.read(info))

            workbook = read_xml("xl/workbook.xml")
            workbook_properties = workbook.find(f"{{{MAIN}}}workbookPr")
            date1904 = workbook_properties is not None and workbook_properties.get("date1904", "false").lower() in ("true", "1")
            relationships = read_xml("xl/_rels/workbook.xml.rels")
            targets = {rel.get("Id"): rel.get("Target") for rel in relationships.findall(f"{{{PKG_REL}}}Relationship")}
            try:
                strings_xml = read_xml("xl/sharedStrings.xml")
                strings = [
                    "".join(t.text or "" for t in item.iter(f"{{{MAIN}}}t"))
                    for item in strings_xml.findall(f"{{{MAIN}}}si")
                ]
            except KeyError:
                strings = []
            try:
                style_kinds = cell_style_kinds(read_xml("xl/styles.xml"))
            except KeyError:
                style_kinds = []

            sheets = []
            staged_rows = []
            staged_characters = 0
            for sheet in workbook.findall(f".//{{{MAIN}}}sheet"):
                name = sheet.get("name", "")
                target = targets.get(sheet.get(f"{{{REL}}}id"))
                if not target:
                    continue
                path = posixpath.normpath(posixpath.join("xl", target.lstrip("/")))
                if target.startswith("/"):
                    path = target.lstrip("/")
                if not path.startswith("xl/worksheets/"):
                    continue
                root = read_xml(path)
                preview = []
                conflicts = []
                seen = set()
                nonempty = 0
                code_spec = CODE_COLUMNS.get(name.upper())
                for row in root.findall(f".//{{{MAIN}}}sheetData/{{{MAIN}}}row"):
                    values = {}
                    formulas = {}
                    cell_details = {}
                    for cell in row.findall(f"{{{MAIN}}}c"):
                        address = cell.get("r", "")
                        value_node = cell.find(f"{{{MAIN}}}v")
                        formula_node = cell.find(f"{{{MAIN}}}f")
                        if cell.get("t") == "inlineStr":
                            value = "".join(t.text or "" for t in cell.iter(f"{{{MAIN}}}t"))
                        elif value_node is not None and cell.get("t") == "s":
                            index = int(value_node.text or 0)
                            if index < 0 or index >= len(strings):
                                raise ValueError("El libro contiene referencias de texto inválidas")
                            value = strings[index]
                        else:
                            value = value_node.text if value_node is not None else ""
                        if value:
                            values[address] = str(value)
                            cell_type = cell.get("t", "n")
                            if cell_type == "e":
                                cell_details[address] = {"kind": "error", "value": str(value)}
                            elif cell_type == "b":
                                cell_details[address] = {"kind": "boolean", "value": value == "1"}
                            elif cell_type in ("n", ""):
                                style_index = int(cell.get("s", "0"))
                                if style_index < 0 or (style_kinds and style_index >= len(style_kinds)):
                                    raise ValueError("El libro contiene un estilo de celda inválido")
                                kind = style_kinds[style_index] if style_kinds else "number"
                                if kind in ("date", "time", "datetime"):
                                    interpreted = excel_temporal_value(str(value), kind, date1904)
                                    cell_details[address] = {"kind": kind, "iso": interpreted, "date_system": "1904" if date1904 else "1900"}
                                else:
                                    cell_details[address] = {"kind": "number"}
                            elif cell_type == "d":
                                cell_details[address] = {"kind": "date_text", "value": str(value)}
                        if formula_node is not None:
                            formulas[address] = formula_node.text or ""
                    if not values and not formulas:
                        continue
                    if len(values) + len(formulas) > 4096:
                        raise ValueError(f"El libro tiene una fila demasiado ancha para revisión: {name}, fila {row.get('r')}")
                    staged_characters += sum(len(key) + len(value) for key, value in values.items())
                    staged_characters += sum(len(key) + len(value) for key, value in formulas.items())
                    if len(staged_rows) >= MAX_STAGED_ROWS or staged_characters > MAX_STAGED_CHARACTERS:
                        raise ValueError("El libro supera el límite de filas o texto para revisión")
                    nonempty += 1
                    row_number = int(row.get("r", 0))
                    if len(preview) < 6:
                        preview.append({"row": row_number, "cells": {key: value[:300] for key, value in list(values.items())[:12]}})
                    code = ""
                    issues = []
                    for address, detail in cell_details.items():
                        if detail["kind"] == "error" and len(issues) < 10:
                            issues.append(f"Error de Excel en {address}: {detail['value'][:80]}")
                        elif detail["kind"] in ("date", "datetime") and detail["iso"] is None and len(issues) < 10:
                            issues.append(f"Fecha de Excel no interpretable en {address}")
                    if code_spec and row_number >= code_spec[1]:
                        code_column = code_spec[0]
                        address = f"{code_column}{row.get('r')}"
                        code = values.get(address, "").strip()
                        normalized = code.casefold()
                        if code:
                            reason = "Repetido en esta hoja" if normalized in seen else "Ya existe en Django" if normalized in existing_codes else None
                            if reason:
                                issues.append(reason)
                                if len(conflicts) < 100:
                                    conflicts.append({"row": row_number, "code": code[:300], "reason": reason})
                            seen.add(normalized)
                    staged_rows.append({"sheet": name, "source_row": row_number, "cells": values, "formulas": formulas, "cell_details": cell_details, "source_code": code[:300], "issues": issues})
                sheets.append({"name": name, "rows": nonempty, "preview": preview, "conflicts": conflicts})
            return {"filename": upload.name, "sheets": sheets, "read_only": True,
                    "date_system": "1904" if date1904 else "1900", "staged_rows": staged_rows}
    except (zipfile.BadZipFile, ET.ParseError, KeyError, ValueError, IndexError) as error:
        if isinstance(error, ValueError) and str(error).startswith(("Selecciona", "El libro")):
            raise
        raise ValueError("El archivo no es un libro Excel válido o está dañado") from error
