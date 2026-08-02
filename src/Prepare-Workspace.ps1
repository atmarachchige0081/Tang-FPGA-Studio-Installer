[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Template,
    [Parameter(Mandatory)] [string] $Destination
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$templateRoot = [IO.Path]::GetFullPath($Template).TrimEnd('\')
$workspaceRoot = [IO.Path]::GetFullPath($Destination).TrimEnd('\')
if (-not (Test-Path -LiteralPath (Join-Path $templateRoot 'fpga.ps1') -PathType Leaf)) { throw 'The packaged workspace template is incomplete.' }
if ($workspaceRoot -eq [IO.Path]::GetPathRoot($workspaceRoot)) { throw "Unsafe workspace destination: $workspaceRoot" }
New-Item -ItemType Directory -Force -Path $workspaceRoot | Out-Null

$managedFiles = @('fpga.ps1', 'INSTALL.md', 'LICENSE', 'README.md', 'scripts/setup-toolchain.ps1')
$managedFolders = @('boards/', 'ip/', 'plugins/', 'templates/')
foreach ($source in Get-ChildItem -LiteralPath $templateRoot -Recurse -File) {
    $relative = $source.FullName.Substring($templateRoot.Length + 1).Replace('\', '/')
    $destinationFile = Join-Path $workspaceRoot $relative
    $managed = $managedFiles -contains $relative -or @($managedFolders | Where-Object { $relative.StartsWith($_, [StringComparison]::OrdinalIgnoreCase) }).Count -gt 0
    if ((Test-Path -LiteralPath $destinationFile -PathType Leaf) -and -not $managed) { continue }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destinationFile) | Out-Null
    $temporary = "$destinationFile.installing"
    Copy-Item -LiteralPath $source.FullName -Destination $temporary -Force
    Move-Item -LiteralPath $temporary -Destination $destinationFile -Force
}

$marker = Join-Path $workspaceRoot '.fpga-studio-install.json'
@{ application='Tang FPGA Studio'; workspace=$workspaceRoot; preparedAt=[DateTime]::UtcNow.ToString('o') } |
    ConvertTo-Json | Set-Content -LiteralPath $marker -Encoding UTF8
Write-Host "Workspace ready: $workspaceRoot" -ForegroundColor Green
