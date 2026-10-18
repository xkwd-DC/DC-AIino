#requires -Version 5.1
<#
.SYNOPSIS
  DC 粮食风险系统 · 打包成免安装绿色便携包（比赛现场拷贝即用）

.DESCRIPTION
  产出一个自包含目录：拷到任何 Windows 10/11 x64 机器（U 盘 / 移动硬盘 / 微信压缩包），
  双击 start_dc.cmd 就能用浏览器打开系统。目标机器**不需要**装 Python、不需要 npm、
  不需要联网、不需要本机任何 Python 环境。

  包里带了什么：
    runtime\        绿色 Python 3.12（从 backend\.venv 的 base 解释器 + site-packages 拼出来的）
    backend\        Flask 应用 + 数据库(grain.db / county.db) + 模型 artifact + ChromaDB 索引
    frontend\dist\  已构建前端（含县级地图 counties_10provinces.json）
    docs\           RAG 知识库的原始文档
    start_dc.cmd    双击入口（ASCII，避免 cmd 中文编码坑）
    start_dc.ps1    真正逻辑（UTF-8 with BOM，中文提示走这里）

  为什么是"拷解释器"而不是"重装依赖"：
    backend\.venv 是 venv 布局，Scripts\python.exe 靠 pyvenv.cfg 指回本机 base 解释器，
    换台机器必然找不到 —— 所以把 base 解释器目录搬进包，再把 site-packages 并进去，
    得到的是一个路径无关的标准安装布局（python.exe 从自身所在目录找 Lib）。

.EXAMPLE
  # 默认：完整功能包（含 torch，M06 知识助手可用），约 5.9 GB
  powershell -ExecutionPolicy Bypass -File deploy\make_portable.ps1 -Verify

  # 精简版：去掉 torch 系，省 ~2.8 GB，M06 知识助手不可用（其余模块不受影响）
  powershell -ExecutionPolicy Bypass -File deploy\make_portable.ps1 -Slim

  # 连 BGE-M3 本地模型一起带（+2.2 GB，现场不必联网下模型）
  powershell -ExecutionPolicy Bypass -File deploy\make_portable.ps1 -WithRagModels

  # 要发给别人：默认已抹掉 .env 里的 DEEPSEEK_API_KEY；自己现场演示想用 API 就加 -IncludeSecrets
  powershell -ExecutionPolicy Bypass -File deploy\make_portable.ps1 -IncludeSecrets

.NOTES
  - 打包**必须**在本机 venv 完好时做（backend\.venv\Lib\site-packages 是唯一依赖来源）。
  - 包内不含 npm / node_modules：前端用已构建的 frontend\dist，现场不需要重新构建。
  - 本脚本自身必须是 UTF-8 with BOM（Windows PowerShell 5.1 对无 BOM 的中文脚本按 GBK 解析）。
#>
[CmdletBinding()]
param(
    # 产物目录（整个目录可以整块拷走）
    # 注意默认用纯 ASCII 名：ChromaDB 的 Rust 层在非 ASCII 路径下读不了 HNSW 索引
    # （M06 知识助手会失效）。要中文名就自己在 zip / 外层文件夹上做，别改这一层。
    [string]$OutDir = 'D:\DC\portable\DC-GrainRisk-System',
    # 去掉 torch / transformers / chromadb 等 RAG 依赖，省 ~2.8GB；M06 知识助手随之不可用
    [switch]$Slim,
    # 把 BGE-M3 本地嵌入模型一起打进包（+2.2GB），现场无需联网下载
    [switch]$WithRagModels,
    # 保留 .env 里的 DEEPSEEK_API_KEY（默认抹掉，防止包外发时泄露 key）
    [switch]$IncludeSecrets,
    # 不打包 docs\（RAG 文档源，105MB）
    [switch]$SkipDocs,
    # 打包后打成一个 zip（用 tar.exe，绕开 Compress-Archive 的 2GB 上限）
    [switch]$Zip,
    # 打包后立刻用包内 Python 起一次服务探活（强烈建议）
    [switch]$Verify,
    # 复用已有的 runtime\（依赖没变时重打包省掉 5GB 拷贝；仅配合 -Force 生效）
    [switch]$ReuseRuntime,
    # 产物目录已存在时先清掉旧的子目录再打
    [switch]$Force
)

$ErrorActionPreference = 'Stop'

$Root     = Split-Path -Parent $PSScriptRoot
$Backend  = Join-Path $Root 'backend'
$Venv     = Join-Path $Backend '.venv'
$SitePkgs = Join-Path $Venv 'Lib\site-packages'
$Frontend = Join-Path $Root 'frontend'
$Docs     = Join-Path $Root 'docs'

