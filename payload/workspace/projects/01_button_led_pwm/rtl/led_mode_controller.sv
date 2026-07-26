`timescale 1ns/1ps
`default_nettype none

module led_mode_controller #(
    parameter integer LED_COUNT          = 6,
    parameter integer BASE_STEP_CYCLES   = 6_750_000,
    parameter integer BREATH_STEP_CYCLES = 54_000,
    parameter integer PWM_BITS           = 8
) (
    input  logic                 clk,
    input  logic                 reset,
    input  logic [4:0]           press_pulse,
    output logic [LED_COUNT-1:0] led_on,
    output logic [1:0]           mode,
    output logic [1:0]           speed,
    output logic [PWM_BITS-1:0]  brightness,
    output logic                 reverse
);
    localparam integer STEP_COUNTER_WIDTH =
        (BASE_STEP_CYCLES < 2) ? 1 : $clog2(BASE_STEP_CYCLES);
    localparam integer BREATH_COUNTER_WIDTH =
        (BREATH_STEP_CYCLES < 2) ? 1 : $clog2(BREATH_STEP_CYCLES);
    localparam integer CHASE_INDEX_WIDTH =
        (LED_COUNT < 2) ? 1 : $clog2(LED_COUNT);
    localparam logic [PWM_BITS-1:0] BRIGHTNESS_INCREMENT =
        {{(PWM_BITS-2){1'b0}}, 2'b01} << (PWM_BITS-2);
    localparam logic [CHASE_INDEX_WIDTH-1:0] LAST_LED_INDEX =
        CHASE_INDEX_WIDTH'(LED_COUNT - 1);

    logic [STEP_COUNTER_WIDTH-1:0] step_counter;
    logic [BREATH_COUNTER_WIDTH-1:0] breath_counter;
    logic step_tick;
    logic breath_tick;
    logic [CHASE_INDEX_WIDTH-1:0] chase_index;
    logic [LED_COUNT-1:0] binary_count;
    logic [PWM_BITS-1:0] pwm_counter;
    logic [PWM_BITS-1:0] breath_level;
    logic breath_up;
    logic [STEP_COUNTER_WIDTH-1:0] step_limit;

    always_comb begin
        case (speed)
            2'd0: step_limit = STEP_COUNTER_WIDTH'(BASE_STEP_CYCLES - 1);
            2'd1: step_limit = ((BASE_STEP_CYCLES / 2) > 0) ?
                               STEP_COUNTER_WIDTH'((BASE_STEP_CYCLES / 2) - 1) : '0;
            2'd2: step_limit = ((BASE_STEP_CYCLES / 4) > 0) ?
                               STEP_COUNTER_WIDTH'((BASE_STEP_CYCLES / 4) - 1) : '0;
            default: step_limit = ((BASE_STEP_CYCLES / 8) > 0) ?
                                  STEP_COUNTER_WIDTH'((BASE_STEP_CYCLES / 8) - 1) : '0;
        endcase
    end

    always_ff @(posedge clk) begin
        if (reset) begin
            mode         <= 2'd0;
            speed        <= 2'd1;
            brightness   <= {1'b1, {(PWM_BITS-1){1'b0}}};
            reverse      <= 1'b0;
            step_counter <= '0;
            breath_counter <= '0;
            step_tick    <= 1'b0;
            breath_tick  <= 1'b0;
            chase_index  <= 3'd0;
            binary_count <= '0;
            pwm_counter  <= '0;
            breath_level <= '0;
            breath_up    <= 1'b1;
        end else begin
            step_tick   <= 1'b0;
            breath_tick <= 1'b0;
            pwm_counter <= pwm_counter + 1'b1;

            if (step_counter >= step_limit) begin
                step_counter <= '0;
                step_tick    <= 1'b1;
            end else begin
                step_counter <= step_counter + 1'b1;
            end

            if ((BREATH_STEP_CYCLES <= 1) ||
                (breath_counter == BREATH_COUNTER_WIDTH'(BREATH_STEP_CYCLES - 1))) begin
                breath_counter <= '0;
                breath_tick    <= 1'b1;
            end else begin
                breath_counter <= breath_counter + 1'b1;
            end

            // BTN0: next mode; BTN1/2: faster/slower; BTN3: brightness;
            // BTN4: reverse the chase direction.
            if (press_pulse[0]) mode <= mode + 1'b1;
            if (press_pulse[1] && speed != 2'd3) speed <= speed + 1'b1;
            if (press_pulse[2] && speed != 2'd0) speed <= speed - 1'b1;
            if (press_pulse[3]) brightness <= brightness + BRIGHTNESS_INCREMENT;
            if (press_pulse[4]) reverse <= !reverse;

            if (step_tick) begin
                binary_count <= binary_count + 1'b1;
                if (reverse)
                    chase_index <= (chase_index == '0) ? LAST_LED_INDEX : chase_index - 1'b1;
                else
                    chase_index <= (chase_index == LAST_LED_INDEX) ? '0 : chase_index + 1'b1;
            end

            if (breath_tick) begin
                if (breath_up) begin
                    if (&breath_level) begin
                        breath_up    <= 1'b0;
                        breath_level <= breath_level - 1'b1;
                    end else begin
                        breath_level <= breath_level + 1'b1;
                    end
                end else begin
                    if (breath_level == 0) begin
                        breath_up    <= 1'b1;
                        breath_level <= breath_level + 1'b1;
                    end else begin
                        breath_level <= breath_level - 1'b1;
                    end
                end
            end
        end
    end

    always_comb begin
        case (mode)
            2'd0: led_on = binary_count;
            2'd1: led_on = {{(LED_COUNT-1){1'b0}}, 1'b1} << chase_index;
            2'd2: led_on = (pwm_counter < brightness) ? {LED_COUNT{1'b1}} : '0;
            default: led_on = (pwm_counter < breath_level) ? {LED_COUNT{1'b1}} : '0;
        endcase
    end
endmodule

`default_nettype wire
