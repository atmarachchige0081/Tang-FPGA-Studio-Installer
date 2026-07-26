`timescale 1ns/1ps

module tb_top;
    logic       clk_27mhz = 1'b0;
    logic [3:0] led_n;

    always #5 clk_27mhz = ~clk_27mhz;

    top #(
        .COUNTER_WIDTH(8)
    ) dut (
        .clk_27mhz(clk_27mhz),
        .led_n(led_n)
    );

    initial begin
        $dumpfile("build/waves.vcd");
        $dumpvars(0, tb_top);

        repeat (16) @(posedge clk_27mhz);
        #1;
        if (led_n !== 4'b1110) begin
            $fatal(1, "Unexpected LED value after 16 clocks: %b", led_n);
        end

        repeat (240) @(posedge clk_27mhz);
        $display("PASS: counter and active-low LED mapping behave as expected");
        $finish;
    end

    initial begin
        #10000;
        $fatal(1, "Simulation timeout");
    end
endmodule