function Step([string]$m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Ok([string]$m)   { Write-Host "    $m" -ForegroundColor Green }
function Warn([string]$m) { Write-Host "    $m" -ForegroundColor Yellow }
function Die([string]$m)  { Write-Host "[FATAL] $m" -ForegroundColor Red; exit 1 }

function Invoke-Robocopy {
    param(
        [Parameter(Mandatory)][string]$Src,
        [Parameter(Mandatory)][string]$Dst,
        [string[]]$ExcludeDirs = @(),
        [string[]]$ExcludeFiles = @()
    )
    # /E 子目录含空目录；/MT 多线程；/NFL /NDL /NJH /NJS /NP 静音
    # 注意：不加 /SL —— 默认行为是跟随符号链接把目标内容复制成真实文件，
    # 这正是 HF 缓存（snapshots 里全是 symlink）搬进包里想要的效果。
    $a = @($Src, $Dst, '/E', '/MT:16', '/NFL', '/NDL', '/NJH', '/NJS', '/NP', '/R:1', '/W:1')
    if ($ExcludeDirs.Count)  { $a += '/XD'; $a += $ExcludeDirs }
    if ($ExcludeFiles.Count) { $a += '/XF'; $a += $ExcludeFiles }
    & robocopy.exe @a | Out-Null
    if ($LASTEXITCODE -ge 8) { Die "robocopy 失败（退出码 $LASTEXITCODE）：$Src -> $Dst" }
}

function Get-DirSize([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return 0 }
    return (Get-ChildItem -LiteralPath $Path -Recurse -File -ErrorAction SilentlyContinue |
            Measure-Object Length -Sum).Sum
}

function Format-Size([double]$Bytes) {
    if ($Bytes -ge 1GB) { return ('{0:N2} GB' -f ($Bytes / 1GB)) }
    return ('{0:N1} MB' -f ($Bytes / 1MB))
}

# ────────────────────────────────────────────────────────────────
# 0) 源侧预检
# ────────────────────────────────────────────────────────────────
Step '源侧预检'

$VenvPy = Join-Path $Venv 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $VenvPy)) { Die "缺后端虚拟环境：$VenvPy" }
if (-not (Test-Path -LiteralPath $SitePkgs)) { Die "缺 site-packages：$SitePkgs" }
Ok "虚拟环境   : $Venv"

# base 解释器位置从 pyvenv.cfg 的 home 行读（本机这份是 Codex 运行时自带的 Python 3.12.13，
# 所以备份解释器目录进包还有额外好处：将来 Codex 升级把那个目录换掉，便携包里的照样能用）
$cfgPath = Join-Path $Venv 'pyvenv.cfg'
if (-not (Test-Path -LiteralPath $cfgPath)) { Die "缺 pyvenv.cfg：$cfgPath" }
$homeLine = Get-Content -LiteralPath $cfgPath | Where-Object { $_ -match '^\s*home\s*=' } | Select-Object -First 1
if (-not $homeLine) { Die 'pyvenv.cfg 里没有 home 行，无法定位 base 解释器' }
$BasePy = (($homeLine -split '=', 2)[1]).Trim()
$BasePyExe = Join-Path $BasePy 'python.exe'
if (-not (Test-Path -LiteralPath $BasePyExe)) { Die "base 解释器不存在：$BasePyExe" }
Ok "base Python: $BasePy"

$distIndex = Join-Path $Frontend 'dist\index.html'
if (-not (Test-Path -LiteralPath $distIndex)) {
    Die '缺 frontend\dist\index.html —— 先在 frontend 下跑 npm ci && npm run build'
}
Ok '前端产物   : frontend\dist'

foreach ($need in @('data\grain.db', 'data\county.db', 'data\provinces_baseline.json', 'models', 'chroma_db', 'app.py')) {
    $p = Join-Path $Backend $need
    if (-not (Test-Path -LiteralPath $p)) { Warn "缺 $need（包里会少这一块能力，建议先跑 deploy\serve_local.ps1 补齐）" }
}

if ($OutDir -match '[^\x00-\x7F]') {
    Warn "产物路径含非 ASCII 字符：$OutDir"
    Warn 'ChromaDB 在非 ASCII 路径下加载不了 HNSW 索引（M06 知识助手会失效）。'
    Warn '启动器有"向量库同步到 TEMP"的兜底，但别赌现场环境 —— 建议换纯英文目录名。'
}

# ────────────────────────────────────────────────────────────────
# 1) 目标目录准备
# ────────────────────────────────────────────────────────────────
Step "准备产物目录 $OutDir"

if (Test-Path -LiteralPath $OutDir) {
    if (-not $Force) {
        Die "产物目录已存在：$OutDir（加 -Force 覆盖重打）"
    }
    $outFull = (Resolve-Path -LiteralPath $OutDir).Path
    # 只清这个包自己的几个子目录，绝不递归删 OutDir 本身以外的任何东西
    foreach ($sub in @('runtime', 'backend', 'frontend', 'docs', 'hf-cache', 'start_dc.ps1', 'start_dc.cmd', 'stop_dc.cmd', '使用说明.txt')) {
        $target = Join-Path $outFull $sub
        if (Test-Path -LiteralPath $target) {
            $resolved = (Resolve-Path -LiteralPath $target).Path
            if (-not $resolved.StartsWith($outFull, [StringComparison]::OrdinalIgnoreCase)) {
                Die "拒绝删除包目录之外的东西：$resolved"
            }
            if ($ReuseRuntime -and $sub -eq 'runtime') { Ok '保留已有 runtime\（-ReuseRuntime）'; continue }
            Remove-Item -LiteralPath $resolved -Recurse -Force
        }
    }
    Ok '已清掉旧产物'
}
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$OutRuntime = Join-Path $OutDir 'runtime'
$OutBackend = Join-Path $OutDir 'backend'
$OutFront   = Join-Path $OutDir 'frontend'

$sw = [Diagnostics.Stopwatch]::StartNew()

