# UART terminal: greeting and echo

This beginner project turns the Tang Primer 20K Dock into a real 115200-baud
UART device. After reset it sends:

```text
Tang Primer 20K UART ready
>
```

Every byte received afterward is echoed. The six LEDs show the low six bits of
the most recently received byte; pressing any user button restarts the greeting.

## What this teaches

- UART 8-N-1 framing: idle, start bit, eight least-significant-bit-first data
  bits, and a stop bit.
- Turning the 27 MHz clock into a baud-period counter.
- Ready/valid handshakes between a producer and transmitter.
- Mid-bit sampling and framing-error detection in a receiver.
- Verifying a complete serial protocol before touching hardware.

## Design structure

- `rtl/uart_tx.sv` sends one byte and exposes a ready/valid interface.
- `rtl/uart_rx.sv` samples RX and pulses `valid_o` for each good frame.
- `rtl/top.sv` sends the greeting, queues an echo, and drives the LEDs.
- `sim/tb_top.sv` checks all 30 greeting bytes and a bidirectional echo.

The Dock UART pins are constrained to FPGA TX `M11` and FPGA RX `T13`. The
JTAG debugger's **Interface 1** must keep its serial/COM driver. WinUSB belongs
on **Interface 0 only** for JTAG programming.

## Verify and use it

From the repository root:

```powershell
.\fpga.ps1 lint   -Project projects/03_uart_terminal
.\fpga.ps1 sim    -Project projects/03_uart_terminal
.\fpga.ps1 wave   -Project projects/03_uart_terminal
.\fpga.ps1 build  -Project projects/03_uart_terminal
.\fpga.ps1 upload -Project projects/03_uart_terminal
```

Then open **UART terminal** in Tang Primer Studio, select the COM port for
Interface 1, choose `115200`, `ascii`, and `CRLF`, and press **Connect**. Press
any user button to replay the greeting. Test with SRAM before considering persistent
Flash.
