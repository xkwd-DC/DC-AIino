"""RAG 模块 CLI — 命令行构建索引 + 测试问答。

用法:
    # 构建/重建知识库索引
    python -m rag.cli build

    # 单次问答测试
    python -m rag.cli ask "极端气候对粮食产量的影响机制？"

    # 交互式多轮对话
    python -m rag.cli chat

    # 查看向量库状态
    python -m rag.cli status

环境要求:
    DEEPSEEK_API_KEY 必须在 .env 中设置。
    首次运行会自动下载 BGE-small-zh 模型 (~130MB)。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 确保 backend/ 在 sys.path 中（从任意目录运行均可找到 rag 包）
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from dotenv import load_dotenv
load_dotenv()


def cmd_build():
    """构建/重建知识库索引。"""
    from rag.config import DOCS_DIR, validate
    from rag.pipeline import build_index

    issues = validate()
    for i in issues:
        print(f"[WARN] {i}")

    print(f"文档目录: {DOCS_DIR}")
    print("正在构建索引...")
    result = build_index()
    print(f"完成: documents={result['documents']}, chunks={result['chunks']}, "
          f"collection_count={result['collection_count']}")


def cmd_ask(question: str):
    """单次问答。"""
    from rag.config import validate
    from rag.pipeline import query

    issues = validate()
    key_issue = next((i for i in issues if "API_KEY" in i), None)
    if key_issue:
        print(f"[ERROR] {key_issue}")
        return

    print(f"问题: {question}\n检索中...")
    result = query(question)
    print(f"\n{'='*60}")
    print(result["answer"])
    print(f"{'='*60}")
    print(f"\n来源 ({result['results_count']} 条, {result['tokens_used']} tokens):")
    for i, s in enumerate(result["sources"], 1):
        print(f"  [{i}] {s['title']} ({s['source']}) sim={s['similarity']}")


def cmd_chat():
    """交互式多轮问答。"""
    from rag.config import validate
    from rag.pipeline import query

    issues = validate()
    key_issue = next((i for i in issues if "API_KEY" in i), None)
    if key_issue:
        print(f"[ERROR] {key_issue}")
        return

    print("稷韧云图 RAG 知识助手")
    print("输入问题开始对话，/quit 退出，/rebuild 重建索引\n")

    history: list[dict[str, str]] = []
    while True:
        try:
            q = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not q:
            continue
        if q == "/quit":
            break
        if q == "/rebuild":
            cmd_build()
            history = []
            continue

        print("思考中...")
        result = query(q, history=history)
        print(f"\n{result['answer']}\n")

        history.append({"role": "user", "content": q})
        history.append({"role": "assistant", "content": result["answer"]})
        if len(history) > 12:
            history = history[-12:]


def cmd_status():
    """查询向量库状态和配置。"""
    from rag.vector_store import collection_stats
    from rag.config import validate

    print("配置检查:")
    issues = validate()
    if not issues:
        print("  [OK] 全部通过")
    else:
        for i in issues:
            print(f"  [WARN] {i}")

    try:
        stats = collection_stats()
        print(f"\n向量库:")
        for k, v in stats.items():
            print(f"  {k}: {v}")
    except Exception as exc:
        print(f"\n向量库状态获取失败: {exc}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmds = {
        "build":  lambda: cmd_build(),
        "ask":    lambda: cmd_ask(" ".join(sys.argv[2:])),
        "chat":   lambda: cmd_chat(),
        "status": lambda: cmd_status(),
    }

    action = cmds.get(sys.argv[1].lower())
    if action is None:
        print(f"未知命令: {sys.argv[1]}")
        print("可用: build | ask <问题> | chat | status")
        sys.exit(1)

    if sys.argv[1].lower() == "ask" and len(sys.argv) < 3:
        print("用法: python -m rag.cli ask <问题>")
        sys.exit(1)

    action()
