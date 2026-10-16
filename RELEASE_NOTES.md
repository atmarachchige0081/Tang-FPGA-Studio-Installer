# Tang FPGA Studio Installer v3.5.0

This one-file Windows installer was generated automatically from the verified
[v3.5.0 Studio release](https://github.com/atmarachchige0081/Tang-FPGA-Studio/releases/tag/v3.5.0). It includes the IDE, learning projects,
first-launch release notes, netlist viewer, and the dependency setup workflow.

Download `TangPrimerFPGAStudio-Setup-3.5.0.exe` and verify the adjacent
SHA-256 file or GitHub build-provenance attestation before installation.

## Studio release notes

# Tang FPGA Studio 3.5.0

Windows and Ubuntu now share the same native FPGA workbench.

- Ubuntu 22.04, 24.04 and 26.04 x86_64 support, with `.deb` and AppImage packages,
  native FPGA tools, PowerShell 7 and Linux USB/serial setup.
- A simpler retro workspace with dark/light themes, readable controls and
  resizable Explorer, assistant and output panels.
- Open existing project folders with Ctrl+O, including portable Studio projects
  and older build configurations.
- A real PowerShell/Bash terminal with working input, cancellation and recovery.
- Live editor updates for saved external and AI edits, explicit unsaved-conflict
  handling, persistent change markers and native read-only before/after review.
- Assistant reconnection across projects, accessible approvals, steering,
  optional inline suggestions and separate component recovery.

## Downloads and setup

Choose the Windows x64 NSIS installer, Ubuntu x86_64 `.deb`, or x86_64 AppImage.
Verify downloaded files against the attached SHA-256 checksums.
The separate [Windows one-file installer](https://github.com/atmarachchige0081/Tang-FPGA-Studio-Installer/releases)
adds guided toolchain setup; its publication runs separately, so check the version.

See [Windows installation](https://github.com/atmarachchige0081/Tang-FPGA-Studio/blob/v3.5.0/INSTALL.md) and [Ubuntu setup](https://github.com/atmarachchige0081/Tang-FPGA-Studio/blob/v3.5.0/docs/LINUX.md).
Packages do not include the full FPGA toolchain. AppImages use the host GTK/WebKit
libraries. Console 60K place/route requires Gowin EDA. AI requests require your own
Codex authentication; ordinary editing and FPGA commands work without AI.

## Verification limits

Release checks cover frontend/native regressions, Windows installation and smoke,
Ubuntu native UI/package workflows and software FPGA builds. Logs and results are
retained in the release commit's GitHub Actions runs. See [validation scope](https://github.com/atmarachchige0081/Tang-FPGA-Studio/blob/v3.5.0/docs/LINUX_VALIDATION.md).
No cloud hardware result is claimed. Physical JTAG, flash, UART and analyzer
acceptance require a connected board. Change-review snapshots are bounded and
in memory; restart begins a new baseline, so use Git for durable history.

## Build and validation

Release commit: `987fb116c5a87e9e187854213c99a39ab86ca726`.

- [Quality gates](https://github.com/atmarachchige0081/Tang-FPGA-Studio/actions/runs/38870442488)
- [Windows MSVC package validation](https://github.com/atmarachchige0081/Tang-FPGA-Studio/actions/runs/38870464409)
- [Ubuntu native application](https://github.com/atmarachchige0081/Tang-FPGA-Studio/actions/runs/38870442417)
