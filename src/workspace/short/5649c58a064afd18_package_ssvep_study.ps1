# Create a new, verified recovery artifact; never overwrite an existing package.
$ErrorActionPreference = 'Stop'
$taskRoot = 'D:\ican\codex_project'
$taskOutput = Join-Path $taskRoot 'eeg_apps_z15\output\ssvep_free_study_20261003'
$taskPackage = Join-Path $taskOutput 'package'
$taskZip = Join-Path $taskOutput 'guardianloop_ssvep_study_arm_recovery_20261003.zip'
$taskReport = Join-Path $taskOutput 'recovery_zip_verification.json'
if ((Test-Path -LiteralPath $taskZip) -or (Test-Path -LiteralPath $taskReport)) {
    throw 'Recovery artifacts already exist; preserve them.'
}
$taskDeployment = Get-Content -LiteralPath (Join-Path $taskOutput 'deployment.json') -Raw | ConvertFrom-Json
$taskSoak = Get-Content -LiteralPath (Join-Path $taskOutput 'no_data_soak.json') -Raw | ConvertFrom-Json
$taskRefusal = Get-Content -LiteralPath (Join-Path $taskOutput 'no_data_refusal.json') -Raw | ConvertFrom-Json
if ($taskDeployment.phase -ne 'verified' -or !$taskSoak.passed -or !$taskRefusal.passed) {
    throw 'Deployment and no-data checks must pass before packaging.'
}
$taskLedger = Get-Content -LiteralPath (Join-Path $taskPackage 'transaction.json') -Raw | ConvertFrom-Json
foreach ($taskProperty in $taskLedger.runtime_sha256.PSObject.Properties) {
    $taskHash = (Get-FileHash -LiteralPath (Join-Path $taskPackage ('runtime\' + $taskProperty.Name)) -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($taskHash -ne $taskProperty.Value) { throw ('Runtime hash mismatch: ' + $taskProperty.Name) }
}
$taskEntries = [System.Collections.Generic.List[object]]::new()
foreach ($taskFile in Get-ChildItem -LiteralPath $taskPackage -Recurse -File) {
    $taskRelative = $taskFile.FullName.Substring($taskPackage.Length + 1)
    if ($taskRelative -match '(^|[\\/])__pycache__([\\/]|$)' -or $taskFile.Extension -eq '.pyc') { continue }
    if ($taskFile.Attributes -band [System.IO.FileAttributes]::ReparsePoint) { throw 'Unexpected link in bundle' }
    $taskEntries.Add([pscustomobject]@{ Source=$taskFile.FullName; Entry=$taskRelative.Replace('\','/') })
}
foreach ($taskFile in Get-ChildItem -LiteralPath $taskOutput -File) {
    if ($taskFile.Extension -in '.json','.log') {
        $taskEntries.Add([pscustomobject]@{ Source=$taskFile.FullName; Entry=('evidence/' + $taskFile.Name) })
    }
}
$taskExtras = @{
    'docs/SSVEP_FREE_STUDY_20261003.md' = Join-Path $taskRoot 'docs\SSVEP_FREE_STUDY_20261003.md'
    'docs/README.md' = Join-Path $taskRoot 'pynq_guardianloop\README.md'
    'tools/audit_ssvep_study.py' = Join-Path $taskRoot 'pynq_guardianloop\audit_ssvep_study.py'
    'evidence/PLAN.json' = Join-Path $taskRoot 'eeg_apps_z15\output\ssvep_free_study_plan_20261003.json'
}
foreach ($taskKey in $taskExtras.Keys) {
    $taskEntries.Add([pscustomobject]@{ Source=$taskExtras[$taskKey]; Entry=$taskKey })
}
if (($taskEntries.Entry | Sort-Object -Unique).Count -ne $taskEntries.Count) { throw 'Duplicate ZIP entries' }
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$taskSourceHashes = @{}
$taskArchive = [System.IO.Compression.ZipFile]::Open($taskZip, [System.IO.Compression.ZipArchiveMode]::Create)
try {
    foreach ($taskEntry in $taskEntries) {
        $taskSourceHashes[$taskEntry.Entry] = (Get-FileHash -LiteralPath $taskEntry.Source -Algorithm SHA256).Hash.ToLowerInvariant()
        [void][System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($taskArchive, $taskEntry.Source, $taskEntry.Entry)
    }
} finally { $taskArchive.Dispose() }
$taskArchive = [System.IO.Compression.ZipFile]::OpenRead($taskZip)
$taskVerified = [System.Collections.Generic.List[object]]::new()
try {
    foreach ($taskEntry in $taskArchive.Entries) {
        $taskStream = $taskEntry.Open()
        $taskHasher = [System.Security.Cryptography.SHA256]::Create()
        try { $taskHash = [BitConverter]::ToString($taskHasher.ComputeHash($taskStream)).Replace('-','').ToLowerInvariant() }
        finally { $taskStream.Dispose(); $taskHasher.Dispose() }
        if ($taskHash -ne $taskSourceHashes[$taskEntry.FullName]) { throw ('ZIP content mismatch: ' + $taskEntry.FullName) }
        $taskVerified.Add([pscustomobject]@{ entry=$taskEntry.FullName; bytes=$taskEntry.Length; sha256=$taskHash })
    }
} finally { $taskArchive.Dispose() }
$taskZipHash = (Get-FileHash -LiteralPath $taskZip -Algorithm SHA256).Hash.ToLowerInvariant()
$taskResult = [ordered]@{
    passed=$true; zip=$taskZip; sha256=$taskZipHash; entry_count=$taskVerified.Count
    entries=$taskVerified; excludes=@('SSH credentials','human EEG','__pycache__','pyc files')
    scope='ARM application transaction/recovery, not an SD image or rebuildable FPGA project'
}
$taskJson = $taskResult | ConvertTo-Json -Depth 6
[System.IO.File]::WriteAllText($taskReport, $taskJson, [System.Text.UTF8Encoding]::new($false))
[pscustomobject]@{ passed=$true; entries=$taskVerified.Count; sha256=$taskZipHash; bytes=(Get-Item -LiteralPath $taskZip).Length } | ConvertTo-Json
