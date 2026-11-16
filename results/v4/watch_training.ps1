$host.ui.RawUI.WindowTitle = 'BantayAso v4 training'
Set-Location 'C:\Users\patri\Desktop\straywatch-is'
$esc = [char]27
while ($true) {
    $lines = @()
    try {
        $fs = [System.IO.File]::Open('results\train_v4_output.txt', 'Open', 'Read', 'ReadWrite')
        $len = $fs.Length; $start = [Math]::Max(0, $len - 8000)
        $fs.Seek($start, 'Begin') | Out-Null
        $buf = New-Object byte[] ($len - $start); [void]$fs.Read($buf, 0, $buf.Length); $fs.Close()
        $text = [System.Text.Encoding]::UTF8.GetString($buf) -replace "$esc\[[0-9;]*[A-Za-z]", ''
        $lines = $text -split "[`r`n]+" | Where-Object { $_.Trim() }
    } catch { $lines = @("(log not readable yet: $_)") }
    Clear-Host
    Write-Host "BantayAso YOLO26n v4 training   $(Get-Date -Format 'HH:mm:ss')   (window refreshes every 5 s; closing it does NOT stop training)`n" -ForegroundColor Cyan
    Write-Host "Current progress  (epoch/total  GPU-mem  box_loss  cls_loss  l1_loss  boxes  size  batch-progress):" -ForegroundColor Yellow
    $lines | Select-Object -Last 3 | ForEach-Object { Write-Host $_ }
    $csv = 'runs\train\yolo26n_v4\results.csv'
    if (Test-Path $csv) {
        Write-Host "`nCompleted epochs (validation):" -ForegroundColor Yellow
        Import-Csv $csv | Select-Object -Last 5 | ForEach-Object {
            [pscustomobject]@{ epoch = $_.epoch; precision = [math]::Round([double]$_.'metrics/precision(B)', 3)
                recall = [math]::Round([double]$_.'metrics/recall(B)', 3); mAP50 = [math]::Round([double]$_.'metrics/mAP50(B)', 3)
                'mAP50-95' = [math]::Round([double]$_.'metrics/mAP50-95(B)', 3); seconds = [math]::Round([double]$_.time) }
        } | Format-Table -AutoSize | Out-String | Write-Host
    }
    Start-Sleep 5
}
