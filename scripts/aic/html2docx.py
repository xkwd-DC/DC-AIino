"""Convert the proposal/evidence HTML into a structured, editable DOCX.

Uses only the standard library: the documents are parsed into a small tree and
emitted as WordprocessingML with real heading styles, tables and inline images.
"""

from __future__ import annotations

import html
import re
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import Path

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
PR = "http://schemas.openxmlformats.org/package/2006/relationships"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

EMU_PER_CM = 360000
CONTENT_CM = 16.6  # A4 width minus 2 x 2.2cm margins

VOID = {"img", "br", "meta", "link", "hr"}


class Node:
    def __init__(self, tag: str, attrs: dict[str, str] | None = None) -> None:
        self.tag = tag
        self.attrs = attrs or {}
        self.children: list[Node] = []
        self.text = ""
        # (\"text\", str) | (\"node\", Node) entries in document order, so inline
        # markup keeps its position relative to the surrounding text.
        self.parts: list[tuple[str, object]] = []

    def cls(self) -> str:
        return self.attrs.get("class", "")

    def find_all(self, tag: str) -> list["Node"]:
        out = []
        for child in self.children:
            if child.tag == tag:
                out.append(child)
            out.extend(child.find_all(tag))
        return out

    def plain(self) -> str:
        if not self.parts:
            return self.text
        out = []
        for kind, item in self.parts:
            out.append(item if kind == "text" else item.plain())
        return "".join(out)


class TreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("root")
        self.stack = [self.root]
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "title"):
            self.skip += 1
            return
        if self.skip:
            return
        node = Node(tag, {k: (v or "") for k, v in attrs})
        self.stack[-1].children.append(node)
        self.stack[-1].parts.append(("node", node))
        if tag not in VOID:
            self.stack.append(node)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "title"):
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if self.skip:
            return
        if data.strip():
            self.stack[-1].text += data
            self.stack[-1].parts.append(("text", data))


def esc(text: str) -> str:
    return html.escape(text, quote=False)


