#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成应用图标（桌面快捷方式 / 任务栏用）。

图案对齐站点顶部品牌标（frontend/src/App.vue 的 .brand-logo）：
绿底圆角方块 + 「粮」字，深色字压在浅色渐变上 —— 让"先看图标再看标题"这套
在桌面上也成立，不用另做一套视觉。

产出：
    deploy/assets/dc-app.ico            多尺寸图标（16/24/32/48/64/128/256）
    deploy/assets/dc-app-preview.png    512 预览图（给人看 / 进文档，不被引用）

用法：
    python scripts/make_app_icon.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "deploy" / "assets"
ICO = OUT_DIR / "dc-app.ico"
PREVIEW = OUT_DIR / "dc-app-preview.png"

CANVAS = 1024                      # 先画大图再缩，边缘更干净
SIZES = [16, 24, 32, 48, 64, 128, 256]
RADIUS_RATIO = 0.22                # 圆角占边长比例

# 与 styles/tokens.css 同源：--green-deep → --green，字色 #0E1A14
GRAD_FROM = (0x6F, 0x8C, 0x5C)
GRAD_TO = (0xA0, 0xB7, 0x85)
TEXT_COLOR = (0x0E, 0x1A, 0x14, 255)
GLYPH = "粮"

# 图标尺寸小，粗黑体比宋体可读。按优先级挑第一个存在的。
FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyhbd.ttc",   # 微软雅黑 Bold
    r"C:\Windows\Fonts\msyh.ttc",     # 微软雅黑
    r"C:\Windows\Fonts\simhei.ttf",   # 黑体
    r"C:\Windows\Fonts\simsun.ttc",   # 宋体
]


def pick_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise SystemExit("[FATAL] 找不到中文字体（试过 msyhbd/msyh/simhei/simsun）")


def make_master() -> Image.Image:
    """斜向渐变 + 圆角遮罩 + 居中「粮」。"""
    # 对角渐变：0 → 1 沿左上到右下
    ramp = np.linspace(0.0, 1.0, CANVAS, dtype=np.float32)
    t = (ramp[:, None] + ramp[None, :]) / 2.0
    rgb = np.zeros((CANVAS, CANVAS, 3), dtype=np.float32)
    for ch in range(3):
        rgb[:, :, ch] = GRAD_FROM[ch] + (GRAD_TO[ch] - GRAD_FROM[ch]) * t
    grad = Image.fromarray(rgb.astype(np.uint8), mode="RGB").convert("RGBA")

    # 圆角遮罩（4x 超采样画圆角，缩回来做抗锯齿）
    ss = 4
    mask = Image.new("L", (CANVAS * ss, CANVAS * ss), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, CANVAS * ss - 1, CANVAS * ss - 1),
        radius=int(CANVAS * RADIUS_RATIO * ss),
        fill=255,
    )
    mask = mask.resize((CANVAS, CANVAS), Image.LANCZOS)

    master = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    master.paste(grad, (0, 0), mask)

    # 居中「粮」：用 bbox 而不是 anchor，跨字体更稳
    font = pick_font(int(CANVAS * 0.56))
    draw = ImageDraw.Draw(master)
    left, top, right, bottom = draw.textbbox((0, 0), GLYPH, font=font)
    draw.text(
        ((CANVAS - (right - left)) / 2 - left, (CANVAS - (bottom - top)) / 2 - top),
        GLYPH,
        font=font,
        fill=TEXT_COLOR,
    )
    return master


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    master = make_master()
    master.save(ICO, format="ICO", sizes=[(s, s) for s in SIZES])
    master.resize((512, 512), Image.LANCZOS).save(PREVIEW, format="PNG")
    print(f"[输出] {ICO.relative_to(PROJECT_ROOT)}  {ICO.stat().st_size / 1024:.1f} KB  sizes={SIZES}")
    print(f"[输出] {PREVIEW.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
