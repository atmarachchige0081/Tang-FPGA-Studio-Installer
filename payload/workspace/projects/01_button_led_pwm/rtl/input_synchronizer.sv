`timescale 1ns/1ps
`default_nettype none

// Two flip-flops reduce the probability that asynchronous button transitions
// propagate metastability into the rest of the design.
module input_synchronizer #(
    parameter integer WIDTH = 1,
    parameter logic [WIDTH-1:0] RESET_VALUE = {WIDTH{1'b1}}
) (
    input  logic             clk,
    input  logic             reset,
    input  logic [WIDTH-1:0] async_in,
    output logic [WIDTH-1:0] sync_out
);
    (* async_reg = "true" *) logic [WIDTH-1:0] meta;
    (* async_reg = "true" *) logic [WIDTH-1:0] synced;

    always_ff @(posedge clk) begin
        if (reset) begin
            meta   <= RESET_VALUE;
            synced <= RESET_VALUE;
        end else begin
            meta   <= async_in;
            synced <= meta;
        end
    end

    assign sync_out = synced;
endmodule

`default_nettype wire
