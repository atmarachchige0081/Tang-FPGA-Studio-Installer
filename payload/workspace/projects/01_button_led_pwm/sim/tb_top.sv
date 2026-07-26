`timescale 1ns/1ps
`default_nettype none

module tb_top;
    localparam integer DEBOUNCE_CYCLES = 4;

    logic clk_27mhz = 1'b0;
    logic [4:0] btn_n = 5'b11111;
    logic [5:0] led_n;

    top #(
        .RESET_CYCLES       (4),
        .DEBOUNCE_CYCLES    (DEBOUNCE_CYCLES),
        .BASE_STEP_CYCLES   (16),
        .BREATH_STEP_CYCLES (2),
        .PWM_BITS           (4)
    ) dut (
        .clk_27mhz (clk_27mhz),
        .btn_n     (btn_n),
        .led_n     (led_n)
    );

    always #5 clk_27mhz = ~clk_27mhz;

    task automatic wait_clocks(input integer count);
        repeat (count) @(posedge clk_27mhz);
    endtask

    // Model both press and release contact bounce. Only the stable low interval
    // is long enough to be accepted by the debouncer.
    task automatic bounce_press(input integer index);
        btn_n[index] = 1'b0; wait_clocks(1);
        btn_n[index] = 1'b1; wait_clocks(1);
        btn_n[index] = 1'b0; wait_clocks(1);
        btn_n[index] = 1'b1; wait_clocks(1);
        btn_n[index] = 1'b0; wait_clocks(DEBOUNCE_CYCLES + 5);
        btn_n[index] = 1'b1; wait_clocks(1);
        btn_n[index] = 1'b0; wait_clocks(1);
        btn_n[index] = 1'b1; wait_clocks(DEBOUNCE_CYCLES + 5);
    endtask

    task automatic check(input logic condition, input string message);
        if (!condition) begin
            $error("FAIL: %s", message);
            $fatal(1);
        end
    endtask

    function automatic logic is_onehot6(input logic [5:0] value);
        is_onehot6 = (value != 0) && ((value & (value - 1'b1)) == 0);
    endfunction

    initial begin
        $dumpfile("build/waves.vcd");
        $dumpvars(0, tb_top);

        wait_clocks(12);
        check(dut.mode == 0, "power-on mode must be binary counter");
        check(dut.speed == 1, "power-on speed must be level 1");
        check(dut.reverse == 0, "power-on chase direction must be forward");

        bounce_press(0);
        check(dut.mode == 1, "one bouncing BTN0 press must advance exactly one mode");

        wait_clocks(20);
        check(is_onehot6(~led_n), "chase mode must illuminate exactly one LED");

        bounce_press(1);
        check(dut.speed == 2, "BTN1 must select a faster speed");
        bounce_press(2);
        check(dut.speed == 1, "BTN2 must select a slower speed");

        bounce_press(4);
        check(dut.reverse == 1, "BTN4 must reverse chase direction");

        bounce_press(0);
        check(dut.mode == 2, "BTN0 must advance to manual PWM mode");
        check(dut.brightness == 4'b1000, "manual brightness must start at 50 percent");
        bounce_press(3);
        check(dut.brightness == 4'b1100, "BTN3 must increase manual brightness");

        bounce_press(0);
        check(dut.mode == 3, "BTN0 must advance to breathing mode");
        wait_clocks(8);
        check(dut.controller.breath_level != 0, "breathing duty cycle must change automatically");

        bounce_press(0);
        check(dut.mode == 0, "mode selection must wrap from 3 back to 0");

        $display("PASS: synchronization, debounce, modes, speed, brightness, and direction verified");
        $finish;
    end
endmodule

`default_nettype wire
