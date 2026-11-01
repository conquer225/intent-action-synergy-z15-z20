# Run only after explicit authorization to replace the spare COM17 firmware.
param(
    [string]$ManifestName = 'com17_ble_mouse_preflash_20261006.json',
    [string]$LogPrefix = 'com17_ble_mouse'
)
$ErrorActionPreference = 'Stop'
$esptoolPath = 'C:\Users\lenovo\AppData\Local\Arduino15\packages\esp32\tools\esptool_py\5.3.1\esptool.exe'
$logRoot = Join-Path $PSScriptRoot 'output'
if ([IO.Path]::GetFileName($ManifestName) -ne $ManifestName -or $LogPrefix -notmatch '^[a-zA-Z0-9_]+$') { throw 'Invalid manifest or log name.' }
$manifest = Get-Content -LiteralPath (Join-Path $logRoot $ManifestName) -Raw | ConvertFrom-Json
foreach ($phoneLogSuffix in @('rom_id','write','verify','reset')) {
    if (Test-Path -LiteralPath (Join-Path $logRoot ($LogPrefix + '_' + $phoneLogSuffix + '_20261006.log'))) { throw 'Deployment logs already exist; do not overwrite an earlier run.' }
}
$target = @(Get-PnpDevice -PresentOnly | Where-Object { $_.FriendlyName -match '\(COM17\)$' })
if ($target.Count -ne 1) { throw 'COM17 missing or ambiguous; no hardware action taken.' }
$parentId = (Get-PnpDeviceProperty -InstanceId $target[0].InstanceId -KeyName 'DEVPKEY_Device_Parent').Data
if ($parentId -notlike '*\28:84:85:60:CD:9C') { throw 'COM17 USB identity mismatch; no hardware action taken.' }
foreach ($item in @($manifest.application, $manifest.original_full_backup, $manifest.original_slot_recovery)) {
    if ((Get-FileHash -LiteralPath $item.path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $item.sha256) {
        throw 'Artifact or recovery backup hash mismatch; no hardware action taken.'
    }
}
foreach ($property in $manifest.source_sha256.PSObject.Properties) {
    $sourcePath = Join-Path $PSScriptRoot $property.Name
    if ((Get-FileHash -LiteralPath $sourcePath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $property.Value) {
        throw 'Source changed since preflash preparation; no hardware action taken.'
    }
}
if ($manifest.application.offset -ne 65536 -or $manifest.application.bytes -gt 3342336) {
    throw 'Unexpected application range; no hardware action taken.'
}

$env:PYTHONUNBUFFERED = '1'
$completed = $false
try {
    & $esptoolPath --chip esp32s3 --port COM17 --before default-reset --after no-reset --no-stub flash-id 2>&1 |
        Tee-Object -FilePath (Join-Path $logRoot ($LogPrefix + '_rom_id_20261006.log'))
    if ($LASTEXITCODE -ne 0) { throw 'ROM identity read failed; application not written.' }
    $identity = Get-Content -LiteralPath (Join-Path $logRoot ($LogPrefix + '_rom_id_20261006.log')) -Raw
    if ($identity -notmatch 'MAC:\s+28:84:85:60:cd:9c' -or $identity -notmatch 'Detected flash size: 16MB') {
        throw 'ROM device identity/capacity mismatch; application not written.'
    }
    & $esptoolPath --chip esp32s3 --port COM17 --before no-reset --after no-reset write-flash --flash-mode keep --flash-freq keep --flash-size keep 0x10000 $manifest.application.path 2>&1 |
        Tee-Object -FilePath (Join-Path $logRoot ($LogPrefix + '_write_20261006.log'))
    if ($LASTEXITCODE -ne 0) { throw 'Application write failed; recovery remains available and is not automatically written.' }
    & $esptoolPath --chip esp32s3 --port COM17 --before default-reset --after no-reset --no-stub verify-flash --flash-mode keep --flash-freq keep --flash-size keep 0x10000 $manifest.application.path 2>&1 |
        Tee-Object -FilePath (Join-Path $logRoot ($LogPrefix + '_verify_20261006.log'))
    if ($LASTEXITCODE -ne 0) { throw 'New application ROM digest mismatch; recovery remains available.' }
    $completed = $true
}
finally {
    & $esptoolPath --chip esp32s3 --port COM17 --before default-reset --after hard-reset --no-stub read-mac 2>&1 |
        Tee-Object -FilePath (Join-Path $logRoot ($LogPrefix + '_reset_20261006.log'))
    $resetExit = $LASTEXITCODE
    Write-Output "RESET_EXIT=$resetExit"
}
if (-not $completed -or $resetExit -ne 0) { exit 1 }
Write-Output 'COM17_APPLICATION_WRITE_AND_ROM_DIGEST_VERIFICATION_PASSED; BLE_RUNTIME_NOT_YET_VERIFIED'
