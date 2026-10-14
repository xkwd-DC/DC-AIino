"""Pull the regional yearbook Excel files out of the split archive by size."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from zip_over_parts import open_split_zip  # noqa: E402


def main() -> int:
    chunks = Path(r"D:\DC\DC-AIino\data\raw\statistical_yearbook_chunks")
    out = Path(r"D:\DC\_scan\yb2")
    out.mkdir(parents=True, exist_ok=True)
    wanted = {int(x) for x in sys.argv[1:]}

    parts = sorted(chunks.glob("*.part*.zip"))
    with open_split_zip(parts) as zf:
        for idx, info in enumerate(zf.infolist()):
            if info.is_dir() or info.file_size not in wanted:
                continue
            target = out / f"member{idx:03d}_{info.file_size}.bin"
            print(f"extract {info.file_size/1e6:>7.2f} MB -> {target.name}")
            with zf.open(info) as src, target.open("wb") as dst:
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    dst.write(chunk)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
