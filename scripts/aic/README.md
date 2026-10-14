# AIC 参赛材料生成工具链

本目录存放把"匿名版方案 → 可提交 PDF/DOCX/PPTX"的脚本，避免材料只能靠手工调整。

## 输入与输出

| 输入 | 脚本 | 输出 |
|---|---|---|
| `docs/aic/提交材料-赛题二/proposal.html`（或 `evidence.html`） | `html2docx.py` | 同名 `.docx`（标题样式、表格、内嵌图片） |
| 上述 `.docx` | WPS COM（`Documents.Open` + `ExportAsFixedFormat`，格式码 17） | 同名 `.pdf` |
| `deck_data_track2.json` | `build_deck_track2.ps1`（WPS Presentation COM） | 答辩材料 `.pptx` + 导出 `.pdf`，并按页导出 `deck_png/slideNN.png` |

## 用法

```powershell
# 1) HTML → DOCX
python scripts/aic/html2docx.py "docs/aic/提交材料-赛题二/proposal.html" "docs/aic/提交材料-赛题二/禾衡-...-技术方案.docx"

# 2) DOCX → PDF（WPS）
$wps = New-Object -ComObject KWPS.Application
$wps.Visible = $false
$doc = $wps.Documents.Open("<docx 绝对路径>", $false, $true)
$doc.ExportAsFixedFormat("<pdf 绝对路径>", 17)
$doc.Close(0); $wps.Quit()

# 3) 答辩 PPTX + PDF
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/aic/build_deck_track2.ps1
```

## 幻灯片定义

`deck_data_track2.json` 里 `outPptx` / `outPdf` / `imageDir` 为绝对路径（本机工作目录布局），
`slides[]` 每项的 `kind` 决定版式，支持：`cover`、`cols3`、`cols4`、`table`、`bands`、
`steps8`、`twocol`、`engine`、`image`、`mix`。改内容只改 JSON，不要改版式代码。

## 注意

- 依赖本机安装 WPS 或 Office（COM 组件 `KWPS.Application` / `KWPP.Application`）；
- 幻灯片与文档中的数字必须与 `docs/aic/提交材料-赛题二/` 内的定稿一致，
  叙事口径以 `docs/AGENT_BRIEFING.md` §4 为准（不得回滚到"跨省高精度预测"）；
- 对外材料导出后仍需执行 `docs/aic/00_参赛方案总览与脱敏清单.md` §3.3 的匿名化 grep。
