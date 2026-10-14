"""Extract selected members from the split yearbook zip using corrected names."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from zip_over_parts import open_split_zip  # noqa: E402


def fix_name(raw: str) -> str:
    """Outer archive stores GBK names without the UTF-8 flag set."""
    try:
        return raw.encode("cp437").decode("gbk")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


def main() -> int:
    chunks_dir = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    # sizes given on the command line identify members unambiguously, because the
    # archive stores GBK names under a UTF-8 flag and the names decode lossily.
    wanted = {int(s) for s in sys.argv[3:]}
    out_dir.mkdir(parents=True, exist_ok=True)

    parts = sorted(chunks_dir.glob("*.part*.zip"))
    with open_split_zip(parts) as zf:
        for idx, info in enumerate(zf.infolist()):
            if info.is_dir() or info.file_size not in wanted:
                continue
            target = out_dir / f"member{idx:03d}_{info.file_size}.bin"
            if target.exists() and target.stat().st_size == info.file_size:
                print(f"skip (exists) {target.name}")
                continue
            print(f"extract {info.file_size/1e6:>8.2f} MB  {target.name}")
            with zf.open(info) as src, target.open("wb") as dst:
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    dst.write(chunk)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
