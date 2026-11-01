param([Parameter(Mandatory=$true)][string]$Port)
$ErrorActionPreference='Stop'
$serial=New-Object System.IO.Ports.SerialPort $Port,115200,None,8,One
$serial.Handshake=[System.IO.Ports.Handshake]::None
$serial.DtrEnable=$false
$serial.RtsEnable=$false
$serial.ReadTimeout=100
$serial.WriteTimeout=500
$root=Split-Path $PSScriptRoot -Parent
$log=Join-Path $root ('report/board_'+(Get-Date -Format yyyyMMdd_HHmmss)+'.txt')
try {
    $serial.Open()
    Write-Host "Connected $Port, 115200 8N1. c=calibrate, t=retry failed point, a=auto, r=clear, p=status, q=quit."
    Write-Host "Log: $log"
    while ($true) {
        $received=$serial.ReadExisting()
        if ($received.Length) {
            [Console]::Write($received)
            Add-Content -LiteralPath $log -Value $received -NoNewline -Encoding utf8
        }
        if ([Console]::KeyAvailable) {
            $key=[Console]::ReadKey($true).KeyChar
            if ($key -eq 'q') { break }
            if ('ctaprmCTAPRM'.Contains([string]$key)) {
                $serial.Write([string]$key)
                Add-Content -LiteralPath $log -Value "`r`nHOST SENT $key`r`n" -NoNewline -Encoding utf8
            }
        }
        Start-Sleep -Milliseconds 20
    }
} finally {
    if ($serial.IsOpen) { $serial.Close() }
    $serial.Dispose()
}
