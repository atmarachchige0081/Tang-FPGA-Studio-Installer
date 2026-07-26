// Tang Primer 20K Dock starter design.
// The four Dock LEDs are active-low, so a zero turns an LED on.
`timescale 1ns/1ps

module top #(
    parameter integer COUNTER_WIDTH = 25
) (
    input  logic       clk_27mhz,
    output logic [3:0] led_n
);
    logic [COUNTER_WIDTH-1:0] counter = '0;

    always_ff @(posedge clk_27mhz) begin
        counter <= counter + 1'b1;
    end

    // Use the most significant counter bits for four visible blink rates.
    assign led_n = ~counter[COUNTER_WIDTH-1 -: 4];
endmodule
