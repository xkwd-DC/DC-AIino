"""RAG 模块 CLI — 命令行构建索引 + 测试问答。

用法:
    # 构建/重建全库知识库索引 (docs/ → dc_knowledge)
    python -m rag.cli build

    # 构建/重建论文独立索引 (docs/papers → dc_papers)
    python -m rag.cli build-papers

    # 对指定目录/集合建索引
    python -m rag.cli build --dir docs/papers --collection dc_papers

    # 单次问答（默认查全库，--collection 切换）
    python -m rag.cli ask "极端气候对粮食产量的影响机制？"
    python -m rag.cli ask-papers "NeuralCrop 用的是什么模型？"

    # 交互式多轮对话
    python -m rag.cli chat

    # 查看向量库状态
    python -m rag.cli status
    python -m rag.cli status-papers

    # 检索评测：向量 / BM25 / 混合 / GraphRAG 四档对照 + 消融
    python -m rag.cli eval-run --suite eval/suites/dc_rag_v1.json

环境要求:
    DEEPSEEK_API_KEY 必须在 .env 中设置。
    首次运行会自动下载 BGE-M3 模型 (~2.2GB)。
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


def cmd_eval_run(args) -> None:
    """跑检索评测：四档对照 + 消融，输出 JSON 与 Markdown 表。

    注意: eval-run 的 --collection 要写在子命令后面
    （``rag.cli eval-run --collection dc_knowledge ...``）。
    不传则用全局 -c 或默认集合。
    """
    import logging

    from eval.retrievers import ALL_SYSTEMS, build_retrievers
    from eval.runner import (
        parse_int_list,
        render_markdown_table,
        run_suite,
        write_report,
    )
    from eval.schema import load_suite

    logging.basicConfig(level=logging.WARNING, format="%(message)s")

    suite_path = Path(args.suite)
    if not suite_path.is_absolute():
        suite_path = _BACKEND_DIR / suite_path
    items = load_suite(suite_path)

    systems = [s.strip() for s in args.systems.split(",") if s.strip()]
    unknown = [s for s in systems if s not in ALL_SYSTEMS]
    if unknown:
        print(f"[ERROR] 未知档位 {unknown}，可选: {', '.join(ALL_SYSTEMS)}")
        return

    top_ks = parse_int_list(args.top_k)
    ks = parse_int_list(args.ks)
    collection = getattr(args, "collection", None)

    print(f"题库: {suite_path.name}（{len(items)} 题）")
    print(f"档位: {', '.join(systems)}")
    print(f"top_k: {top_ks}    指标截断: {ks}\n")

    for top_k in top_ks:
        retrievers = build_retrievers(systems, collection)
        result = run_suite(items, retrievers, ks=ks, top_k=top_k)

        out = Path(args.out)
        if not out.is_absolute():
            out = _BACKEND_DIR / out
        if len(top_ks) > 1:
            out = out.with_name(f"{out.stem}_k{top_k}{out.suffix}")
        markdown_path = out.with_suffix(".md") if args.markdown else None

        write_report(result, out, markdown_path)
        print(render_markdown_table(result))
        print(f"\n已写出: {out}" + (f"  与  {markdown_path}" if markdown_path else ""))


def cmd_build(args) -> None:
    """构建/重建索引，支持指定目录与集合。"""
    from rag.config import DOCS_DIR, DOCS_PAPERS_DIR, validate
    from rag.pipeline import build_index

    collection = getattr(args, "collection", None) or "dc_knowledge"
    docs_dir = getattr(args, "dir", None)
    if docs_dir is None:
        # 论文集合默认打到 docs/papers，否则全库 docs/
        docs_dir = str(DOCS_PAPERS_DIR) if collection == "dc_papers" else str(DOCS_DIR)

    issues = validate()
    for i in issues:
        print(f"[WARN] {i}")

    print(f"文档目录: {docs_dir}")
    print(f"集合名:   {collection}")
    print("正在构建索引...")
    result = build_index(docs_dir=str(docs_dir), collection_name=collection)
    print(
        f"完成: documents={result['documents']}, chunks={result['chunks']}, "
        f"collection_count={result['collection_count']}, "
        f"collection={result['collection_name']}"
    )


def cmd_ask(question: str, args) -> None:
    """单次问答。"""
    from rag.config import validate
    from rag.pipeline import query

    issues = validate()
    key_issue = next((i for i in issues if "API_KEY" in i), None)
    if key_issue:
        print(f"[ERROR] {key_issue}")
        return

    collection = getattr(args, "collection", None) or "dc_knowledge"
    print(f"问题: {question}\n集合: {collection}\n检索中...")
    result = query(question, collection_name=collection)
    print(f"\n{'='*60}")
    print(result["answer"])
    print(f"{'='*60}")
    print(f"\n来源 ({result['results_count']} 条, {result['tokens_used']} tokens):")
    for i, s in enumerate(result["sources"], 1):
        print(f"  [{i}] {s['title']} ({s['source']}) sim={s['similarity']}")


def cmd_chat(args) -> None:
    """交互式多轮问答。"""
    from rag.config import validate
    from rag.pipeline import query

    issues = validate()
    key_issue = next((i for i in issues if "API_KEY" in i), None)
    if key_issue:
        print(f"[ERROR] {key_issue}")
        return

    collection = getattr(args, "collection", None) or "dc_knowledge"
    print(f"稷韧云图 RAG 知识助手（集合: {collection}）")
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
            cmd_build(args)
            history = []
            continue

        print("思考中...")
        result = query(q, history=history, collection_name=collection)
        print(f"\n{result['answer']}\n")

        history.append({"role": "user", "content": q})
        history.append({"role": "assistant", "content": result["answer"]})
        if len(history) > 12:
            history = history[-12:]


def cmd_status(args) -> None:
    """查询向量库状态和配置。"""
    from rag.vector_store import collection_stats
    from rag.config import validate

    collection = getattr(args, "collection", None) or "dc_knowledge"

    print("配置检查:")
    issues = validate()
    if not issues:
        print("  [OK] 全部通过")
    else:
        for i in issues:
            print(f"  [WARN] {i}")

    try:
        stats = collection_stats(collection)
        print(f"\n向量库（{collection}）:")
        for k, v in stats.items():
            print(f"  {k}: {v}")
    except Exception as exc:
        print(f"\n向量库状态获取失败: {exc}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="rag.cli",
        description="稷韧云图 RAG 命令行",
    )
    parser.add_argument(
        "--collection", "-c",
        default=None,
        help="目标集合名（默认 dc_knowledge；论文集合为 dc_papers）",
    )
    sub = parser.add_subparsers(dest="cmd")

    p_build = sub.add_parser("build", help="构建全库索引")
    p_build.add_argument("--dir", default=None, help="文档目录（默认 docs/）")

    p_build_papers = sub.add_parser("build-papers", help="构建论文独立索引 (docs/papers → dc_papers)")
    p_build_papers.set_defaults(collection="dc_papers")

    p_ask = sub.add_parser("ask", help="单次问答")
    p_ask.add_argument("question", nargs="+", help="问题")

    p_ask_papers = sub.add_parser("ask-papers", help="论文集合单次问答")
    p_ask_papers.add_argument("question", nargs="+", help="问题")
    p_ask_papers.set_defaults(collection="dc_papers")

    p_chat = sub.add_parser("chat", help="交互式多轮问答")
    p_status = sub.add_parser("status", help="查看向量库状态")

    p_status_papers = sub.add_parser("status-papers", help="查看论文集合状态")
    p_status_papers.set_defaults(collection="dc_papers")

    p_eval = sub.add_parser("eval-run", help="检索评测：四档对照 + 消融")
    p_eval.add_argument("--suite", required=True, help="题库 JSON 路径（相对 backend/）")
    p_eval.add_argument(
        "--systems",
        default="vector,bm25,hybrid,graphrag",
        help="逗号分隔的档位，默认四档主表",
    )
    p_eval.add_argument("--top-k", default="10", help='检索条数，可多值，如 "5,10"')
    p_eval.add_argument("--ks", default="5,10", help='指标截断点，如 "5,10"')
    p_eval.add_argument("--out", default="eval/reports/dc_rag_v1.json", help="结果 JSON 输出路径")
    p_eval.add_argument("--markdown", action="store_true", help="同时输出 Markdown 摘要")
    p_eval.add_argument(
        "--collection",
        default=argparse.SUPPRESS,
        help="目标集合（默认沿用全局 -c 或 dc_knowledge）",
    )

    args = parser.parse_args()

    if args.cmd == "build":
        cmd_build(args)
    elif args.cmd == "build-papers":
        cmd_build(args)
    elif args.cmd == "ask":
        cmd_ask(" ".join(args.question), args)
    elif args.cmd == "ask-papers":
        cmd_ask(" ".join(args.question), args)
    elif args.cmd == "chat":
        cmd_chat(args)
    elif args.cmd == "status":
        cmd_status(args)
    elif args.cmd == "status-papers":
        cmd_status(args)
    elif args.cmd == "eval-run":
        cmd_eval_run(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
