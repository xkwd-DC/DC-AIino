"""Read a split zip archive (part01, part02, ...) without merging to disk.

Provides a seekable file-like view over the concatenation of the part files,
so zipfile can read the central directory and extract members directly.
"""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path


class SplitFile(io.RawIOBase):
    """Seekable read-only view over an ordered list of part files."""

    def __init__(self, parts: list[Path]) -> None:
        self.parts = parts
        self.sizes = [p.stat().st_size for p in parts]
        self.offsets: list[int] = []
        running = 0
        for size in self.sizes:
            self.offsets.append(running)
            running += size
        self.total = running
        self.pos = 0
        self._handles: dict[int, io.BufferedReader] = {}

    def _handle(self, idx: int) -> io.BufferedReader:
        handle = self._handles.get(idx)
        if handle is None:
            handle = self.parts[idx].open("rb")
            self._handles[idx] = handle
        return handle

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

    def readinto(self, buffer) -> int:
        want = len(buffer)
        if want == 0 or self.pos >= self.total:
            return 0

        # locate the part containing self.pos
        idx = 0
        for i, off in enumerate(self.offsets):
            if self.pos >= off:
                idx = i
            else:
                break

        written = 0
        while written < want and idx < len(self.parts):
            local = self.pos - self.offsets[idx]
            handle = self._handle(idx)
            handle.seek(local)
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


def open_split_zip(part_files: list[Path]) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BufferedReader(SplitFile(part_files)))


def main() -> int:
    chunks_dir = Path(sys.argv[1])
    parts = sorted(chunks_dir.glob("*.part*.zip"))
    if not parts:
        print("no part files found", file=sys.stderr)
        return 1

    print(f"parts: {len(parts)}  total {sum(p.stat().st_size for p in parts)/1e9:.2f} GB")
    with open_split_zip(parts) as zf:
        names = zf.namelist()
        print(f"members: {len(names)}")
        for name in names[:200]:
            info = zf.getinfo(name)
            print(f"  {info.file_size:>10}  {name}")
        if len(names) > 200:
            print(f"  ... and {len(names) - 200} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
