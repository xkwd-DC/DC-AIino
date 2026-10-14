"""Inspect an .xlsx without openpyxl: sheet names + first rows of each sheet.

Streams sharedStrings.xml so a 70 MB workbook stays cheap to inspect.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}
RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def sheet_map(zf: zipfile.ZipFile) -> list[tuple[str, str]]:
    wb = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rid_to_target = {
        rel.get("Id"): rel.get("Target") for rel in rels.findall(f"{{{RELS_NS}}}Relationship")
    }
    out = []
    for sheet in wb.findall(".//m:sheets/m:sheet", NS):
        rid = sheet.get(f"{{{NS['r']}}}id")
        target = rid_to_target.get(rid, "")
        if target.startswith("/"):
            target = target.lstrip("/")
        elif not target.startswith("xl/"):
            target = f"xl/{target}"
        out.append((sheet.get("name", "?"), target))
    return out


def first_strings(zf: zipfile.ZipFile, limit: int = 4000) -> tuple[list[str], int]:
    strings: list[str] = []
    total = 0
    with zf.open("xl/sharedStrings.xml") as stream:
        for event, elem in ET.iterparse(stream, events=("end",)):
            if elem.tag != f"{{{NS['m']}}}si":
                continue
            total += 1
            if len(strings) < limit:
                strings.append("".join(t.text or "" for t in elem.iter(f"{{{NS['m']}}}t")))
            elem.clear()
    return strings, total


def rows_of(zf: zipfile.ZipFile, path: str, strings: list[str], max_rows: int) -> list[list[tuple[str, str]]]:
    rows: list[list[tuple[str, str]]] = []
    with zf.open(path) as stream:
        for event, elem in ET.iterparse(stream, events=("end",)):
            if elem.tag != f"{{{NS['m']}}}row":
                continue
            cells: list[tuple[str, str]] = []
            for cell in elem.findall("m:c", NS):
                kind = cell.get("t")
                if kind == "inlineStr":
                    text = "".join(t.text or "" for t in cell.iter(f"{{{NS['m']}}}t"))
                else:
                    value = cell.find("m:v", NS)
                    text = value.text if value is not None and value.text else ""
                    if kind == "s" and text.isdigit():
                        idx = int(text)
                        text = strings[idx] if idx < len(strings) else f"<str#{idx}>"
                cells.append((cell.get("r", "?"), text))
            rows.append(cells)
            elem.clear()
            if len(rows) >= max_rows:
                break
    return rows


def main() -> int:
    target = Path(sys.argv[1])
    max_sheets = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    max_rows = int(sys.argv[3]) if len(sys.argv) > 3 else 4
    max_cols = int(sys.argv[4]) if len(sys.argv) > 4 else 25
    out_path = Path(sys.argv[5]) if len(sys.argv) > 5 else None
    refs = "--refs" in sys.argv
    if out_path is not None:
        sys.stdout = out_path.open("w", encoding="utf-8")

    with zipfile.ZipFile(target) as zf:
        strings, total = first_strings(zf)
        print(f"file: {target.name}  shared strings: {total} (cached {len(strings)})")
        sheets = sheet_map(zf)
        print(f"sheets: {len(sheets)}")
        for name, path in sheets[:max_sheets]:
            print(f"\n=== sheet: {name}  ({path}) ===")
            try:
                for row in rows_of(zf, path, strings, max_rows):
                    cells = [c for c in row if c != ""]
                    if cells:
                        if refs:
                            print(f"  [{len(row)} cells] " + " | ".join(
                                f"{ref}={val}" for ref, val in cells[:max_cols]))
                        else:
                            print(f"  [{len(row)} cells] " + " | ".join(val for _, val in cells[:max_cols]))
            except KeyError as exc:
                print(f"  (missing {exc})")
        if len(sheets) > max_sheets:
            print(f"\n... {len(sheets) - max_sheets} more sheets: "
                  + ", ".join(n for n, _ in sheets[max_sheets:max_sheets + 20]))
    if out_path is not None:
        sys.stdout.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
