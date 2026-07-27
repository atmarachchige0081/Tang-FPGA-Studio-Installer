`timescale 1ns/1ps
`default_nettype none

// Transmit one UART byte using the common ready/valid handshake.
// Frame format: one start bit, eight data bits (LSB first), one stop bit.
module uart_tx #(
    parameter integer CLOCK_HZ  = 27_000_000,
    parameter integer BAUD_RATE = 115_200
) (
    input  logic       clk,
    input  logic       rst_n,
    input  logic [7:0] data_i,
    input  logic       valid_i,
    output logic       ready_o,
    output logic       tx_o
);
    // Rounding gives 234 clocks/bit: 115384.6 baud, only +0.16% error.
    localparam integer CLKS_PER_BIT =
        (CLOCK_HZ + (BAUD_RATE / 2)) / BAUD_RATE;
    localparam integer COUNT_WIDTH =
        (CLKS_PER_BIT <= 1) ? 1 : $clog2(CLKS_PER_BIT);
    localparam logic [COUNT_WIDTH-1:0] LAST_CLOCK_COUNT =
        COUNT_WIDTH'(CLKS_PER_BIT - 1);

    logic [COUNT_WIDTH-1:0] clock_count;
    logic [3:0]             bit_index;
    logic [9:0]             frame;
    logic                   busy;

    // A UART line rests high. frame[0] is the start bit, followed by the
    // eight data bits and frame[9], the stop bit.
    assign ready_o = ~busy;
    assign tx_o    = busy ? frame[bit_index] : 1'b1;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            clock_count <= '0;
            bit_index   <= '0;
            frame       <= 10'h3ff;
            busy        <= 1'b0;
        end else if (!busy) begin
            clock_count <= '0;
            bit_index   <= '0;

            // A transfer starts only when valid_i and ready_o are both high.
            if (valid_i) begin
                frame <= {1'b1, data_i, 1'b0};
                busy  <= 1'b1;
            end
        end else if (clock_count == LAST_CLOCK_COUNT) begin
            clock_count <= '0;

            if (bit_index == 4'd9) begin
                bit_index <= '0;
                busy      <= 1'b0;
            end else begin
                bit_index <= bit_index + 1'b1;
            end
        end else begin
            clock_count <= clock_count + 1'b1;
        end
    end
endmodule

`default_nettype wire
