[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string] $SourceRoot,

    [Parameter(Mandatory)]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string] $Version,

    [string[]] $ExcludeProject = @()
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$installerRoot = [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')
$upstreamRoot = [IO.Path]::GetFullPath($SourceRoot).TrimEnd('\')
$excludedDirectories = @('.git', '.github', '.fpga-studio', '__pycache__', 'build', 'dist', 'gen', 'obj_dir', 'node_modules', 'target')

foreach ($required in @('studio\package.json', 'studio\src-tauri\Cargo.toml', 'fpga.ps1', 'projects', 'boards', 'plugins', 'templates', 'ip', 'scripts\setup-toolchain.ps1')) {
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
            if ($item.Name -like '*.tsbuildinfo') { continue }
            Copy-Item -LiteralPath $item.FullName -Destination $target -Force
        }
    }
}

$nativeTarget = Join-Path $installerRoot 'native\studio'
$workspaceTarget = Join-Path $installerRoot 'payload\workspace'
$imagesTarget = Join-Path $installerRoot 'docs\images'
Reset-ManagedDirectory $nativeTarget
Reset-ManagedDirectory $workspaceTarget
Reset-ManagedDirectory $imagesTarget

Copy-FilteredTree -Source (Join-Path $upstreamRoot 'studio') -Destination $nativeTarget

foreach ($file in @('fpga.ps1', 'fpga.config.psd1', 'INSTALL.md', 'LICENSE', 'README.md')) {
    $source = Join-Path $upstreamRoot $file
    if (Test-Path -LiteralPath $source -PathType Leaf) {
        Copy-Item -LiteralPath $source -Destination (Join-Path $workspaceTarget $file) -Force
    }
}
foreach ($directory in @('boards', 'constraints', 'ip', 'plugins', 'projects', 'rtl', 'sim', 'templates')) {
    $source = Join-Path $upstreamRoot $directory
    if (Test-Path -LiteralPath $source -PathType Container) {
        $destination = Join-Path $workspaceTarget $directory
        if ($directory -eq 'projects' -and $ExcludeProject.Count -gt 0) {
            New-Item -ItemType Directory -Force -Path $destination | Out-Null
            foreach ($projectDirectory in Get-ChildItem -LiteralPath $source -Directory) {
                if ($ExcludeProject -notcontains $projectDirectory.Name) {
                    Copy-FilteredTree -Source $projectDirectory.FullName -Destination (Join-Path $destination $projectDirectory.Name)
                }
            }
        }
        else {
            Copy-FilteredTree -Source $source -Destination $destination
        }
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

Write-Host "Synchronized Tang FPGA Studio v$Version from $upstreamRoot" -ForegroundColor Green
Write-Host "Native Studio source files: $(@(Get-ChildItem -LiteralPath $nativeTarget -Recurse -File).Count)"
Write-Host "Packaged projects: $(@(Get-ChildItem -LiteralPath (Join-Path $workspaceTarget 'projects') -Directory).Count)"
