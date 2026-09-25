"""把三套字体子集化成小的本地文件。

为什么不直接用 Google Fonts 的 208 个 unicode-range 分片：
把 970KB 的 @font-face CSS 内联进 4 个 composition 后，渲染器报
「Font localization failed: Invalid array length」，snapshot 也导航超时。

做法：
1. 取四份 composition 里出现过的全部字符（CSS/JS 里的拉丁字符也一并带上，反正便宜）
2. 从 google/fonts 拉三套可变字体源文件
3. pyftsubset 子集化，保留 wght 可变轴，一个家族一个文件
4. 写出 assets/fonts/local.css（6 条以内的 @font-face）

用法: <hermes venv python> tools/build-fonts-local.py
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "assets" / "fonts"
SRC_DIR = ROOT / ".cache" / "fonts-src"
COMPOSITIONS = sorted((ROOT / "compositions").glob("*.html"))

SOURCES = {
    "NotoSansSC": "https://github.com/google/fonts/raw/main/ofl/notosanssc/NotoSansSC%5Bwght%5D.ttf",
    "NotoSerifSC": "https://github.com/google/fonts/raw/main/ofl/notoserifsc/NotoSerifSC%5Bwght%5D.ttf",
    "JetBrainsMono": "https://github.com/google/fonts/raw/main/ofl/jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf",
}

# 无论片子里有没有出现都保一手：标点、数字、常用符号
BASE_CHARS = (
    "0123456789"
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    " .,:;!?/()[]{}<>+-=_*&%$#@'\"`|\\~^"
    "，。、；：！？“”‘’（）《》〈〉—…·～￥％"
    "−→←↑↓⇌◉◈⚙◊⟳√×÷≈≥≤±°"
)


def curl(url: str, out: pathlib.Path) -> bool:
    args = ["curl.exe", "-sSL", "--connect-timeout", "25", "--retry", "2", url, "-o", str(out)]
    for extra in ([], ["--proxy", "http://127.0.0.1:7890"]):
        try:
            subprocess.run(args + extra, check=True, capture_output=True)
            if out.exists() and out.stat().st_size > 1024:
                return True
        except subprocess.CalledProcessError:
            continue
    return False


def collect_chars() -> str:
    chars = set(BASE_CHARS)
    for file in COMPOSITIONS:
        chars |= set(file.read_text(encoding="utf-8"))
    for extra in ("narration.txt", "SCRIPT.md", "STORYBOARD.md"):
        p = ROOT / extra
        if p.exists():
            chars |= set(p.read_text(encoding="utf-8"))
    return "".join(sorted(c for c in chars if not c.isspace() or c == " "))


def main() -> int:
    FONT_DIR.mkdir(parents=True, exist_ok=True)
    SRC_DIR.mkdir(parents=True, exist_ok=True)

    chars = collect_chars()
    print(f"unique chars: {len(chars)}")

    for name, url in SOURCES.items():
        src = SRC_DIR / f"{name}.ttf"
        if not src.exists() or src.stat().st_size < 100_000:
            print(f"fetching {name} …")
            if not curl(url, src):
                print(f"  ! failed: {url}")
                return 1
        out = FONT_DIR / f"{name}-subset.woff2"
        cmd = [
            sys.executable,
            "-m",
            "fontTools.subset",
            str(src),
            f"--text={chars}",
            "--layout-features=*",
            "--flavor=woff2",
            "--output-file=" + str(out),
            "--no-hinting",
            "--desubroutinize",
        ]
        subprocess.run(cmd, check=True)
        print(f"  {name}: {src.stat().st_size / 1024:.0f} KB → {out.stat().st_size / 1024:.1f} KB")

    css = """/* 本地字体子集 — 由 tools/build-fonts-local.py 生成，不要手改。
   只包含片子里出现过的字符；变量字体的 wght 轴保留，所以每个家族一个文件。 */
@font-face {
  font-family: 'Noto Sans SC';
  src: url('assets/fonts/NotoSansSC-subset.woff2') format('woff2-variations');
  font-weight: 100 900;
  font-style: normal;
  font-display: block;
}
@font-face {
  font-family: 'Noto Serif SC';
  src: url('assets/fonts/NotoSerifSC-subset.woff2') format('woff2-variations');
  font-weight: 100 900;
  font-style: normal;
  font-display: block;
}
@font-face {
  font-family: 'JetBrains Mono';
  src: url('assets/fonts/JetBrainsMono-subset.woff2') format('woff2-variations');
  font-weight: 100 900;
  font-style: normal;
  font-display: block;
}
"""
    (FONT_DIR / "local.css").write_text(css, encoding="utf-8")
    print(f"wrote {FONT_DIR / 'local.css'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
