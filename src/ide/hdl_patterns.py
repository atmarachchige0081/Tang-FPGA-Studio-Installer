"""Curated HDL patterns used by the Studio editor and learning library.

The examples are intentionally compact building blocks rather than complete
projects.  Signal and parameter names are descriptive so a beginner can adapt
the pattern, then verify the result with lint and simulation.
"""

from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True, slots=True)
class HDLPattern:
    title: str
    category: str
    difficulty: str
    summary: str
    code: str
    aliases: tuple[str, ...]
    synthesizable: bool = True


def _pattern(
    title: str,
    category: str,
    difficulty: str,
    summary: str,
    aliases: tuple[str, ...],
    code: str,
    *,
    synthesizable: bool = True,
) -> HDLPattern:
    return HDLPattern(
        title=title,
        category=category,
        difficulty=difficulty,
        summary=summary,
        code=code.strip(),
        aliases=aliases,
        synthesizable=synthesizable,
    )


PATTERNS: tuple[HDLPattern, ...] = (
    # Sequential logic -----------------------------------------------------
    _pattern(
        "Clocked register with synchronous reset", "Sequential logic", "Beginner",
        "Stores a value on the rising clock edge and clears it synchronously.", ("ffreg",),
        """
always_ff @(posedge clk) begin
    if (reset) begin
        value <= '0;
    end else begin
        value <= next_value;
    end
end
""",
    ),
    _pattern(
        "Clocked register with asynchronous reset", "Sequential logic", "Beginner",
        "Asserts reset immediately; use only when the target reset strategy requires it.", ("ffasync",),
        """
always_ff @(posedge clk or posedge reset) begin
    if (reset) begin
        value <= '0;
    end else begin
        value <= next_value;
    end
end
""",
    ),
    _pattern(
        "Register with clock enable", "Sequential logic", "Beginner",
        "Updates a register only when enable is high without creating a gated clock.", ("ffen",),
        """
always_ff @(posedge clk) begin
    if (reset) begin
        value <= '0;
    end else if (enable) begin
        value <= next_value;
    end
end
""",
    ),
    _pattern(
        "Sticky status flag", "Sequential logic", "Beginner",
        "Remembers an event until software or control logic explicitly clears it.", ("sticky",),
        """
always_ff @(posedge clk) begin
    if (reset) begin
        event_seen <= 1'b0;
    end else if (clear) begin
        event_seen <= 1'b0;
    end else if (event_pulse) begin
        event_seen <= 1'b1;
    end
end
""",
    ),
    _pattern(
        "Rising-edge detector", "Sequential logic", "Beginner",
        "Creates a one-clock pulse when a synchronous signal changes from 0 to 1.", ("rise",),
        """
logic signal_d;

always_ff @(posedge clk) begin
    if (reset) signal_d <= 1'b0;
    else       signal_d <= signal_in;
end

assign rise_pulse = signal_in & ~signal_d;
""",
    ),
    _pattern(
        "Falling-edge detector", "Sequential logic", "Beginner",
        "Creates a one-clock pulse when a synchronous signal changes from 1 to 0.", ("fall",),
        """
logic signal_d;

always_ff @(posedge clk) begin
    if (reset) signal_d <= 1'b1;
    else       signal_d <= signal_in;
end

assign fall_pulse = ~signal_in & signal_d;
""",
    ),
    _pattern(
        "Toggle register on pulse", "Sequential logic", "Beginner",
        "Flips a state bit for each single-cycle event pulse.", ("toggle",),
        """
always_ff @(posedge clk) begin
    if (reset) begin
        toggle_state <= 1'b0;
    end else if (toggle_pulse) begin
        toggle_state <= ~toggle_state;
    end
end
""",
    ),
    _pattern(
        "Parameterized shift register", "Sequential logic", "Intermediate",
        "Shifts serial data through a configurable-width register; WIDTH must be at least two.", ("shiftreg",),
        """
logic [WIDTH-1:0] shift_reg;

always_ff @(posedge clk) begin
    if (reset) begin
        shift_reg <= '0;
    end else if (shift_enable) begin
        shift_reg <= {shift_reg[WIDTH-2:0], serial_in};
    end
end

assign serial_out = shift_reg[WIDTH-1];
""",
    ),

    # Combinational logic --------------------------------------------------
    _pattern(
        "Defaulted combinational logic", "Combinational logic", "Beginner",
        "Assigns defaults first so every output is driven on every path.", ("comb",),
        """
always_comb begin
    next_value = value;
    output_valid = 1'b0;

    if (condition) begin
        next_value = new_value;
        output_valid = 1'b1;
    end
end
""",
    ),
    _pattern(
        "Two-input multiplexer", "Combinational logic", "Beginner",
        "Selects one of two values with a conditional operator.", ("mux2",),
        """
assign selected_data = select ? data_b : data_a;
""",
    ),
    _pattern(
        "Four-input multiplexer", "Combinational logic", "Beginner",
        "Uses a complete case statement with a defensive default.", ("mux4",),
        """
always_comb begin
    unique case (select)
        2'd0: selected_data = data_0;
        2'd1: selected_data = data_1;
        2'd2: selected_data = data_2;
        2'd3: selected_data = data_3;
        default: selected_data = '0;
    endcase
end
""",
    ),
    _pattern(
        "Priority encoder", "Combinational logic", "Intermediate",
        "Returns the highest-priority asserted request and a valid flag.", ("priority",),
        """
always_comb begin
    encoded = '0;
    valid = 1'b1;
    priority casez (request)
        4'b1???: encoded = 2'd3;
        4'b01??: encoded = 2'd2;
        4'b001?: encoded = 2'd1;
        4'b0001: encoded = 2'd0;
        default: begin
            encoded = '0;
            valid = 1'b0;
        end
    endcase
end
""",
    ),
    _pattern(
        "Binary-to-one-hot decoder", "Combinational logic", "Beginner",
        "Converts a binary index into a one-hot vector.", ("onehot",),
        """
always_comb begin
    one_hot = '0;
    if (enable) begin
        one_hot[index] = 1'b1;
    end
end
""",
    ),
    _pattern(
        "One-hot-to-binary encoder", "Combinational logic", "Intermediate",
        "Encodes a one-hot input and reports whether any bit is asserted.", ("hotencode",),
        """
always_comb begin
    index = '0;
    valid = |one_hot;
    for (int i = 0; i < WIDTH; i++) begin
        if (one_hot[i]) index = INDEX_WIDTH'(i);
    end
end
""",
    ),
    _pattern(
        "Unsigned minimum and maximum", "Combinational logic", "Beginner",
        "Produces the smaller and larger of two unsigned values.", ("minmax",),
        """
always_comb begin
    if (value_a < value_b) begin
        minimum = value_a;
        maximum = value_b;
    end else begin
        minimum = value_b;
        maximum = value_a;
    end
end
""",
    ),
    _pattern(
        "Population count", "Combinational logic", "Intermediate",
        "Counts how many bits in a vector are high.", ("popcount",),
        """
always_comb begin
    bit_count = '0;
    for (int i = 0; i < WIDTH; i++) begin
        bit_count = bit_count + input_bits[i];
    end
end
""",
    ),

    # Counters and timing --------------------------------------------------
    _pattern(
        "Free-running counter", "Counters and timing", "Beginner",
        "Increments on every clock and naturally wraps at its maximum value.", ("counter",),
        """
logic [WIDTH-1:0] counter;

always_ff @(posedge clk) begin
    if (reset) counter <= '0;
    else       counter <= counter + 1'b1;
end
""",
    ),
    _pattern(
        "Modulo-N counter", "Counters and timing", "Beginner",
        "Counts from zero through LIMIT-1 and emits a one-cycle wrap pulse.", ("modcounter",),
        """
always_ff @(posedge clk) begin
    if (reset) begin
        count <= '0;
        wrap_pulse <= 1'b0;
    end else begin
        wrap_pulse <= 1'b0;
        if (count == LIMIT-1) begin
            count <= '0;
            wrap_pulse <= 1'b1;
        end else begin
            count <= count + 1'b1;
        end
    end
end
""",
    ),
    _pattern(
        "Clock-enable pulse divider", "Counters and timing", "Beginner",
        "Generates a slow one-cycle enable while keeping all logic on the main clock.", ("tickgen",),
        """
always_ff @(posedge clk) begin
    if (reset) begin
        divider <= '0;
        tick <= 1'b0;
    end else begin
        tick <= 1'b0;
        if (divider == DIVISOR-1) begin
            divider <= '0;
            tick <= 1'b1;
        end else begin
            divider <= divider + 1'b1;
        end
    end
end
""",
    ),
    _pattern(
        "Restartable interval timer", "Counters and timing", "Intermediate",
        "Starts on command and raises done for one cycle after the selected interval.", ("timer",),
        """
always_ff @(posedge clk) begin
    if (reset) begin
        timer_count <= '0;
        timer_busy <= 1'b0;
        timer_done <= 1'b0;
    end else begin
        timer_done <= 1'b0;
        if (start) begin
            timer_count <= '0;
            timer_busy <= 1'b1;
        end else if (timer_busy && timer_count == INTERVAL-1) begin
            timer_busy <= 1'b0;
            timer_done <= 1'b1;
        end else if (timer_busy) begin
            timer_count <= timer_count + 1'b1;
        end
    end
end
""",
    ),
    _pattern(
        "Watchdog timeout", "Counters and timing", "Intermediate",
        "Raises a sticky fault if a periodic service pulse stops arriving.", ("watchdog",),
        """
always_ff @(posedge clk) begin
    if (reset || service) begin
        watchdog_count <= '0;
        watchdog_fault <= 1'b0;
    end else if (!watchdog_fault) begin
        if (watchdog_count == TIMEOUT_CYCLES-1) begin
            watchdog_fault <= 1'b1;
        end else begin
            watchdog_count <= watchdog_count + 1'b1;
        end
    end
end
""",
    ),
    _pattern(
        "Pulse stretcher", "Counters and timing", "Intermediate",
        "Extends a single-cycle event so slower logic can observe it.", ("stretch",),
        """
always_ff @(posedge clk) begin
    if (reset) begin
        stretch_count <= '0;
    end else if (input_pulse) begin
        stretch_count <= STRETCH_CYCLES;
    end else if (stretch_count != 0) begin
        stretch_count <= stretch_count - 1'b1;
    end
end

assign stretched = (stretch_count != 0);
""",
    ),
    _pattern(
        "PWM generator", "Counters and timing", "Beginner",
        "Compares a free-running phase counter with a duty-cycle value.", ("pwm",),
        """
logic [PWM_BITS-1:0] pwm_counter;

always_ff @(posedge clk) begin
    if (reset) pwm_counter <= '0;
    else       pwm_counter <= pwm_counter + 1'b1;
end

assign pwm_out = (pwm_counter < duty_cycle);
""",
    ),
    _pattern(
        "LED blink divider", "Counters and timing", "Beginner",
        "Toggles an LED state after a configurable number of clock cycles.", ("blink",),
        """
always_ff @(posedge clk) begin
    if (reset) begin
        blink_count <= '0;
        led_state <= 1'b0;
    end else if (blink_count == HALF_PERIOD-1) begin
        blink_count <= '0;
        led_state <= ~led_state;
    end else begin
        blink_count <= blink_count + 1'b1;
    end
end
""",
    ),
    _pattern(
        "Event frequency counter", "Counters and timing", "Advanced",
        "Counts synchronized event edges during a fixed measurement window.", ("freqcount",),
        """
always_ff @(posedge clk) begin
    if (reset) begin
        window_count <= '0;
        event_count <= '0;
        measured_count <= '0;
        measurement_valid <= 1'b0;
    end else begin
        measurement_valid <= 1'b0;
        if (event_pulse) event_count <= event_count + 1'b1;
        if (window_count == WINDOW_CYCLES-1) begin
            window_count <= '0;
            measured_count <= event_count + event_pulse;
            event_count <= '0;
            measurement_valid <= 1'b1;
        end else begin
            window_count <= window_count + 1'b1;
        end
    end
end
""",
    ),
    _pattern(
        "Programmable rate divider", "Counters and timing", "Intermediate",
        "Reloads a down-counter to produce a programmable one-cycle tick.", ("ratediv",),
        """
always_ff @(posedge clk) begin
    if (reset) begin
        rate_count <= '0;
        rate_tick <= 1'b0;
    end else if (rate_count == 0) begin
        rate_count <= reload_value;
        rate_tick <= 1'b1;
    end else begin
        rate_count <= rate_count - 1'b1;
        rate_tick <= 1'b0;
    end
end
""",
    ),

    # Clock-domain crossing and inputs ------------------------------------
    _pattern(
        "Two-flop bit synchronizer", "CDC and inputs", "Beginner",
        "Reduces metastability risk for a slowly changing single-bit input.", ("sync2",),
        """
(* async_reg = "true" *) logic async_meta;
(* async_reg = "true" *) logic async_sync;

always_ff @(posedge clk) begin
    async_meta <= async_input;
    async_sync <= async_meta;
end
""",
    ),
    _pattern(
        "Asynchronous-assert reset synchronizer", "CDC and inputs", "Advanced",
        "Asserts reset immediately and releases it synchronously in the destination domain.", ("resetsync",),
        """
(* async_reg = "true" *) logic [1:0] reset_pipe;

always_ff @(posedge clk or negedge async_reset_n) begin
    if (!async_reset_n) reset_pipe <= 2'b00;
    else                reset_pipe <= {reset_pipe[0], 1'b1};
end

assign reset_n = reset_pipe[1];
""",
    ),
    _pattern(
        "Toggle-based pulse synchronizer", "CDC and inputs", "Advanced",
        "Transfers an occasional pulse between unrelated clock domains using a toggle.", ("cdcpulse",),
        """
// Source clock domain
always_ff @(posedge source_clk) begin
    if (source_reset) source_toggle <= 1'b0;
    else if (source_pulse) source_toggle <= ~source_toggle;
end

// Destination clock domain
always_ff @(posedge dest_clk) begin
    if (dest_reset) begin
        toggle_meta <= 1'b0;
        toggle_sync <= 1'b0;
        toggle_sync_d <= 1'b0;
    end else begin
        toggle_meta <= source_toggle;
        toggle_sync <= toggle_meta;
        toggle_sync_d <= toggle_sync;
    end
end

assign dest_pulse = toggle_sync ^ toggle_sync_d;
""",
    ),
    _pattern(
        "Gray-code counter synchronizer", "CDC and inputs", "Advanced",
        "Transfers a changing counter safely by synchronizing its Gray-coded representation.", ("graycdc",),
        """
// Source domain
assign source_gray = source_binary ^ (source_binary >> 1);

// Destination domain
always_ff @(posedge dest_clk) begin
    gray_meta <= source_gray;
    gray_sync <= gray_meta;
end

always_comb begin
    dest_binary[WIDTH-1] = gray_sync[WIDTH-1];
    for (int i = WIDTH-2; i >= 0; i--) begin
        dest_binary[i] = dest_binary[i+1] ^ gray_sync[i];
    end
end
""",
    ),
    _pattern(
        "Synchronized edge detector", "CDC and inputs", "Intermediate",
        "Synchronizes an external bit before producing a clean rising-edge pulse.", ("syncedge",),
        """
logic input_meta, input_sync, input_sync_d;

always_ff @(posedge clk) begin
    input_meta <= async_input;
    input_sync <= input_meta;
    input_sync_d <= input_sync;
end

assign input_rise = input_sync & ~input_sync_d;
""",
    ),
    _pattern(
        "Counter-based button debouncer", "CDC and inputs", "Intermediate",
        "Accepts a synchronized input change only after it remains stable.", ("debounce",),
        """
always_ff @(posedge clk) begin
    if (reset) begin
        stable_state <= 1'b0;
        debounce_count <= '0;
    end else if (sampled_input == stable_state) begin
        debounce_count <= '0;
    end else if (debounce_count == STABLE_CYCLES-1) begin
        stable_state <= sampled_input;
        debounce_count <= '0;
    end else begin
        debounce_count <= debounce_count + 1'b1;
    end
end
""",
    ),
    _pattern(
        "Digital glitch filter", "CDC and inputs", "Intermediate",
        "Changes output only after every sample in a short history agrees.", ("glitchfilter",),
        """
logic [FILTER_LENGTH-1:0] sample_history;

always_ff @(posedge clk) begin
    if (reset) begin
        sample_history <= '0;
        filtered_output <= 1'b0;
    end else begin
        sample_history <= {sample_history[FILTER_LENGTH-2:0], sampled_input};
        if (&sample_history)       filtered_output <= 1'b1;
        else if (~|sample_history) filtered_output <= 1'b0;
    end
end
""",
    ),
    _pattern(
        "Source-held multi-bit bus capture", "CDC and inputs", "Advanced",
        "Use only when the source guarantees the bus remains stable for several destination clocks; otherwise use a handshake or asynchronous FIFO.", ("stablebus",),
        """
always_ff @(posedge dest_clk) begin
    bus_meta <= async_bus;
    bus_sample <= bus_meta;
    bus_previous <= bus_sample;
    if (bus_sample == bus_previous) begin
        captured_bus <= bus_sample;
        captured_valid <= 1'b1;
    end else begin
        captured_valid <= 1'b0;
    end
end
""",
    ),

    # State machines and control ------------------------------------------
    _pattern(
        "Safe finite-state machine", "State machines", "Intermediate",
        "Uses typed states, a registered state, defaults, and recovery from illegal values.", ("fsm",),
        """
typedef enum logic [1:0] {IDLE, ACTIVE, DONE} state_t;
state_t state, next_state;

always_ff @(posedge clk) begin
    if (reset) state <= IDLE;
    else       state <= next_state;
end

always_comb begin
    next_state = state;
    unique case (state)
        IDLE:    if (start) next_state = ACTIVE;
        ACTIVE:  if (finished) next_state = DONE;
        DONE:    next_state = IDLE;
        default: next_state = IDLE;
    endcase
end
""",
    ),
    _pattern(
        "Moore FSM with registered state", "State machines", "Intermediate",
        "Derives outputs only from the current state for stable cycle-aligned control.", ("moore",),
        """
always_ff @(posedge clk) begin
    if (reset) state <= IDLE;
    else       state <= next_state;
end

always_comb begin
    next_state = state;
    busy = 1'b0;
    done = 1'b0;
    case (state)
        IDLE: if (start) next_state = WORK;
        WORK: begin
            busy = 1'b1;
            if (finished) next_state = COMPLETE;
        end
        COMPLETE: begin
            done = 1'b1;
            next_state = IDLE;
        end
        default: next_state = IDLE;
    endcase
end
""",
    ),
    _pattern(
        "Mealy FSM output", "State machines", "Intermediate",
        "Produces an output from both the current state and current input.", ("mealy",),
        """
always_ff @(posedge clk) begin
    if (reset) state <= WAITING;
    else       state <= next_state;
end

always_comb begin
    next_state = state;
    accept = 1'b0;
    case (state)
        WAITING: if (request) begin
            accept = 1'b1;
            next_state = ACTIVE;
        end
        ACTIVE: if (complete) next_state = WAITING;
        default: next_state = WAITING;
    endcase
end
""",
    ),
    _pattern(
        "One-hot finite-state machine", "State machines", "Advanced",
        "Uses one state bit per state for simple decode logic.", ("fsm1h",),
        """
localparam logic [2:0] S_IDLE = 3'b001;
localparam logic [2:0] S_READ = 3'b010;
localparam logic [2:0] S_DONE = 3'b100;

always_ff @(posedge clk) begin
    if (reset) state <= S_IDLE;
    else       state <= next_state;
end

always_comb begin
    next_state = S_IDLE;
    unique case (1'b1)
        state[0]: next_state = start ? S_READ : S_IDLE;
        state[1]: next_state = valid ? S_DONE : S_READ;
        state[2]: next_state = S_IDLE;
        default:  next_state = S_IDLE;
    endcase
end
""",
    ),
    _pattern(
        "Request-acknowledge controller", "State machines", "Intermediate",
        "Holds a request until acknowledge arrives, then waits for acknowledge to drop.", ("reqack",),
        """
typedef enum logic [1:0] {READY, REQUESTING, WAIT_LOW} handshake_state_t;

always_ff @(posedge clk) begin
    if (reset) state <= READY;
    else       state <= next_state;
end

always_comb begin
    next_state = state;
    request = 1'b0;
    case (state)
        READY:      if (start) next_state = REQUESTING;
        REQUESTING: begin
            request = 1'b1;
            if (acknowledge) next_state = WAIT_LOW;
        end
        WAIT_LOW:   if (!acknowledge) next_state = READY;
        default:    next_state = READY;
    endcase
end
""",
    ),
    _pattern(
        "Two-client round-robin arbiter", "State machines", "Advanced",
        "Alternates priority after successful grants so both requesters make progress.", ("rrarb",),
        """
always_comb begin
    grant = 2'b00;
    if (request == 2'b11) grant[last_grant ^ 1'b1] = 1'b1;
    else if (request[0])  grant[0] = 1'b1;
    else if (request[1])  grant[1] = 1'b1;
end

always_ff @(posedge clk) begin
    if (reset) last_grant <= 1'b1;
    else if (grant[0] && accept) last_grant <= 1'b0;
    else if (grant[1] && accept) last_grant <= 1'b1;
end
""",
    ),
    _pattern(
        "1011 sequence detector", "State machines", "Intermediate",
        "Recognizes the serial bit pattern 1011 and allows overlapping matches.", ("seq1011",),
        """
typedef enum logic [1:0] {NONE, SAW_1, SAW_10, SAW_101} seq_state_t;

always_ff @(posedge clk) begin
    if (reset) state <= NONE;
    else       state <= next_state;
end

always_comb begin
    detected = 1'b0;
    unique case (state)
        NONE:    next_state = serial_bit ? SAW_1 : NONE;
        SAW_1:   next_state = serial_bit ? SAW_1 : SAW_10;
        SAW_10:  next_state = serial_bit ? SAW_101 : NONE;
        SAW_101: begin
            detected = serial_bit;
            next_state = serial_bit ? SAW_1 : SAW_10;
        end
        default: next_state = NONE;
    endcase
end
""",
    ),

    # Arithmetic and data path --------------------------------------------
    _pattern(
        "Add-subtract datapath", "Arithmetic and data path", "Beginner",
        "Selects addition or subtraction while keeping the result width explicit.", ("addsub",),
        """
logic [WIDTH:0] extended_a, extended_b;

assign extended_a = {1'b0, operand_a};
assign extended_b = {1'b0, operand_b};
assign result = subtract ? (extended_a - extended_b)
                         : (extended_a + extended_b);
""",
    ),
    _pattern(
        "Saturating unsigned adder", "Arithmetic and data path", "Intermediate",
        "Clamps an overflowing unsigned sum instead of wrapping to zero.", ("satadd",),
        """
logic [WIDTH:0] wide_sum;

assign wide_sum = {1'b0, value_a} + {1'b0, value_b};
assign saturated_sum = wide_sum[WIDTH] ? {WIDTH{1'b1}}
                                       : wide_sum[WIDTH-1:0];
""",
    ),
    _pattern(
        "Signed absolute value", "Arithmetic and data path", "Beginner",
        "Returns the magnitude of a two's-complement signed input.", ("absval",),
        """
assign magnitude = signed_value[WIDTH-1]
                 ? (~signed_value + 1'b1)
                 : signed_value;
""",
    ),
    _pattern(
        "Accumulator with clear", "Arithmetic and data path", "Beginner",
        "Adds samples into a wider running total under clock-enable control.", ("accum",),
        """
always_ff @(posedge clk) begin
    if (reset || clear) begin
        accumulator <= '0;
    end else if (sample_valid) begin
        accumulator <= accumulator + sample_value;
    end
end
""",
    ),
    _pattern(
        "Power-of-two moving average", "Arithmetic and data path", "Advanced",
        "Maintains a running sum so an average needs only subtraction, addition, and a shift.", ("movavg",),
        """
always_ff @(posedge clk) begin
    if (reset) begin
        sample_index <= '0;
        running_sum <= '0;
        for (int i = 0; i < SAMPLE_COUNT; i++) samples[i] <= '0;
    end else if (sample_valid) begin
        running_sum <= running_sum - samples[sample_index] + new_sample;
        samples[sample_index] <= new_sample;
        sample_index <= sample_index + 1'b1;
    end
end

assign average = running_sum >> $clog2(SAMPLE_COUNT);
""",
    ),
    _pattern(
        "Barrel shifter", "Arithmetic and data path", "Intermediate",
        "Performs a variable left or right logical shift in combinational logic.", ("barrel",),
        """
always_comb begin
    if (shift_left) shifted_data = input_data << shift_amount;
    else            shifted_data = input_data >> shift_amount;
end
""",
    ),
    _pattern(
        "Leading-zero counter", "Arithmetic and data path", "Advanced",
        "Counts zeros from the most-significant bit until the first one.", ("lzc",),
        """
always_comb begin
    leading_zeros = WIDTH;
    found_one = 1'b0;
    for (int i = WIDTH-1; i >= 0; i--) begin
        if (!found_one && input_data[i]) begin
            leading_zeros = WIDTH-1-i;
            found_one = 1'b1;
        end
    end
end
""",
    ),
    _pattern(
        "Fibonacci LFSR", "Arithmetic and data path", "Intermediate",
        "Generates a repeatable pseudo-random sequence from a nonzero seed.", ("lfsr",),
        """
logic feedback;
assign feedback = lfsr[15] ^ lfsr[13] ^ lfsr[12] ^ lfsr[10];

always_ff @(posedge clk) begin
    if (reset) begin
        lfsr <= 16'h0001;
    end else if (advance) begin
        lfsr <= {lfsr[14:0], feedback};
    end
end
""",
    ),

    # Interfaces and handshakes -------------------------------------------
    _pattern(
        "Ready-valid pipeline register", "Interfaces and handshakes", "Intermediate",
        "Moves one transfer stage while applying backpressure correctly.", ("rvpipe",),
        """
assign input_ready = !output_valid || output_ready;

always_ff @(posedge clk) begin
    if (reset) begin
        output_valid <= 1'b0;
    end else if (input_ready) begin
        output_valid <= input_valid;
        if (input_valid) output_data <= input_data;
    end
end
""",
    ),
    _pattern(
        "One-entry skid buffer", "Interfaces and handshakes", "Advanced",
        "Temporarily stores one ready-valid transfer when downstream stalls.", ("skid",),
        """
assign input_ready = !buffer_valid;
assign output_valid = buffer_valid || input_valid;
assign output_data = buffer_valid ? buffer_data : input_data;

always_ff @(posedge clk) begin
    if (reset) begin
        buffer_valid <= 1'b0;
    end else begin
        if (input_valid && input_ready && !output_ready) begin
            buffer_data <= input_data;
            buffer_valid <= 1'b1;
        end else if (output_ready) begin
            buffer_valid <= 1'b0;
        end
    end
end
""",
    ),
    _pattern(
        "UART baud-rate tick", "Interfaces and handshakes", "Intermediate",
        "Creates the clock-enable tick used by a UART transmitter or receiver.", ("uartbaud",),
        """
always_ff @(posedge clk) begin
    if (reset) begin
        baud_count <= '0;
        baud_tick <= 1'b0;
    end else if (baud_count == CLKS_PER_BIT-1) begin
        baud_count <= '0;
        baud_tick <= 1'b1;
    end else begin
        baud_count <= baud_count + 1'b1;
        baud_tick <= 1'b0;
    end
end
""",
    ),
    _pattern(
        "UART receive start detector", "Interfaces and handshakes", "Intermediate",
        "Detects a falling edge on an already synchronized UART receive input.", ("uartstart",),
        """
always_ff @(posedge clk) begin
    if (reset) rx_sync_d <= 1'b1;
    else       rx_sync_d <= rx_sync;
end

assign uart_start = rx_sync_d & ~rx_sync;
""",
    ),
    _pattern(
        "SPI mode-0 shift register", "Interfaces and handshakes", "Advanced",
        "Samples MISO and advances MOSI in the SPI clock domain; synchronize completed data before another domain uses it.", ("spishift",),
        """
always_ff @(posedge spi_clk) begin
    if (!chip_select_n) begin
        rx_shift <= {rx_shift[6:0], miso};
    end
end

always_ff @(negedge spi_clk) begin
    if (!chip_select_n) begin
        tx_shift <= {tx_shift[6:0], 1'b0};
    end
end

assign mosi = tx_shift[7];
""",
    ),
    _pattern(
        "I2C open-drain output", "Interfaces and handshakes", "Intermediate",
        "Drives an I2C line low or releases it; the board must provide the required pull-up.", ("i2cod",),
        """
assign sda = drive_sda_low ? 1'b0 : 1'bz;
assign sampled_sda = sda;
""",
    ),
    _pattern(
        "Memory-mapped register write", "Interfaces and handshakes", "Beginner",
        "Updates a control register when write-enable and its address match.", ("regwrite",),
        """
always_ff @(posedge clk) begin
    if (reset) begin
        control_register <= RESET_VALUE;
    end else if (write_enable && address == CONTROL_ADDRESS) begin
        control_register <= write_data;
    end
end
""",
    ),
    _pattern(
        "Interrupt event latch", "Interfaces and handshakes", "Intermediate",
        "Keeps an interrupt pending until it is acknowledged.", ("irq",),
        """
always_ff @(posedge clk) begin
    if (reset) begin
        interrupt_pending <= 1'b0;
    end else begin
        if (interrupt_ack)   interrupt_pending <= 1'b0;
        if (interrupt_event) interrupt_pending <= 1'b1;
    end
end

assign interrupt_request = interrupt_pending;
""",
    ),

    # Memories and buffers ------------------------------------------------
    _pattern(
        "Synchronous single-port RAM", "Memories and buffers", "Intermediate",
        "Infers a RAM with synchronous write and registered read data.", ("spram",),
        """
logic [DATA_WIDTH-1:0] memory [0:DEPTH-1];

always_ff @(posedge clk) begin
    if (write_enable) begin
        memory[address] <= write_data;
    end
    read_data <= memory[address];
end
""",
    ),
    _pattern(
        "Simple dual-port RAM", "Memories and buffers", "Advanced",
        "Uses independent synchronous ports; verify same-address read/write behavior for the target memory primitive.", ("dpram",),
        """
logic [DATA_WIDTH-1:0] memory [0:DEPTH-1];

always_ff @(posedge write_clk) begin
    if (write_enable) memory[write_address] <= write_data;
end

always_ff @(posedge read_clk) begin
    read_data <= memory[read_address];
end
""",
    ),
    _pattern(
        "Case-statement ROM", "Memories and buffers", "Beginner",
        "Describes a small constant lookup table with a complete default.", ("romcase",),
        """
always_comb begin
    unique case (address)
        3'd0: rom_data = 8'h3C;
        3'd1: rom_data = 8'h42;
        3'd2: rom_data = 8'h81;
        3'd3: rom_data = 8'hA5;
        default: rom_data = 8'h00;
    endcase
end
""",
    ),
    _pattern(
        "Initialized ROM array", "Memories and buffers", "Intermediate",
        "Loads constant contents from a hex file; confirm memory-file synthesis support in the target toolchain.", ("rominit",),
        """
logic [DATA_WIDTH-1:0] rom [0:DEPTH-1];

initial begin
    $readmemh("rom_data.hex", rom);
end

always_ff @(posedge clk) begin
    read_data <= rom[address];
end
""",
    ),
    _pattern(
        "Synchronous FIFO core", "Memories and buffers", "Advanced",
        "Implements single-clock FIFO storage with guarded operations and explicit pointer wrapping.", ("fifo",),
        """
logic [DATA_WIDTH-1:0] fifo_memory [0:DEPTH-1];

assign empty = (item_count == 0);
assign full = (item_count == DEPTH);

always_ff @(posedge clk) begin
    if (reset) begin
        write_pointer <= '0;
        read_pointer <= '0;
        item_count <= '0;
    end else begin
        if (write_enable && !full) begin
            fifo_memory[write_pointer] <= write_data;
            write_pointer <= (write_pointer == DEPTH-1) ? '0 : write_pointer + 1'b1;
        end
        if (read_enable && !empty) begin
            read_data <= fifo_memory[read_pointer];
            read_pointer <= (read_pointer == DEPTH-1) ? '0 : read_pointer + 1'b1;
        end
        case ({write_enable && !full, read_enable && !empty})
            2'b10: item_count <= item_count + 1'b1;
            2'b01: item_count <= item_count - 1'b1;
            default: item_count <= item_count;
        endcase
    end
end
""",
    ),
    _pattern(
        "Circular-buffer pointer", "Memories and buffers", "Intermediate",
        "Wraps a pointer explicitly for depths that are not powers of two.", ("ringptr",),
        """
always_ff @(posedge clk) begin
    if (reset) begin
        pointer <= '0;
    end else if (advance) begin
        if (pointer == DEPTH-1) pointer <= '0;
        else                    pointer <= pointer + 1'b1;
    end
end
""",
    ),
    _pattern(
        "Tapped delay line", "Memories and buffers", "Intermediate",
        "Delays a data word by a fixed number of enabled clock cycles.", ("delayline",),
        """
logic [DATA_WIDTH-1:0] delay_pipe [0:DELAY_CYCLES];

always_ff @(posedge clk) begin
    if (enable) begin
        delay_pipe[0] <= input_data;
        for (int i = 1; i <= DELAY_CYCLES; i++) begin
            delay_pipe[i] <= delay_pipe[i-1];
        end
    end
end

assign delayed_data = delay_pipe[DELAY_CYCLES];
""",
    ),

    # Verification and testbenches ----------------------------------------
    _pattern(
        "Testbench clock generator", "Verification", "Beginner",
        "Generates a periodic testbench clock; never place delay controls in synthesizable RTL.", ("tbclock",),
        """
logic clk = 1'b0;
always #(CLOCK_PERIOD_NS / 2.0) clk = ~clk;
""",
        synthesizable=False,
    ),
    _pattern(
        "Testbench reset sequence", "Verification", "Beginner",
        "Applies reset for several rising edges before starting stimulus.", ("tbreset",),
        """
initial begin
    reset = 1'b1;
    repeat (5) @(posedge clk);
    reset = 1'b0;
    @(posedge clk);
end
""",
        synthesizable=False,
    ),
    _pattern(
        "Immediate simulation assertion", "Verification", "Beginner",
        "Stops a simulation immediately when an observed value is wrong.", ("assertx",),
        """
if (actual !== expected) begin
    $error("Mismatch: actual=%0h expected=%0h", actual, expected);
    $fatal(1);
end
""",
        synthesizable=False,
    ),
    _pattern(
        "Concurrent property assertion", "Verification", "Advanced",
        "Checks on every clock that a request receives an acknowledge within four cycles.", ("sva_reqack",),
        """
property request_gets_acknowledged;
    @(posedge clk) disable iff (reset)
        request |-> ##[1:4] acknowledge;
endproperty

assert property (request_gets_acknowledged)
    else $error("Request was not acknowledged in time");
""",
        synthesizable=False,
    ),
    _pattern(
        "Simulation timeout guard", "Verification", "Beginner",
        "Prevents a broken testbench from running forever.", ("tbtimeout",),
        """
initial begin
    #(MAX_SIMULATION_NS);
    $fatal(1, "TIMEOUT: simulation did not finish");
end
""",
        synthesizable=False,
    ),
    _pattern(
        "Wait for clock cycles", "Verification", "Beginner",
        "Advances a testbench by an exact number of synchronous cycles.", ("waitcycles",),
        """
repeat (CYCLE_COUNT) @(posedge clk);
""",
        synthesizable=False,
    ),
    _pattern(
        "Reusable pulse task", "Verification", "Intermediate",
        "Drives a clean one-cycle input pulse from a testbench.", ("tbpulse",),
        """
task automatic send_pulse;
    begin
        @(negedge clk);
        pulse_input = 1'b1;
        @(negedge clk);
        pulse_input = 1'b0;
    end
endtask
""",
        synthesizable=False,
    ),
    _pattern(
        "Deterministic randomized stimulus", "Verification", "Intermediate",
        "Applies bounded pseudo-random inputs while retaining a repeatable seed.", ("tbrandom",),
        """
int unsigned random_seed = 32'h1A2B3C4D;

repeat (100) begin
    @(negedge clk);
    input_valid = $urandom(random_seed) & 1'b1;
    input_data = $urandom(random_seed);
end
""",
        synthesizable=False,
    ),
)


