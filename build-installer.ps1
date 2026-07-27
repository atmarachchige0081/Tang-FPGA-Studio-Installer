[CmdletBinding()]
param(
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string] $Version = '1.2.0',
    [switch] $SkipPythonInstall,
    [switch] $SkipInnoInstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
$venv = Join-Path $root '.venv'
$venvPython = Join-Path $venv 'Scripts\python.exe'
$pyInstaller = Join-Path $venv 'Scripts\pyinstaller.exe'
$appDist = Join-Path $root 'build\app-dist'
$pyWork = Join-Path $root 'build\pyinstaller'
$specDir = Join-Path $root 'build\spec'
$installerName = "TangPrimerFPGAStudio-Setup-$Version.exe"

function Assert-InBuildRoot {
    param([Parameter(Mandatory)] [string] $Path)
    $resolved = [IO.Path]::GetFullPath($Path)
    if (-not $resolved.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to modify a path outside the installer workspace: $resolved"
    }
}

function Clear-BuildDirectory {
    param([Parameter(Mandatory)] [string] $Path)
    Assert-InBuildRoot $Path
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host 'Creating isolated Python build environment...'
    & python -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw "python -m venv failed with exit code $LASTEXITCODE" }
}

if (-not $SkipPythonInstall) {
    Write-Host 'Installing pinned packaging dependencies...'
    & $venvPython -m pip install --disable-pip-version-check -r (Join-Path $root 'requirements-build.txt')
    if ($LASTEXITCODE -ne 0) { throw "pip failed with exit code $LASTEXITCODE" }
}

& $venvPython (Join-Path $root 'generate_assets.py') --version $Version
if ($LASTEXITCODE -ne 0) { throw "Icon generation failed with exit code $LASTEXITCODE" }

Clear-BuildDirectory $appDist
Clear-BuildDirectory $pyWork
Clear-BuildDirectory $specDir

$payload = Join-Path $root 'payload\workspace'
$source = Join-Path $root 'src\launcher.py'
$icon = Join-Path $root 'assets\TangPrimerFPGAStudio.ico'
$versionInfo = Join-Path $root 'assets\version_info.txt'
$dataArgument = '{0};workspace-template' -f $payload

Write-Host 'Freezing the Python/Tkinter application...'
& $pyInstaller `
    '--noconfirm' `
    '--clean' `
    '--windowed' `
    '--name' 'TangPrimerFPGAStudio' `
    '--icon' $icon `
    '--version-file' $versionInfo `
    '--paths' (Join-Path $root 'src') `
    '--add-data' $dataArgument `
    '--contents-directory' 'internal' `
    '--distpath' $appDist `
    '--workpath' $pyWork `
    '--specpath' $specDir `
    $source
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

$isccCandidates = @(
    (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
    (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
    (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe')
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

if (-not $isccCandidates -and -not $SkipInnoInstall) {
    Write-Host 'Installing Inno Setup for the packaging step...'
    & winget install --id JRSoftware.InnoSetup --exact --silent `
        --accept-package-agreements --accept-source-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup installation failed with exit code $LASTEXITCODE" }
    $isccCandidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
        (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe')
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
}

if (-not $isccCandidates) {
    throw 'ISCC.exe was not found. Install Inno Setup 6 or rerun without -SkipInnoInstall.'
}

$iscc = @($isccCandidates)[0]
Write-Host 'Compiling the single-file Windows installer...'
& $iscc '/Q' "/DMyAppVersion=$Version" (Join-Path $root 'installer\TangPrimerFPGAStudio.iss')
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed with exit code $LASTEXITCODE" }

$installer = Join-Path $root "dist\$installerName"
if (-not (Test-Path -LiteralPath $installer)) {
    throw "Expected installer was not created: $installer"
}
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $installer).Hash.ToLowerInvariant()
$sizeMB = [math]::Round((Get-Item -LiteralPath $installer).Length / 1MB, 1)
$checksumPath = "$installer.sha256"
Set-Content -LiteralPath $checksumPath -Encoding ascii `
    -Value ("{0} *{1}" -f $hash, (Split-Path -Leaf $installer))
Write-Host "Installer ready: $installer" -ForegroundColor Green
Write-Host "Size: $sizeMB MB"
Write-Host "SHA-256: $hash"
Write-Host "Checksum file: $checksumPath"
