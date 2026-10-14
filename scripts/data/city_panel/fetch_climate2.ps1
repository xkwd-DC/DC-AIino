# Fetch only the cities still missing from the climate cache.
$list = "D:\DC\_scan\cities2.csv"
$cache = "D:\DC\_scan\climate_cache3"
if (-not (Test-Path $cache)) { New-Item -ItemType Directory -Path $cache | Out-Null }
$cities = Import-Csv -Path $list -Encoding UTF8
$n = 0
foreach ($c in $cities) {
    $out = Join-Path $cache ($c.key + ".json")
    if ((Test-Path $out) -and ((Get-Item $out).Length -gt 2000)) { continue }
    $url = "https://power.larc.nasa.gov/api/temporal/monthly/point?parameters=T2M,PRECTOTCORR,T2MDEW&community=AG&longitude=$($c.lon)&latitude=$($c.lat)&start=2000&end=2024&format=JSON"
    & curl.exe -sS --max-time 90 -A "Mozilla/5.0" $url -o $out
    if ((Test-Path $out) -and ((Get-Item $out).Length -gt 2000)) { $n++; Write-Output ("fetched " + $c.key) } else { Write-Output ("FAILED " + $c.key) }
    Start-Sleep -Milliseconds 400
}
Write-Output ("newly fetched: {0}" -f $n)
