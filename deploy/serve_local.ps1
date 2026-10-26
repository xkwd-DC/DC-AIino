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

  powershell -ExecutionPolicy Bypass -File deploy\serve_local.ps1 -Open
      启动后顺便用默认浏览器打开（桌面快捷方式走的这条）

.NOTES
  - 前端与 API 同源（axios baseURL '/api'），所以必须由本服务一起提供，不能单独开 vite dev 才能用真数据。
  - 生产部署（GCP + nginx + TLS）见 deploy/README.md；本脚本只管本地。
#>
[CmdletBinding()]
param(
    [int]$Port = 8000,
    [switch]$Lan,
    [switch]$Foreground,
    [switch]$Open,
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
# 运行态文件按端口区分：否则起第二个实例（换端口）会覆盖第一个的 PID 记录，
# 之后 -Stop 就会杀错进程。
$PidFile = Join-Path $RunDir "server-$Port.pid"
$OutLog = Join-Path $RunDir "server-$Port.out.log"
$ErrLog = Join-Path $RunDir "server-$Port.err.log"
# stdin 用「每端口一个空文件」。绝不能叫 nul.in —— "NUL" 是 Windows 保留设备名，
# 带扩展名也照样被当设备（nul.in 会被解析成 NUL 设备），Test-Path / New-Item 在它上面
# 行为不可预期，两个实例还会互相锁住。
$NullIn = Join-Path $RunDir "stdin-$Port.empty"
$Py = Join-Path $Backend '.venv\Scripts\python.exe'
$BindHost = if ($Lan) { '0.0.0.0' } else { '127.0.0.1' }
$ProbeHost = '127.0.0.1'

# SQLite/模型库会写临时文件；跟随项目盘，避免 C 盘满或沙箱临时目录不可写。
$RuntimeTemp = Join-Path $RunDir 'tmp'
New-Item -ItemType Directory -Force -Path $RuntimeTemp | Out-Null
$env:TEMP = $RuntimeTemp
$env:TMP = $RuntimeTemp
$env:SQLITE_TMPDIR = $RuntimeTemp

function Write-Step([string]$Message) { Write-Host "==> $Message" -ForegroundColor Cyan }
function Write-Ok([string]$Message) { Write-Host "    $Message" -ForegroundColor Green }
function Write-Warn2([string]$Message) { Write-Host "    $Message" -ForegroundColor Yellow }

function Open-Site {
    # 用默认浏览器打开本机地址（桌面快捷方式走的就是这条）
    try { Start-Process "http://${ProbeHost}:$Port" | Out-Null; Write-Ok "已用默认浏览器打开 http://${ProbeHost}:$Port" }
    catch { Write-Warn2 "打不开浏览器，手动访问 http://${ProbeHost}:$Port" }
}

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
    # 只留真实网卡的地址：Hyper-V / VMware / VirtualBox 之类的虚拟网卡（vEthernet…）
    # 打出来会让人以为手机连不上。带上网卡名，方便判断"连 WiFi 就用哪个"。
    Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
        ForEach-Object {
            $alias = (Get-NetAdapter -InterfaceIndex $_.InterfaceIndex -ErrorAction SilentlyContinue).Name
            [pscustomobject]@{ IP = $_.IPAddress; Alias = $alias }
        } |
        Where-Object {
            $_.Alias -and $_.Alias -notmatch 'vEthernet|VMware|VirtualBox|Hyper-V|Loopback|Bluetooth|Npcap|TAP|WSL'
        } |
        Select-Object -Property IP, Alias -Unique
}

function Stop-ProcessTree([int]$ProcId, [int]$ListenPort) {
    # 这里的进程链是三层的（waitress-serve.exe → venv python 垫片 → 真解释器），
    # 只杀记录下来的那个 PID 会留下孤儿进程继续占端口，所以按进程树杀。
    if (Get-Process -Id $ProcId -ErrorAction SilentlyContinue) {
        & taskkill.exe /PID $ProcId /T /F 2>&1 | Out-Null
    }
    # 兜底只认「谁在监听这个端口」——绝不能按进程名泛杀：
    # 那样会把别的端口上正在跑的实例一起带走（本项目同时开两个端口时踩过）。
    Start-Sleep -Milliseconds 300
    $still = Get-NetTCPConnection -LocalPort $ListenPort -State Listen -ErrorAction SilentlyContinue
    foreach ($c in $still) { Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue }
}

