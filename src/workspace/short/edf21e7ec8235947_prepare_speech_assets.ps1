param(
    [string]$OutputDirectory = (Join-Path $PSScriptRoot 'audio_assets')
)
$ErrorActionPreference = 'Stop'
$target = [System.IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $target | Out-Null
$speaker = New-Object -ComObject SAPI.SpVoice
$voices = $speaker.GetVoices()
$chinese = $null
for ($i = 0; $i -lt $voices.Count; $i++) {
    if ($voices.Item($i).GetDescription() -eq 'Microsoft Huihui Desktop - Chinese (Simplified)') {
        $chinese = $voices.Item($i)
    }
}
if ($null -eq $chinese) { throw 'The installed Huihui Chinese synthesis voice is required.' }
$speaker.Voice = $chinese
$speaker.Rate = -1
$speaker.Volume = 70
$phrases = @(
    @{ File = 'need_water.wav'; Text = -join [char[]](0x6211,0x60f3,0x559d,0x6c34,0x3002) },
    @{ File = 'need_help.wav'; Text = -join [char[]](0x6211,0x9700,0x8981,0x5e2e,0x52a9,0x3002) }
)
foreach ($phrase in $phrases) {
    $path = Join-Path $target $phrase.File
    if (Test-Path -LiteralPath $path) { throw "Refuse to overwrite: $path" }
    $stream = New-Object -ComObject SAPI.SpFileStream
    $stream.Format.Type = 22 # 22.05 kHz, 16-bit mono PCM
    $stream.Open($path, 3, $false)
    try {
        $speaker.AudioOutputStream = $stream
        $null = $speaker.Speak($phrase.Text, 0)
    } finally {
        $stream.Close()
    }
}
Write-Output "Synthesized WAV files only; no speaker playback: $target"
