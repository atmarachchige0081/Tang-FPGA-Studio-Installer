# Tang FPGA Studio Installer v2.0.0

This one-file Windows installer was generated from the verified
[v2.0.0 Studio release](https://github.com/atmarachchige0081/Tang-FPGA-Studio/releases/tag/v2.0.0).
It installs the native Tauri/Rust IDE, learning workspace, board packages,
first-launch release notes, netlist and waveform viewers, and dependency setup.

Download `TangPrimerFPGAStudio-Setup-2.0.0.exe` and verify the adjacent SHA-256
file or GitHub build-provenance attestation before installation.

## Studio release notes

Tang FPGA Studio 2.0 broadens the beginner path to Tang Nano 1K, 4K, 9K, and
20K plus Tang Primer 20K Dock, Core, and Lite profiles.

Highlights:

- native, local-first desktop workspace with real menus and a `Ctrl+K` action center;
- bounded waveform, netlist, and console rendering with blocking work moved off the UI thread;
- searchable HDL patterns, source intelligence, real Git status, and declarative plugins;
- beginner UART command-console project with friendly `HELP`, `PING`, LED, and status replies;
- guarded JTAG recovery, uncompressed validated Gowin bitstreams, and a programmer watchdog;
- accessible dark/light themes, guided hardware setup, and automatic one-file packaging.

Release acceptance passed 17 native UI checks, 22 Rust checks, 34 companion
regression checks, repeated concurrency stress, full builds for five device
families, and a live Primer 20K SRAM plus 115200-baud `PING`/`PONG` test.

Latest installer: https://github.com/atmarachchige0081/Tang-FPGA-Studio-Installer/releases/latest
