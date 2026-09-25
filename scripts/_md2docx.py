# -*- coding: utf-8 -*-
"""把 docs/papers/v6_论文_投稿版.md 转换为 officecli batch JSON，生成《农业工程学报》风格 docx。"""
import io, json, re
from pathlib import Path

SRC = Path("docs/papers/v6_论文_投稿版.md")
OPS_JSON = Path("docs/papers/_submission_ops.json")

EA = "SimSun"          # 宋体（东亚）
LA = "Times New Roman"  # 西文
SZ = "10.5pt"          # 五号
LS = "1.5x"
IND = "420"            # 首行缩进约2字符

ops = []

def para(text, *, align=None, size=SZ, bold=False, italic=False, line=LS,
         first=False, indent=None, hang=None, sa=None, sb=None):
    p = {"command": "add", "parent": "/body", "type": "paragraph",
         "props": {"text": text, "font.ea": EA, "font.latin": LA, "size": size,
                   "lineSpacing": line}}
    if align: p["props"]["align"] = align
    if bold: p["props"]["bold"] = "true"
    if italic: p["props"]["italic"] = "true"
    if first: p["props"]["firstLineIndent"] = IND
    if indent: p["props"]["indent"] = indent
    if hang: p["props"]["hangingIndent"] = hang
    if sa: p["props"]["spaceAfter"] = sa
    if sb: p["props"]["spaceBefore"] = sb
    ops.append(p)

def rich_para(text, **kw):
    """支持 $...$ 内行公式与 **粗体** / `代码` 的段落。"""
    # 预清：去掉 markdown 粗体/代码标记，保留文本
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    # 按 $...$ 切分
    parts = re.split(r"\$(.+?)\$", text)
    if len(parts) == 1:
        para(parts[0], **kw)
        return
    # 首段
    p = {"command": "add", "parent": "/body", "type": "paragraph",
         "props": {"font.ea": EA, "font.latin": LA, "size": kw.get("size", SZ), "lineSpacing": LS}}
    if kw.get("first"): p["props"]["firstLineIndent"] = IND
    if kw.get("align"): p["props"]["align"] = kw["align"]
    ops.append(p)
    # 后续文本/公式
    for i, seg in enumerate(parts):
        if i % 2 == 0:
            if seg:
                ops.append({"command": "add", "parent": "/body/p[last()]", "type": "run",
                            "props": {"text": seg}})
        else:
            ops.append({"command": "add", "parent": "/body/p[last()]", "type": "equation",
                        "props": {"mode": "inline", "formula": seg}})

def heading(text, level):
    sizes = {1: "15pt", 2: "13pt", 3: "11.5pt"}
    bold = level <= 2
    italic = level == 3
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    para(s, size=sizes[level], bold=bold, italic=italic, sb="12pt", sa="6pt")

def add_table(rows):
    """rows: list of list[str]（已含表头）。三线表。"""
    nrow, ncol = len(rows), max(len(r) for r in rows)
    # 统一列数
    for r in rows:
        while len(r) < ncol: r.append("")
    ops.append({"command": "add", "parent": "/body", "type": "table",
                "props": {"rows": str(nrow), "cols": str(ncol), "width": "100%"}})
    for ri, r in enumerate(rows):
        for ci, val in enumerate(r):
            cell = f"/body/tbl[last()]/tr[{ri+1}]/tc[{ci+1}]/p[1]"
            bold = "true" if ri == 0 else None
            props = {"text": val, "font.ea": EA, "font.latin": LA, "size": "10pt"}
            if bold: props["bold"] = bold
            ops.append({"command": "set", "path": cell, "props": props})
    # 三线表：上/下粗线 + 表头下细线；其余无边框
    ops.append({"command": "set", "path": "/body/tbl[last()]",
                "props": {"border.top": "single;1.5pt;000000", "border.bottom": "single;1.5pt;000000"}})
    for ci in range(1, ncol + 1):
        ops.append({"command": "set", "path": f"/body/tbl[last()]/tr[1]/tc[{ci}]",
                    "props": {"border.bottom": "single;0.75pt;000000"}})

def add_figure(path):
    ops.append({"command": "add", "parent": "/body", "type": "picture",
                "props": {"src": path, "width": "7.5cm", "anchor": "true",
                          "hAlign": "center", "hRelative": "margin"}})

