# Thin project-local entry point. The maintained implementation lives at the
# repository root, so improvements apply to every learning project.
$workspaceCommand = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\fpga.ps1'))
& $workspaceCommand @args -Project $PSScriptRoot
