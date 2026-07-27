[CmdletBinding()]
param(
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string] $Version = '1.2.0',
    [switch] $Install
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
$app = Join-Path $root 'build\app-dist\TangPrimerFPGAStudio\TangPrimerFPGAStudio.exe'
$installer = Join-Path $root "dist\TangPrimerFPGAStudio-Setup-$Version.exe"
$testWorkspace = Join-Path $root 'build\test-workspace'

if (-not (Test-Path -LiteralPath $app)) { throw "Packaged application not found: $app" }
if (-not (Test-Path -LiteralPath $installer)) { throw "Installer not found: $installer" }

Write-Host 'Running packaged dark-theme UI smoke test...'
$darkArguments = '--workspace "{0}" --ui-smoke-test --theme dark --project projects/01_button_led_pwm' -f $testWorkspace
$darkProcess = Start-Process -FilePath $app -ArgumentList $darkArguments -Wait -PassThru
if ($darkProcess.ExitCode -ne 0) { throw "Dark UI smoke test failed with exit code $($darkProcess.ExitCode)" }

Write-Host 'Running packaged light-theme UI smoke test...'
$lightArguments = '--workspace "{0}" --ui-smoke-test --theme light --project projects/01_button_led_pwm' -f $testWorkspace
$lightProcess = Start-Process -FilePath $app -ArgumentList $lightArguments -Wait -PassThru
if ($lightProcess.ExitCode -ne 0) { throw "Light UI smoke test failed with exit code $($lightProcess.ExitCode)" }

if ($Install) {
    Write-Host 'Installing silently for shortcut and installed-layout validation...'
    $installProcess = Start-Process -FilePath $installer -ArgumentList '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /TASKS="desktopicon"' -Wait -PassThru
    if ($installProcess.ExitCode -ne 0) { throw "Installer test failed with exit code $($installProcess.ExitCode)" }
    $installedApp = Join-Path $env:ProgramFiles 'Tang Primer FPGA Studio\TangPrimerFPGAStudio.exe'
    $desktopCandidates = @(
        (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Tang Primer FPGA Studio.lnk'),
        (Join-Path ([Environment]::GetFolderPath('CommonDesktopDirectory')) 'Tang Primer FPGA Studio.lnk')
    )
    $desktopShortcut = $desktopCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not (Test-Path -LiteralPath $installedApp)) { throw "Installed EXE missing: $installedApp" }
    if (-not $desktopShortcut) { throw "Desktop shortcut missing. Checked: $($desktopCandidates -join ', ')" }
    Write-Host "Installed application: $installedApp" -ForegroundColor Green
    Write-Host "Desktop shortcut: $desktopShortcut" -ForegroundColor Green
}

Write-Host 'INSTALLER TESTS PASSED' -ForegroundColor Green
