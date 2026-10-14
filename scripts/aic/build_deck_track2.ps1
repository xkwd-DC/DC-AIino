# Build the defence deck as an editable PPTX through the WPS Presentation COM API.
# 用法：powershell -NoProfile -ExecutionPolicy Bypass -File scripts/aic/build_deck_track2.ps1
#      可选 -DataJson 指向另一份幻灯片定义（默认同目录下的 deck_data_track2.json）。
param(
    [string]$DataJson = (Join-Path $PSScriptRoot "deck_data_track2.json")
)
$ErrorActionPreference = "Stop"

function RGB([int]$r, [int]$g, [int]$b) { return [int]($r + $g * 256 + $b * 65536) }

$DARK   = RGB 18 53 42
$GREEN  = RGB 30 77 59
$LIGHT  = RGB 244 247 245
$BORDER = RGB 220 228 223
$INK    = RGB 26 26 26
$MUTED  = RGB 122 139 131
$WHITE  = RGB 255 255 255
$HDR    = RGB 31 56 100
$ZEBRA  = RGB 245 247 250
$KICK   = RGB 168 196 182
$DESC   = RGB 220 231 225
$ACCENT = RGB 127 176 105

$FONT = "Microsoft YaHei"

function Add-Text($slide, [double]$l, [double]$t, [double]$w, [double]$h, $text,
                  [double]$size, [bool]$bold, [int]$color, [int]$align, [bool]$wrap = $true) {
    if ([string]::IsNullOrEmpty($text)) { return $null }
    $shape = $slide.Shapes.AddTextbox(1, $l, $t, $w, $h)
    $tf = $shape.TextFrame
    $tf.WordWrap = if ($wrap) { -1 } else { 0 }
    $tf.MarginLeft = 0; $tf.MarginRight = 0; $tf.MarginTop = 0; $tf.MarginBottom = 0
    $shape.Line.Visible = 0
    $shape.Fill.Visible = 0
    $tr = $tf.TextRange
    $tr.Text = $text.Replace("\n", [string][char]11)
    $tr.Font.Size = $size
    $tr.Font.Name = $FONT
    $tr.Font.NameFarEast = $FONT
    $tr.Font.Bold = if ($bold) { -1 } else { 0 }
    $tr.Font.Color.RGB = $color
    $tr.ParagraphFormat.Alignment = $align
    return $shape
}

function Add-Box($slide, [double]$l, [double]$t, [double]$w, [double]$h, [int]$fill, [int]$line = -1) {
    $shape = $slide.Shapes.AddShape(1, $l, $t, $w, $h)
    $shape.Fill.Solid()
    $shape.Fill.ForeColor.RGB = $fill
    if ($line -lt 0) { $shape.Line.Visible = 0 } else {
        $shape.Line.Visible = -1
        $shape.Line.ForeColor.RGB = $line
        $shape.Line.Weight = 0.75
    }
    $shape.TextFrame.TextRange.Text = ""
    return $shape
}

function Add-Table($slide, [double]$l, [double]$t, [double]$w, [double]$h, $header, $rows, $widths) {
    $nRows = $rows.Count + 1
    $nCols = $header.Count
    $shape = $slide.Shapes.AddTable($nRows, $nCols, $l, $t, $w, $h)
    $tbl = $shape.Table

    for ($c = 1; $c -le $nCols; $c++) {
        $pct = if ($widths -and $c -le $widths.Count) { [double]$widths[$c - 1] } else { 100.0 / $nCols }
        $tbl.Columns($c).Width = [double]($w * $pct / 100.0)
    }

    for ($c = 1; $c -le $nCols; $c++) {
        $cell = $tbl.Cell(1, $c)
        $cell.Shape.TextFrame.TextRange.Text = [string]$header[$c - 1]
        $cell.Shape.TextFrame.TextRange.Font.Size = 11
        $cell.Shape.TextFrame.TextRange.Font.Name = $FONT
        $cell.Shape.TextFrame.TextRange.Font.NameFarEast = $FONT
        $cell.Shape.TextFrame.TextRange.Font.Bold = -1
        $cell.Shape.TextFrame.TextRange.Font.Color.RGB = $WHITE
        $cell.Shape.TextFrame.TextRange.ParagraphFormat.Alignment = 2
        $cell.Shape.Fill.Solid()
        $cell.Shape.Fill.ForeColor.RGB = $HDR
        try {
            $cell.Shape.TextFrame.MarginLeft = 4; $cell.Shape.TextFrame.MarginRight = 4
            $cell.Shape.TextFrame.MarginTop = 2; $cell.Shape.TextFrame.MarginBottom = 2
        } catch { }
    }

    for ($r = 1; $r -le $rows.Count; $r++) {
        $row = $rows[$r - 1]
        for ($c = 1; $c -le $nCols; $c++) {
            $txt = if ($c -le $row.Count) { [string]$row[$c - 1] } else { "" }
            $cell = $tbl.Cell($r + 1, $c)
            $cell.Shape.TextFrame.TextRange.Text = $txt
            $cell.Shape.TextFrame.TextRange.Font.Size = 11
            $cell.Shape.TextFrame.TextRange.Font.Name = $FONT
            $cell.Shape.TextFrame.TextRange.Font.NameFarEast = $FONT
            $cell.Shape.TextFrame.TextRange.Font.Color.RGB = $INK
            $cell.Shape.TextFrame.TextRange.ParagraphFormat.Alignment = if ($c -eq $nCols -and $nCols -ge 3) { 2 } else { 1 }
            $cell.Shape.Fill.Solid()
            $cell.Shape.Fill.ForeColor.RGB = if ($r % 2) { $WHITE } else { $ZEBRA }
            try {
                $cell.Shape.TextFrame.MarginLeft = 4; $cell.Shape.TextFrame.MarginRight = 4
                $cell.Shape.TextFrame.MarginTop = 2; $cell.Shape.TextFrame.MarginBottom = 2
            } catch { }
        }
    }
    return $shape
}

