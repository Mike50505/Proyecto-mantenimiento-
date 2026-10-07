"""Small dependency-free XLSX writer for controlled, typed exports."""

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from xml.etree.ElementTree import Element, SubElement, tostring
from zipfile import ZIP_DEFLATED, ZipFile

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
XML = "http://www.w3.org/XML/1998/namespace"


def _tag(namespace, name):
    return f"{{{namespace}}}{name}"


def _column_name(number):
    name = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _excel_date(value):
    if isinstance(value, datetime):
        value = value.replace(tzinfo=None)
        return (value - datetime(1899, 12, 30)).total_seconds() / 86400
    return (value - date(1899, 12, 30).date()).days


def make_workbook(sheet_name, headers, rows, date_columns=(), decimal_columns=(), decimal_precision_columns=()):
    """Return a one-sheet XLSX. Strings are inline text, dates/numbers are numeric cells."""
    date_columns, decimal_columns = set(date_columns), set(decimal_columns)
    decimal_precision_columns = set(decimal_precision_columns)
    workbook = Element(_tag(MAIN, "workbook"))
    workbook.set("xmlns:r", REL)
    sheets = SubElement(workbook, _tag(MAIN, "sheets"))
    sheet = SubElement(sheets, _tag(MAIN, "sheet"), {"name": sheet_name[:31], "sheetId": "1"})
    sheet.set(_tag(REL, "id"), "rId1")

    rels = Element(_tag(PKG_REL, "Relationships"))
    SubElement(rels, _tag(PKG_REL, "Relationship"), {
        "Id": "rId1", "Type": f"{REL}/worksheet", "Target": "worksheets/sheet1.xml"
    })
    SubElement(rels, _tag(PKG_REL, "Relationship"), {
        "Id": "rId2", "Type": f"{REL}/styles", "Target": "styles.xml"
    })

    styles = Element(_tag(MAIN, "styleSheet"))
    custom = SubElement(styles, _tag(MAIN, "numFmts"), {"count": "3"})
    SubElement(custom, _tag(MAIN, "numFmt"), {"numFmtId": "164", "formatCode": "yyyy-mm-dd hh:mm"})
    SubElement(custom, _tag(MAIN, "numFmt"), {"numFmtId": "165", "formatCode": "0.00"})
    SubElement(custom, _tag(MAIN, "numFmt"), {"numFmtId": "166", "formatCode": "0.0000"})
    fonts = SubElement(styles, _tag(MAIN, "fonts"), {"count": "2"})
    SubElement(fonts, _tag(MAIN, "font"))
    bold = SubElement(fonts, _tag(MAIN, "font")); SubElement(bold, _tag(MAIN, "b"))
    fills = SubElement(styles, _tag(MAIN, "fills"), {"count": "2"})
    SubElement(fills, _tag(MAIN, "fill"), {}).append(Element(_tag(MAIN, "patternFill"), {"patternType": "none"}))
    header_fill = SubElement(fills, _tag(MAIN, "fill")); SubElement(header_fill, _tag(MAIN, "patternFill"), {"patternType": "solid"}).append(Element(_tag(MAIN, "fgColor"), {"rgb": "FF17324D"}))
    borders = SubElement(styles, _tag(MAIN, "borders"), {"count": "1"}); SubElement(borders, _tag(MAIN, "border"))
    SubElement(styles, _tag(MAIN, "cellStyleXfs"), {"count": "1"}).append(Element(_tag(MAIN, "xf"), {"numFmtId": "0", "fontId": "0", "fillId": "0", "borderId": "0"}))
    cell_xfs = SubElement(styles, _tag(MAIN, "cellXfs"), {"count": "5"})
    for attrs in ({"numFmtId": "0", "fontId": "0", "fillId": "0"},
                  {"numFmtId": "0", "fontId": "1", "fillId": "1", "applyFont": "1", "applyFill": "1"},
                  {"numFmtId": "164", "fontId": "0", "fillId": "0", "applyNumberFormat": "1"},
                  {"numFmtId": "165", "fontId": "0", "fillId": "0", "applyNumberFormat": "1"},
                  {"numFmtId": "166", "fontId": "0", "fillId": "0", "applyNumberFormat": "1"}):
        SubElement(cell_xfs, _tag(MAIN, "xf"), {**attrs, "borderId": "0", "xfId": "0"})
    SubElement(styles, _tag(MAIN, "cellStyles"), {"count": "1"}).append(Element(_tag(MAIN, "cellStyle"), {"name": "Normal", "xfId": "0", "builtinId": "0"}))

    sheet_data = Element(_tag(MAIN, "worksheet"))
    sheet_data.set("xmlns:r", REL)
    dimension = f"A1:{_column_name(len(headers))}{max(1, len(rows) + 1)}"
    SubElement(sheet_data, _tag(MAIN, "dimension"), {"ref": dimension})
    views = SubElement(sheet_data, _tag(MAIN, "sheetViews")); view = SubElement(views, _tag(MAIN, "sheetView"), {"workbookViewId": "0"})
    SubElement(view, _tag(MAIN, "pane"), {"ySplit": "1", "topLeftCell": "A2", "activePane": "bottomLeft", "state": "frozen"})
    SubElement(sheet_data, _tag(MAIN, "sheetFormatPr"), {"defaultRowHeight": "18"})
    cols = SubElement(sheet_data, _tag(MAIN, "cols"))
    for index, header in enumerate(headers, 1):
        width = max(12, min(42, len(str(header)) + 3))
        SubElement(cols, _tag(MAIN, "col"), {"min": str(index), "max": str(index), "width": str(width), "customWidth": "1"})
    data = SubElement(sheet_data, _tag(MAIN, "sheetData"))

    def add_row(row_number, values, header=False):
        row = SubElement(data, _tag(MAIN, "row"), {"r": str(row_number)})
        for index, value in enumerate(values, 1):
            if value is None:
                continue
            cell = SubElement(row, _tag(MAIN, "c"), {"r": f"{_column_name(index)}{row_number}"})
            if header:
                cell.set("s", "1")
            elif index in date_columns and isinstance(value, (datetime, date)):
                cell.set("s", "2"); SubElement(cell, _tag(MAIN, "v")).text = str(_excel_date(value))
            elif index in decimal_columns and isinstance(value, (int, float, Decimal)):
                cell.set("s", "3"); SubElement(cell, _tag(MAIN, "v")).text = str(value)
            elif index in decimal_precision_columns and isinstance(value, (int, float, Decimal)):
                cell.set("s", "4"); SubElement(cell, _tag(MAIN, "v")).text = str(value)
            elif isinstance(value, bool):
                cell.set("t", "b"); SubElement(cell, _tag(MAIN, "v")).text = "1" if value else "0"
            elif isinstance(value, (int, float, Decimal)):
                SubElement(cell, _tag(MAIN, "v")).text = str(value)
            else:
                cell.set("t", "inlineStr")
                inline = SubElement(cell, _tag(MAIN, "is")); text = SubElement(inline, _tag(MAIN, "t"))
                text.set(_tag(XML, "space"), "preserve"); text.text = str(value)

    add_row(1, headers, header=True)
    for number, values in enumerate(rows, 2):
        add_row(number, values)
    SubElement(sheet_data, _tag(MAIN, "autoFilter"), {"ref": dimension})

    content_types = Element(_tag(CT, "Types"))
    SubElement(content_types, _tag(CT, "Default"), {"Extension": "rels", "ContentType": "application/vnd.openxmlformats-package.relationships+xml"})
    SubElement(content_types, _tag(CT, "Default"), {"Extension": "xml", "ContentType": "application/xml"})
    SubElement(content_types, _tag(CT, "Override"), {"PartName": "/xl/workbook.xml", "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"})
    SubElement(content_types, _tag(CT, "Override"), {"PartName": "/xl/worksheets/sheet1.xml", "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"})
    SubElement(content_types, _tag(CT, "Override"), {"PartName": "/xl/styles.xml", "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"})
    root_rels = Element(_tag(PKG_REL, "Relationships"))
    SubElement(root_rels, _tag(PKG_REL, "Relationship"), {"Id": "rId1", "Type": f"{REL}/officeDocument", "Target": "xl/workbook.xml"})

    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, root in (("[Content_Types].xml", content_types), ("_rels/.rels", root_rels),
                           ("xl/workbook.xml", workbook), ("xl/_rels/workbook.xml.rels", rels),
                           ("xl/styles.xml", styles), ("xl/worksheets/sheet1.xml", sheet_data)):
            archive.writestr(name, tostring(root, encoding="utf-8", xml_declaration=True))
    return output.getvalue()
