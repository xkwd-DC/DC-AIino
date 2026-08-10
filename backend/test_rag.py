"""RAG test - skip rebuild, test multiple queries."""
import sys, io
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
from rag.vector_store import collection_stats
from rag.pipeline import build_index, query

stats = collection_stats()
if stats.get("count", 0) == 0:
    print("Index empty, building...")
    r = build_index()
    print(f"  docs={r['documents']} chunks={r['chunks']}")
else:
    print(f"Index OK: {stats['count']} chunks")

questions = [
    "极端气候对粮食产量的影响机制是什么？",
    "SHAP分析方法在农业研究中的应用？",
    "NDVI对作物产量预测的贡献有多大？",
]

for q in questions:
    print(f"\n{'='*60}")
    print(f"Q: {q}")
    print("=" * 60)
    r2 = query(q)
    ans = r2["answer"]
    if len(ans) > 500:
        ans = ans[:500] + "..."
    print(f"\n{ans}")
    print(f"\n  Sources ({r2['tokens_used']} tokens):")
    for i, s in enumerate(r2["sources"], 1):
        print(f"  [{i}] {s['title'][:60]} (sim={s['similarity']})")

print("\nDONE!")
