# CLAUDE.md — DC Project Knowledge Base

## Wiki (Shared Knowledge)
Project knowledge wiki at ~/wiki/ — maintained by Hermes Agent.
Before answering DC research questions, check these pages:

### Core
- entities/dc-project.md — Project overview, status, data versions, model cards
- comparisons/dc-papers-overview.md — Literature review: 6 papers + cross-comparison

### Literature (精读笔记)
- concepts/dc-paper-yin-climate-resilience.md — 尹朝静: food production climate resilience (SMM + geo-detector)
- concepts/dc-paper-guo-extreme-climate.md — 郭珊: extreme climate × farmland transfer (296-city panel FE + threshold)
- concepts/dc-paper-li-extreme-northeast.md — 李浩天: NE China extreme temp/precipitation spatiotemporal
- concepts/dc-paper-wang-resilience.md — 王萍萍: grain production resilience measurement (spatial Durbin)
- concepts/dc-paper-zhang-cyanobacteria.md — 张娜: SHAP attribution for cyanobacteria blooms
- concepts/dc-paper-yang-review.md — 杨倩倩: climate change impact on grain production (review)

### Models & Data
- concepts/xgboost-food-risk.md — XGBoost-SHAP: R²=0.9072
- concepts/lstm-food-risk.md — LSTM/Attention-LSTM: R²=0.8856/0.8160
- concepts/dc-data-expansion-plan.md — v5 prefecture-level panel expansion
- concepts/dc-remote-sensing-status.md — Remote sensing (MODIS/CLCD) data status

Usage: `cat ~/wiki/<path>` or `ls ~/wiki/concepts/` to list all pages.

## Document Editing (文档编辑规范)

**ALWAYS use officecli as the primary tool for ALL .docx manipulation.**
Never attempt PowerShell COM objects, python-docx direct manipulation, or other
approaches unless officecli is confirmed unavailable.

Before any .docx work:
- Verify officecli is available: `officecli --help`
- Check Word isn't locking the file: `Get-Process WINWORD`
- If WINWORD is running, warn user to close Word before proceeding

### Practice Report Workflow (实习报告生成)

When generating student practice reports:
1. **ALWAYS start by analyzing the provided .docx template** — read its structure with officecli
2. Systematically identify sections and placeholder content
3. Fill in content section by section using officecli
4. Add figure captions with `officecli caption add` (use `size` not `font.size`)
5. After all edits, check for duplicate numbering (numPr + manual text conflict) and fix if found
6. Clear score fields and signature lines
7. **NEVER create a report from scratch** — always fill the template

## Environment / Platform Notes (环境备注)

- **Chinese encoding on Windows**: always use `encoding='utf-8'` in Python scripts,
  handle `UnicodeDecodeError` with GBK fallback
- **Shell commands with Chinese**: use double quotes (`"`), not single quotes (`'`)
- **Smart quotes in Chinese text**: watch for `''` (U+2018/U+2019) and `""` (U+201C/U+201D)
  which can break JSON parsing — normalize to straight quotes when needed

## Pre-flight Checklist (预检清单)

Before editing critical files:
- `.docx` files → check `Get-Process WINWORD` first, warn if Word is running
- `.c` source files → after editing, run `gcc *.c -o output.exe` to verify compilation
- Files with Chinese content → verify encoding (UTF-8 preferred, GBK as fallback)

## Error Recovery (错误恢复)

- When API connections drop (502 errors, timeouts): proactively retry — don't wait for user
  to type "继续"
- For long-running operations (GraphRAG indexing, batch officecli): implement
  checkpoint/resume logic so progress isn't lost on timeout
- When a fix doesn't work: test the fix before reporting success — stale .pyc caches
  and other artifacts can mask real errors

## Wiki Recording (知识沉淀)

After completing significant work or discovering important findings, record to the
wiki at `~/wiki/` (maintained by Hermes Agent). Follow `~/wiki/SCHEMA.md` conventions:

- File names: lowercase, hyphens, no spaces
- Every page starts with YAML frontmatter (title, created, updated, type, tags)
- Add new pages to `~/wiki/index.md` under the correct section
- Append every action to `~/wiki/log.md`
- Link to related pages with `[[wikilinks]]` (minimum 2 outbound links per page)

**When to record:**
- New paper read → `concepts/dc-paper-*.md`
- Project milestone → update `entities/<project>.md`
- Environment/config fix → `concepts/<topic>.md`
- New tool/workflow → `concepts/<tool-name>.md`
- Bug fix with lessons learned → update relevant concept page

**After each DC session:** at minimum, update `entities/dc-project.md` with
current status, data versions, and model performance.
