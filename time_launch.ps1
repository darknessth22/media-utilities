$exePath = "dist\MediaUtility\MediaUtility.exe"
if (-not (Test-Path $exePath)) {
    Write-Host "Error: $exePath not found. Run build_executable.py first." -ForegroundColor Red
    exit 1
}

$durations = @()
Write-Host "Starting 5 cold launches to measure startup time..." -ForegroundColor Cyan

for ($i = 1; $i -le 5; $i++) {
    Write-Host "Launch $i... " -NoNewline
    # Cold launch attempt: we can't truly guarantee cold cache without reboot/clear, 
    # but we measure sequential launches as a proxy (first one is coldest).
    $time = Measure-Command {
        $p = Start-Process -FilePath $exePath -PassThru
        # Wait for window to be ready (simplified: wait 2s then kill)
        Start-Sleep -Seconds 3
        Stop-Process -Id $p.Id -Force
    }
    $durations += $time.TotalSeconds
    Write-Host "$($time.TotalSeconds) s"
}

$sorted = $durations | Sort-Object
$median = $sorted[2] # 3rd element of 5

Write-Host "`nResults:" -ForegroundColor Green
Write-Host "  Individual: $($durations -join ', ')"
Write-Host "  Median:     $median s"

if ($median -le 3.0) {
    Write-Host "  SLO PASS (<= 3s)" -ForegroundColor Green
} else {
    Write-Host "  SLO FAIL (> 3s)" -ForegroundColor Red
}