# ────────────────────────────────────────────────────────────────
# -Stop / -Status：管理既有实例，不进预检
# ────────────────────────────────────────────────────────────────
if ($Stop) {
    $procId = Get-ServerPid
    if ($null -eq $procId) { Write-Warn2 '没有记录在案的实例（deploy/run/server.pid 不存在）'; exit 0 }
    Write-Step "停止 PID $procId（含子进程）"
    Stop-ProcessTree $procId -ListenPort $Port
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

# 端口占用检查。注意判据：pidfile 里记的是启动器进程（waitress-serve.exe），
# 而真正持有监听套接字的是它的子进程，两者 PID 必然不同 —— 所以只能看
# "记录下来的进程是否还活着"，不能拿 PID 跟 socket owner 比。
$occupied = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($occupied) {
    $owner = ($occupied | Select-Object -First 1).OwningProcess
    $known = Get-ServerPid
    $knownAlive = if ($known) { [bool](Get-Process -Id $known -ErrorAction SilentlyContinue) } else { $false }
    if ($knownAlive) {
        Write-Warn2 "端口 $Port 已在跑本脚本的实例（PID $owner）"
        Write-Host "    访问 http://${ProbeHost}:$Port ；重启用 -Stop 再启动。"
        if ($Open) { Open-Site }
        exit 0
    }
    Write-Host "[FATAL] 端口 $Port 被 PID $owner 占用（不是本脚本启动的实例）" -ForegroundColor Red
    Write-Host "        若是上次实例的残留：先 -Stop（会按端口兜底清掉），或 taskkill /PID $owner /T /F"
    Write-Host "        否则换个端口： -Port 8081"
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
    if ($Lan) { Get-LanAddresses | ForEach-Object { Write-Host "    局域网 http://$($_.IP):$Port  （网卡 $($_.Alias)）" } }
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
if (-not (Test-Path -LiteralPath $NullIn)) {
    try { New-Item -ItemType File -Path $NullIn -ErrorAction Stop | Out-Null }
    catch { $NullIn = 'NUL' }   # 兜底：NUL 设备永远可读且不会被锁
}
$launchedAt = Get-Date
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

# 探活成功不等于"我们刚起的进程接管了端口"——如果端口上本来就有一个实例，
# 健康检查是被它答的，而新进程可能已经因端口冲突死掉，看日志还全是正常。
# 用一个不变式兜住：正在监听该端口的进程，启动时间必须不早于本次启动。
$listener = (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1).OwningProcess
$listenerStart = if ($listener) { (Get-Process -Id $listener -ErrorAction SilentlyContinue).StartTime } else { $null }
if ($listenerStart -and $listenerStart -lt $launchedAt.AddSeconds(-2)) {
    Write-Host "[FATAL] 端口 $Port 是被更早的实例（PID $listener，启动于 $($listenerStart.ToString('HH:mm:ss'))）提供的，" -ForegroundColor Red
    Write-Host "        本次启动的进程没接管端口。先 -Stop 掉旧实例再启动（或换 -Port）。" -ForegroundColor Red
    if (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue) {
        & taskkill.exe /PID $proc.Id /T /F 2>&1 | Out-Null   # 只清自己刚起的那个，别碰旧实例
    }
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
    Get-LanAddresses | ForEach-Object { Write-Host "    http://$($_.IP):$Port  （局域网 · 网卡 $($_.Alias)）" -ForegroundColor Green }
}
Write-Host ''
Write-Host '    M00 系统总览 / M01 省级风险地图 / M07 县级风险地图（1,199 县）'
Write-Host "    停止： powershell -File deploy\serve_local.ps1 -Stop"

if ($Open) { Open-Site }