# ────────────────────────────────────────────────────────────────
# 2) 绿色 Python 运行时
# ────────────────────────────────────────────────────────────────
$outPy = Join-Path $OutRuntime 'python.exe'
if ($ReuseRuntime -and (Test-Path -LiteralPath $outPy)) {
    Step '复用已有 runtime\（不重拷依赖）'
    Ok ('runtime          ' + (Format-Size (Get-DirSize $OutRuntime)))
} else {
    Step '组装绿色 Python 运行时（base 解释器 + venv 的 site-packages）'

    # base 解释器：排除它自己的 site-packages（那是 Codex 的依赖，混进来只会让包变胖）
    Invoke-Robocopy -Src $BasePy -Dst $OutRuntime -ExcludeDirs @(
        (Join-Path $BasePy 'Lib\site-packages'),
        (Join-Path $BasePy 'Lib\test'),
        (Join-Path $BasePy 'Lib\idlelib'),
        (Join-Path $BasePy 'Lib\lib2to3'),
        (Join-Path $BasePy 'Lib\turtledemo'),
        (Join-Path $BasePy 'Lib\ensurepip'),
        (Join-Path $BasePy 'include'),
        (Join-Path $BasePy 'libs'),
        (Join-Path $BasePy 'Scripts'),
        '__pycache__'
    )
    Ok ('解释器 + 标准库  ' + (Format-Size (Get-DirSize $OutRuntime)))

    # 依赖：venv 的 site-packages 整体并入（路径无关，标准 sys.path 就能找到）
    $excludePkgs = @('__pycache__')
    if ($Slim) {
        $excludePkgs += @(
            'torch', 'torchgen', 'torch-*', 'functorch',
            'transformers', 'sentence_transformers', 'FlagEmbedding', 'datasets',
            'chromadb', 'chromadb_rust_bindings', 'onnxruntime', 'llvmlite', 'numba',
            'tokenizers', 'safetensors', 'huggingface_hub', 'sentencepiece'
        )
    }
    $spDest = Join-Path $OutRuntime 'Lib\site-packages'
    Invoke-Robocopy -Src $SitePkgs -Dst $spDest -ExcludeDirs $excludePkgs
    Ok ('site-packages    ' + (Format-Size (Get-DirSize $spDest)))
}

if (-not (Test-Path -LiteralPath $outPy)) { Die "运行时组装失败，缺 $outPy" }

# 组装完立刻验一次 import —— 这一步不通过，后面全是白搭。
# 自检脚本写临时文件而不是 python -c：PowerShell 5.1 给原生命令传长参数里的引号/空格很难伺候。
# 必须复现 .env 里的 USE_TF=0 / TRANSFORMERS_NO_TF=1，否则 transformers 会去走 TF 集成分支
# 并因为本机是 Keras 3 而报 "install tf-keras"（那是不存在的运行时问题）。
$extraMods = if ($Slim) { '' } else { "    'torch', 'sentence_transformers', 'chromadb'," }
$checkCode = @"
import os
os.environ.setdefault('USE_TF', '0')
os.environ.setdefault('TRANSFORMERS_NO_TF', '1')
os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '3')
mods = [
$extraMods
    'flask', 'waitress', 'numpy', 'pandas', 'xgboost', 'sklearn', 'tensorflow', 'shap', 'dotenv', 'pyarrow',
]
for m in mods:
    __import__(m)
print('core-ok')
"@
$checkFile = Join-Path $env:TEMP 'dc-portable-import-check.py'
[IO.File]::WriteAllText($checkFile, $checkCode, (New-Object Text.UTF8Encoding $false))
# 原生命令往 stderr 打字（tensorflow 的 oneDNN 提示就是）在 PowerShell 5.1 里会变成
# NativeCommandError；$ErrorActionPreference='Stop' 下会直接终止脚本。这里临时降级。
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$importCheck = (& $outPy $checkFile 2>&1 | Out-String)
$importCode = $LASTEXITCODE
$ErrorActionPreference = $prevEAP
if ($importCode -ne 0) {
    Write-Host $importCheck
    Die '包内解释器 import 自检失败（看上面的报错）'
}
Ok '包内解释器 import 自检通过'

# ────────────────────────────────────────────────────────────────
# 3) 应用代码 + 数据
# ────────────────────────────────────────────────────────────────
Step '复制后端（代码 + 数据库 + 模型 artifact + 向量索引）'

# backend\chroma_db 和 data\*.db 是"活库"：本机服务正在运行时它们是打开状态，
# 拷出来可能是坏副本（实测 dc_knowledge 的 HNSW 索引拷后加载失败：
#  "Error loading hnsw index"）。所以先探一下 8000 上有没有实例在跑。
$live = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($live) {
    Warn "检测到本机 8000 上有服务在跑（PID $(($live | Select-Object -First 1).OwningProcess)）"
    Warn '向量索引/数据库处于打开状态，拷出来的副本可能损坏。强烈建议先停：'
    Warn '    powershell -ExecutionPolicy Bypass -File deploy\serve_local.ps1 -Stop'
}

Invoke-Robocopy -Src $Backend -Dst $OutBackend -ExcludeDirs @(
    (Join-Path $Backend '.venv'),
    (Join-Path $Backend '__pycache__'),
    (Join-Path $Backend '.pytest_cache'),
    (Join-Path $Backend 'tests'),
    (Join-Path $Backend 'eval'),
    (Join-Path $Backend 'chroma_db.bak-20260917'),
    '__pycache__'
)
Ok ('backend          ' + (Format-Size (Get-DirSize $OutBackend)))

