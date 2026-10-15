<#
.SYNOPSIS
  DC 粮食生产风险系统 · Windows 本地部署脚本（单端口：Flask API + 已构建的前端 dist）

.DESCRIPTION
  一条命令把站点在本机跑起来。全程不依赖外网：域名、证书、nginx、Cloudflare 都不参与，
  浏览器直连 http://127.0.0.1:<Port>。

  脚本做三件事：
    1) 预检运行产物，缺什么补什么 —— backend/data/grain.db（省级）、backend/data/county.db（县级）、
       frontend/dist（前端）+ frontend/public/maps/counties_10provinces.json（县级地图资产）；
    2) 启动 WSGI 服务：优先 waitress（多线程、Windows 可用），没有则退回 Flask 内置服务器；
    3) 探活并打印访问地址。后台模式把 PID / 日志写在 deploy/run/ 下。

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File deploy\serve_local.ps1
      后台启动，地址 http://127.0.0.1:8000

  powershell -ExecutionPolicy Bypass -File deploy\serve_local.ps1 -Foreground
      前台启动，Ctrl+C 停止（排查问题用）

  powershell -ExecutionPolicy Bypass -File deploy\serve_local.ps1 -Lan
      监听 0.0.0.0，同一局域网内的手机/平板可访问（打印局域网地址）

  powershell -ExecutionPolicy Bypass -File deploy\serve_local.ps1 -Status
  powershell -ExecutionPolicy Bypass -File deploy\serve_local.ps1 -Stop
      查看状态 / 停止

.NOTES
  - 前端与 API 同源（axios baseURL '/api'），所以必须由本服务一起提供，不能单独开 vite dev 才能用真数据。
  - 生产部署（GCP + nginx + TLS）见 deploy/README.md；本脚本只管本地。
#>
[CmdletBinding()]
param(
    [int]$Port = 8000,
    [switch]$Lan,
    [switch]$Foreground,
    [switch]$Status,
    [switch]$Stop,
    [switch]$SkipBuild,
    [int]$HealthTimeoutSec = 120
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'
$RunDir = Join-Path $PSScriptRoot 'run'
$PidFile = Join-Path $RunDir 'server.pid'
$OutLog = Join-Path $RunDir 'server.out.log'
$ErrLog = Join-Path $RunDir 'server.err.log'
$NullIn = Join-Path $RunDir 'nul.in'
$Py = Join-Path $Backend '.venv\Scripts\python.exe'
$BindHost = if ($Lan) { '0.0.0.0' } else { '127.0.0.1' }
$ProbeHost = '127.0.0.1'

function Write-Step([string]$Message) { Write-Host "==> $Message" -ForegroundColor Cyan }
function Write-Ok([string]$Message) { Write-Host "    $Message" -ForegroundColor Green }
function Write-Warn2([string]$Message) { Write-Host "    $Message" -ForegroundColor Yellow }

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

function Get-LanAddresses {
    Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.PrefixOrigin -ne 'WellKnown' } |
        Select-Object -ExpandProperty IPAddress -Unique
}

function Stop-ProcessTree([int]$ProcId) {
    # 这里的进程链是三层的（waitress-serve.exe → venv python 垫片 → 真解释器），
    # 只杀记录下来的那个 PID 会留下孤儿进程继续占端口，所以按进程树杀。
    $known = [bool](Get-Process -Id $ProcId -ErrorAction SilentlyContinue)
    if ($known) { & taskkill.exe /PID $ProcId /T /F 2>&1 | Out-Null }
    # 兜底：树上还有残留（比如垫片先退出）时，按进程名 + 命令行匹配清一次
    $left = Get-CimInstance Win32_Process -Filter "Name='python.exe' or Name='waitress-serve.exe'" -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -and $_.CommandLine -match 'waitress-serve|app:app' }
    foreach ($p in $left) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
}

# ────────────────────────────────────────────────────────────────
# -Stop / -Status：管理既有实例，不进预检
# ────────────────────────────────────────────────────────────────
if ($Stop) {
    $procId = Get-ServerPid
    if ($null -eq $procId) { Write-Warn2 '没有记录在案的实例（deploy/run/server.pid 不存在）'; exit 0 }
    Write-Step "停止 PID $procId（含子进程）"
    Stop-ProcessTree $procId
    Remove-Item -LiteralPath $PidFile -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 800
    $still = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($still) {
        $owner = ($still | Select-Object -First 1).OwningProcess
        Write-Warn2 "端口 $Port 仍被 PID $owner 占用，再试一次： taskkill /PID $owner /T /F"
        exit 1
    }
    Write-Ok "已停止，端口 $Port 已释放"
    exit 0
}

