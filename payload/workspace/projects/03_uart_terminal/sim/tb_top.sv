`timescale 1ns/1ps
`default_nettype none

module tb_top;
    localparam integer CLOCK_HZ     = 27_000_000;
    localparam integer BAUD_RATE    = 115_200;
    localparam integer CLKS_PER_BIT =
        (CLOCK_HZ + (BAUD_RATE / 2)) / BAUD_RATE;

    logic clk_27mhz = 1'b0;
    logic [4:0] btn_n = 5'b11111;
    logic uart_rx = 1'b1;
    logic uart_tx;
    logic [5:0] led_n;
    logic [7:0] received;

    top dut (
        .clk_27mhz (clk_27mhz),
        .btn_n     (btn_n),
        .uart_rx   (uart_rx),
        .uart_tx   (uart_tx),
        .led_n     (led_n)
    );

    always #5 clk_27mhz = ~clk_27mhz;

    function automatic logic [7:0] expected_greeting(input integer index);
        case (index)
            0: expected_greeting = "T";  1: expected_greeting = "a";
            2: expected_greeting = "n";  3: expected_greeting = "g";
            4: expected_greeting = " ";  5: expected_greeting = "P";
            6: expected_greeting = "r";  7: expected_greeting = "i";
            8: expected_greeting = "m";  9: expected_greeting = "e";
            10: expected_greeting = "r"; 11: expected_greeting = " ";
            12: expected_greeting = "2"; 13: expected_greeting = "0";
            14: expected_greeting = "K"; 15: expected_greeting = " ";
            16: expected_greeting = "U"; 17: expected_greeting = "A";
            18: expected_greeting = "R"; 19: expected_greeting = "T";
            20: expected_greeting = " "; 21: expected_greeting = "r";
            22: expected_greeting = "e"; 23: expected_greeting = "a";
            24: expected_greeting = "d"; 25: expected_greeting = "y";
            26: expected_greeting = 8'h0d; 27: expected_greeting = 8'h0a;
            28: expected_greeting = ">"; 29: expected_greeting = " ";
            default: expected_greeting = 8'h00;
        endcase
    endfunction

    task automatic receive_uart_byte(output logic [7:0] value);
        begin
            @(negedge uart_tx);
            repeat (CLKS_PER_BIT / 2) @(posedge clk_27mhz);
            if (uart_tx !== 1'b0) $fatal(1, "UART TX start bit was not low");
            for (integer bit_no = 0; bit_no < 8; bit_no = bit_no + 1) begin
                repeat (CLKS_PER_BIT) @(posedge clk_27mhz);
                value[bit_no] = uart_tx;
            end
            repeat (CLKS_PER_BIT) @(posedge clk_27mhz);
            if (uart_tx !== 1'b1) $fatal(1, "UART TX stop bit was not high");
        end
    endtask

    task automatic send_uart_byte(input logic [7:0] value);
        begin
            @(negedge clk_27mhz);
            uart_rx = 1'b0;
            repeat (CLKS_PER_BIT) @(posedge clk_27mhz);
            for (integer bit_no = 0; bit_no < 8; bit_no = bit_no + 1) begin
                @(negedge clk_27mhz);
                uart_rx = value[bit_no];
                repeat (CLKS_PER_BIT) @(posedge clk_27mhz);
            end
            @(negedge clk_27mhz);
            uart_rx = 1'b1;
            // Return near the stop-bit center so the echo start is not missed.
            repeat ((CLKS_PER_BIT / 2) + 2) @(posedge clk_27mhz);
        end
    endtask

    initial begin
        $dumpfile("build/waves.vcd");
        $dumpvars(0, tb_top);

        for (integer index = 0; index < 30; index = index + 1) begin
            receive_uart_byte(received);
            if (received !== expected_greeting(index))
                $fatal(1, "Greeting byte %0d expected %02x, got %02x", index, expected_greeting(index), received);
        end

        send_uart_byte(8'h41);
        receive_uart_byte(received);
        if (received !== 8'h41) $fatal(1, "UART echo expected 41, got %02x", received);
        repeat (2) @(posedge clk_27mhz);
        if (led_n !== 6'b111110) $fatal(1, "LED byte display mismatch");

        $display("PASS: 30-byte UART greeting and bidirectional 115200-baud echo verified");
        $finish;
    end
endmodule

`default_nettype wire