Step '复制前端 dist'
Invoke-Robocopy -Src (Join-Path $Frontend 'dist') -Dst (Join-Path $OutFront 'dist')
Ok ('frontend\dist    ' + (Format-Size (Get-DirSize (Join-Path $OutFront 'dist'))))

if (-not $SkipDocs -and (Test-Path -LiteralPath $Docs)) {
    Step '复制 docs（RAG 文档源）'
    # docs 必须整份带上：watcher 启动时比对 chroma_db\file_hashes.json，少任何一个被索引过的
    # 文件都会被判成"已删除"，对应切片直接从向量库里清掉（实测漏拷 docs\papers\*.md → 少 124 条）。
    Invoke-Robocopy -Src $Docs -Dst (Join-Path $OutDir 'docs')
    Ok ('docs             ' + (Format-Size (Get-DirSize (Join-Path $OutDir 'docs'))))
}

# ────────────────────────────────────────────────────────────────
# 4) 可选：BGE-M3 本地嵌入模型
# ────────────────────────────────────────────────────────────────
if ($WithRagModels) {
    Step '复制 BGE-M3 本地模型（HF 缓存布局）'
    $hfSrcRoot = 'D:\DC\.hf-cache'
    $srcHub = Join-Path $hfSrcRoot 'hub'
    $srcM3  = Join-Path $srcHub 'models--BAAI--bge-m3'
    if (-not (Test-Path -LiteralPath $srcM3)) {
        Warn "本机没有 BGE-M3 缓存（$srcM3），跳过。现场第一次问答会尝试联网下载，可能失败。"
    } else {
        $dstHub = Join-Path $OutDir 'hf-cache\hub'
        # refs\main 记录当前 revision，只拷那个 snapshot，省掉另一份 2GB 权重
        $revFile = Join-Path $srcM3 'refs\main'
        $rev = if (Test-Path -LiteralPath $revFile) { (Get-Content -LiteralPath $revFile -Raw).Trim() } else { $null }
        if (-not $rev) { Die "读不到 $revFile（HF 缓存的 revision 记录）" }
        Ok "revision: $rev"
        Invoke-Robocopy -Src (Join-Path $srcM3 'refs') -Dst (Join-Path $dstHub 'models--BAAI--bge-m3\refs')
        Invoke-Robocopy -Src (Join-Path $srcM3 "snapshots\$rev") -Dst (Join-Path $dstHub "models--BAAI--bge-m3\snapshots\$rev")
        # blobs 里的真实内容（snapshots 里只是符号链接，目标必须一起带，否则 HF 校验不过）
        $snapDir = Join-Path $srcM3 "snapshots\$rev"
        $blobNames = @()
        Get-ChildItem -LiteralPath $snapDir -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
            if ($_.LinkType -and $_.Target) {
                # Target 形如 ..\..\blobs\<name>
                $blobNames += ($_.Target -replace '^.*[\\/]', '')
            }
        }
        $blobNames = $blobNames | Sort-Object -Unique
        Ok ("需要 $($blobNames.Count) 个 blob")
        $blobDest = Join-Path $dstHub 'models--BAAI--bge-m3\blobs'
        New-Item -ItemType Directory -Force -Path $blobDest | Out-Null
        foreach ($b in $blobNames) {
            $bf = Join-Path (Join-Path $srcM3 'blobs') $b
            if (Test-Path -LiteralPath $bf) { Copy-Item -LiteralPath $bf -Destination (Join-Path $blobDest $b) -Force }
        }
        Ok ('hf-cache         ' + (Format-Size (Get-DirSize (Join-Path $OutDir 'hf-cache'))))
    }
}

# ────────────────────────────────────────────────────────────────
# 5) .env（默认抹掉 API key）
# ────────────────────────────────────────────────────────────────
Step '生成包内 backend\.env'
$envSrc = Join-Path $Backend '.env'
if (Test-Path -LiteralPath $envSrc) {
    $lines = Get-Content -LiteralPath $envSrc -Encoding UTF8
    if (-not $IncludeSecrets) {
        $lines = $lines | ForEach-Object {
            if ($_ -match '^\s*DEEPSEEK_API_KEY\s*=') { 'DEEPSEEK_API_KEY=' } else { $_ }
        }
    }
    # python-dotenv 读 UTF-8 无 BOM；带 BOM 会把第一个 key 变成 \ufeffKEY 而静默失效
    [IO.File]::WriteAllText((Join-Path $OutBackend '.env'), (($lines -join "`r`n") + "`r`n"), (New-Object Text.UTF8Encoding $false))
    if ($IncludeSecrets) { Warn '已保留 DEEPSEEK_API_KEY —— 这个包别外发/别上传网盘' }
    else { Ok 'DEEPSEEK_API_KEY 已抹空（现场要用知识助手问答就自己填回）' }
} else {
    Warn "源 .env 不存在，包里不会有 .env（M06 需要它）"
}

# ────────────────────────────────────────────────────────────────
# 6) 启动器 + 说明
# ────────────────────────────────────────────────────────────────
Step '写启动器与使用说明'

