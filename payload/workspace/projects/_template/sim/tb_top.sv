`timescale 1ns/1ps
`default_nettype none

module tb_top;
    logic clk_27mhz = 1'b0;
    logic [4:0] btn_n = 5'b11111;
    logic [5:0] led_n;

    top dut (
        .clk_27mhz (clk_27mhz),
        .btn_n     (btn_n),
        .led_n     (led_n)
    );

    always #5 clk_27mhz = ~clk_27mhz;

    initial begin
        $dumpfile("build/waves.vcd");
        $dumpvars(0, tb_top);

        repeat (3) @(posedge clk_27mhz);
        if (led_n[4:0] !== 5'b11111) $fatal(1, "released buttons must leave LEDs off");

        btn_n[2] = 1'b0;
        #1;
        if (led_n[2] !== 1'b0) $fatal(1, "pressed BTN2 must illuminate LED2");

        btn_n[2] = 1'b1;
        #1;
        if (led_n[2] !== 1'b1) $fatal(1, "released BTN2 must turn LED2 off");

        $display("PASS: template button/LED behavior verified");
        $finish;
    end
endmodule

`default_nettype wire