CATEGORIES: tuple[str, ...] = tuple(dict.fromkeys(pattern.category for pattern in PATTERNS))
DIFFICULTIES: tuple[str, ...] = ("Beginner", "Intermediate", "Advanced")
PATTERN_BY_TITLE = {pattern.title: pattern for pattern in PATTERNS}
HDL_SNIPPETS = {pattern.title: pattern.code for pattern in PATTERNS}
HDL_SNIPPET_ALIASES = {
    alias: pattern.title
    for pattern in PATTERNS
    for alias in pattern.aliases
}


def search_patterns(
    query: str = "",
    category: str = "All categories",
    difficulty: str = "All levels",
) -> list[HDLPattern]:
    """Return library entries matching metadata, aliases, or example code."""
    needle = query.strip().casefold()
    matches: list[HDLPattern] = []
    for pattern in PATTERNS:
        if category != "All categories" and pattern.category != category:
            continue
        if difficulty != "All levels" and pattern.difficulty != difficulty:
            continue
        haystack = "\n".join((
            pattern.title,
            pattern.category,
            pattern.difficulty,
            "synthesizable rtl" if pattern.synthesizable else "simulation only testbench",
            pattern.summary,
            " ".join(pattern.aliases),
            pattern.code,
        )).casefold()
        if not needle or needle in haystack:
            matches.append(pattern)
    return matches