$launcher = @'
<#
  DC 粮食风险系统 · 便携版启动器

  常规用法（现场演示）：
      双击 start_dc.cmd            → 后台起服务 + 自动用默认浏览器打开

  手动用法：
      powershell -ExecutionPolicy Bypass -File start_dc.ps1 -Port 8081
      powershell -ExecutionPolicy Bypass -File start_dc.ps1 -Lan        # 同一 WiFi 下手机/平板可看
      powershell -ExecutionPolicy Bypass -File start_dc.ps1 -Foreground # 前台跑，Ctrl+C 停（排查用）
      powershell -ExecutionPolicy Bypass -File start_dc.ps1 -Status
      powershell -ExecutionPolicy Bypass -File start_dc.ps1 -Stop

  运行态（PID / 日志）写在 %TEMP%\dc-grainrisk\：便携包可能放在写保护的 U 盘上，
  所以不往包目录里写。
#>
[CmdletBinding()]
param(
    [int]$Port = 8000,
    [switch]$Lan,
    [switch]$Stop,
    [switch]$Status,
    [switch]$Foreground,
    [switch]$NoBrowser,
    [int]$HealthTimeoutSec = 240
)

$ErrorActionPreference = 'Stop'
$Root    = $PSScriptRoot
$Py      = Join-Path $Root 'runtime\python.exe'
$Backend = Join-Path $Root 'backend'
$RunDir  = Join-Path $env:TEMP 'dc-grainrisk'
$PidFile = Join-Path $RunDir "server-$Port.pid"
$OutLog  = Join-Path $RunDir "server-$Port.out.log"
$ErrLog  = Join-Path $RunDir "server-$Port.err.log"
$NullIn  = Join-Path $RunDir "stdin-$Port.empty"
$ProbeHost = '127.0.0.1'
$BindHost  = if ($Lan) { '0.0.0.0' } else { '127.0.0.1' }

function Step([string]$m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Ok([string]$m)   { Write-Host "    $m" -ForegroundColor Green }
function Warn([string]$m) { Write-Host "    $m" -ForegroundColor Yellow }

function Get-ServerPid {
    if (-not (Test-Path -LiteralPath $PidFile)) { return $null }
    $raw = (Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if (-not $raw) { return $null }
    $procId = 0
    if (-not [int]::TryParse($raw.Trim(), [ref]$procId)) { return $null }
    return $procId
}

function Test-Health([int]$TimeoutSec) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri "http://${ProbeHost}:$Port/api/health" -TimeoutSec 3 -UseBasicParsing
            if ($r.StatusCode -eq 200) { return $true }
        } catch { }
        Start-Sleep -Milliseconds 700
    }
    return $false
}

function Stop-ProcessTree([int]$ProcId, [int]$ListenPort) {
    # 不要写 2>&1 ：原生命令的 stderr 被重定向后会变成 ErrorRecord，Stop 模式下会误杀脚本
    if (Get-Process -Id $ProcId -ErrorAction SilentlyContinue) { & taskkill.exe /PID $ProcId /T /F | Out-Null }
    Start-Sleep -Milliseconds 300
    $still = Get-NetTCPConnection -LocalPort $ListenPort -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $still) { Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue }
}

if ($Stop) {
    $procId = Get-ServerPid
    if ($null -eq $procId) { Warn '没有记录在案的实例'; exit 0 }
    Step "停止 PID $procId（含子进程）"
    Stop-ProcessTree $procId -ListenPort $Port
    Remove-Item -LiteralPath $PidFile -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500
    if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { Warn "端口 $Port 仍被占用"; exit 1 }
    Ok "已停止，端口 $Port 已释放"
    exit 0
}

if ($Status) {
    $procId = Get-ServerPid
    Write-Host "PID  : $(if ($null -ne $procId) { $procId } else { '(未记录)' })"
    Write-Host "探活 : $(if (Test-Health 5) { 'OK' } else { '无响应' })"
    Write-Host "地址 : http://${ProbeHost}:$Port"
    exit 0
}

if (-not (Test-Path -LiteralPath $Py)) { Write-Host "[FATAL] 缺 runtime\python.exe，包不完整" -ForegroundColor Red; exit 1 }
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

# 环境变量：必须在 python 启动前设，load_dotenv 默认不覆盖已存在的环境变量，
# 所以这里设的值会盖掉 .env 里那些指向打包机器（D:\DC\...）的绝对路径。
# 清掉目标机器可能存在的 PYTHONHOME / PYTHONPATH —— 它们会把包内解释器带偏。
$env:PYTHONHOME = ''
$env:PYTHONPATH = ''
$env:PYTHONUTF8 = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
$hfCache = Join-Path $Root 'hf-cache'
if (Test-Path -LiteralPath $hfCache) {
    $env:HF_HOME = $hfCache
    $env:HUGGINGFACE_HUB_CACHE = Join-Path $hfCache 'hub'
    $env:HF_HUB_OFFLINE = '1'
}

