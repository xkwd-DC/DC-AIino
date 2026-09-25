# 检索评测模块（eval/）

给 GraphRAG 论文提供实验表格：四档检索器对照 + 消融，输出 JSON（逐题明细）与 Markdown 摘要。

## 快速开始

```bash
cd backend

# 四档主表
python -m rag.cli eval-run --suite eval/suites/dc_rag_v1.json \
  --systems vector,bm25,hybrid,graphrag --top-k 10 --ks 5,10 \
  --out eval/reports/dc_rag_v1_four_system.json --markdown

# 消融
python -m rag.cli eval-run --suite eval/suites/dc_rag_v1.json \
  --systems hybrid_rerank,graphrag_no_rerank,graphrag_no_bm25 \
  --out eval/reports/dc_rag_v1_ablation.json

# 重新草拟题库（会覆盖，人工改动请先备份）
python -m eval.build_suite --per-type 20 --out eval/suites/dc_rag_v1.json
```

跑 GraphRAG 档位需要 `DEEPSEEK_API_KEY`；跑精排档位需要 `RAG_RERANKER_MODEL` 指向本地权重
（huggingface.co 直连不通，权重从 ModelScope 取，放在 `D:\huggingface\models\bge-reranker-v2-m3`）。

## 档位

| 名称 | 含义 |
|------|------|
| `vector` | BGE-M3 稠密向量 |
| `bm25` | BM25Okapi 关键词 |
| `hybrid` | BM25 + 向量，RRF 融合（生产默认） |
| `graphrag` | 混合召回 + 图谱展开 + RRF + BGE-Reranker |
| `hybrid_rerank` | 消融：去图谱 |
| `graphrag_no_rerank` | 消融：去精排 |
| `graphrag_no_bm25` | 消融：去关键词 |

## 三条必须知道的约定

1. **文档级判定。** 图谱索引用 2000 字分块、向量库用 800 字分块，块 ID 对不上，
   所以 gold 与命中都经 `normalize_doc()` 归一到文档路径后再比。
2. **题库来源决定结论。** 草稿题由图谱机械生成，对 GraphRAG 有结构性偏袒。
   报告会自动单列"仅人工核对"子集（`verified: true`），**结论请以该子集为准**。
   实测：全部 60 题上 GraphRAG 的 recall@5 是 0.821，9 道人工核对题上只有 0.259。
3. **gold 文档数上限 5。** 「XGBoost-SHAP 与 R² 是什么关系」这类题能牵出 44 篇文档，
   gold 过大任何一篇命中都算召回，指标会虚高，这类题在出题阶段就被剔除。

## 题库

- `eval/suites/seeds_verified.json` — **人工核对过的题**，gold 逐条在源文件里定位过（note 里记了行号）。
  这是唯一有结论价值的子集，**继续扩充它**。
- `eval/suites/dc_rag_v1.json` — 最终题库（9 题种子 + 51 题草稿），草稿题 `verified: false`，
  需要人工改问法后打开开关。

## 目录

```
eval/
├── schema.py        题库条目与命中，含文档级归一化
├── metrics.py       Recall@k / MRR / nDCG@k（二值相关性）
├── retrievers.py    四档检索器 + 消融 + RRF 融合 + 图谱展开
├── runner.py        执行、按题型聚合、渲染 Markdown
├── build_suite.py   从图谱机械草拟题库
└── suites/          题库
```
