[CmdletBinding()]
param(
    [string] $InstallBase = 'C:\fpga-tools',
    [switch] $SkipVsCodeExtension
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Version = '2026-07-26'
$AssetName = 'oss-cad-suite-windows-x64-20260726.exe'
$AssetUrl = "https://github.com/YosysHQ/oss-cad-suite-build/releases/download/$Version/$AssetName"
$ExpectedSha256 = 'df275642362cd27f1cb90a7408818b6c2ed5292c974a754074d41c9250487ecc'
$DownloadDir = Join-Path $InstallBase 'downloads'
$Installer = Join-Path $DownloadDir $AssetName
$VersionRoot = Join-Path $InstallBase $Version
$ToolchainRoot = Join-Path $VersionRoot 'oss-cad-suite'
$EnvironmentScript = Join-Path $ToolchainRoot 'environment.ps1'
$ZadigVersion = '2.9'
$ZadigPath = Join-Path $InstallBase "zadig-$ZadigVersion.exe"
$ZadigUrl = 'https://github.com/pbatard/libwdi/releases/download/v1.5.1/zadig-2.9.exe'
$ZadigSha256 = '4ecaa95df3da3621486a043aef8b3050b8bafe7c901402871e816229ef82039b'

if (Test-Path -LiteralPath $EnvironmentScript) {
    Write-Host "OSS CAD Suite $Version is already installed at $ToolchainRoot" -ForegroundColor Green
} else {
    New-Item -ItemType Directory -Force -Path $DownloadDir, $VersionRoot | Out-Null

    $needsDownload = -not (Test-Path -LiteralPath $Installer)
    if (-not $needsDownload) {
        $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Installer).Hash.ToLowerInvariant()
        $needsDownload = $actualHash -ne $ExpectedSha256
    }

    if ($needsDownload) {
        Write-Host "Downloading $AssetName..."
        $curl = Get-Command 'curl.exe' -ErrorAction SilentlyContinue
        if ($curl) {
            & $curl.Source '-L' '--fail' '--retry' '3' '--output' $Installer $AssetUrl
            if ($LASTEXITCODE -ne 0) { throw "curl failed with exit code $LASTEXITCODE" }
        } else {
            Invoke-WebRequest -UseBasicParsing -Uri $AssetUrl -OutFile $Installer
        }
    }

    $actualHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Installer).Hash.ToLowerInvariant()
    if ($actualHash -ne $ExpectedSha256) {
        throw "Checksum mismatch for $Installer. Expected $ExpectedSha256, got $actualHash."
    }

    Write-Host "Extracting to $VersionRoot..."
    & $Installer '-y' "-o$VersionRoot"
    if ($LASTEXITCODE -ne 0) { throw "Extraction failed with exit code $LASTEXITCODE" }
    if (-not (Test-Path -LiteralPath $EnvironmentScript)) {
        throw "Extraction completed, but $EnvironmentScript was not created."
    }
    Write-Host "Installed OSS CAD Suite $Version at $ToolchainRoot" -ForegroundColor Green
}

$zadigNeedsDownload = -not (Test-Path -LiteralPath $ZadigPath)
if (-not $zadigNeedsDownload) {
    $zadigHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ZadigPath).Hash.ToLowerInvariant()
    $zadigNeedsDownload = $zadigHash -ne $ZadigSha256
}
if ($zadigNeedsDownload) {
    New-Item -ItemType Directory -Force -Path $InstallBase | Out-Null
    Write-Host "Downloading signed Zadig $ZadigVersion driver helper..."
    $curl = Get-Command 'curl.exe' -ErrorAction SilentlyContinue
    if ($curl) {
        & $curl.Source '-L' '--fail' '--retry' '3' '--output' $ZadigPath $ZadigUrl
        if ($LASTEXITCODE -ne 0) { throw "Zadig download failed with exit code $LASTEXITCODE" }
    } else {
        Invoke-WebRequest -UseBasicParsing -Uri $ZadigUrl -OutFile $ZadigPath
    }
}
$zadigHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ZadigPath).Hash.ToLowerInvariant()
if ($zadigHash -ne $ZadigSha256) {
    throw "Checksum mismatch for $ZadigPath. Expected $ZadigSha256, got $zadigHash."
}
$zadigSignature = Get-AuthenticodeSignature -FilePath $ZadigPath
if ($zadigSignature.Status -ne 'Valid' -or $zadigSignature.SignerCertificate.Subject -notmatch 'Akeo Consulting') {
    throw "The Authenticode signature on $ZadigPath is not valid for Akeo Consulting."
}
Write-Host "Signed JTAG driver helper ready at $ZadigPath" -ForegroundColor Green

if (-not $SkipVsCodeExtension) {
    $code = Get-Command 'code' -ErrorAction SilentlyContinue
    if ($code) {
        & $code.Source '--install-extension' 'mshr-h.VerilogHDL' '--force'
        if ($LASTEXITCODE -ne 0) {
            Write-Warning 'VS Code HDL extension installation failed; the command-line FPGA tools are still ready.'
        }
    } else {
        Write-Warning "VS Code's 'code' command was not found; install the recommended extension from .vscode/extensions.json."
    }
}

Write-Host "Run '.\fpga.ps1 doctor' to validate the installation. Use '.\fpga.ps1 driver' if JTAG needs WinUSB."
