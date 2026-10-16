#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 AIC 参赛底稿（Markdown）转成带 A4 打印版式的 HTML，供 html2docx.py 再转 DOCX。

为什么需要它
============
仓库里现成的 `提交材料-赛题二/proposal.html` 是**手写**的（573 行），排版好但不可维护：
底稿每改一次（比如这次加入县级层），HTML 就得跟着手改一遍。
本脚本把"版式"从"内容"里剥出来：内容留在 `.md`，版式留在本文件底部的 CSS，
一条命令重出 HTML。版式与赛题二那份手写稿保持一致（同一套 A4 / 字体 / 表头配色）。

用法
====
    python scripts/aic/md2proposal.py docs/aic/01_AI+学科交叉_技术方案_匿名版.md \
        docs/aic/提交材料-学科交叉/proposal.html \
        --kicker "AIC 第八届算法创新赛 · 赛题5「AI+学科交叉」" \
        --subtitle "技术方案（匿名版）" \
        --meta "作品名称=禾衡·粮食生产气候风险归因决策系统" \
        --meta "参赛赛题=AI+学科交叉" \
        --meta "材料日期=2026 年 10 月"

两条约定
========
1. **`〔作者备注〕` 的引用块不会进 HTML**：底稿里写给自己的话（"提交前必须重绘架构图"之类）
   挂在 `> 〔作者备注〕…` 里，转换时整块丢弃，避免误入提交件；
2. 一级标题（`# `）只用于封面标题，正文里会被去掉。
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import markdown

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CSS = """
  @page { size: A4; margin: 18mm 16mm 16mm 16mm; }
  * { box-sizing: border-box; }
  html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  body {
    margin: 0; color: #000;
    font-family: "SimSun", "宋体", "Songti SC", serif;
    font-size: 10.5pt; line-height: 1.75;
  }
  h1, h2, h3, h4 { font-family: "Microsoft YaHei", "微软雅黑", "PingFang SC", sans-serif; color: #000; }
  h2 { font-size: 14pt; margin: 0 0 8pt 0; padding: 0; }
  h3 { font-size: 11.5pt; margin: 12pt 0 5pt 0; }
  h4 { font-size: 10.5pt; margin: 10pt 0 4pt 0; }
  p { margin: 0 0 7pt 0; text-align: justify; text-justify: inter-ideograph; }
  ul, ol { margin: 0 0 7pt 0; padding-left: 1.5em; }
  li { margin-bottom: 3pt; text-align: justify; }
  strong { font-family: "Microsoft YaHei", "微软雅黑", sans-serif; font-weight: 700; }
  code { font-family: "Consolas", monospace; font-size: 9.5pt; }
  blockquote {
    margin: 0 0 8pt 0; padding: 5pt 8pt; border-left: 2pt solid #1F3864;
    background: #F5F7FA; font-size: 10pt;
  }
  blockquote p { margin: 0; }
  /* ---------- 图 ---------- */
  figure { margin: 10pt 0 12pt 0; break-inside: avoid; }
  figure img { width: 100%; display: block; }
  figcaption { font-size: 9.5pt; text-align: center; margin-top: 4pt; font-family: "Microsoft YaHei", sans-serif; }
  .section { break-before: page; }
  /* ---------- 封面 ---------- */
  .cover { height: 246mm; position: relative; }
  .cover .kicker { font-family: "Microsoft YaHei", sans-serif; font-size: 11pt; letter-spacing: 2px; text-align: center; margin-top: 42mm; }
  .cover h1 { font-size: 24pt; text-align: center; margin: 10mm 0 4mm 0; letter-spacing: 1px; }
  .cover .sub { text-align: center; font-size: 13pt; font-family: "Microsoft YaHei", sans-serif; margin-bottom: 26mm; }
  .cover .meta { width: 118mm; margin: 0 auto; font-size: 11pt; }
  .cover .meta div { display: flex; gap: 6mm; padding: 2.6mm 0; border-bottom: 1px solid #D9D9D9; }
  .cover .meta span:first-child { width: 28mm; color: #000; font-family: "Microsoft YaHei", sans-serif; }
  .cover .foot { position: absolute; bottom: 0; width: 100%; text-align: center; font-size: 10pt; }
  /* ---------- 表格 ---------- */
  table { width: 100%; border-collapse: collapse; margin: 6pt 0 10pt 0; font-size: 9.5pt; break-inside: auto; }
  th, td { border: 1px solid #D9D9D9; padding: 4pt 5pt; vertical-align: middle; line-height: 1.5; }
  thead th { background: #1F3864; color: #fff; font-family: "Microsoft YaHei", sans-serif; font-weight: 600; text-align: center; }
  tbody tr:nth-child(even) td { background: #F5F7FA; }
  tr { break-inside: avoid; }
  thead { display: table-header-group; }
  @media screen {
    body { width: 178mm; margin: 18mm auto 16mm auto; background: #fff; }
    html { background: #eceff3; }
  }
"""

