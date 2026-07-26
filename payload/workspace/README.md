# Tang Primer 20K FPGA Studio

[![Quality gates](https://github.com/atmarachchige0081/Tang-Primer-20K-FPGA-Studio/actions/workflows/quality-gates.yml/badge.svg)](https://github.com/atmarachchige0081/Tang-Primer-20K-FPGA-Studio/actions/workflows/quality-gates.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-6c63ff.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-4f9cff.svg)](https://www.python.org/)
[![Release: v1.1.0](https://img.shields.io/badge/release-v1.1.0-42d392.svg)](CHANGELOG.md)

An open-source, beginner-friendly FPGA IDE and development environment for the
Sipeed Tang Primer 20K (`GW2A-LV18PG256C8/I7`). Simulate, inspect waveforms,
lint, debug, build, upload to SRAM, and flash persistent designs through a
polished desktop interface or single commands. The Dock carrier is the default
pin map and programmer.

**Installing for the first time?** Follow [INSTALL.md](INSTALL.md) from a clean
Windows computer through dependencies, simulation, JTAG setup, build, and your
first LED program on real hardware.

The pinned [OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build) provides Yosys synthesis, nextpnr-himbaechel placement/routing, Project Apicula bitstream packing, openFPGALoader programming, Verilator linting, Icarus simulation, GTKWave, and formal tools. It is installed at `C:\fpga-tools\2026-07-26\oss-cad-suite` so the tool path contains no spaces, as recommended by YosysHQ. The project path may contain spaces because all build commands run with relative paths.

## Beginner desktop IDE

Start the graphical interface with one command:

```powershell
.\FPGA-IDE.ps1
```

Windows users can alternatively double-click `Open-FPGA-IDE.cmd`.

| Accessible dark mode | New accessible light mode |
|---|---|
| ![Tang Primer FPGA Studio dark workspace](docs/images/studio-main.png) | ![Tang Primer FPGA Studio light workspace](docs/images/studio-main-light.png) |

The release workspace includes custom iconography, searchable project
navigation, open-file tabs, signal/module intelligence, contextual HDL
explanations, project-wide search, a command palette, a searchable library of
72 reviewed HDL patterns, safe quick fixes, a pin assignment inspector, and a
design-health dashboard.
The dashboard turns build reports into timing, utilization, hierarchy,
artifact, and verification-readiness insights. Live console actions cover
simulation, GTKWave, lint, debug, build, SRAM upload, persistent flash, JTAG
detection, hardware diagnosis, UART monitoring, tool setup, and driver setup.

Version 1.1.0 can switch the complete live workspace between dark and light
modes from the header, **View** menu, or `Ctrl+Alt+T`. The choice is remembered
locally. Editors, dialogs, menus, selections, syntax colors, status states,
tooltips, and all custom icons change together without closing files or losing
work. Both palettes are checked for WCAG contrast, and a release stress test
switches themes repeatedly with dialogs open and verifies automatic rollback
after an injected UI failure. To force a startup theme, run
`./FPGA-IDE.ps1 -Theme light` or `./FPGA-IDE.ps1 -Theme dark`.

### Intelligent workspace

| Project health, hierarchy, timing and readiness | Searchable command palette |
|---|---|
| ![Project Insights dashboard](docs/images/studio-insights.png) | ![Searchable command palette](docs/images/studio-command-palette.png) |

| Searchable 72-pattern HDL reference | Pin and electrical-standard inspection |
|---|---|
| ![HDL Pattern Library](docs/images/studio-pattern-library.png) | ![Pin Assignment Inspector](docs/images/studio-pin-inspector.png) |

| Pattern reference in dark mode | The same live dialog in light mode |
|---|---|
| ![Dark HDL Pattern Library](docs/images/studio-pattern-library.png) | ![Light HDL Pattern Library](docs/images/studio-pattern-library-light.png) |

The Studio is local and offline after toolchain installation: it requires no
account, sends no telemetry, contains projects inside the workspace, blocks
hardware programming when smart checks contain red errors, warns before
persistent flash, and records rotating diagnostic logs under `.fpga-studio/`.

Put design code in the selected project's `rtl/` folder, verification code in
`sim/`, and top-level pin assignments in `constraints/`. The `build/` folder is
generated output. See the [IDE guide](ide/README.md) for the complete workflow,
shortcuts, and supported release scope. In VS Code, the same launcher is available under
**Terminal > Run Task > FPGA: Open Beginner IDE**.

For release validation, operations, security reporting, and contributions, see
[Deployment](docs/DEPLOYMENT.md), [Security](SECURITY.md),
[Contributing](CONTRIBUTING.md), and the [Changelog](CHANGELOG.md). The project
is available under the [MIT License](LICENSE).

## Daily commands

Run these in PowerShell from this folder:

```powershell
.\fpga.ps1 build                 # create build/top.fs
.\fpga.ps1 upload                # build + load SRAM (fast, volatile)
.\fpga.ps1 flash                 # build + write/verify persistent flash
.\fpga.ps1 sim                   # self-checking RTL simulation
.\fpga.ps1 wave                  # simulate + open GTKWave with saved signals
.\fpga.ps1 debug                 # lint + simulate + open GTKWave
.\fpga.ps1 lint                  # Verilator lint only
.\fpga.ps1 doctor                # tools, USB programmer, and COM-port checks
.\fpga.ps1 driver                # configure WinUSB for Dock JTAG interface A
.\fpga.ps1 detect                # scan the FPGA JTAG chain
.\fpga.ps1 serial -Port COM5     # UART monitor, default 115200 baud
.\fpga.ps1 clean                 # remove generated build files
```

Use `-NoBuild` with `upload` or `flash` to reuse the existing bitstream. In VS Code, `Ctrl+Shift+B` builds; the other commands are under **Terminal > Run Task**. Opening `build/waves.vcd` uses the HDL extension's built-in waveform viewer.

## First hardware connection

1. Seat the Primer 20K core module firmly in the Dock.
2. Put Dock DIP switch **1 down** to enable the FPGA core board. Sipeed documents that JTAG will not work while the core is disabled.
3. Connect the Dock's USB-C **JTAG/UART** port directly to the PC, preferably without a USB hub.
4. Run `.\fpga.ps1 doctor`, then `.\fpga.ps1 detect`.
5. Run `.\fpga.ps1 upload`. The four Dock LEDs should blink at different rates.

On Windows, openFPGALoader needs WinUSB on the Dock's JTAG half. Run `.\fpga.ps1 driver`, allow the administrator prompt, then in Zadig choose **Options > List All Devices**, select **USB Serial Converter A (Interface 0 / MI_00)**, choose **WinUSB**, and click **Replace Driver**. Do not change Converter B / MI_01: it must keep the FTDI driver so UART remains available (currently COM11 on this machine). The setup script downloads the official Zadig 2.9 binary, verifies its pinned SHA-256, and checks its Akeo Consulting Authenticode signature before it can be launched.

If the JTAG interface still does not appear, update the Dock's BL702 debugger firmware using [Sipeed's debugger update guide](https://wiki.sipeed.com/hardware/en/tang/common-doc/update_debugger.html). Firmware updating is deliberately not automated: the board must be placed into its special boot mode using the `702-BOOT` button, and choosing the wrong attached COM device is unsafe.

`upload` writes SRAM and is the normal edit/test loop; its design disappears at power-off. `flash` writes the persistent configuration storage and verifies it. Avoid using JTAG/dual-purpose pins as GPIO unless you understand the recovery procedure.

## Project layout

- `rtl/` - synthesizable Verilog/SystemVerilog; `top.sv` is the starter design.
- `constraints/primer20k_dock.cst` - physical pin and electrical constraints.
- `sim/` - self-checking testbenches, GTKWave layouts, and VCD generation.
- `build/` - generated netlists, reports, simulation output, and `top.fs`.
- `fpga.config.psd1` - device, family, top module, constraint, programmer, and toolchain settings.
- `fpga.ps1` - single entry point for building, programming, simulation, and diagnosis.

The command-line build discovers `.v` and `.sv` files under `rtl/` automatically. `rtl/files.f` is available for external tools that prefer an explicit file list.

## Learning projects

| Project | Skills and result |
|---|---|
| [`01_button_led_pwm`](projects/01_button_led_pwm) | Synchronizers, debouncing, clock enables, counters, PWM, state/mode control, self-checking bounce simulation, and a prepared GTKWave layout. |
| [`_template`](projects/_template) | Minimal, buildable starting point for creating additional examples with the same commands. |

Each project is self-contained. For Project 01:

```powershell
cd projects\01_button_led_pwm
.\fpga.ps1 sim       # compile and run the self-checking testbench
.\fpga.ps1 wave      # simulate and open the prepared GTKWave view
.\fpga.ps1 debug     # lint, simulate, and open GTKWave
.\fpga.ps1 build     # synthesize, place/route, and create build/top.fs
.\fpga.ps1 upload    # build and load volatile SRAM
.\fpga.ps1 flash     # build and verify persistent flash
```

The same project can be selected without changing folders:

```powershell
.\fpga.ps1 sim -Project projects/01_button_led_pwm
.\fpga.ps1 wave -Project projects/01_button_led_pwm
```

### Creating another example project

Use a two-digit sequence number and a short lowercase name, such as
`02_uart_terminal` or `03_spi_controller`. Copy the maintained template:

```powershell
Copy-Item -Recurse projects\_template projects\02_uart_terminal
cd projects\02_uart_terminal
```

Then follow this method:

1. Put synthesizable `.v`/`.sv` modules in `rtl/`, with `rtl/top.sv` as the configured top module.
2. List source files in `rtl/files.f` for editor/external-tool compatibility. The command runner also discovers RTL files automatically.
3. Put a self-checking `tb_top` testbench in `sim/`; write `build/waves.vcd` from that testbench.
4. Edit `sim/waves.gtkw` to preload the most useful GTKWave signals.
5. Update `constraints/primer20k_dock.cst` whenever top-level ports or pins change. Never guess voltage standards—check the board schematic or official constraints.
6. Update `fpga.config.psd1` if the top module, constraint filename, board, or clock changes.
7. Run `sim`, `lint`, and `build` before `upload`; use `flash` only after the SRAM behavior is correct.
8. Give the project its own README with its specification, controls, block-level explanation, verification results, timing/utilization, and known limitations.

The project-local `fpga.ps1` is only a thin forwarding wrapper. The maintained
build implementation remains at the repository root, so new projects should
copy the wrapper unchanged.

## Debugging support

- Verilator provides editor and command-line lint diagnostics.
- Icarus runs the self-checking testbench and creates `build/waves.vcd`.
- GTKWave or the VS Code waveform viewer supports signal-level debugging.
- `build/timing.json` contains utilization and timing information from nextpnr.
- `serial` monitors on-device UART diagnostics.

This setup does not provide an open-source on-chip logic analyzer. If you specifically need internal live signal capture over JTAG, install Gowin EDA Education and use Gowin Analyzer Oscilloscope (GAO); that proprietary package requires an interactive Gowin download/install and is not needed for this open-source build/upload flow.

## Lite carrier or custom board pins

The Primer 20K Lite has no onboard JTAG/UART programmer; connect an external debugger to `5V0, TMS, TDO, TCK, TDI, RX, TX, GND` (UART TX/RX cross over). Create a Lite-specific `.cst`, then change `Constraint` in `fpga.config.psd1`. Sipeed's Lite bring-up example uses clock pin `H11` and a PMOD LED on `L14`.

## Reinstalling

The setup is reproducible on Windows 10/11:

```powershell
.\fpga.ps1 setup
```

The installer is pinned to OSS CAD Suite `2026-07-26` and verified with the SHA-256 published on its GitHub release. Set `OSS_CAD_SUITE_ROOT` before a command if you intentionally want to use another compatible installation.

## Primary references

- [Sipeed Tang Primer 20K board documentation](https://wiki.sipeed.com/hardware/en/tang/tang-primer-20k/primer-20k.html)
- [Sipeed TangPrimer-20K official examples and pin constraints](https://github.com/sipeed/TangPrimer-20K-example)
- [Project Apicula Gowin flow and Primer 20K support](https://github.com/YosysHQ/apicula)
- [openFPGALoader board/programmer documentation](https://github.com/trabucayre/openFPGALoader)
- [OSS CAD Suite installation and included tools](https://github.com/YosysHQ/oss-cad-suite-build)