class DocBuilder:
    def __init__(self, base_dir: Path) -> None:
        self.base = base_dir
        self.parts: list[str] = []
        self.media: dict[str, bytes] = {}
        self.rels: list[str] = []
        self._rid = 10

    # ---------- primitives ----------
    def _next_rid(self) -> str:
        self._rid += 1
        return f"rId{self._rid}"

    def para(self, runs: str, style: str = "Body", align: str = "both",
             page_break: bool = False, shading: str | None = None,
             indent: int = 0, space_before: int = 0, space_after: int = 80) -> None:
        pr = [f'<w:pStyle w:val="{style}"/>']
        if page_break:
            pr.append('<w:pageBreakBefore/>')
        pr.append(f'<w:jc w:val="{align}"/>')
        pr.append(f'<w:spacing w:before="{space_before}" w:after="{space_after}" w:line="320" w:lineRule="auto"/>')
        if indent:
            pr.append(f'<w:ind w:left="{indent}"/>')
        if shading:
            pr.append(f'<w:shd w:val="clear" w:color="auto" w:fill="{shading}"/>')
        self.parts.append(f"<w:p><w:pPr>{''.join(pr)}</w:pPr>{runs}</w:p>")

    def text_run(self, text: str, bold: bool = False, size: int | None = None,
                 color: str | None = None, east_asia: str | None = None) -> str:
        rpr = []
        if bold:
            rpr.append("<w:b/>")
        if size:
            rpr.append(f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>')
        if color:
            rpr.append(f'<w:color w:val="{color}"/>')
        if east_asia:
            rpr.append(f'<w:rFonts w:ascii="{east_asia}" w:hAnsi="{east_asia}" w:eastAsia="{east_asia}"/>')
        body = f"<w:rPr>{''.join(rpr)}</w:rPr>" if rpr else ""
        return f'<w:r>{body}<w:t xml:space="preserve">{esc(text)}</w:t></w:r>'

    def inline_runs(self, node: Node, base_bold: bool = False) -> str:
        """Flatten a node's inline content into runs, honouring bold spans."""
        runs = []
        if not node.parts:
            if node.text.strip():
                runs.append(self.text_run(node.text.strip(), bold=base_bold))
            return "".join(runs)
        for kind, item in node.parts:
            if kind == "text":
                if item.strip():
                    runs.append(self.text_run(item.strip(), bold=base_bold))
                continue
            child = item
            if child.tag == "br":
                runs.append("<w:r><w:br/></w:r>")
                continue
            bold = base_bold or child.tag in ("b", "strong")
            runs.append(self.inline_runs(child, base_bold=bold))
        return "".join(runs)

    def image(self, node: Node) -> None:
        src = node.attrs.get("src", "")
        path = (self.base / src).resolve()
        if not path.exists():
            return
        data = path.read_bytes()
        name = f"image{len(self.media) + 1}{path.suffix}"
        self.media[name] = data
        rid = self._next_rid()
        self.rels.append(
            f'<Relationship Id="{rid}" Type="{R}/image" Target="media/{name}"/>'
        )
        width_emu = int(CONTENT_CM * EMU_PER_CM)
        # PNG/JPEG pixel size -> keep aspect ratio
        if path.suffix.lower() == ".png":
            import struct

            px_w, px_h = struct.unpack(">II", data[16:24])
        else:
            px_w, px_h = 1268, 755
        height_emu = int(width_emu * px_h / px_w)
        doc_id = len(self.media)
        self.parts.append(
            "<w:p><w:pPr><w:jc w:val=\"center\"/><w:spacing w:before=\"60\" w:after=\"40\"/></w:pPr>"
            f'<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0">'
            f'<wp:extent cx="{width_emu}" cy="{height_emu}"/>'
            f'<wp:docPr id="{doc_id}" name="{name}"/>'
            f'<a:graphic xmlns:a="{A}"><a:graphicData uri="{A}/picture">'
            f'<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
            f'<pic:nvPicPr><pic:cNvPr id="{doc_id}" name="{name}"/><pic:cNvPicPr/></pic:nvPicPr>'
            f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
            f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{width_emu}" cy="{height_emu}"/></a:xfrm>'
            f'<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
            f"</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>"
        )

    def table(self, node: Node) -> None:
        caption = next((c for c in node.children if c.tag == "caption"), None)
        if caption is not None:
            self.para(self.text_run(caption.plain().strip(), size=18), style="Caption", align="center", space_after=60)

        rows: list[Node] = []
        header_cells = 0
        for section in node.children:
            if section.tag in ("thead", "tbody"):
                for tr in section.find_all("tr"):
                    rows.append(tr)
                    if section.tag == "thead":
                        header_cells += 1
        if not rows:
            return

        col_count = max(len(tr.find_all("th") + tr.find_all("td")) for tr in rows)
        widths = self._col_widths(node, col_count)
        grid = "".join(f'<w:gridCol w:w="{w}"/>' for w in widths)

        out = [
            "<w:tbl><w:tblPr>",
            '<w:tblW w:w="0" w:type="auto"/>',
            '<w:tblBorders>'
            '<w:top w:val="single" w:sz="4" w:color="D9D9D9"/>'
            '<w:left w:val="single" w:sz="4" w:color="D9D9D9"/>'
            '<w:bottom w:val="single" w:sz="4" w:color="D9D9D9"/>'
            '<w:right w:val="single" w:sz="4" w:color="D9D9D9"/>'
            '<w:insideH w:val="single" w:sz="4" w:color="D9D9D9"/>'
            '<w:insideV w:val="single" w:sz="4" w:color="D9D9D9"/>'
            "</w:tblBorders>",
            '<w:tblCellMar><w:top w:w="60" w:type="dxa"/><w:left w:w="90" w:type="dxa"/>'
            '<w:bottom w:w="60" w:type="dxa"/><w:right w:w="90" w:type="dxa"/></w:tblCellMar>',
            "</w:tblPr>",
            f"<w:tblGrid>{grid}</w:tblGrid>",
        ]
        for index, tr in enumerate(rows):
            is_header = index < header_cells
            cells = tr.find_all("th") + tr.find_all("td")
            out.append("<w:tr>")
            if is_header:
                out.append('<w:trPr><w:tblHeader/></w:trPr>')
            for col in range(col_count):
                cell = cells[col] if col < len(cells) else None
                shade = "1F3864" if is_header else ("F5F7FA" if index % 2 else "FFFFFF")
                color = "FFFFFF" if is_header else None
                align = "center" if (is_header or (cell is not None and "c" in cell.cls().split())) else "both"
                runs = "" if cell is None else self.inline_runs(cell, base_bold=is_header)
                out.append(
                    f'<w:tc><w:tcPr><w:tcW w:w="{widths[col]}" w:type="dxa"/>'
                    f'<w:shd w:val="clear" w:color="auto" w:fill="{shade}"/>'
                    f'<w:vAlign w:val="center"/></w:tcPr>'
                    f'<w:p><w:pPr><w:jc w:val="{align}"/><w:spacing w:before="30" w:after="30" w:line="280" w:lineRule="auto"/>'
                    f'<w:rPr><w:sz w:val="18"/></w:rPr></w:pPr>'
                    f'{"".join(self._recolor(runs, color))}</w:p></w:tc>'
                )
            out.append("</w:tr>")
        out.append("</w:tbl>")
        self.parts.append("".join(out))
        self.para("", space_after=40, align="left")

    def _recolor(self, runs_xml: str, color: str | None) -> list[str]:
        if not color:
            return [runs_xml]
        return [re.sub(r"<w:r><w:rPr>", f'<w:r><w:rPr><w:color w:val="{color}"/>', runs_xml)]

    def _col_widths(self, node: Node, col_count: int) -> list[int]:
        total = int(CONTENT_CM * 567)  # cm -> twips
        first_row = None
        for section in node.children:
            if section.tag in ("thead", "tbody"):
                first_row = section.find_all("tr")
                break
        pcts: list[float] = []
        if first_row:
            for cell in first_row[0].find_all("th") + first_row[0].find_all("td"):
                match = re.search(r"width:\s*([\d.]+)%", cell.attrs.get("style", ""))
                pcts.append(float(match.group(1)) if match else 0.0)
        known = sum(pcts)
        if known <= 0:
            return [total // col_count] * col_count
        unknown = [i for i, p in enumerate(pcts) if p == 0]
        remaining = 100.0 - known
        for i in unknown:
            pcts[i] = remaining / max(1, len(unknown))
        pcts = (pcts + [100.0 / col_count] * col_count)[:col_count]
        return [max(600, int(total * p / 100)) for p in pcts]

    # ---------- block walker ----------
    def walk(self, node: Node, first_heading: bool = True) -> None:
        for child in node.children:
            self.block(child)

    def block(self, node: Node) -> None:
        tag, cls = node.tag, node.cls()
        if tag in ("h1", "h2", "h3", "h4"):
            level = {"h1": "Title", "h2": "Heading1", "h3": "Heading2", "h4": "Heading3"}[tag]
            self.para(
                self.inline_runs(node),
                style=level,
                align="left",
                page_break=(tag == "h2" and bool(self.parts)),
                space_before=0 if tag != "h3" else 120,
                space_after=100,
            )
            return
        if tag == "p":
            style = "Caption" if "note" in cls else "Body"
            align = "center" if style == "Caption" else "both"
            self.para(self.inline_runs(node), style=style, align=align)
            return
        if tag in ("ul", "ol"):
            ordered = tag == "ol"
            for i, li in enumerate(node.find_all("li") if tag == "ul" else node.children):
                if li.tag != "li":
                    continue
                prefix = f"{i + 1}. " if ordered else "· "
                runs = self.text_run(prefix) + self.inline_runs(li)
                self.para(runs, indent=340)
            return
        if tag == "table":
            self.table(node)
            return
        if tag == "figure":
            for img in node.find_all("img"):
                self.image(img)
            for cap in node.find_all("figcaption"):
                self.para(self.text_run(cap.plain().strip(), size=18), style="Caption", align="center")
            return
        if tag == "img":
            self.image(node)
            return
        if tag == "div" and "cover" in cls.split():
            self.cover(node)
            return
        if tag == "div" and "arch" in cls.split():
            self.arch(node)
            return
        if tag == "div" and "step" in cls.split():
            name = next((c for c in node.children if "nm" in c.cls().split()), None)
            desc = next((c for c in node.children if "ds" in c.cls().split()), None)
            idx = next((c for c in node.children if "idx" in c.cls().split()), None)
            label = f"{idx.plain().strip()}　" if idx is not None else ""
            runs = self.text_run(label + (name.plain().strip() if name else ""), bold=True)
            if desc is not None:
                runs += self.text_run("　" + desc.plain().strip())
            self.para(runs, shading="F4F7F5", indent=120)
            return
        if tag == "div" and "col" in cls.split():
            self.col_block(node)
            return
        if tag == "div" and "takeaway" in cls.split():
            self.para(self.inline_runs(node), space_before=120)
            return
        if tag == "div" and "trace" in cls.split():
            runs = "".join(self.inline_runs(c) for c in node.children)
            self.para(runs, shading="F4F7F5", indent=120)
            return
        if tag == "div" and "refs" in cls.split():
            for entry in node.children:
                self.para(self.inline_runs(entry), indent=0, space_after=40)
            return
        if tag == "div" and "arrow" in cls.split():
            return
        if tag == "div" and "pageno" in cls.split():
            return
        if tag in ("div", "section", "body", "main", "figure"):
            self.walk(node)
            return
        if tag in ("header", "footer", "nav"):
            return
        if node.children:
            self.walk(node)

    def col_block(self, node: Node) -> None:
        heading = None
        body = []
        for child in node.children:
            if child.tag in ("h3", "h4") and heading is None:
                heading = child.plain().strip()
            elif child.tag == "p":
                body.append(child.plain().strip())
            elif child.tag == "div" and "n" in child.cls().split():
                heading = (child.plain().strip() + "　" + (heading or "")).strip()
        runs = self.text_run(heading or "", bold=True)
        for text in body:
            runs += self.text_run("　" + text)
        self.para(runs, shading="F4F7F5", indent=120)

    def arch(self, node: Node) -> None:
        layer = next((c for c in node.children if "layer" in c.cls().split()), None)
        body = next((c for c in node.children if "body" in c.cls().split()), None)
        runs = ""
        if layer is not None:
            runs += self.text_run(layer.plain().strip() + "　", bold=True)
        if body is not None:
            runs += self.inline_runs(body)
        self.para(runs, shading="EEF2F8", indent=120)

    def cover(self, node: Node) -> None:
        kicker = next((c for c in node.children if "kicker" in c.cls().split()), None)
        title = next((c for c in node.children if c.tag == "h1"), None)
        sub = next((c for c in node.children if "sub" in c.cls().split()), None)
        meta = next((c for c in node.children if "meta" in c.cls().split()), None)
        foot = next((c for c in node.children if "foot" in c.cls().split()), None)
        self.para("", space_after=1200)
        if kicker is not None:
            self.para(self.text_run(kicker.plain().strip(), size=22), align="center", space_after=400)
        if title is not None:
            self.para(self.text_run(title.plain().strip(), bold=True, size=44), style="Title", align="center", space_after=200)
        if sub is not None:
            self.para(self.text_run(sub.plain().strip(), size=28), align="center", space_after=800)
        if meta is not None:
            rows = [[c.text.strip() or c.plain().strip() for c in entry.children] for entry in meta.children]
            rows = [r for r in rows if any(r)]
            self.simple_table(rows, ["30%", "70%"], center_first=True)
        if foot is not None:
            self.para("", space_after=600)
            self.para(self.text_run(foot.plain().strip(), size=18), align="center")

    def simple_table(self, rows: list[list[str]], widths: list[str], center_first: bool = False) -> None:
        total = int(CONTENT_CM * 567)
        cols = [int(total * float(w.strip("%")) / 100) for w in widths]
        out = ["<w:tbl><w:tblPr><w:tblW w:w=\"0\" w:type=\"auto\"/><w:tblBorders>"]
        for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
            out.append(f'<w:{side} w:val="single" w:sz="4" w:color="D9D9D9"/>')
        out.append("</w:tblBorders></w:tblPr>")
        out.append("<w:tblGrid>" + "".join(f'<w:gridCol w:w="{w}"/>' for w in cols) + "</w:tblGrid>")
        for row in rows:
            out.append("<w:tr>")
            for i in range(len(cols)):
                text = row[i] if i < len(row) else ""
                align = "center" if (center_first and i == 0) else "left"
                out.append(
                    f'<w:tc><w:tcPr><w:tcW w:w="{cols[i]}" w:type="dxa"/><w:vAlign w:val="center"/></w:tcPr>'
                    f'<w:p><w:pPr><w:jc w:val="{align}"/><w:spacing w:before="40" w:after="40"/></w:pPr>'
                    f'{self.text_run(text, size=20)}</w:p></w:tc>'
                )
            out.append("</w:tr>")
        out.append("</w:tbl>")
        self.parts.append("".join(out))

    # ---------- package ----------
    def save(self, out_path: Path) -> None:
        document = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:document xmlns:w="{W}" xmlns:r="{R}" xmlns:wp="{WP}" xmlns:a="{A}">'
            "<w:body>" + "".join(self.parts) +
            '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
            '<w:pgMar w:top="1247" w:right="1247" w:bottom="1134" w:left="1247" '
            'w:header="851" w:footer="992" w:gutter="0"/></w:sectPr>'
            "</w:body></w:document>"
        )
        content_types = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Default Extension="png" ContentType="image/png"/>'
            '<Default Extension="jpeg" ContentType="image/jpeg"/>'
            '<Default Extension="jpg" ContentType="image/jpeg"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
            '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
            '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
            "</Types>"
        )
        rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Relationships xmlns="{PR}">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
            "</Relationships>"
        )
        doc_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Relationships xmlns="{PR}">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            + "".join(self.rels) +
            "</Relationships>"
        )
        styles = styles_xml()
        core = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
            'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
            'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            "<dc:title>禾衡·农业智能体决策服务平台</dc:title><dc:creator></dc:creator>"
            "<cp:lastModifiedBy></cp:lastModifiedBy>"
            "</cp:coreProperties>"
        )
        app = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
            "<Application>Microsoft Office Word</Application></Properties>"
        )

        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", content_types)
            zf.writestr("_rels/.rels", rels)
            zf.writestr("word/document.xml", document)
            zf.writestr("word/_rels/document.xml.rels", doc_rels)
            zf.writestr("word/styles.xml", styles)
            zf.writestr("docProps/core.xml", core)
            zf.writestr("docProps/app.xml", app)
            for name, data in self.media.items():
                zf.writestr(f"word/media/{name}", data)