if ($Status) {
    $procId = Get-ServerPid
    if ($null -eq $procId) { Write-Warn2 '未记录实例'; exit 1 }
    $alive = [bool](Get-Process -Id $procId -ErrorAction SilentlyContinue)
    Write-Host "PID      : $procId ($(if ($alive) { '运行中' } else { '不存在' }))"
    Write-Host "探活     : $(if (Test-Health 5) { 'OK' } else { '无响应' })"
    Write-Host "地址     : http://${ProbeHost}:$Port"
    Write-Host "日志     : $OutLog"
    exit 0
}

# ────────────────────────────────────────────────────────────────
# 0) 环境预检
# ────────────────────────────────────────────────────────────────
Write-Step "环境预检"
if (-not (Test-Path -LiteralPath $Py)) {
    Write-Host "[FATAL] 缺后端虚拟环境：$Py" -ForegroundColor Red
    Write-Host '        先执行： cd backend; python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt'
    exit 1
}
Write-Ok "Python  : $Py"

# 端口占用检查（属于本脚本记录的实例则视为重复启动）
$occupied = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($occupied) {
    $owner = ($occupied | Select-Object -First 1).OwningProcess
    $known = Get-ServerPid
    if ($known -eq $owner) {
        Write-Warn2 "端口 $Port 已在跑本脚本的实例（PID $owner）"
        Write-Host "    访问 http://${ProbeHost}:$Port ；重启用 -Stop 再启动。"
        exit 0
    }
    Write-Host "[FATAL] 端口 $Port 被 PID $owner 占用（不是本脚本启动的实例）" -ForegroundColor Red
    Write-Host "        换个端口： -Port 8081 ；或先释放该端口。"
    exit 1
}

# ────────────────────────────────────────────────────────────────
# 1) 运行产物：缺什么补什么
# ────────────────────────────────────────────────────────────────
$GrainDb = Join-Path $Backend 'data\grain.db'
$CountyDb = Join-Path $Backend 'data\county.db'
$DistIndex = Join-Path $Frontend 'dist\index.html'
$CountyGeo = Join-Path $Frontend 'public\maps\counties_10provinces.json'

if ($SkipBuild) {
    Write-Step "跳过产物构建（-SkipBuild）"
    foreach ($p in @($GrainDb, $CountyDb, $DistIndex, $CountyGeo)) {
        if (-not (Test-Path -LiteralPath $p)) {
            Write-Host "[FATAL] 缺 $p（-SkipBuild 下不会自动补）" -ForegroundColor Red
            exit 1
        }
    }
    Write-Ok '四件产物齐备'
} else {
    Write-Step '省级面板 grain.db（31 省 × 13 年 = 403 行）'
    if (Test-Path -LiteralPath $GrainDb) { Write-Ok '已存在，跳过' }
    else {
        Push-Location $Root
        try { & $Py (Join-Path $Root '_build_grain_db.py') } finally { Pop-Location }
        if ($LASTEXITCODE -ne 0) { Write-Host '[FATAL] grain.db 构建失败' -ForegroundColor Red; exit 1 }
        Write-Ok '已生成'
    }

    Write-Step '县级面板 county.db（1,199 县 × 12 年 = 14,388 行）'
    if ((Test-Path -LiteralPath $CountyDb) -and (Test-Path -LiteralPath $CountyGeo)) {
        Write-Ok '已存在，跳过'
    } else {
        Push-Location $Root
        try {
            & $Py (Join-Path $Root 'scripts\data\v9_01_build_county_site_db.py')
            if ($LASTEXITCODE -ne 0) { Write-Host '[FATAL] 县级 ETL 失败' -ForegroundColor Red; exit 1 }
            & $Py (Join-Path $Root 'scripts\data\v9_02_train_county_climg.py')
            if ($LASTEXITCODE -ne 0) { Write-Host '[FATAL] 县级模型训练失败' -ForegroundColor Red; exit 1 }
        } finally { Pop-Location }
        Write-Ok '已生成（含模型与 SHAP 预计算）'
    }

    Write-Step '前端构建 dist/'
    if (Test-Path -LiteralPath $DistIndex) { Write-Ok '已存在，跳过（要强制重建就先删掉 frontend\dist 再跑本脚本）' }
    else {
        if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
            Write-Host '[FATAL] 找不到 npm，无法构建前端' -ForegroundColor Red
            exit 1
        }
        Push-Location $Frontend
        try {
            if (-not (Test-Path -LiteralPath (Join-Path $Frontend 'node_modules'))) {
                Write-Ok 'node_modules 缺失，先 npm ci'
                & npm ci
                if ($LASTEXITCODE -ne 0) { Write-Host '[FATAL] npm ci 失败' -ForegroundColor Red; exit 1 }
            }
            & npm run build
            if ($LASTEXITCODE -ne 0) { Write-Host '[FATAL] npm run build 失败' -ForegroundColor Red; exit 1 }
        } finally { Pop-Location }
        Write-Ok '已构建'
    }
}

