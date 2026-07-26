`timescale 1ns/1ps
`default_nettype none

// Accept a new button state only after it remains unchanged for STABLE_CYCLES.
// The physical buttons and all ports in this module are active-low.
module button_debouncer #(
    parameter integer STABLE_CYCLES = 270_000
) (
    input  logic clk,
    input  logic reset,
    input  logic sampled_n,
    output logic pressed,
    output logic press_pulse
);
    localparam integer COUNTER_WIDTH =
        (STABLE_CYCLES < 2) ? 1 : $clog2(STABLE_CYCLES);
    localparam logic [COUNTER_WIDTH-1:0] STABLE_LIMIT =
        COUNTER_WIDTH'(STABLE_CYCLES - 1);

    logic [COUNTER_WIDTH-1:0] counter;
    logic stable_n;

    always_ff @(posedge clk) begin
        if (reset) begin
            counter     <= '0;
            stable_n    <= 1'b1;
            press_pulse <= 1'b0;
        end else begin
            press_pulse <= 1'b0;
            if (sampled_n == stable_n) begin
                counter <= '0;
            end else if ((STABLE_CYCLES <= 1) ||
                         (counter == STABLE_LIMIT)) begin
                counter     <= '0;
                stable_n    <= sampled_n;
                press_pulse <= stable_n && !sampled_n;
            end else begin
                counter <= counter + 1'b1;
            end
        end
    end

    assign pressed = !stable_n;
endmodule

`default_nettype wire
