# AIC 参赛材料生成工具链

本目录存放把"匿名版方案 → 可提交 PDF/DOCX/PPTX"的脚本，避免材料只能靠手工调整。

## 输入与输出

| 输入 | 脚本 | 输出 |
|---|---|---|
| 底稿 `docs/aic/0N_*.md` | `md2proposal.py` | 带 A4 打印版式的 `proposal.html`（剥离作者备注、图包 figure、章节分页） |
| `proposal.html`（或 `evidence.html`） | `html2docx.py` | 同名 `.docx`（标题样式、表格、内嵌图片） |
| 上述 `.docx` | **LibreOffice headless** | 同名 `.pdf` |
| `deck_data_track2.json` | `build_deck_track2.ps1`（WPS Presentation COM） | 答辩材料 `.pptx` + 导出 `.pdf`，并按页导出 `deck_png/slideNN.png` |

## 用法

```powershell
# 0) 底稿 Markdown → A4 版式 HTML（新赛道请走这条，别手写 HTML）
python scripts/aic/md2proposal.py "docs/aic/01_AI+学科交叉_技术方案_匿名版.md" `
    "docs/aic/提交材料-学科交叉/proposal.html" `
    --kicker "AIC 第八届算法创新赛 · 赛题5「AI+学科交叉」" --subtitle "技术方案（匿名版）" `
    --meta "作品名称=禾衡·粮食生产气候风险归因决策系统" --meta "参赛赛题=AI+学科交叉" --meta "材料日期=2026 年 10 月" `
    --strip-src-prefix "提交材料-学科交叉/"

# 1) HTML → DOCX
python scripts/aic/html2docx.py "docs/aic/提交材料-学科交叉/proposal.html" "docs/aic/提交材料-学科交叉/禾衡-...-技术方案.docx"

# 2) DOCX → PDF（LibreOffice headless）
& "D:\LibreOffice\program\soffice.com" --headless --norestore `
    "-env:UserInstallation=file:///D:/libreoffice-profile" --convert-to pdf --outdir . "<docx 绝对路径>"

# 3) 答辩 PPTX + PDF
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/aic/build_deck_track2.ps1
```

> ⚠️ **WPS 的 COM 组件在本机已不可用**（`New-Object -ComObject KWPS.Application` 报
> `没有注册类 0x80040154`），所以上表与第 2 步改用 LibreOffice headless 转 PDF。
> 第 3 步的 `build_deck_track2.ps1` 依赖 WPS Presentation COM，**目前同样跑不通**；
> 要出答辩 PPT 需要另找路径（Office 的 PowerPoint COM 或直接用 pptx 库生成）。

## 底稿写法约定（md2proposal.py）

- 一级标题 `# …` 只作封面标题；`## ` 章在导出时自动分页；
- 写给自己的话放 `> 〔作者备注〕…`（含紧随的引用续行），**导出时整块剥离**，不会进 PDF；
- 整段一张图用 `![图 1　说明文字](提交材料-XXX/img/M00.png)`，导出时自动包成 `<figure>` + 图注；
  路径写"相对底稿目录"的形式，配合 `--strip-src-prefix` 让 HTML 里的相对路径也成立。

## 幻灯片定义

`deck_data_track2.json` 里 `outPptx` / `outPdf` / `imageDir` 为绝对路径（本机工作目录布局），
`slides[]` 每项的 `kind` 决定版式，支持：`cover`、`cols3`、`cols4`、`table`、`bands`、
`steps8`、`twocol`、`engine`、`image`、`mix`。改内容只改 JSON，不要改版式代码。

## 注意

- 依赖本机安装 WPS 或 Office（COM 组件 `KWPS.Application` / `KWPP.Application`）；
- 幻灯片与文档中的数字必须与 `docs/aic/提交材料-赛题二/` 内的定稿一致，
  叙事口径以 `docs/AGENT_BRIEFING.md` §4 为准（不得回滚到"跨省高精度预测"）；
- 对外材料导出后仍需执行 `docs/aic/00_参赛方案总览与脱敏清单.md` §3.3 的匿名化 grep。