function Add-Title($slide, $text) {
    Add-Text $slide 54 30 852 44 $text 26 $true $DARK 1 | Out-Null
    Add-Box $slide 54 80 66 4 $GREEN | Out-Null
}

function Add-PageNo($slide, [int]$n) {
    Add-Text $slide 880 504 40 20 ([string]$n) 10 $false $MUTED 3 | Out-Null
}

function Add-Bullets($slide, [double]$l, [double]$t, [double]$w, $items, [double]$size = 11.5) {
    $text = ($items | ForEach-Object { [string]$_ }) -join [string][char]11
    Add-Text $slide $l $t $w 160 $text $size $false $INK 1 | Out-Null
}

# ---------------------------------------------------------------- load data
$data = Get-Content -Path $DataJson -Encoding UTF8 -Raw | ConvertFrom-Json
$outPptx = $data.outPptx
$outPdf  = $data.outPdf
$imgDir  = $data.imageDir
$pngDir  = Join-Path $PSScriptRoot "deck_png"
if (-not (Test-Path $pngDir)) { New-Item -ItemType Directory -Path $pngDir | Out-Null }
foreach ($f in @($outPptx, $outPdf)) {
    if (Test-Path $f) {
        try { Remove-Item $f -Force } catch { Write-Output ("note: cannot overwrite " + $f) }
    }
}