# 包路径含非 ASCII（比如有人把文件夹改名成中文）时，ChromaDB 的 Rust 层加载不了
# HNSW 索引，M06 检索会直接报 "Error loading hnsw index"。
# 兜底：把向量库同步一份到 ASCII 的 %TEMP% 目录，再用 DC_CHROMA_DIR 指过去
# （后端读取点见 backend/rag/config.py）。
if ($Root -match '[^\x00-\x7F]') {
    $srcChroma = Join-Path $Backend 'chroma_db'
    $tmpChroma = Join-Path $RunDir 'chroma_db'
    if (Test-Path -LiteralPath $srcChroma) {
        Warn '包路径含非 ASCII 字符 → 向量库同步到 ASCII 临时目录（ChromaDB 读不了非 ASCII 路径下的 HNSW 索引）'
        # robocopy /E 是增量的，第二次起基本瞬间返回
        & robocopy.exe $srcChroma $tmpChroma /E /NFL /NDL /NJH /NJS /NP /R:1 /W:1 | Out-Null
        $env:DC_CHROMA_DIR = $tmpChroma
    }
}

$occupied = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($occupied) {
    $known = Get-ServerPid
    if ($known -and (Get-Process -Id $known -ErrorAction SilentlyContinue)) {
        Warn "本包的服务已在 $Port 上跑着"
        if (-not $NoBrowser) { Start-Process "http://${ProbeHost}:$Port" | Out-Null }
        exit 0
    }
    $owner = ($occupied | Select-Object -First 1).OwningProcess
    Write-Host "[FATAL] 端口 $Port 被别的程序占用（PID $owner），换端口： start_dc.ps1 -Port 8081" -ForegroundColor Red
    exit 1
}

if ($Foreground) {
    Step "前台启动（${BindHost}:$Port，Ctrl+C 停止）"
    Write-Host "    地址 http://${ProbeHost}:$Port"
    Push-Location $Backend
    try { & $Py -m waitress "--host=$BindHost" "--port=$Port" '--threads=8' '--ident=dc-grainrisk' 'app:app' }
    finally { Pop-Location }
    exit $LASTEXITCODE
}