def _style(sid: str, name: str, sz: int, font: str, before: int, after: int,
           bold: bool = False, align: str = "both") -> str:
    return (
        f'<w:style w:type="paragraph" w:styleId="{sid}"><w:name w:val="{name}"/>'
        f'<w:basedOn w:val="Normal"/><w:qFormat/>'
        f'<w:pPr><w:jc w:val="{align}"/><w:spacing w:before="{before}" w:after="{after}" w:line="320" w:lineRule="auto"/></w:pPr>'
        f'<w:rPr><w:rFonts w:ascii="{font}" w:hAnsi="{font}" w:eastAsia="{font}"/>'
        f'{"<w:b/>" if bold else ""}<w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/></w:rPr></w:style>'
    )


def styles_xml() -> str:
    body = "".join(
        [
            _style("Title", "标题", sz=44, bold=True, font="微软雅黑", before=0, after=200, align="center"),
            _style("Heading1", "标题 1", sz=30, bold=True, font="微软雅黑", before=240, after=140),
            _style("Heading2", "标题 2", sz=24, bold=True, font="微软雅黑", before=200, after=100),
            _style("Heading3", "标题 3", sz=22, bold=True, font="微软雅黑", before=160, after=90),
            _style("Body", "正文", sz=21, font="宋体", before=0, after=90),
            _style("Caption", "图注", sz=18, font="微软雅黑", before=40, after=120, align="center"),
        ]
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:styles xmlns:w="{W}">'
        '<w:docDefaults><w:rPrDefault><w:rPr>'
        '<w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="宋体" w:cs="Times New Roman"/>'
        '<w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr></w:rPrDefault>'
        '<w:pPrDefault><w:pPr><w:spacing w:line="320" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
        + body
        + "</w:styles>"
    )


def convert(src_html: Path, out_docx: Path) -> int:
    parser = TreeParser()
    parser.feed(src_html.read_text(encoding="utf-8"))
    body = parser.root.find_all("body")[0]
    builder = DocBuilder(src_html.parent)
    builder.walk(body)
    builder.save(out_docx)
    return len(builder.parts), len(builder.media)


if __name__ == "__main__":
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    blocks, images = convert(src, dst)
    print(f"{src.name} -> {dst.name}: {blocks} blocks, {images} images, {dst.stat().st_size/1024:.0f} KB")
