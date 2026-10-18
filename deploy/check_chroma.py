"""检查一个（或多个）ChromaDB 目录能否正常打开，并打印各 collection 的条数。

便携包打包后用它验证向量索引有没有拷坏。最常见的翻车点：ChromaDB 的 Rust 层
**不支持非 ASCII 路径** —— 同一个库放在中文目录下，打开时就报
`Error loading hnsw index`，换到纯 ASCII 路径立刻正常。所以这个检查既能查拷贝
完整性，也能顺带确认包所在路径是不是 ASCII。

用法：
    <python.exe> deploy/check_chroma.py <chroma_dir> [<chroma_dir> ...]
"""
import sys
from pathlib import Path


def probe(root: str) -> bool:
    """返回该目录是否完全健康。"""
    p = Path(root)
    print(f"== {root}")
    if not p.exists():
        print("   (目录不存在)")
        return False

    healthy = True
    ascii_only = all(ord(ch) < 128 for ch in str(p.resolve()))
    if not ascii_only:
        print("   注意：路径含非 ASCII 字符，ChromaDB 在 Windows 上很可能加载不了 HNSW 索引")

    try:
        import chromadb

        client = chromadb.PersistentClient(path=str(p))
        for col in client.list_collections():
            try:
                print(f"   collection {col.name!r}: count={col.count()}")
            except Exception as exc:  # noqa: BLE001
                healthy = False
                print(f"   collection {col.name!r}: FAILED -> {type(exc).__name__}: {exc}")
    except Exception as exc:  # noqa: BLE001
        healthy = False
        print(f"   打开失败 -> {type(exc).__name__}: {exc}")
    return healthy


ok = all(probe(arg) for arg in sys.argv[1:])
sys.exit(0 if ok else 1)
