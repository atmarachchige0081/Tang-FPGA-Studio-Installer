`timescale 1ns/1ps
`default_nettype none

// Minimal buildable starting point. Replace this behavior in the new project.
module top (
    input  logic       clk_27mhz,
    input  logic [4:0] btn_n,
    output logic [5:0] led_n
);
    logic [23:0] counter = '0;

    always_ff @(posedge clk_27mhz)
        counter <= counter + 1'b1;

    // LEDs and buttons are active-low, so each pressed button lights its LED.
    assign led_n[4:0] = btn_n;
    assign led_n[5]   = ~counter[23];
endmodule

`default_nettype wire
