"""Repair and validate LF014's quotation workbook print metadata.

The Artifact Tool already emits pageMargins. The original post-processing
appended a second pageMargins element, which violates the worksheet schema and
causes Microsoft Excel to repair sheet1.xml. This script replaces the relevant
nodes in schema order and writes the package atomically.
"""

from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"m": MAIN}
ET.register_namespace("", MAIN)


def qn(name: str) -> str:
    return f"{{{MAIN}}}{name}"


def repair(path: Path) -> None:
    with zipfile.ZipFile(path, "r") as source:
        bad_entry = source.testzip()
        if bad_entry:
            raise ValueError(f"CRC failure before repair: {bad_entry}")
        files = {name: source.read(name) for name in source.namelist()}

    required = {
        "[Content_Types].xml",
        "_rels/.rels",
        "xl/workbook.xml",
        "xl/_rels/workbook.xml.rels",
        "xl/worksheets/sheet1.xml",
        "xl/worksheets/sheet2.xml",
    }
    missing = required.difference(files)
    if missing:
        raise ValueError(f"Missing XLSX components: {sorted(missing)}")

    sheet = ET.fromstring(files["xl/worksheets/sheet1.xml"])
    for tag in ("pageMargins", "pageSetup", "headerFooter"):
        for node in list(sheet.findall(qn(tag))):
            sheet.remove(node)

    children = list(sheet)
    anchor_names = {
        "sheetCalcPr",
        "sheetProtection",
        "protectedRanges",
        "scenarios",
        "autoFilter",
        "sortState",
        "dataConsolidate",
        "customSheetViews",
        "mergeCells",
        "phoneticPr",
        "conditionalFormatting",
        "dataValidations",
        "hyperlinks",
        "printOptions",
    }
    insert_at = 0
    for i, node in enumerate(children):
        if node.tag.split("}")[-1] in anchor_names:
            insert_at = i + 1

    margins = ET.Element(
        qn("pageMargins"),
        {
            "left": "0.3",
            "right": "0.3",
            "top": "0.35",
            "bottom": "0.45",
            "header": "0.1",
            "footer": "0.2",
        },
    )
    setup = ET.Element(
        qn("pageSetup"),
        {
            "paperSize": "9",
            "orientation": "portrait",
            "fitToWidth": "1",
            "fitToHeight": "1",
        },
    )
    header_footer = ET.Element(qn("headerFooter"))
    ET.SubElement(header_footer, qn("oddHeader")).text = (
        "&LEMACTIVA - LeadFlow&RCotización"
    )
    ET.SubElement(header_footer, qn("oddFooter")).text = (
        "&CIdeas que avanzan contigo"
    )
    for offset, node in enumerate((margins, setup, header_footer)):
        sheet.insert(insert_at + offset, node)

    workbook = ET.fromstring(files["xl/workbook.xml"])
    defined_names = workbook.find(qn("definedNames"))
    if defined_names is None:
        defined_names = ET.SubElement(workbook, qn("definedNames"))
    matches = [
        node
        for node in defined_names.findall(qn("definedName"))
        if node.get("name") == "_xlnm.Print_Area"
        and node.get("localSheetId") == "0"
    ]
    if matches:
        print_area = matches[0]
        for duplicate in matches[1:]:
            defined_names.remove(duplicate)
    else:
        print_area = ET.SubElement(
            defined_names,
            qn("definedName"),
            {"name": "_xlnm.Print_Area", "localSheetId": "0"},
        )
    print_area.text = "'COTIZACIÓN'!$A$1:$H$34"

    files["xl/worksheets/sheet1.xml"] = ET.tostring(
        sheet, encoding="utf-8", xml_declaration=True
    )
    files["xl/workbook.xml"] = ET.tostring(
        workbook, encoding="utf-8", xml_declaration=True
    )

    repaired_sheet = ET.fromstring(files["xl/worksheets/sheet1.xml"])
    order = [node.tag.split("}")[-1] for node in repaired_sheet]
    expected_tail = ["pageMargins", "pageSetup", "headerFooter"]
    if order[-3:] != expected_tail:
        raise ValueError(f"Invalid worksheet tail order: {order[-5:]}")
    for tag in expected_tail:
        count = len(repaired_sheet.findall(qn(tag)))
        if count != 1:
            raise ValueError(f"Expected one {tag}, found {count}")

    for name, payload in files.items():
        if name.endswith((".xml", ".rels")):
            ET.fromstring(payload)

    temp = path.with_suffix(path.suffix + ".tmp")
    with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as target:
        for name, payload in files.items():
            target.writestr(name, payload)
    with zipfile.ZipFile(temp, "r") as check:
        bad_entry = check.testzip()
        if bad_entry:
            raise ValueError(f"CRC failure after repair: {bad_entry}")
    os.replace(temp, path)


if __name__ == "__main__":
    workbook_path = Path(
        sys.argv[1]
        if len(sys.argv) > 1
        else "labs/LAB-LF-014/LEADFLOW_PLANTILLA_COTIZACION.xlsx"
    )
    repair(workbook_path)
    print(f"Repaired: {workbook_path}")