def strip_author_notes(text: str) -> tuple[str, int]:
    """删除 `> 〔作者备注〕…` 段落，返回 (文本, 删除条数)。

    备注块 = 以 `> 〔作者备注〕` 开头的那一行，加上紧随其后的引用续行
    （形如 `> xxx`，直到出现非引用行）。
    """
    lines = text.split("\n")
    out: list[str] = []
    dropped = 0
    i = 0
    while i < len(lines):
        if lines[i].lstrip().startswith("> 〔作者备注〕") or lines[i].lstrip().startswith(">〔作者备注〕"):
            dropped += 1
            i += 1
            while i < len(lines) and lines[i].lstrip().startswith(">"):
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out), dropped


def drop_thematic_breaks(text: str) -> str:
    """删掉单独的 `---` 分隔行。

    底稿用 `---` 分隔章节，但转换后每章已经是独立 `<section>`（`break-before: page`），
    再留一条水平线只会在上一页末尾多出一条孤零零的横线。
    （表格里的分隔行是 `|---|` 形式，不会被误伤。）
    """
    return "\n".join("" if line.strip() == "---" else line for line in text.split("\n"))


def split_title(text: str) -> tuple[str, str]:
    """取出第一个一级标题作为封面标题，并从正文里移除它。"""
    m = re.search(r"^# +(.+?)\s*$", text, re.MULTILINE)
    if not m:
        raise SystemExit("[FATAL] 底稿里没有一级标题（# …），无法生成封面")
    title = m.group(1).strip()
    return title, text[: m.start()] + text[m.end():]


def build(title: str, body_md: str, kicker: str, subtitle: str,
          meta: list[tuple[str, str]], strip_src_prefix: str = "") -> str:
    html_body = markdown.markdown(
        body_md,
        extensions=["tables", "sane_lists", "attr_list"],
        output_format="html",
    )
    # 单独成段的图片包成 <figure>，图片说明取 markdown 的 alt 文本
    # （CSS 里 figure/figcaption 已有版式；html2docx 会把 alt 之外的结构照搬）
    html_body = re.sub(
        r'<p>\s*<img([^>]*?)alt="([^"]*)"([^>]*?)>\s*</p>',
        lambda m: (
            f'<figure><img{m.group(1)}alt="{m.group(2)}"{m.group(3)}>'
            f'<figcaption>{m.group(2)}</figcaption></figure>'
        ),
        html_body,
    )
    # 底稿里的图片路径相对「底稿所在目录」，HTML 里的要相对「HTML 所在目录」。
    # 用 --strip-src-prefix 去掉那层目录名，两边各自都能对上（html2docx 按 HTML 目录解析 src）。
    if strip_src_prefix:
        html_body = html_body.replace(f'src="{strip_src_prefix}', 'src="')
    # 每个 ## 章单独成页（与手写稿的 <section class="section"> 一致）
    chunks = [c for c in re.split(r"(?=<h2)", html_body) if c.strip()]
    sections = "\n".join(f'<section class="section">\n{c.strip()}\n</section>' for c in chunks)

    meta_html = "\n".join(
        f'    <div><span>{k}</span><span>{v}</span></div>' for k, v in meta
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{title} {subtitle}</title>
<style>{CSS}</style>
</head>
<body>
<div class="cover">
  <div class="kicker">{kicker}</div>
  <h1>{title}</h1>
  <div class="sub">{subtitle}</div>
  <div class="meta">
{meta_html}
  </div>
  <div class="foot">本材料已按大赛要求匿名化处理：不含参赛团队所在学校名称、标识与指导教师信息。</div>
</div>

{sections}
</body>
</html>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="AIC 底稿 Markdown → A4 版式 HTML")
    ap.add_argument("input", type=Path, help="底稿 .md")
    ap.add_argument("output", type=Path, help="输出 .html")
    ap.add_argument("--kicker", default="AIC · 技术方案", help="封面顶部小字")
    ap.add_argument("--subtitle", default="技术方案（匿名版）", help="封面副标题")
    ap.add_argument("--meta", action="append", default=[], help="封面信息行，格式 键=值（可重复）")
    ap.add_argument("--strip-src-prefix", default="",
                    help="图片 src 去掉该前缀（让底稿与 HTML 各自相对自己的目录都能解析）")
    args = ap.parse_args()

    raw = args.input.read_text(encoding="utf-8")
    title, body = split_title(raw)
    body, dropped = strip_author_notes(body)
    body = drop_thematic_breaks(body)
    meta = []
    for item in args.meta:
        if "=" not in item:
            raise SystemExit(f"[FATAL] --meta 需要 键=值 形式，收到 {item!r}")
        k, v = item.split("=", 1)
        meta.append((k.strip(), v.strip()))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        build(title, body, args.kicker, args.subtitle, meta, args.strip_src_prefix),
        encoding="utf-8",
    )
    print(f"[输入] {args.input}  （标题：{title}；剥离作者备注 {dropped} 条）")
    print(f"[输出] {args.output}  {args.output.stat().st_size / 1024:.1f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