# ────────────────────────────────────────────────────────────────
# 2) 启动服务
# ────────────────────────────────────────────────────────────────
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

$hasWaitress = $false
try {
    & $Py -c 'import waitress' 2>$null
    $hasWaitress = ($LASTEXITCODE -eq 0)
} catch { $hasWaitress = $false }

if ($Foreground) {
    Write-Step "前台启动（$BindHost`:$Port，Ctrl+C 停止）"
    Write-Host "    地址 http://${ProbeHost}:$Port"
    if ($Lan) { Get-LanAddresses | ForEach-Object { Write-Host "    局域网 http://$_`:$Port" } }
    if ($hasWaitress) {
        $env:PORT = "$Port"
        Push-Location $Backend
        try {
            & (Join-Path $Backend '.venv\Scripts\waitress-serve.exe') "--host=$BindHost" "--port=$Port" '--threads=8' 'app:app'
        } finally { Pop-Location }
    } else {
        $env:FLASK_HOST = $BindHost
        $env:PORT = "$Port"
        Push-Location $Backend
        try { & $Py (Join-Path $Backend 'app.py') } finally { Pop-Location }
    }
    exit $LASTEXITCODE
}

Write-Step "后台启动（$BindHost`:$Port）"
if ($hasWaitress) {
    $exe = Join-Path $Backend '.venv\Scripts\waitress-serve.exe'
    $argList = @("--host=$BindHost", "--port=$Port", '--threads=8', '--ident=dc-grainrisk', 'app:app')
} else {
    Write-Warn2 '未安装 waitress，退回 Flask 内置服务器（不建议用于演示）'
    $exe = $Py
    $argList = @('app.py')
}

$env:FLASK_HOST = $BindHost
$env:PORT = "$Port"
if (-not (Test-Path -LiteralPath $NullIn)) { New-Item -ItemType File -Force -Path $NullIn | Out-Null }
# 三个标准流全部改到文件/NUL：否则子进程会继承父 shell 的管道句柄，
# 调用方（CI、脚本、agent）会一直等管道 EOF 而挂着不返回。
$proc = Start-Process -FilePath $exe -ArgumentList $argList -WorkingDirectory $Backend `
    -WindowStyle Hidden -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog `
    -RedirectStandardInput $NullIn -PassThru
Set-Content -LiteralPath $PidFile -Value $proc.Id -Encoding ascii
Write-Ok "PID $($proc.Id)（日志 $OutLog）"

# ────────────────────────────────────────────────────────────────
# 3) 探活
# ────────────────────────────────────────────────────────────────
Write-Step "探活（最多 $HealthTimeoutSec 秒）"
if (-not (Test-Health $HealthTimeoutSec)) {
    Write-Host '[FATAL] 服务未起来，看错误日志：' -ForegroundColor Red
    if (Test-Path -LiteralPath $ErrLog) { Get-Content -LiteralPath $ErrLog -Tail 25 | ForEach-Object { "    $_" } }
    exit 1
}
Write-Ok '/api/health OK'

try {
    $prov = Invoke-WebRequest -Uri "http://${ProbeHost}:$Port/api/provinces?year=2023" -TimeoutSec 15 -UseBasicParsing
    $county = Invoke-WebRequest -Uri "http://${ProbeHost}:$Port/api/counties?year=2022" -TimeoutSec 30 -UseBasicParsing
    # 字符串切分而不是 ConvertFrom-Json：Invoke-WebRequest 在 .NET Framework 下会把 UTF-8 中文解坏
    $provText = if ($prov.Content -is [byte[]]) { [Text.Encoding]::UTF8.GetString($prov.Content) } else { [string]$prov.Content }
    $countyText = if ($county.Content -is [byte[]]) { [Text.Encoding]::UTF8.GetString($county.Content) } else { [string]$county.Content }
    $nProv = ([regex]::Matches($provText, '"province"')).Count
    $nCounty = ([regex]::Matches($countyText, '"county_code"')).Count
    Write-Ok "省级面板 $nProv 行 / 县级面板 $nCounty 行"
} catch {
    Write-Warn2 "面板接口探活未通过：$($_.Exception.Message)"
}

Write-Host ''
Write-Host '部署完成。浏览器打开：' -ForegroundColor Green
Write-Host "    http://${ProbeHost}:$Port" -ForegroundColor Green
if ($Lan) {
    Get-LanAddresses | ForEach-Object { Write-Host "    http://$_`:$Port  （局域网）" -ForegroundColor Green }
}
Write-Host ''
Write-Host '    M00 系统总览 / M01 省级风险地图 / M07 县级风险地图（1,199 县）'
Write-Host "    停止： powershell -File deploy\serve_local.ps1 -Stop"
