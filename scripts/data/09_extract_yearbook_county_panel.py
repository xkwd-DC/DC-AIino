#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从分卷压缩的《中国县域统计年鉴 2000-2024》中提取县级面板。

背景
====
``data/raw/statistical_yearbook_chunks/`` 下是同一个 zip 的 23 个分卷
（part01 ~ part23，共 2.21 GB）。直接对 part01 调用 ``zipfile`` 会报
"File is not a zip file"，必须先拼接；本脚本用可寻址的虚拟拼接视图读取，
不需要在磁盘上落地 2.2 GB 的合并文件。

另外，压缩包内的中文文件名是 GBK 编码，但被错误地打上了 UTF-8 标志位，
解出来是乱码且不可逆。因此本脚本按 **文件大小** 定位目标成员，而不是按名字。

产出
====
``data/raw/statistical_yearbook_extracted/county_panel_2000_2022_<sheet>.csv``
县级 × 年度面板，82 列，含经度/纬度、粮食总产量、播种面积、耕地面积等。

用法
====
    python scripts/data/09_extract_yearbook_county_panel.py
    python scripts/data/09_extract_yearbook_county_panel.py --list
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CHUNKS_DIR = PROJECT_ROOT / "data" / "raw" / "statistical_yearbook_chunks"
OUT_DIR = PROJECT_ROOT / "data" / "raw" / "statistical_yearbook_extracted"

# 处理后总表的文件大小（字节），用作稳定标识
PANEL_SIZE = 73_186_343
# 分省 Excel 汇总包（2024 县市卷，镇级表）
TOWN_PACK_SIZE = 2_747_808

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
COL_RE = re.compile(r"([A-Z]+)")


class SplitFile(io.RawIOBase):
    """把多个分卷文件虚拟拼接成一个可 seek 的只读文件对象。"""

    def __init__(self, parts: list[Path]) -> None:
        self.parts = parts
        self.offsets: list[int] = []
        running = 0
        for part in parts:
            self.offsets.append(running)
            running += part.stat().st_size
        self.total = running
        self.pos = 0
        self._handles: dict[int, io.BufferedReader] = {}

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            new = offset
        elif whence == io.SEEK_CUR:
            new = self.pos + offset
        elif whence == io.SEEK_END:
            new = self.total + offset
        else:
            raise ValueError(f"bad whence: {whence}")
        if new < 0:
            raise ValueError("negative seek")
        self.pos = new
        return self.pos

    def readinto(self, buffer) -> int:  # type: ignore[override]
        want = len(buffer)
        if want == 0 or self.pos >= self.total:
            return 0
        idx = 0
        for i, off in enumerate(self.offsets):
            if self.pos >= off:
                idx = i
            else:
                break
        written = 0
        while written < want and idx < len(self.parts):
            handle = self._handles.get(idx)
            if handle is None:
                handle = self.parts[idx].open("rb")
                self._handles[idx] = handle
            handle.seek(self.pos - self.offsets[idx])
            chunk = handle.read(want - written)
            if not chunk:
                idx += 1
                continue
            buffer[written:written + len(chunk)] = chunk
            written += len(chunk)
            self.pos += len(chunk)
        return written

    def close(self) -> None:
        for handle in self._handles.values():
            handle.close()
        self._handles.clear()
        super().close()


def open_archive(chunks_dir: Path) -> zipfile.ZipFile:
    parts = sorted(chunks_dir.glob("*.part*.zip"))
    if not parts:
        raise SystemExit(f"未找到分卷文件: {chunks_dir}")
    print(f"分卷 {len(parts)} 个，合计 {sum(p.stat().st_size for p in parts) / 1e9:.2f} GB")
    return zipfile.ZipFile(io.BufferedReader(SplitFile(parts)))


def find_member(zf: zipfile.ZipFile, size: int) -> zipfile.ZipInfo:
    for info in zf.infolist():
        if not info.is_dir() and info.file_size == size:
            return info
    raise SystemExit(f"未找到大小为 {size} 的成员")


def sheet_targets(zf: zipfile.ZipFile) -> list[tuple[str, str]]:
    wb = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rid_to_target = {rel.get("Id"): rel.get("Target") for rel in rels.findall(f"{{{RELS_NS}}}Relationship")}
    targets = []
    for sheet in wb.findall(".//m:sheets/m:sheet", NS):
        target = rid_to_target.get(sheet.get(f"{{{'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}}}id"), "")
        if target.startswith("/"):
            target = target.lstrip("/")
        elif not target.startswith("xl/"):
            target = f"xl/{target}"
        targets.append((sheet.get("name", "?"), target))
    return targets


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


def sheet_to_csv(zf: zipfile.ZipFile, sheet_path: str, out_path: Path, strings: list[str]) -> int:
    rows = 0
    with zf.open(sheet_path) as stream, out_path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
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
            writer.writerow(row)
            rows += 1
            elem.clear()
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="提取县域统计年鉴县级面板")
    parser.add_argument("--chunks-dir", type=Path, default=CHUNKS_DIR)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    parser.add_argument("--list", action="store_true", help="只列出成员，不导出")
    args = parser.parse_args()
    try:  # Windows 控制台默认 GBK，中文提示会乱码
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:  # pragma: no cover
        pass

    args.out_dir.mkdir(parents=True, exist_ok=True)
    with open_archive(args.chunks_dir) as zf:
        if args.list:
            for info in zf.infolist():
                if not info.is_dir():
                    print(f"{info.file_size:>12}  {info.filename[:80]}")
            return 0

        panel = find_member(zf, PANEL_SIZE)
        print(f"目标成员大小 {panel.file_size}（县域经济数据 2001-2023 处理后总表）")

        # 内层 xlsx 是压缩流，无法直接 seek；先落到本地再当作普通 zip 读
        inner_path = args.out_dir / "_county_panel_tmp.xlsx"
        try:
            with zf.open(panel) as src, inner_path.open("wb") as dst:
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    dst.write(chunk)

            with zipfile.ZipFile(inner_path) as inner:
                strings = list(shared_strings(inner))
                print(f"共享字符串 {len(strings)} 条；工作表 {len(sheet_targets(inner))} 个")
                for name, path in sheet_targets(inner):
                    # 只导出原始数据与线性插值，跳过回归填补与说明页
                    if name not in ("原始数据", "线性插值"):
                        continue
                    suffix = "raw" if name == "原始数据" else "interpolated"
                    out_path = args.out_dir / f"county_panel_2000_2022_{suffix}.csv"
                    rows = sheet_to_csv(inner, path, out_path, strings)
                    print(f"  {name}: {rows} 行 → {out_path.name}")
        finally:
            inner_path.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
