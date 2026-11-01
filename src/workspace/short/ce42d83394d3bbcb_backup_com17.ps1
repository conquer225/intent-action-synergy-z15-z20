# Requires a fresh user authorization before each hardware run.
$ErrorActionPreference = 'Stop'
$esptoolPath = 'C:\Users\lenovo\AppData\Local\Arduino15\packages\esp32\tools\esptool_py\5.3.1\esptool.exe'
$targetSerial = '28:84:85:60:CD:9C'
$targetPort = 'COM17'
$backupRoot = Join-Path $PSScriptRoot 'firmware_backups'
$logRoot = Join-Path $PSScriptRoot 'output'
$backupPath = Join-Path $backupRoot 'com17_20261006_full_01.bin'
$romBackupPath = Join-Path $backupRoot 'com17_20261006_rom_full_02.bin'

$device = @(Get-PnpDevice -PresentOnly | Where-Object { $_.FriendlyName -match '\(COM17\)$' })
if ($device.Count -ne 1) { throw 'COM17 is missing or ambiguous; no hardware action taken.' }
$parentId = (Get-PnpDeviceProperty -InstanceId $device[0].InstanceId -KeyName 'DEVPKEY_Device_Parent').Data
if ($parentId -notlike "*\$targetSerial") { throw 'COM17 USB identity mismatch; no hardware action taken.' }
if ((Test-Path -LiteralPath $backupPath) -or (Test-Path -LiteralPath $romBackupPath)) {
    throw 'Backup filename already exists; refusing to overwrite.'
}

$env:PYTHONUNBUFFERED = '1'
$readTimer = [Diagnostics.Stopwatch]::StartNew()
$completed = $false
$resetSucceeded = $false
try {
    & $esptoolPath --chip esp32s3 --port $targetPort --before default-reset --after no-reset read-flash --no-progress 0 0x1000000 $backupPath 2>&1 |
        Tee-Object -FilePath (Join-Path $logRoot 'com17_read_20261006.log')
    $readExit = $LASTEXITCODE
    if ($readExit -ne 0) {
        Write-Output "RAM reader failed (exit $readExit); using ROM reader and a new file."
        $backupPath = $romBackupPath
        & $esptoolPath --chip esp32s3 --port $targetPort --before default-reset --after no-reset --no-stub read-flash --no-progress 0 0x1000000 $backupPath 2>&1 |
            Tee-Object -FilePath (Join-Path $logRoot 'com17_rom_read_20261006.log')
        $readExit = $LASTEXITCODE
    }
    $readTimer.Stop()
    Write-Output "READ_EXIT=$readExit READ_ELAPSED_SECONDS=$($readTimer.Elapsed.TotalSeconds)"
    if ($readExit -ne 0) { throw 'Full flash read failed; backup is not verified.' }
    $backupFile = Get-Item -LiteralPath $backupPath
    if ($backupFile.Length -ne 16777216) { throw 'Backup size is not exactly 16 MiB.' }
    $backupHash = (Get-FileHash -LiteralPath $backupPath -Algorithm SHA256).Hash.ToLowerInvariant()
    Write-Output "BACKUP_PATH=$backupPath BACKUP_BYTES=$($backupFile.Length) SHA256=$backupHash"

    & $esptoolPath --chip esp32s3 --port $targetPort --before default-reset --after no-reset --no-stub verify-flash --flash-size keep --flash-mode keep --flash-freq keep 0 $backupPath 2>&1 |
        Tee-Object -FilePath (Join-Path $logRoot 'com17_verify_20261006.log')
    $verifyExit = $LASTEXITCODE
    Write-Output "VERIFY_EXIT=$verifyExit"
    if ($verifyExit -ne 0) { throw 'ROM digest verification failed; do not treat backup as verified.' }
    $completed = $true
}
finally {
    & $esptoolPath --chip esp32s3 --port $targetPort --before default-reset --after hard-reset --no-stub read-mac 2>&1 |
        Tee-Object -FilePath (Join-Path $logRoot 'com17_restore_run_20261006.log')
    $resetExit = $LASTEXITCODE
    $resetSucceeded = $resetExit -eq 0
    Write-Output "RESET_EXIT=$resetExit"
}
if (-not $completed -or -not $resetSucceeded) { exit 1 }
Write-Output 'BACKUP_AND_ROM_DIGEST_VERIFICATION_PASSED; ORIGINAL_APP_RESET_REQUESTED; NO_FLASH_WRITE'
