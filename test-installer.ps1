[CmdletBinding()]
param(
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string] $Version = '2.0.0',
    [switch] $Install
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
$appDirectory = Join-Path $root 'build\app-dist\TangFPGAStudio'
$app = Join-Path $appDirectory 'fpga-studio.exe'
$installer = Join-Path $root "dist\TangPrimerFPGAStudio-Setup-$Version.exe"
$testWorkspace = Join-Path $root 'build\test-workspace'
if (-not (Test-Path -LiteralPath $app)) { throw "Packaged native application not found: $app" }
if (-not (Test-Path -LiteralPath $installer)) { throw "Installer not found: $installer" }

if (Test-Path -LiteralPath $testWorkspace) {
    $resolved = [IO.Path]::GetFullPath($testWorkspace)
    if (-not $resolved.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) { throw "Unsafe test path: $resolved" }
    Remove-Item -LiteralPath $testWorkspace -Recurse -Force
}
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $appDirectory 'Prepare-Workspace.ps1') -Template (Join-Path $appDirectory 'workspace-template') -Destination $testWorkspace
if ($LASTEXITCODE -ne 0) { throw 'Workspace preparation smoke test failed.' }

Write-Host 'Running packaged native workspace/provider smoke test...'
$arguments = @('--workspace', ('"' + $testWorkspace + '"'), '--smoke-test')
$process = Start-Process -FilePath $app -ArgumentList $arguments -WorkingDirectory $testWorkspace -Wait -PassThru -WindowStyle Hidden
if ($process.ExitCode -ne 0) { throw "Native smoke test failed with exit code $($process.ExitCode)" }

$hashFile = "$installer.sha256"
if (-not (Test-Path -LiteralPath $hashFile)) { throw 'Installer checksum file is missing.' }
$expected = ((Get-Content -LiteralPath $hashFile -Raw).Trim() -split '\s+')[0]
$actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $installer).Hash.ToLowerInvariant()
if ($actual -ne $expected.ToLowerInvariant()) { throw 'Installer checksum does not match.' }

if ($Install) {
    Write-Host 'Installing silently for shortcut and installed-layout validation...'
    $installProcess = Start-Process -FilePath $installer -ArgumentList '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /TASKS="desktopicon"' -Wait -PassThru
    if ($installProcess.ExitCode -ne 0) { throw "Installer test failed with exit code $($installProcess.ExitCode)" }
    $installedApp = Join-Path $env:ProgramFiles 'Tang Primer FPGA Studio\fpga-studio.exe'
    $desktopCandidates = @((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Tang FPGA Studio.lnk'), (Join-Path ([Environment]::GetFolderPath('CommonDesktopDirectory')) 'Tang FPGA Studio.lnk'))
    if (-not (Test-Path -LiteralPath $installedApp)) { throw "Installed EXE missing: $installedApp" }
    $desktopShortcut = $desktopCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $desktopShortcut) { throw "Desktop shortcut missing. Checked: $($desktopCandidates -join ', ')" }
}
Write-Host 'NATIVE INSTALLER TESTS PASSED' -ForegroundColor Green
