[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string] $SourceRoot,

    [Parameter(Mandatory)]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string] $Version
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$installerRoot = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
$upstreamRoot = [IO.Path]::GetFullPath($SourceRoot).TrimEnd('\')
$excludedDirectories = @('.git', '.github', '.fpga-studio', '__pycache__', 'build', 'dist', 'obj_dir')

foreach ($required in @('ide\fpga_ide.py', 'fpga.ps1', 'projects', 'scripts\setup-toolchain.ps1')) {
    if (-not (Test-Path -LiteralPath (Join-Path $upstreamRoot $required))) {
        throw "The upstream checkout is incomplete; missing $required under $upstreamRoot"
    }
}

function Assert-ManagedTarget {
    param([Parameter(Mandatory)] [string] $Path)
    $resolved = [IO.Path]::GetFullPath($Path)
    if (-not $resolved.StartsWith($installerRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to modify a path outside the installer repository: $resolved"
    }
}

function Reset-ManagedDirectory {
    param([Parameter(Mandatory)] [string] $Path)
    Assert-ManagedTarget $Path
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

function Copy-FilteredTree {
    param(
        [Parameter(Mandatory)] [string] $Source,
        [Parameter(Mandatory)] [string] $Destination
    )
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    foreach ($item in Get-ChildItem -LiteralPath $Source -Force) {
        if ($item.PSIsContainer -and $excludedDirectories -contains $item.Name) {
            continue
        }
        $target = Join-Path $Destination $item.Name
        if ($item.PSIsContainer) {
            Copy-FilteredTree -Source $item.FullName -Destination $target
        }
        else {
            Copy-Item -LiteralPath $item.FullName -Destination $target -Force
        }
    }
}

$ideTarget = Join-Path $installerRoot 'src\ide'
$workspaceTarget = Join-Path $installerRoot 'payload\workspace'
$imagesTarget = Join-Path $installerRoot 'docs\images'
Reset-ManagedDirectory $ideTarget
Reset-ManagedDirectory $workspaceTarget
Reset-ManagedDirectory $imagesTarget

Get-ChildItem -LiteralPath (Join-Path $upstreamRoot 'ide') -Filter '*.py' -File | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $ideTarget $_.Name) -Force
}

foreach ($file in @('fpga.ps1', 'fpga.config.psd1', 'INSTALL.md', 'LICENSE', 'README.md')) {
    $source = Join-Path $upstreamRoot $file
    if (Test-Path -LiteralPath $source -PathType Leaf) {
        Copy-Item -LiteralPath $source -Destination (Join-Path $workspaceTarget $file) -Force
    }
}
foreach ($directory in @('constraints', 'projects', 'rtl', 'sim')) {
    $source = Join-Path $upstreamRoot $directory
    if (Test-Path -LiteralPath $source -PathType Container) {
        Copy-FilteredTree -Source $source -Destination (Join-Path $workspaceTarget $directory)
    }
}
$setupScriptSource = Join-Path $upstreamRoot 'scripts\setup-toolchain.ps1'
$setupScriptTarget = Join-Path $workspaceTarget 'scripts\setup-toolchain.ps1'
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $setupScriptTarget) | Out-Null
Copy-Item -LiteralPath $setupScriptSource -Destination $setupScriptTarget -Force

$upstreamImages = Join-Path $upstreamRoot 'docs\images'
if (Test-Path -LiteralPath $upstreamImages -PathType Container) {
    Get-ChildItem -LiteralPath $upstreamImages -Filter 'studio-*.png' -File | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $imagesTarget $_.Name) -Force
    }
}

$versionModule = Join-Path $installerRoot 'src\build_version.py'
[IO.File]::WriteAllText(
    $versionModule,
    "`"`"`"Version injected by the installer build and upstream synchronization jobs.`"`"`"`n`nAPP_VERSION = `"$Version`"`n",
    [Text.UTF8Encoding]::new($false)
)
[IO.File]::WriteAllText(
    (Join-Path $installerRoot 'UPSTREAM_VERSION'),
    "v$Version`n",
    [Text.UTF8Encoding]::new($false)
)

Write-Host "Synchronized Tang Primer FPGA Studio v$Version from $upstreamRoot" -ForegroundColor Green
Write-Host "IDE modules: $(@(Get-ChildItem -LiteralPath $ideTarget -Filter '*.py' -File).Count)"
Write-Host "Packaged projects: $(@(Get-ChildItem -LiteralPath (Join-Path $workspaceTarget 'projects') -Directory).Count)"
