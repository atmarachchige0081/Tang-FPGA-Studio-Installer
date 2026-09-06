[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
$installerPath = Join-Path $root 'installer\TangPrimerFPGAStudio.iss'
$setupPath = Join-Path $root 'payload\workspace\scripts\setup-toolchain.ps1'

function Assert-Contains {
    param(
        [Parameter(Mandatory)] [string] $Text,
        [Parameter(Mandatory)] [string] $Pattern,
        [Parameter(Mandatory)] [string] $Message
    )
    if ($Text -notmatch $Pattern) { throw $Message }
}

$installer = Get-Content -LiteralPath $installerPath -Raw
$setup = Get-Content -LiteralPath $setupPath -Raw

Assert-Contains $installer 'Name:\s*"toolchain"[^\r\n]*OSS CAD Suite[^\r\n]*Zadig' `
    'The installer must visibly offer the OSS CAD Suite and Zadig dependency task.'
Assert-Contains $installer 'Name:\s*"toolchain"[^\r\n]*Flags:\s*checkedonce' `
    'The dependency task must be selected by default.'
Assert-Contains $installer "WizardIsTaskSelected\('toolchain'\)" `
    'The installer must execute the selected dependency task.'
Assert-Contains $installer 'setup-toolchain\.ps1' `
    'The installer no longer invokes the verified dependency setup script.'
Assert-Contains $installer 'Continue without the FPGA tools\?' `
    'Users who deselect dependencies must receive a clear capability warning.'
Assert-Contains $installer 'Name:\s*"jtagdriver"[^\r\n]*Flags:\s*unchecked' `
    'Zadig driver configuration must remain an explicit opt-in action.'

Assert-Contains $setup 'YosysHQ/oss-cad-suite-build/releases/download' `
    'OSS CAD Suite must be downloaded from the expected upstream release.'
Assert-Contains $setup '\$ExpectedSha256\s*=\s*''[0-9a-f]{64}''' `
    'OSS CAD Suite must have a pinned SHA-256 digest.'
Assert-Contains $setup 'pbatard/libwdi/releases/download' `
    'Zadig must be downloaded from the expected upstream release.'
Assert-Contains $setup '\$ZadigSha256\s*=\s*''[0-9a-f]{64}''' `
    'Zadig must have a pinned SHA-256 digest.'
Assert-Contains $setup 'Get-AuthenticodeSignature' `
    'Zadig must be Authenticode-verified before use.'
Assert-Contains $setup 'Akeo Consulting' `
    'Zadig signature verification must require the expected publisher.'

Write-Host 'INSTALLER DEPENDENCY CONTRACT PASSED' -ForegroundColor Green
