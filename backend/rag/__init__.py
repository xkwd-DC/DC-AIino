"""RAG (Retrieval-Augmented Generation) 模块。

为 DC 项目提供基于文档检索的智能问答能力：
- 索引 docs/ 下所有 .md 和 .pdf 文件
- 中文语义检索 (BGE embedding)
- DeepSeek API 生成回答

使用方式:
    from rag import RAGPipeline
    rag = RAGPipeline()
    answer, sources = rag.query("极端气候对粮食产量的影响机制是什么？")
"""

from __future__ import annotations

__version__ = "0.1.0"