Step "后台启动（${BindHost}:$Port）"
if (-not (Test-Path -LiteralPath $NullIn)) {
    try { New-Item -ItemType File -Path $NullIn -ErrorAction Stop | Out-Null } catch { $NullIn = 'NUL' }
}
$launchedAt = Get-Date
# 三个标准流全部重定向：只重定向 stdout/stderr 时子进程会继承父 shell 的 stdin 管道句柄，
# 调用方（cmd / 外层脚本）会一直等管道 EOF，表现为"命令不返回"。
$proc = Start-Process -FilePath $Py `
    -ArgumentList @('-m', 'waitress', "--host=$BindHost", "--port=$Port", '--threads=8', '--ident=dc-grainrisk', 'app:app') `
    -WorkingDirectory $Backend -WindowStyle Hidden `
    -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog -RedirectStandardInput $NullIn -PassThru
Set-Content -LiteralPath $PidFile -Value $proc.Id -Encoding ascii
Ok "PID $($proc.Id)（日志 $ErrLog）"

Step "探活（最多 $HealthTimeoutSec 秒，首次冷启动要加载 tensorflow，慢是正常的）"
if (-not (Test-Health $HealthTimeoutSec)) {
    Write-Host '[FATAL] 服务没起来，错误日志最后 25 行：' -ForegroundColor Red
    if (Test-Path -LiteralPath $ErrLog) { Get-Content -LiteralPath $ErrLog -Tail 25 | ForEach-Object { "    $_" } }
    exit 1
}

# 端口上可能是更早的实例在作答，用启动时间兜一道
$listener = (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess
$listenerStart = if ($listener) { (Get-Process -Id $listener -ErrorAction SilentlyContinue).StartTime } else { $null }
if ($listenerStart -and $listenerStart -lt $launchedAt.AddSeconds(-2)) {
    Write-Host "[FATAL] 端口 $Port 是更早的实例（PID $listener）在提供，本次启动没接管端口" -ForegroundColor Red
    if (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue) { & taskkill.exe /PID $proc.Id /T /F | Out-Null }
    exit 1
}
Ok '/api/health OK'

Write-Host ''
Write-Host '系统已启动，浏览器打开：' -ForegroundColor Green
Write-Host "    http://${ProbeHost}:$Port" -ForegroundColor Green
if ($Lan) {
    Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
        ForEach-Object {
            $alias = (Get-NetAdapter -InterfaceIndex $_.InterfaceIndex -ErrorAction SilentlyContinue).Name
            if ($alias -and $alias -notmatch 'vEthernet|VMware|VirtualBox|Hyper-V|Loopback|Bluetooth|Npcap|TAP|WSL') {
                Write-Host "    http://$($_.IP):$Port  （局域网 · $alias）" -ForegroundColor Green
            }
        }
}
Write-Host ''
Write-Host '    停止： start_dc.ps1 -Stop'

if (-not $NoBrowser) {
    try { Start-Process "http://${ProbeHost}:$Port" | Out-Null } catch { Warn "浏览器没打开，手动访问 http://${ProbeHost}:$Port" }
}
'@

$launcherPath = Join-Path $OutDir 'start_dc.ps1'
# UTF-8 with BOM：Windows PowerShell 5.1 对无 BOM 的中文脚本按系统 ANSI 代码页解析，会报一堆语法错误
[IO.File]::WriteAllText($launcherPath, $launcher, (New-Object Text.UTF8Encoding $true))

$cmd = @'
@echo off
rem ---------------------------------------------------------------------------
rem  DC grain-risk system - portable launcher.  DOUBLE-CLICK THIS FILE.
rem
rem  ASCII ONLY on purpose: cmd.exe parses .bat/.cmd with the ACTIVE code page,
rem  so UTF-8 Chinese comments turn into mojibake commands. Chinese messages
rem  are printed by start_dc.ps1 (UTF-8 with BOM) instead.
rem ---------------------------------------------------------------------------
chcp 65001 >nul
title DC grain-risk system
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_dc.ps1"
echo.
echo The service keeps running in the background - closing this window will NOT stop it.
echo Stop it:  powershell -ExecutionPolicy Bypass -File "%~dp0start_dc.ps1" -Stop
echo.
pause
'@
[IO.File]::WriteAllText((Join-Path $OutDir 'start_dc.cmd'), $cmd, (New-Object Text.UTF8Encoding $false))

$stopCmd = @'
@echo off
chcp 65001 >nul
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_dc.ps1" -Stop
pause
'@
[IO.File]::WriteAllText((Join-Path $OutDir 'stop_dc.cmd'), $stopCmd, (New-Object Text.UTF8Encoding $false))

$readme = @"
DC 粮食风险系统 · 便携版
========================

怎么用（现场演示）
------------------
1. 把整个文件夹拷到目标电脑（U 盘 / 移动硬盘 / 直接拖过去）。
2. 双击 start_dc.cmd。
3. 等 10~60 秒（第一次启动要加载 tensorflow，慢是正常的），浏览器会自动打开系统。
   没自动打开就手动访问： http://127.0.0.1:8000
4. 结束：关掉浏览器即可；要彻底停服务就双击 stop_dc.cmd。

目标电脑不需要装 Python / Node / npm，也不需要联网。
系统是"本机跑一个服务 + 浏览器看"，所以窗口别全关（服务在后台，关掉黑色窗口不影响）。

换个端口 / 手机同看
------------------
    powershell -ExecutionPolicy Bypass -File start_dc.ps1 -Port 8081
    powershell -ExecutionPolicy Bypass -File start_dc.ps1 -Lan      （同一 WiFi 下手机可看，会打印地址）

能看什么
--------
    M00 系统总览 / M01 省级风险地图 / M02~M05 归因·情景·监测 / M07 县级风险地图
    M06 知识助手：需要 DEEPSEEK_API_KEY（见下）

关于 M06 知识助手（唯一需要网络的模块）
------------------------------------
* 检索用的嵌入模型 BGE-M3 是本地跑的；但"生成回答"要调 DeepSeek API，所以现场要有网。
* backend\.env 里 DEEPSEEK_API_KEY 默认被抹空（防止这个包发出去时泄露）。自己演示时填上即可：
      用记事本打开 backend\.env，把 DEEPSEEK_API_KEY= 后面补上 key，保存。
* 如果打包时带了 hf-cache\（BGE-M3 本地模型），现场即使没网也能做"检索"，只是不生成回答。

关于文件夹名（踩过的坑）
----------------------
包所在路径必须是纯英文/数字：知识助手用的 ChromaDB 在中文路径下读不了向量索引
（报 "Error loading hnsw index"），M06 检索会失效。所以默认目录名是 DC-GrainRisk-System。
启动器检测到中文路径会自动把向量库同步到 %TEMP% 顶一下，但每次启动会多几秒 ——
演示前尽量把包放在英文路径下（例如 D:\demo\DC-GrainRisk-System）。

出问题了看哪里
--------------
* 日志： %TEMP%\dc-grainrisk\server-8000.err.log（把最新的错误贴给 Codex 看）
* 端口被占：换端口  -Port 8081
* 缺 VC++ 运行库（报错含 VCRUNTIME140.dll / msvcp140.dll）：
  装一次微软官方 "Visual C++ Redistributable 2015-2022 x64" 即可。

包里带了什么
------------
    runtime\        绿色 Python 3.12 + 全部依赖（不需要目标机器装 Python）
    backend\        Flask 后端 + 数据库 + 模型 + 向量索引
    frontend\dist\  已构建前端
    docs\           RAG 文档源
    hf-cache\       （可选）BGE-M3 本地模型

这个包是从 D:\DC\DC-AIino 打包出来的快照，改了源工程要重新打一次：
    powershell -ExecutionPolicy Bypass -File deploy\make_portable.ps1 -Force -Verify
"@
[IO.File]::WriteAllText((Join-Path $OutDir '使用说明.txt'), $readme, (New-Object Text.UTF8Encoding $true))
Ok 'start_dc.cmd / stop_dc.cmd / start_dc.ps1 / 使用说明.txt'

# ────────────────────────────────────────────────────────────────
# 7) 可选：探活验证（用包里的 Python，和现场完全同一条路径）
# ────────────────────────────────────────────────────────────────
if ($Verify) {
    Step '用包内 Python 起服务探活（模拟现场运行）'
    $vPort = 8123
    $vOut = Join-Path $env:TEMP 'dc-portable-verify-server.out.log'
    $vErr = Join-Path $env:TEMP 'dc-portable-verify-server.err.log'
    $vIn  = Join-Path $env:TEMP 'dc-portable-verify-stdin.empty'
    if (-not (Test-Path -LiteralPath $vIn)) { New-Item -ItemType File -Path $vIn | Out-Null }

    # 现场双击走的是 start_dc.ps1，至少做一次语法自检
    $vp = Join-Path $OutDir 'start_dc.ps1'
    $perr = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($vp, [ref]$null, [ref]$perr)
    if ($perr -and $perr.Count) {
        $perr | Select-Object -First 5 | ForEach-Object { Warn "start_dc.ps1 第 $($_.Extent.StartLineNumber) 行：$($_.Message)" }
        Die 'start_dc.ps1 语法不通过'
    }
    Ok 'start_dc.ps1 语法自检通过'

    # 这里自己起 waitress，而不是去调 start_dc.ps1 —— 两种调用方式都会把脚本挂死：
    #   `& powershell.exe ... | ForEach-Object`  后台 waitress 继承了外层 stdout 管道句柄，管道等不到 EOF
    #   Start-Process -Wait                      它等的是整棵进程树，会把后台 waitress 一直等下去
    $vProc = Start-Process -FilePath (Join-Path $OutRuntime 'python.exe') `
        -ArgumentList @('-m', 'waitress', '--host=127.0.0.1', "--port=$vPort", '--threads=4', 'app:app') `
        -WorkingDirectory $OutBackend -WindowStyle Hidden `
        -RedirectStandardOutput $vOut -RedirectStandardError $vErr -RedirectStandardInput $vIn -PassThru
    Ok "探活实例 PID $($vProc.Id)"

    $ok = $false
    for ($i = 0; $i -lt 90; $i++) {
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:$vPort/api/health" -TimeoutSec 3 -UseBasicParsing
            if ($r.StatusCode -eq 200) { $ok = $true; break }
        } catch { }
        Start-Sleep -Milliseconds 800
    }
    if (-not $ok) {
        if (Test-Path -LiteralPath $vErr) { Get-Content -LiteralPath $vErr -Tail 20 | ForEach-Object { "    $_" } }
        & taskkill.exe /PID $vProc.Id /T /F | Out-Null
        Die '探活失败：包内服务没起来'
    }

    foreach ($k in @('/api/health', '/api/provinces?year=2023', '/api/counties?year=2022')) {
        try {
            $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$vPort$k" -TimeoutSec 30 -UseBasicParsing
            $text = if ($resp.Content -is [byte[]]) { [Text.Encoding]::UTF8.GetString($resp.Content) } else { [string]$resp.Content }
            Ok ("{0,-30} HTTP {1}  {2} 字节" -f $k, $resp.StatusCode, $text.Length)
        } catch {
            Warn ("{0,-30} 失败：{1}" -f $k, $_.Exception.Message)
        }
    }

    # 先停探活实例，再查向量索引 —— 否则两个进程抢同一个 chroma 目录
    & taskkill.exe /PID $vProc.Id /T /F | Out-Null
    Start-Sleep -Seconds 2

    # 验证向量索引可读（三条最容易翻车的路：非 ASCII 路径 / 拷了正在使用的活库 / 漏拷 docs）
    $checker = Join-Path $PSScriptRoot 'check_chroma.py'
    if (Test-Path -LiteralPath $checker) {
        $prevEAP2 = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        $pyOut = (& (Join-Path $OutRuntime 'python.exe') $checker (Join-Path $OutBackend 'chroma_db') 2>&1 | Out-String)
        $chromaCode = $LASTEXITCODE
        $ErrorActionPreference = $prevEAP2
        foreach ($line in ($pyOut -split "`r?`n")) { if ($line.Trim()) { "    $line" } }
        if ($chromaCode -ne 0) {
            Warn '向量索引检查未通过。三个常见原因：'
            Warn '  1) 产物路径含中文 —— 换纯 ASCII 目录名重打（启动器也有 TEMP 兜底）'
            Warn '  2) 打包时本机 8000 服务在跑 —— 先 serve_local.ps1 -Stop 再打'
            Warn '  3) docs\ 被跳过（-SkipDocs）—— watcher 会把对应切片当成已删除并清掉'
        }
    }
}