def validate_patterns(patterns: tuple[HDLPattern, ...] = PATTERNS) -> list[str]:
    """Validate metadata invariants used by completions and the Pattern Library."""
    problems: list[str] = []
    titles: set[str] = set()
    aliases: set[str] = set()
    valid_difficulties = set(DIFFICULTIES)
    for pattern in patterns:
        if not pattern.title.strip() or pattern.title in titles:
            problems.append(f"Duplicate or empty title: {pattern.title!r}")
        titles.add(pattern.title)
        if pattern.difficulty not in valid_difficulties:
            problems.append(f"Invalid difficulty for {pattern.title}: {pattern.difficulty}")
        if not pattern.category.strip() or not pattern.summary.strip() or not pattern.code.strip():
            problems.append(f"Incomplete pattern metadata: {pattern.title}")
        if "\t" in pattern.code:
            problems.append(f"Tab indentation is not allowed: {pattern.title}")
        for alias in pattern.aliases:
            if not re.fullmatch(r"[a-z][a-z0-9_]*", alias):
                problems.append(f"Invalid alias {alias!r} for {pattern.title}")
            if alias in aliases:
                problems.append(f"Duplicate alias: {alias}")
            aliases.add(alias)
    return problems


_VALIDATION_ERRORS = validate_patterns()
if _VALIDATION_ERRORS:
    raise RuntimeError("Invalid HDL pattern library:\n" + "\n".join(_VALIDATION_ERRORS))
