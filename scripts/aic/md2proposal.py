"""Convert the anonymous Markdown 技术方案 draft into the styled proposal HTML.

The HTML is the single source for both the browser preview and the
`html2docx.py` -> DOCX -> PDF export chain, so the Markdown draft stays the
authoritative content file and no content is retyped by hand.

Usage:
    python scripts/aic/md2proposal.py <in.md> <out.html> --cover <cover.json> \
        --template <existing proposal.html>

Markdown conventions (in addition to headings, paragraphs, lists and bold):
    ![图注](img/xx.png)          -> numbered figure with caption
    <!--cap: 表注-->             -> numbered caption for the table that follows
    <!--widths: 20,44,36-->      -> column widths (percent) for that table
    > text                       -> centred note line (docx "Caption" style)
    4-space indented line        -> centred formula line
"""

from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

EXTRA_CSS = """
  p.formula {
    font-family: "Cambria Math", "Times New Roman", serif;
    text-align: center; margin: 8pt 0 10pt 0; font-size: 11pt;
  }
  p.note { border: none; }
"""


def inline(text: str) -> str:
    """Escape HTML, then re-apply the inline markup we support."""
    out = html.escape(text.strip(), quote=False)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"`(.+?)`", r"<code>\1</code>", out)
    out = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", out)
    return out


def is_table_row(line: str) -> bool:
    return line.strip().startswith("|") and line.strip().endswith("|")


def split_row(line: str) -> list[str]:
    cells = line.strip().strip("|").split("|")
    return [c.strip() for c in cells]


def display_width(text: str) -> int:
    """Approximate half-width character count (CJK glyphs count double)."""
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in text)


def auto_widths(header: list[str], rows: list[list[str]]) -> list[str]:
    """Column widths proportional to the longest content in each column."""
    weights = []
    for i, cell in enumerate(header):
        longest = display_width(re.sub(r"\*\*|`", "", cell))
        for row in rows:
            if i < len(row):
                longest = max(longest, display_width(re.sub(r"\*\*|`", "", row[i])))
        # 16 half-width units ~ 2.7 cm, enough for a four-character label such
        # as "预测模型" without wrapping once cell padding is subtracted.
        weights.append(min(max(longest, 16), 60))
    total = sum(weights)
    pct = [round(w / total * 100) for w in weights]
    pct[-1] += 100 - sum(pct)
    return [str(p) for p in pct]


