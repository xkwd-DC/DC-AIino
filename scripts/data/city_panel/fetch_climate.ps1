# Download NASA POWER monthly climate for each city (ASCII-only script).
$ErrorActionPreference = "Continue"
$list = "D:\DC\_scan\cities.csv"
$cache = "D:\DC\_scan\climate_cache2"
if (-not (Test-Path $cache)) { New-Item -ItemType Directory -Path $cache | Out-Null }

$cities = Import-Csv -Path $list -Encoding UTF8
Write-Output ("cities: {0}" -f $cities.Count)
$done = 0
$skip = 0
foreach ($c in $cities) {
    $out = Join-Path $cache ($c.key + ".json")
    if ((Test-Path $out) -and ((Get-Item $out).Length -gt 2000)) { $skip++; continue }
    $url = "https://power.larc.nasa.gov/api/temporal/monthly/point?parameters=T2M,PRECTOTCORR,T2MDEW&community=AG&longitude=$($c.lon)&latitude=$($c.lat)&start=2000&end=2024&format=JSON"
    & curl.exe -sS --max-time 90 -A "Mozilla/5.0" $url -o $out
    if ((Test-Path $out) -and ((Get-Item $out).Length -gt 2000)) {
        $done++
    } else {
        Write-Output ("FAILED {0} {1}" -f $c.key, $c.city)
    }
    Start-Sleep -Milliseconds 350
    if ($done % 20 -eq 0 -and $done -gt 0) { Write-Output ("fetched {0}" -f $done) }
}
Write-Output ("done={0} skipped={1}" -f $done, $skip)