lines = io.open(SRC, encoding="utf-8").read().split("\n")

i = 0
n = len(lines)
# 前置项：标题/作者/单位/摘要/关键词/中图分类号/英文摘要/关键词/基金
front_keys = ["# 极端气候", "**Extreme-Climate", "【作者姓名"]  # 由特定行触发
# 解析到「## 0 引言」之前
idx_intro = next((k for k, l in enumerate(lines) if l.startswith("## 0 引言")), len(lines))
front = lines[:idx_intro]
body = lines[idx_intro:]

# ---- 逐行处理前置项 ----
for l in front:
    s = l.strip()
    if not s: continue
    if s.startswith("# 极端气候"):
        para(re.sub(r"^# ", "", s), align="center", size="15pt", bold=True, sa="6pt")
    elif s.startswith("**Extreme-Climate"):
        para(s.strip("*"), align="center", size="12pt", bold=True, sa="6pt")
    elif s.startswith("【作者姓名"):
        para(s, align="center", size="11pt")
    elif s.startswith("（【单位"):
        para(s, align="center", size="10.5pt", sa="12pt")
    elif s.startswith("**摘要：**"):
        para("摘  要", size="13pt", bold=True, sb="6pt", sa="4pt")
        para(re.sub(r"^\*\*摘要：\*\*", "", s), size=SZ, line=LS, sa="6pt")
    elif s.startswith("**关键词：**"):
        para(s.replace("**", ""), size=SZ, italic=True, sa="6pt")
    elif s.startswith("**中图分类号：**"):
        para(s.replace("**", ""), size=SZ, sa="10pt")
    elif s.startswith("**Abstract:**"):
        para("Abstract", size="13pt", bold=True, sb="6pt", sa="4pt")
        para(re.sub(r"^\*\*Abstract:\*\*", "", s), size=SZ, line=LS, sa="6pt")
    elif s.startswith("**Key words:**"):
        para(s.replace("**", ""), size=SZ, italic=True, sa="6pt")
    elif s.startswith("【基金项目"):
        para(s, size="9pt", italic=True, sa="6pt")

# ---- 正文 ----
j = 0
while j < len(body):
    l = body[j]
    s = l.strip()
    if not s:
        j += 1; continue
    if s.startswith("## "):
        heading(re.sub(r"^## ", "", s), 1); j += 1; continue
    if s.startswith("### "):
        heading(re.sub(r"^### ", "", s), 2); j += 1; continue
    if s.startswith("#### "):
        heading(re.sub(r"^#### ", "", s), 3); j += 1; continue
    # 表格：以 | 开头，且下一行是分隔线
    if s.startswith("|") and j + 1 < len(body) and re.match(r"^\s*\|[\s:|-]+\|\s*$", body[j+1]):
        rows = []
        while j < len(body) and body[j].strip().startswith("|"):
            cells = [c.strip() for c in body[j].strip().strip("|").split("|")]
            if not re.match(r"^[\s:|-]+$", "".join(cells)):  # 跳过分隔行
                rows.append(cells)
            j += 1
        add_table(rows)
        continue
    # 图：![...](...)
    m = re.match(r"^!\[.*\]\((.+)\)$", s)
    if m:
        add_figure(m.group(1).replace("../", "docs/")); j += 1; continue
    # 图题/表题（中/英）—— 已是独立段落，居中
    if s.startswith("**图 ") or s.startswith("**Fig."):
        para(s.strip("*"), align="center", size="10pt", sa="4pt"); j += 1; continue
    if s.startswith("**表 ") or s.startswith("**Tab."):
        para(s.strip("*"), align="center", size="10pt", bold=True, sa="4pt"); j += 1; continue
    # 参考文献条目
    if re.match(r"^\[\d+\]", s):
        para(s, size=SZ, indent="720", hang="720", line=LS); j += 1; continue
    # 普通正文段（含内行公式）
    rich_para(s, size=SZ, first=True)
    j += 1

io.open(OPS_JSON, "w", encoding="utf-8").write(json.dumps(ops, ensure_ascii=False, indent=1))
print("ops =", len(ops))
print("json ->", OPS_JSON)
