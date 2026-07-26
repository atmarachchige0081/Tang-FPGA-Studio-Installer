`timescale 1ns/1ps
`default_nettype none

module top #(
    parameter integer RESET_CYCLES        = 16,
    parameter integer DEBOUNCE_CYCLES     = 270_000,
    parameter integer BASE_STEP_CYCLES    = 6_750_000,
    parameter integer BREATH_STEP_CYCLES  = 54_000,
    parameter integer PWM_BITS            = 8
) (
    input  logic       clk_27mhz,
    input  logic [4:0] btn_n,
    output logic [5:0] led_n
);
    logic reset;
    logic [4:0] synchronized_btn_n;
    // Kept for the prepared GTKWave view; hardware behavior uses press_pulse.
    /* verilator lint_off UNUSEDSIGNAL */
    logic [4:0] button_pressed;
    logic [4:0] press_pulse;
    logic [5:0] led_on;

    // These signals are intentionally kept visible in simulation waveforms.
    logic [1:0] mode;
    logic [1:0] speed;
    logic [PWM_BITS-1:0] brightness;
    logic reverse;
    /* verilator lint_on UNUSEDSIGNAL */

    reset_generator #(
        .RESET_CYCLES(RESET_CYCLES)
    ) power_on_reset (
        .clk   (clk_27mhz),
        .reset (reset)
    );

    input_synchronizer #(
        .WIDTH       (5),
        .RESET_VALUE (5'b11111)
    ) synchronize_buttons (
        .clk      (clk_27mhz),
        .reset    (reset),
        .async_in (btn_n),
        .sync_out (synchronized_btn_n)
    );

    generate
        for (genvar i = 0; i < 5; i++) begin : create_debouncers
            button_debouncer #(
                .STABLE_CYCLES(DEBOUNCE_CYCLES)
            ) debounce_button (
                .clk         (clk_27mhz),
                .reset       (reset),
                .sampled_n   (synchronized_btn_n[i]),
                .pressed     (button_pressed[i]),
                .press_pulse (press_pulse[i])
            );
        end
    endgenerate

    led_mode_controller #(
        .LED_COUNT          (6),
        .BASE_STEP_CYCLES   (BASE_STEP_CYCLES),
        .BREATH_STEP_CYCLES (BREATH_STEP_CYCLES),
        .PWM_BITS           (PWM_BITS)
    ) controller (
        .clk         (clk_27mhz),
        .reset       (reset),
        .press_pulse (press_pulse),
        .led_on      (led_on),
        .mode        (mode),
        .speed       (speed),
        .brightness  (brightness),
        .reverse     (reverse)
    );
    // Dock LEDs are active-low: drive zero to illuminate an LED.
    assign led_n = ~led_on;
endmodule

`default_nettype wire
