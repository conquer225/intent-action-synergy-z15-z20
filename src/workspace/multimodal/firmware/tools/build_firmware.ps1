[CmdletBinding()]
param(
    [string]$ArduinoCli = '',
    [string]$ArduinoConfig = '',
    [string]$ServoLibrary = ''
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $ArduinoCli) {
    $cliCommand = Get-Command arduino-cli -ErrorAction SilentlyContinue
    if ($cliCommand) { $ArduinoCli = $cliCommand.Source }
    elseif (Test-Path -LiteralPath 'D:\arduino\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe') {
        $ArduinoCli = 'D:\arduino\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe'
    } else { throw 'Pass -ArduinoCli with the installed arduino-cli.exe path.' }
}
if (-not $ArduinoConfig) {
    $candidateConfig = Join-Path $env:USERPROFILE '.arduinoIDE\arduino-cli.yaml'
    if (Test-Path -LiteralPath $candidateConfig) { $ArduinoConfig = $candidateConfig }
}
if (-not $ServoLibrary -and (Test-Path -LiteralPath 'D:\file\01_softwares\arduino\libraries\Servo')) {
    $ServoLibrary = 'D:\file\01_softwares\arduino\libraries\Servo'
}
$targets = @(
    @{ Name='esp32'; Fqbn='esp32:esp32:esp32s3'; Source='esp32\MultiControlS3' },
    @{ Name='esp01'; Fqbn='esp8266:esp8266:generic:eesz=1M64'; Source='esp01\PendulumBridge' },
    @{ Name='nano'; Fqbn='arduino:avr:nano:cpu=atmega328old'; Source='hand_nano\hand_controller' }
)
foreach ($target in $targets) {
    $outputPath = Join-Path $projectRoot ('build\firmware\'+$target.Name)
    New-Item -ItemType Directory -Path $outputPath -Force | Out-Null
    $compileArgs = @('compile','--fqbn',$target.Fqbn,'--output-dir',$outputPath)
    if ($ArduinoConfig) { $compileArgs += @('--config-file',$ArduinoConfig) }
    if ($target.Name -eq 'nano' -and $ServoLibrary) { $compileArgs += @('--library',$ServoLibrary) }
    $compileArgs += (Join-Path $projectRoot $target.Source)
    Write-Output ('Building '+$target.Name+'; no upload')
    $previousPreference = $ErrorActionPreference
    try {
        # Windows PowerShell 5 wraps native stderr progress in ErrorRecord objects.
        # The compiler exit code, not its progress stream, determines success.
        $ErrorActionPreference = 'Continue'
        $compilerOutput = & $ArduinoCli @compileArgs 2>&1
        $compilerExit = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previousPreference }
    $compilerOutput | ForEach-Object { $_.ToString() } | Tee-Object -FilePath (Join-Path $outputPath 'compile.log')
    if ($compilerExit -ne 0) { throw ('Build failed: '+$target.Name) }
}
Write-Output 'Build complete. Configure WiFi/HandConfig before real hardware use. STM32 is built separately in Keil.'