class Converter:
    def __init__(self) -> None:
        self.out: list[str] = []
        self.fig = 0
        self.tbl = 0
        self.pending_cap: str | None = None
        self.pending_widths: list[str] | None = None
        self.section_open = False
        self.started = False

    # ---------- block emitters ----------
    def open_section(self) -> None:
        if self.section_open:
            self.out.append("</div>")
        self.out.append('<div class="section">')
        self.section_open = True

    def close(self) -> None:
        if self.section_open:
            self.out.append("</div>")
            self.section_open = False

    def heading(self, level: int, text: str) -> None:
        if level == 2:
            self.open_section()
        self.out.append(f"<h{level}>{inline(text)}</h{level}>")

    def paragraph(self, text: str) -> None:
        self.out.append(f"<p>{inline(text)}</p>")

    def note(self, text: str) -> None:
        self.out.append(f'<p class="note">{inline(text)}</p>')

    def formula(self, text: str) -> None:
        self.out.append(f'<p class="formula">{inline(text)}</p>')

    def figure(self, caption: str, src: str) -> None:
        self.fig += 1
        alt = html.escape(caption, quote=True)
        self.out.append("<figure>")
        self.out.append(f'  <img src="{html.escape(src, quote=True)}" alt="{alt}">')
        self.out.append(f"  <figcaption>图 {self.fig}　{inline(caption)}</figcaption>")
        self.out.append("</figure>")

    def table(self, header: list[str], rows: list[list[str]]) -> None:
        self.tbl += 1
        cap = self.pending_cap
        widths = self.pending_widths or auto_widths(header, rows)
        self.pending_cap = None
        self.pending_widths = None
        self.out.append("<table>")
        if cap:
            self.out.append(f"  <caption>表 {self.tbl}　{inline(cap)}</caption>")
        self.out.append("  <thead>")
        cells = []
        for i, cell in enumerate(header):
            style = ""
            if widths and i < len(widths):
                style = f' style="width:{widths[i]}%"'
            cells.append(f"<th{style}>{inline(cell)}</th>")
        self.out.append("    <tr>" + "".join(cells) + "</tr>")
        self.out.append("  </thead>")
        self.out.append("  <tbody>")
        for row in rows:
            tds = []
            for i, cell in enumerate(row):
                cls = ' class="k"' if i == 0 else ""
                tds.append(f"<td{cls}>{inline(cell)}</td>")
            self.out.append("    <tr>" + "".join(tds) + "</tr>")
        self.out.append("  </tbody>")
        self.out.append("</table>")

    # ---------- driver ----------
    def convert(self, md: str) -> str:
        lines = md.splitlines()
        i = 0
        while i < len(lines):
            raw = lines[i]
            line = raw.rstrip()
            stripped = line.strip()

            if not stripped:
                i += 1
                continue

            if stripped.startswith("<!--") and stripped.endswith("-->"):
                body = stripped[4:-3].strip()
                if body.startswith("cap:"):
                    self.pending_cap = body[4:].strip()
                elif body.startswith("widths:"):
                    self.pending_widths = [w.strip() for w in body[6:].split(",")]
                i += 1
                continue

            if stripped in ("---", "***", "___"):
                i += 1
                continue

            # Title, draft subtitle and internal notes live on the cover page.
            if not self.started:
                if re.match(r"^##\s+", stripped):
                    self.started = True
                else:
                    i += 1
                    continue

            m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
            if m:
                level = len(m.group(1))
                text = m.group(2).strip()
                if level == 1:
                    i += 1  # document title lives on the cover page
                    continue
                self.heading(min(level, 4), text)
                i += 1
                continue

            img = re.match(r"^!\[(.*?)\]\((.+?)\)$", stripped)
            if img:
                caption = img.group(1).strip()
                if not caption:
                    caption = Path(img.group(2)).stem
                self.figure(caption, img.group(2).strip())
                i += 1
                continue

            if is_table_row(stripped):
                block: list[str] = []
                while i < len(lines) and is_table_row(lines[i].strip()):
                    block.append(lines[i].strip())
                    i += 1
                header = split_row(block[0])
                body_rows = [split_row(r) for r in block[2:]] if len(block) > 2 else []
                self.table(header, body_rows)
                continue

            if stripped.startswith(">"):
                chunk: list[str] = []
                while i < len(lines) and lines[i].strip().startswith(">"):
                    chunk.append(lines[i].strip().lstrip(">").strip())
                    i += 1
                self.note(" ".join(x for x in chunk if x))
                continue

            if re.match(r"^[-*]\s+", stripped) or re.match(r"^\d+\.\s+", stripped):
                ordered = bool(re.match(r"^\d+\.\s+", stripped))
                tag = "ol" if ordered else "ul"
                items: list[str] = []
                while i < len(lines):
                    cur = lines[i].strip()
                    pat = r"^\d+\.\s+(.*)$" if ordered else r"^[-*]\s+(.*)$"
                    mm = re.match(pat, cur)
                    if not mm:
                        break
                    items.append(mm.group(1))
                    i += 1
                self.out.append(f"<{tag}>")
                for item in items:
                    self.out.append(f"  <li>{inline(item)}</li>")
                self.out.append(f"</{tag}>")
                continue

            if raw.startswith("    ") and stripped:
                self.formula(stripped)
                i += 1
                continue

            self.paragraph(stripped)
            i += 1

        self.close()
        return "\n".join(self.out)


def cover_html(cover: dict) -> str:
    meta = "\n".join(
        f'    <div><span>{html.escape(str(label))}</span>'
        f'<span class="yh">{html.escape(str(value))}</span></div>'
        for label, value in cover.get("meta", [])
    )
    return (
        '<!-- ============ 封面 ============ -->\n'
        '<div class="cover">\n'
        f'  <div class="kicker">{html.escape(cover["kicker"])}</div>\n'
        f'  <h1>{html.escape(cover["title"])}</h1>\n'
        f'  <div class="sub">{html.escape(cover["sub"])}</div>\n'
        '  <div class="meta">\n'
        f"{meta}\n"
        "  </div>\n"
        f'  <div class="foot">{html.escape(cover["foot"])}</div>\n'
        "</div>\n"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src_md", type=Path)
    ap.add_argument("out_html", type=Path)
    ap.add_argument("--cover", type=Path, required=True)
    ap.add_argument("--template", type=Path, required=True,
                    help="existing proposal HTML whose <style> block is reused")
    args = ap.parse_args()

    template = args.template.read_text(encoding="utf-8")
    style = re.search(r"<style>.*?</style>", template, re.S)
    if style is None:
        raise SystemExit("template has no <style> block")
    css = style.group(0).replace("</style>", EXTRA_CSS + "</style>")

    cover = json.loads(args.cover.read_text(encoding="utf-8"))
    body = Converter().convert(args.src_md.read_text(encoding="utf-8"))

    doc = (
        "<!DOCTYPE html>\n<html lang=\"zh-CN\">\n<head>\n<meta charset=\"utf-8\">\n"
        f"<title>{html.escape(cover['title'])} {html.escape(cover['sub'])}</title>\n"
        f"{css}\n</head>\n<body>\n\n"
        f"{cover_html(cover)}\n"
        f"{body}\n"
        "</body>\n</html>\n"
    )
    args.out_html.write_text(doc, encoding="utf-8")
    print(f"{args.src_md.name} -> {args.out_html.name}: "
          f"{len(doc)} chars, {doc.count('<table>')} tables, {doc.count('<figure>')} figures")


if __name__ == "__main__":
    main()
