"""Stream one .xlsx sheet to CSV, resolving shared strings and sparse cells."""

from __future__ import annotations

import csv
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
COL_RE = re.compile(r"([A-Z]+)")


def col_index(ref: str) -> int:
    letters = COL_RE.match(ref).group(1)
    index = 0
    for char in letters:
        index = index * 26 + (ord(char) - 64)
    return index - 1


def shared_strings(zf: zipfile.ZipFile):
    with zf.open("xl/sharedStrings.xml") as stream:
        for event, elem in ET.iterparse(stream, events=("end",)):
            if elem.tag == f"{{{NS['m']}}}si":
                yield "".join(t.text or "" for t in elem.iter(f"{{{NS['m']}}}t"))
                elem.clear()


def main() -> int:
    target = Path(sys.argv[1])
    sheet = sys.argv[2]
    out_path = Path(sys.argv[3])
    max_rows = int(sys.argv[4]) if len(sys.argv) > 4 else 0

    with zipfile.ZipFile(target) as zf:
        strings = list(shared_strings(zf))
        with zf.open(sheet) as stream, out_path.open("w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.writer(fh)
            width = 0
            count = 0
            for event, elem in ET.iterparse(stream, events=("end",)):
                if elem.tag != f"{{{NS['m']}}}row":
                    continue
                row: list[str] = []
                for cell in elem.findall("m:c", NS):
                    idx = col_index(cell.get("r", "A1"))
                    if idx >= len(row):
                        row.extend([""] * (idx + 1 - len(row)))
                    kind = cell.get("t")
                    if kind == "inlineStr":
                        value = "".join(t.text or "" for t in cell.iter(f"{{{NS['m']}}}t"))
                    else:
                        node = cell.find("m:v", NS)
                        value = node.text if node is not None and node.text else ""
                        if kind == "s" and value.isdigit():
                            value = strings[int(value)]
                    row[idx] = value
                if not width:
                    width = len(row)
                writer.writerow(row)
                count += 1
                elem.clear()
                if max_rows and count >= max_rows:
                    break
    print(f"rows written: {count}  cols: {width}  -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
