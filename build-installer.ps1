[CmdletBinding()]
param(
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string] $Version = '2.0.0',
    [switch] $SkipPythonInstall,
    [switch] $SkipNodeInstall,
    [switch] $SkipInnoInstall,
    [string] $NativeBinary
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
$venv = Join-Path $root '.venv'
$venvPython = Join-Path $venv 'Scripts\python.exe'
$appDist = Join-Path $root 'build\app-dist'
$appDirectory = Join-Path $appDist 'TangFPGAStudio'
$nativeStudio = Join-Path $root 'native\studio'
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
    if (Test-Path -LiteralPath $Path) { Remove-Item -LiteralPath $Path -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host 'Creating isolated asset-build environment...'
    & python -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw "python -m venv failed with exit code $LASTEXITCODE" }
}
if (-not $SkipPythonInstall) {
    & $venvPython -m pip install --disable-pip-version-check -r (Join-Path $root 'requirements-build.txt')
    if ($LASTEXITCODE -ne 0) { throw "pip failed with exit code $LASTEXITCODE" }
}
& $venvPython (Join-Path $root 'generate_assets.py') --version $Version
if ($LASTEXITCODE -ne 0) { throw "Icon generation failed with exit code $LASTEXITCODE" }

Clear-BuildDirectory $appDist
New-Item -ItemType Directory -Force -Path $appDirectory | Out-Null

$builtBinary = $null
if ($NativeBinary) {
    $builtBinary = [IO.Path]::GetFullPath($NativeBinary)
    if (-not (Test-Path -LiteralPath $builtBinary -PathType Leaf)) { throw "Native binary was not found: $builtBinary" }
    Write-Host "Using prebuilt native Studio: $builtBinary" -ForegroundColor Cyan
} else {
    if (-not (Test-Path -LiteralPath (Join-Path $nativeStudio 'package-lock.json'))) { throw 'Synchronized native Studio source is missing.' }
    Push-Location $nativeStudio
    try {
        if (-not $SkipNodeInstall) {
            & npm.cmd ci --no-audit --no-fund
            if ($LASTEXITCODE -ne 0) { throw "npm ci failed with exit code $LASTEXITCODE" }
        }
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw "Native frontend build failed with exit code $LASTEXITCODE" }
        $cargo = Get-Command cargo.exe -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Source
        if (-not $cargo) {
            $candidate = Join-Path $env:USERPROFILE '.cargo\bin\cargo.exe'
            if (Test-Path -LiteralPath $candidate) { $cargo = $candidate }
        }
        if (-not $cargo) { throw 'Cargo was not found on the Windows build machine.' }
        & $cargo build --release --manifest-path 'src-tauri\Cargo.toml'
        if ($LASTEXITCODE -ne 0) { throw "Native Rust build failed with exit code $LASTEXITCODE" }
        $builtBinary = Join-Path $nativeStudio 'src-tauri\target\release\fpga-studio.exe'
    } finally { Pop-Location }
}

Copy-Item -LiteralPath $builtBinary -Destination (Join-Path $appDirectory 'fpga-studio.exe') -Force
Copy-Item -LiteralPath (Join-Path $root 'src\Prepare-Workspace.ps1') -Destination $appDirectory -Force
Copy-Item -LiteralPath (Join-Path $root 'payload\workspace') -Destination (Join-Path $appDirectory 'workspace-template') -Recurse -Force

$isccCandidates = @(
    (Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'),
    (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'),
    (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe')
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
if (-not $isccCandidates -and -not $SkipInnoInstall) {
    & winget install --id JRSoftware.InnoSetup --exact --silent --accept-package-agreements --accept-source-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup installation failed with exit code $LASTEXITCODE" }
    $isccCandidates = @((Join-Path $env:LOCALAPPDATA 'Programs\Inno Setup 6\ISCC.exe'), (Join-Path ${env:ProgramFiles(x86)} 'Inno Setup 6\ISCC.exe'), (Join-Path $env:ProgramFiles 'Inno Setup 6\ISCC.exe')) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
}
if (-not $isccCandidates) { throw 'ISCC.exe was not found. Install Inno Setup 6 or rerun without -SkipInnoInstall.' }

Write-Host 'Compiling the native one-file Windows installer...'
$iscc = @($isccCandidates)[0]
& $iscc '/Q' "/DMyAppVersion=$Version" (Join-Path $root 'installer\TangPrimerFPGAStudio.iss')
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed with exit code $LASTEXITCODE" }
$installer = Join-Path $root "dist\$installerName"
if (-not (Test-Path -LiteralPath $installer)) { throw "Expected installer was not created: $installer" }
$hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $installer).Hash.ToLowerInvariant()
Set-Content -LiteralPath "$installer.sha256" -Encoding ascii -Value ("{0} *{1}" -f $hash, (Split-Path -Leaf $installer))
Write-Host "Installer ready: $installer" -ForegroundColor Green
Write-Host ("Size: {0:N1} MB" -f ((Get-Item -LiteralPath $installer).Length / 1MB))
Write-Host "SHA-256: $hash"