# ────────────────────────────────────────────────────────────────
# 8) 可选：打 zip
# ────────────────────────────────────────────────────────────────
if ($Zip) {
    Step '打成 zip（用 tar.exe，绕开 Compress-Archive 的 2GB 上限）'
    $zipPath = "$OutDir.zip"
    if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
    $leaf = Split-Path -Leaf $OutDir
    $parent = Split-Path -Parent $OutDir
    Push-Location $parent
    try {
        & tar.exe -a -c -f $zipPath $leaf
        if ($LASTEXITCODE -ne 0) { Warn "tar 打包失败（退出码 $LASTEXITCODE），目录本身仍然可用" }
        else { Ok "已生成 $zipPath（$(Format-Size (Get-Item -LiteralPath $zipPath).Length)）" }
    } finally { Pop-Location }
}

$sw.Stop()
$total = Get-DirSize $OutDir
$files = (Get-ChildItem -LiteralPath $OutDir -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
Write-Host ''
Write-Host '打包完成' -ForegroundColor Green
Write-Host ("    产物 : {0}" -f $OutDir)
Write-Host ("    体积 : {0}（{1:N0} 个文件）" -f (Format-Size $total), $files)
Write-Host ("    耗时 : {0:N1} 分钟" -f $sw.Elapsed.TotalMinutes)
Write-Host ("    入口 : 双击 {0}" -f (Join-Path $OutDir 'start_dc.cmd'))
if (-not $Verify) { Write-Host '    提示 : 加 -Verify 可以立刻用包内 Python 起一次服务探活' -ForegroundColor Yellow }
