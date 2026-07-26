# Project 01: Button-controlled LED and PWM system

This project turns the Tang Primer 20K Dock's five active-low buttons and six
active-low LEDs into a small, properly synchronized digital control system.

## Controls

| Button | Action |
|---|---|
| BTN0 | Select the next LED mode |
| BTN1 | Increase animation speed |
| BTN2 | Decrease animation speed |
| BTN3 | Increase manual PWM brightness |
| BTN4 | Reverse the chase direction |

The four modes are binary count, chasing LED, manual PWM brightness, and
automatic breathing. The design uses clock-enable pulses instead of creating
new clocks.

## Commands

Run these from this project folder:

```powershell
.\fpga.ps1 sim
.\fpga.ps1 wave
.\fpga.ps1 lint
.\fpga.ps1 debug
.\fpga.ps1 build
.\fpga.ps1 upload
.\fpga.ps1 flash
```

`upload` is recommended during development because it writes only volatile
SRAM. Use `flash` after the behavior is verified on hardware.

## What each module teaches

- `reset_generator.sv`: deterministic FPGA startup.
- `input_synchronizer.sv`: two-flop synchronization for asynchronous inputs.
- `button_debouncer.sv`: stable-state filtering and one-cycle event pulses.
- `led_mode_controller.sv`: state, clock enables, PWM, counters, and modes.
- `top.sv`: module composition and active-low board interfaces.
- `sim/tb_top.sv`: self-checking stimulus including contact bounce.

Generated reports and waveforms appear under `build/`. Open
`build/waves.vcd` in VS Code or run `.\fpga.ps1 wave` to rerun the simulation
and open GTKWave with the prepared button, debounce, mode, PWM, and LED signal
layout. `debug` does the same after running Verilator lint.

## Exercises

1. Add a fifth mode that displays the debounced button state on the LEDs.
2. Change BTN3 so brightness saturates instead of wrapping.
3. Make holding BTN1 auto-repeat after one second.
4. Add assertions that mode and speed never leave their valid ranges.
5. Create a pattern in which two LEDs move toward and away from each other.
