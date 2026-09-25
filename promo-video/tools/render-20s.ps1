# 渲染 20s 产品片。把这台机器上三个坑一次性绕开，直接跑就能出片。
#
# 三个坑（2026-09-16 实测）：
#   1. HyperFrames 自带的 chrome-headless-shell 启动即崩（exit 3221225595）
#      → 指向系统 Chrome。
#   2. PATH 上第一个 ffmpeg 是 hermes-agent venv 里的 Lavf55 老版本，缺 adelay 滤镜，
#      音频混音会直接失败；系统里另外几个 ffmpeg 要么没有 libx264，要么滤镜子集不全。
#      → 指向 D:\DC\tools\ffmpeg\bin\ffmpeg.exe（完整 GPL 版，adelay + libx264 都有）。
#   3. C 盘只剩 0.15GB，渲染临时文件默认写 C:\Users\darcy\AppData\Local\Temp
#      → TEMP/TMP 改到 D 盘。
#
# 用法:
#   powershell -File tools/render-20s.ps1                    # 标准质量成片
#   powershell -File tools/render-20s.ps1 -Quality draft     # 快速预览
param(
  [string]$Quality = 'delivery',
  [string]$Output = 'renders/DC-promo-20s.mp4',
  [string]$Fps = '30'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Ffmpeg = 'D:\DC\tools\ffmpeg\bin\ffmpeg.exe'
$Chrome = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
$RenderTemp = 'D:\DC\tmp\hf-render'

if (-not (Test-Path $Ffmpeg)) { throw "找不到 ffmpeg: $Ffmpeg（需要带 adelay + libx264 的完整版）" }
if (-not (Test-Path $Chrome)) { throw "找不到 Chrome: $Chrome" }
New-Item -ItemType Directory -Force -Path $RenderTemp | Out-Null

$env:TEMP = $RenderTemp
$env:TMP = $RenderTemp
$env:HYPERFRAMES_BROWSER_PATH = $Chrome
$env:HYPERFRAMES_FFMPEG_PATH = $Ffmpeg

Push-Location $ProjectRoot
try {
  npx hyperframes render --quality $Quality --fps $Fps --output $Output
  if ($LASTEXITCODE -ne 0) { throw "render 失败，退出码 $LASTEXITCODE" }
  Write-Host "`n成片: $(Join-Path $ProjectRoot $Output)"
}
finally {
  Pop-Location
}
