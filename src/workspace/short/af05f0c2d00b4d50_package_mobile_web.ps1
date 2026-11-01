$ErrorActionPreference = 'Stop'
$taskRoot = 'D:\ican\codex_project'
$taskOutput = Join-Path $taskRoot 'eeg_apps_z15\output\mobile_web_deploy_20261003_223346'
$taskPackage = Join-Path $taskOutput 'recovery_verified'
$taskZipPath = Join-Path $taskOutput 'guardianloop_mobile_web_recovery_verified_20261003.zip'
if ((Test-Path -LiteralPath $taskPackage) -or (Test-Path -LiteralPath $taskZipPath)) { throw 'Preserve existing recovery artifact' }
$taskResult = Get-Content -LiteralPath (Join-Path $taskOutput 'result.json') -Raw | ConvertFrom-Json
if (!$taskResult.passed -or $taskResult.phase -ne 'verified') { throw 'Board postflight must pass first' }
New-Item -ItemType Directory -Path $taskPackage | Out-Null
$taskRuntime = Join-Path $taskPackage 'runtime'
$taskOriginalRuntime = Join-Path $taskRoot 'eeg_apps_z15\output\ssvep_free_study_20261003\package\runtime'
$taskOldManifest = Get-Content -LiteralPath (Join-Path $taskOriginalRuntime 'release_manifest.json') -Raw | ConvertFrom-Json
New-Item -ItemType Directory -Path $taskRuntime | Out-Null
foreach ($taskProperty in $taskOldManifest.files.PSObject.Properties) {
    Copy-Item -LiteralPath (Join-Path $taskOriginalRuntime $taskProperty.Name) -Destination (Join-Path $taskRuntime $taskProperty.Name)
}
foreach ($taskName in @('guardianloop_web.py','mobile.html','mobile.js','release_manifest.json')) {
    Copy-Item -LiteralPath (Join-Path $taskOutput ('runtime\'+$taskName)) -Destination (Join-Path $taskRuntime $taskName)
}
$taskManifest = Get-Content -LiteralPath (Join-Path $taskRuntime 'release_manifest.json') -Raw | ConvertFrom-Json
foreach ($taskProperty in $taskManifest.files.PSObject.Properties) {
    if ((Get-FileHash -LiteralPath (Join-Path $taskRuntime $taskProperty.Name) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $taskProperty.Value) {
        throw ('Frozen runtime mismatch: '+$taskProperty.Name)
    }
}
Copy-Item -LiteralPath (Join-Path $taskOutput 'backup') -Destination (Join-Path $taskPackage 'web_rollback') -Recurse
New-Item -ItemType Directory -Path (Join-Path $taskPackage 'evidence'), (Join-Path $taskPackage 'docs') | Out-Null
foreach ($taskName in @('preflight.json','expected.json','result.json','state.json','run.log')) {
    Copy-Item -LiteralPath (Join-Path $taskOutput $taskName) -Destination (Join-Path $taskPackage 'evidence')
}
Copy-Item -LiteralPath (Join-Path $taskRoot 'docs\ANDROID_MOBILE_WEB_20261003.md') -Destination (Join-Path $taskPackage 'docs')
Compress-Archive -LiteralPath $taskPackage -DestinationPath $taskZipPath
Add-Type -AssemblyName System.IO.Compression.FileSystem
$taskZip = [System.IO.Compression.ZipFile]::OpenRead($taskZipPath)
try {
    foreach ($taskEntry in $taskZip.Entries) {
        $taskSource = Join-Path $taskOutput $taskEntry.FullName
        $taskStream = $taskEntry.Open()
        $taskHasher = [System.Security.Cryptography.SHA256]::Create()
        try {
            $taskDigest = [BitConverter]::ToString($taskHasher.ComputeHash($taskStream)).Replace('-','')
            if ($taskDigest -ne (Get-FileHash -LiteralPath $taskSource -Algorithm SHA256).Hash) { throw ('ZIP mismatch: '+$taskEntry.FullName) }
        } finally { $taskStream.Dispose(); $taskHasher.Dispose() }
    }
    [pscustomobject]@{verified=$true; runtime_files=@($taskManifest.files.PSObject.Properties).Count;
        entries=$taskZip.Entries.Count; sha256=(Get-FileHash -LiteralPath $taskZipPath -Algorithm SHA256).Hash;
        zip=$taskZipPath; bytes=(Get-Item -LiteralPath $taskZipPath).Length} | ConvertTo-Json
} finally { $taskZip.Dispose() }