$app = New-Object -ComObject KWPP.Application
$count = 0
try {
    try { $app.Visible = 0 } catch { }
    try { $app.DisplayAlerts = 1 } catch { }
    $pres = $app.Presentations.Add()
    $pres.PageSetup.SlideWidth = 960
    $pres.PageSetup.SlideHeight = 540

    $index = 0
    foreach ($s in $data.slides) {
        $index++
        $slide = $pres.Slides.Add($index, 12)
        $slide.FollowMasterBackground = 0
        $slide.Background.Fill.Solid()
        $slide.Background.Fill.ForeColor.RGB = if ($s.kind -eq "cover") { $DARK } else { $WHITE }

        switch ($s.kind) {
            "cover" {
                Add-Text $slide 96 132 768 28 $s.kicker 15 $false $KICK 1 | Out-Null
                Add-Text $slide 96 172 768 130 $s.title 44 $true $WHITE 1 | Out-Null
                Add-Box $slide 96 316 100 5 $ACCENT | Out-Null
                Add-Text $slide 96 340 700 80 $s.desc 17 $false $DESC 1 | Out-Null
                Add-Text $slide 96 452 500 28 $s.when 14 $false $KICK 1 | Out-Null
            }
            "cols3" {
                Add-Title $slide $s.title
                for ($i = 0; $i -lt $s.cols.Count; $i++) {
                    $x = 54 + $i * 292
                    Add-Box $slide $x 118 268 210 $LIGHT $BORDER | Out-Null
                    Add-Text $slide ($x + 18) 138 232 20 $s.cols[$i][0] 12 $false $MUTED 1 | Out-Null
                    Add-Text $slide ($x + 18) 164 232 30 $s.cols[$i][1] 17 $true $DARK 1 | Out-Null
                    Add-Text $slide ($x + 18) 202 232 110 $s.cols[$i][2] 12.5 $false $INK 1 | Out-Null
                }
                if ($s.takeaway) { Add-Text $slide 54 372 852 40 $s.takeaway 17 $true $DARK 1 | Out-Null }
            }
            "table" {
                Add-Title $slide $s.title
                $h = 36 * ($s.rows.Count + 1)
                if ($h -gt 360) { $h = 360 }
                Add-Table $slide 54 116 852 $h $s.header $s.rows $s.widths | Out-Null
                if ($s.takeaway) {
                    $y = 116 + $h + 22
                    Add-Text $slide 54 $y 852 40 $s.takeaway 15 $true $DARK 1 | Out-Null
                }
            }
            "bands" {
                Add-Title $slide $s.title
                $y = 112
                foreach ($band in $s.bands) {
                    Add-Box $slide 54 $y 852 56 $LIGHT $BORDER | Out-Null
                    $shape = Add-Text $slide 68 ($y + 16) 824 30 ($band[0] + "　" + $band[1]) 13 $false $INK 1
                    if ($shape -ne $null) {
                        $labelLen = ([string]$band[0]).Length
                        try { $shape.TextFrame.TextRange.Characters(1, $labelLen).Font.Bold = -1 } catch { }
                    }
                    $y += 62
                }
                if ($s.takeaway) { Add-Text $slide 54 ($y + 10) 852 34 $s.takeaway 15 $true $DARK 1 | Out-Null }
            }
            "steps8" {
                Add-Title $slide $s.title
                for ($i = 0; $i -lt $s.steps.Count; $i++) {
                    $col = $i % 4
                    $row = [math]::Floor($i / 4)
                    $x = 54 + $col * 217
                    $y = 112 + $row * 126
                    Add-Box $slide $x $y 200 112 $LIGHT $BORDER | Out-Null
                    Add-Text $slide ($x + 14) ($y + 12) 172 18 $s.steps[$i][0] 11 $true $MUTED 1 | Out-Null
                    Add-Text $slide ($x + 14) ($y + 34) 172 24 $s.steps[$i][1] 15 $true $DARK 1 | Out-Null
                    Add-Text $slide ($x + 14) ($y + 62) 172 44 $s.steps[$i][2] 10.5 $false $INK 1 | Out-Null
                }
                if ($s.trace) {
                    Add-Box $slide 54 372 852 104 $LIGHT $BORDER | Out-Null
                    Add-Box $slide 54 372 5 104 $ACCENT | Out-Null
                    Add-Text $slide 78 386 810 20 $s.trace[0] 11.5 $false $MUTED 1 | Out-Null
                    Add-Text $slide 78 408 810 24 $s.trace[1] 14 $true $DARK 1 | Out-Null
                    Add-Text $slide 78 436 810 34 $s.trace[2] 11.5 $false $INK 1 | Out-Null
                }
            }
            "twocol" {
                Add-Title $slide $s.title
                $leftX = 54; $rightX = 496; $colW = 410
                $y = 112
                foreach ($blk in $s.left) {
                    $bh = if ($blk.items) { 176 } else { 112 }
                    Add-Box $slide $leftX $y $colW $bh $LIGHT $BORDER | Out-Null
                    Add-Text $slide ($leftX + 16) ($y + 14) ($colW - 32) 24 $blk.h 15 $true $DARK 1 | Out-Null
                    if ($blk.text) { Add-Text $slide ($leftX + 16) ($y + 42) ($colW - 32) 60 $blk.text 11 $false $INK 1 | Out-Null }
                    if ($blk.items) {
                        $lines = @()
                        $n = 1
                        foreach ($it in $blk.items) { $lines += ([string]$n + ". " + [string]$it); $n++ }
                        Add-Text $slide ($leftX + 16) ($y + 44) ($colW - 32) 124 ($lines -join [string][char]11) 11 $false $INK 1 | Out-Null
                    }
                    $y += $bh + 12
                }
                $y = 112
                foreach ($blk in $s.right) {
                    $bh = if ($blk.items) { 196 } else { 92 }
                    Add-Box $slide $rightX $y $colW $bh $LIGHT $BORDER | Out-Null
                    Add-Text $slide ($rightX + 16) ($y + 14) ($colW - 32) 24 $blk.h 15 $true $DARK 1 | Out-Null
                    if ($blk.text) { Add-Text $slide ($rightX + 16) ($y + 42) ($colW - 32) 50 $blk.text 11 $false $INK 1 | Out-Null }
                    if ($blk.items) {
                        $lines = @()
                        foreach ($it in $blk.items) { $lines += ("· " + [string]$it) }
                        Add-Text $slide ($rightX + 16) ($y + 86) ($colW - 32) 100 ($lines -join [string][char]11) 11 $false $INK 1 | Out-Null
                    }
                    $y += $bh + 12
                }
                if ($s.takeaway) { Add-Text $slide 54 448 852 30 $s.takeaway 15 $true $DARK 1 | Out-Null }
            }
            "engine" {
                Add-Title $slide $s.title
                Add-Table $slide 54 116 400 150 $s.tableA.header $s.tableA.rows @(45, 55) | Out-Null
                Add-Table $slide 480 116 426 190 $s.tableB.header $s.tableB.rows @(48, 52) | Out-Null
                Add-Box $slide 54 284 400 150 $LIGHT $BORDER | Out-Null
                Add-Text $slide 70 298 368 24 $s.boxA[0] 15 $true $DARK 1 | Out-Null
                Add-Text $slide 70 328 368 92 $s.boxA[1] 11.5 $false $INK 1 | Out-Null
                Add-Box $slide 480 320 426 114 $LIGHT $BORDER | Out-Null
                Add-Text $slide 496 334 394 24 $s.boxB[0] 15 $true $DARK 1 | Out-Null
                Add-Text $slide 496 364 394 60 $s.boxB[1] 11.5 $false $INK 1 | Out-Null
                Add-Text $slide 54 448 852 24 $s.footnote 10.5 $false $MUTED 1 | Out-Null
            }
            "image" {
                Add-Title $slide $s.title
                $pic = Join-Path $imgDir $s.image
                $w = 555.0; $h = 372.0
                $x = (960 - $w) / 2
                $slide.Shapes.AddPicture($pic, 0, -1, $x, 108, $w, $h) | Out-Null
                Add-Text $slide 54 490 852 24 $s.caption 11.5 $false $MUTED 2 | Out-Null
            }
            "cols4" {
                Add-Title $slide $s.title
                for ($i = 0; $i -lt $s.cols.Count; $i++) {
                    $col = $i % 2
                    $row = [math]::Floor($i / 2)
                    $x = 54 + $col * 438
                    $y = 116 + $row * 178
                    Add-Box $slide $x $y 414 160 $LIGHT $BORDER | Out-Null
                    Add-Text $slide ($x + 18) ($y + 16) 378 20 $s.cols[$i][0] 11.5 $false $MUTED 1 | Out-Null
                    Add-Text $slide ($x + 18) ($y + 40) 378 26 $s.cols[$i][1] 16 $true $DARK 1 | Out-Null
                    Add-Text $slide ($x + 18) ($y + 74) 378 72 $s.cols[$i][2] 11.5 $false $INK 1 | Out-Null
                }
            }
            "mix" {
                Add-Title $slide $s.title
                for ($i = 0; $i -lt $s.cols.Count; $i++) {
                    $x = 54 + $i * 292
                    Add-Box $slide $x 112 268 168 $LIGHT $BORDER | Out-Null
                    Add-Text $slide ($x + 18) 128 232 20 $s.cols[$i][0] 11.5 $false $MUTED 1 | Out-Null
                    Add-Text $slide ($x + 18) 152 232 28 $s.cols[$i][1] 15 $true $DARK 1 | Out-Null
                    Add-Text $slide ($x + 18) 188 232 80 $s.cols[$i][2] 11.5 $false $INK 1 | Out-Null
                }
                for ($i = 0; $i -lt $s.steps.Count; $i++) {
                    $x = 54 + $i * 292
                    Add-Box $slide $x 296 268 120 $WHITE $BORDER | Out-Null
                    Add-Text $slide ($x + 18) 310 232 18 $s.steps[$i][0] 11 $true $MUTED 1 | Out-Null
                    Add-Text $slide ($x + 18) 332 232 24 $s.steps[$i][1] 15 $true $DARK 1 | Out-Null
                    Add-Text $slide ($x + 18) 360 232 48 $s.steps[$i][2] 11.5 $false $INK 1 | Out-Null
                }
            }
        }
        if ($s.kind -ne "cover") { Add-PageNo $slide $index }
        try {
            $slide.Export((Join-Path $pngDir ("slide{0:d2}.png" -f $index)), "PNG", 1280, 720)
        } catch { Write-Output ("note: png export failed for slide " + $index) }
    }

    $count = $pres.Slides.Count
    $pres.SaveAs($outPptx)
    Write-Output "saved pptx"
    try {
        $pres.SaveAs($outPdf, 32)
        Write-Output "saved pdf"
    } catch {
        Write-Output ("pdf export failed: " + $_.Exception.Message)
    }
    $pres.Close()
} finally {
    try { $app.Quit() } catch { }
}

Write-Output ("slides={0}  pptx={1}KB" -f $count, [math]::Round((Get-Item $outPptx).Length / 1KB))
