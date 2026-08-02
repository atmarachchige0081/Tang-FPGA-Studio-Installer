# Tang FPGA Studio — Windows Installer

[![Release](https://img.shields.io/github/v/release/atmarachchige0081/Tang-FPGA-Studio-Installer?color=42d392)](https://github.com/atmarachchige0081/Tang-FPGA-Studio-Installer/releases/latest)
[![Build and attest](https://github.com/atmarachchige0081/Tang-FPGA-Studio-Installer/actions/workflows/release.yml/badge.svg)](https://github.com/atmarachchige0081/Tang-FPGA-Studio-Installer/actions/workflows/release.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-6c63ff.svg)](LICENSE)
[![Windows 10/11](https://img.shields.io/badge/Windows-10%20%7C%2011-23d3ee.svg)](#requirements)

The one-file Windows installer for
[Tang FPGA Studio](https://github.com/atmarachchige0081/Tang-FPGA-Studio):
a beginner-friendly IDE for learning Verilog/SystemVerilog, simulating designs,
viewing waveforms, building bitstreams, and programming Sipeed Tang Nano
1K/4K/9K/20K and Tang Primer 20K boards.

| Dark workspace | Accessible light workspace |
|---|---|
| ![Dark Tang FPGA Studio 2](docs/images/studio-main.png) | ![Light Tang FPGA Studio 2](docs/images/studio-main-light.png) |

## One-file installation

1. Open the [latest release](https://github.com/atmarachchige0081/Tang-FPGA-Studio-Installer/releases/latest).
2. Download the newest `TangPrimerFPGAStudio-Setup-X.Y.Z.exe` asset.
3. Double-click the downloaded file and approve the Windows administrator prompt.
4. Keep **Install or verify the pinned FPGA toolchain** selected.
5. Keep **Create a desktop shortcut** selected and finish installation.
6. Double-click **Tang FPGA Studio** on the Desktop.

The first setup can take several minutes because it downloads and verifies the
approximately 1.9 GB FPGA toolchain. Later launches work offline.

Windows may currently display **Unknown publisher** because the project does not
have a commercial Authenticode certificate. See [Release trust](#release-trust)
before deciding whether to run the installer.

## What setup does

- Installs the native Tauri/Rust Studio under Program Files.
- Requires no separate customer Python, Node.js, or Rust installation.
- Checks for 64-bit Windows and at least 4 GB of free disk space.
- Downloads the pinned OSS CAD Suite from YosysHQ.
- Verifies the toolchain download using its pinned SHA-256 checksum.
- Downloads Zadig from its upstream release, verifies its SHA-256 checksum,
  and checks its Akeo Consulting Authenticode signature.
- Creates Start Menu and Desktop shortcuts.
- Creates a writable workspace at
  `Documents\Tang Primer FPGA Studio` without overwriting user projects.
- Provides repair, tool diagnosis, and a standard Windows uninstaller.

JTAG driver replacement is intentionally guided rather than automatic. If it
is needed, choose only **JTAG Debugger / USB Serial Converter A — Interface 0**
and install WinUSB. Never replace Interface 1, because it provides the UART COM
port.

## Requirements

- 64-bit Windows 10 or Windows 11
- At least 4 GB free disk space
- Internet access during the first toolchain setup
- A supported Tang Nano or Tang Primer board for hardware upload/flash operations

Simulation, HDL intelligence, project editing, and bitstream building do not
require the board to remain attached.

## Release trust

Official release installers are built by the public GitHub Actions workflow in
this repository. GitHub generates a signed Sigstore build-provenance
attestation that binds the installer digest to its repository, commit, tag, and
workflow run. A SHA-256 checksum is published beside every installer.

Verify the checksum in PowerShell:

```powershell
Get-FileHash .\TangPrimerFPGAStudio-Setup-X.Y.Z.exe -Algorithm SHA256
```

Verify the signed GitHub provenance with GitHub CLI:

```powershell
gh attestation verify .\TangPrimerFPGAStudio-Setup-X.Y.Z.exe `
  -R atmarachchige0081/Tang-FPGA-Studio-Installer
```

GitHub provenance protects release integrity, but it is not Windows
Authenticode. Windows will continue to show **Unknown publisher** until the
project obtains a trusted code-signing certificate and securely configures it
in the release workflow. A self-signed certificate is deliberately not used.

## Build it yourself

Clone this repository on Windows and run:

```powershell
.\build-installer.ps1 -Version 2.0.1
.\test-installer.ps1 -Version 2.0.1
```

The isolated build creates:

```text
dist\TangPrimerFPGAStudio-Setup-2.0.1.exe
dist\TangPrimerFPGAStudio-Setup-2.0.1.exe.sha256
```

The full FPGA IDE source, HDL examples, documentation, and issue tracker are in
the [main repository](https://github.com/atmarachchige0081/Tang-FPGA-Studio).

## Automatic release synchronization

This repository no longer requires someone to copy each Studio release by
hand. Its public GitHub Actions pipeline accepts an immediate release dispatch
and also checks the main repository's latest release hourly. For every new
semantic version it:

1. fetches the immutable upstream tag;
2. synchronizes only approved IDE, workspace, project, documentation, and
   screenshot paths;
3. commits and tags that exact installer source;
4. builds on a clean Windows VM and tests packaged dark/light startup;
5. publishes the one-file EXE, checksum, and signed build provenance.

The hourly path needs no cross-repository secret. Maintainers may configure a
fine-grained `INSTALLER_REPO_TOKEN` in the main repository for immediate
dispatch; it should be restricted to this installer repository.

## Uninstalling

Open **Settings → Apps → Installed apps**, select **Tang FPGA Studio**,
and choose **Uninstall**. Projects under Documents and the large
`C:\fpga-tools` directory are preserved intentionally so uninstalling cannot
erase HDL work or force another toolchain download.

Licensed under the [MIT License](LICENSE).
