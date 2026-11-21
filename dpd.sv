// Signed samples F14; signed coefficients F12. One clock domain.
// Configure six words while idle and with the producer paused.
module dpd(
    input logic clk, rst,
    input logic cfg_we,
    input logic [2:0] cfg_addr,
    input logic [31:0] cfg_data,
    input logic [31:0] s_data,
    input logic s_valid, s_last,
    output logic s_ready,
    output logic [31:0] m_data,
    output logic m_valid, m_last,
    input logic m_ready
);
    typedef enum logic [1:0] {IDLE, MAC, SEND} state_t;
    state_t state;
    logic [31:0] coeff [0:5];
    logic [2:0] term;
    logic signed [15:0] si, sq, prev_i, prev_q, delay_i, delay_q;
    logic signed [23:0] bi, bq;
    logic signed [18:0] power_reg, previous_power, delayed_power;
    logic signed [31:0] ii, qq;
    logic [31:0] power_sum;
    logic signed [15:0] cr, ci;
    logic signed [42:0] next_bi, next_bq;
    logic signed [47:0] acc_i, acc_q, sum_i, sum_q;

    assign si = s_data[15:0];
    assign sq = s_data[31:16];
    assign ii = si * si;
    assign qq = sq * sq;
    assign power_sum = $unsigned(ii) + $unsigned(qq);
    assign cr = coeff[term][15:0];
    assign ci = coeff[term][31:16];
    assign next_bi = bi * power_reg;
    assign next_bq = bq * power_reg;
    assign sum_i = acc_i + bi*cr - bq*ci;
    assign sum_q = acc_q + bi*ci + bq*cr;
    assign s_ready = state == IDLE && !cfg_we && !rst;
    assign m_valid = state == SEND;

    function automatic logic [15:0] saturate(input logic signed [47:0] value);
        logic signed [47:0] shifted;
        shifted = value >>> 12;
        if (shifted > 32767) return 16'h7fff;
        if (shifted < -32768) return 16'h8000;
        return shifted[15:0];
    endfunction

    always_ff @(posedge clk) begin
        if (rst) begin
            state <= IDLE;
            prev_i <= 0;
            prev_q <= 0;
            previous_power <= 0;
            term <= 0;
            m_last <= 0;
        end else case (state)
            IDLE: begin
                if (cfg_we && cfg_addr < 6) coeff[cfg_addr] <= cfg_data;
                if (s_valid && s_ready) begin
                    bi <= 24'(si);
                    bq <= 24'(sq);
                    power_reg <= 19'(power_sum >> 14);
                    delay_i <= prev_i;
                    delay_q <= prev_q;
                    delayed_power <= previous_power;
                    prev_i <= si;
                    prev_q <= sq;
                    previous_power <= 19'(power_sum >> 14);
                    term <= 0;
                    acc_i <= 0;
                    acc_q <= 0;
                    m_last <= s_last;
                    state <= MAC;
                end
            end
            MAC: begin
                acc_i <= sum_i;
                acc_q <= sum_q;
                if (term == 5) begin
                    m_data <= {saturate(sum_q), saturate(sum_i)};
                    state <= SEND;
                end else begin
                    term <= term + 1'b1;
                    if (term == 2) begin
                        bi <= 24'(delay_i);
                        bq <= 24'(delay_q);
                        power_reg <= delayed_power;
                    end else begin
                        bi <= 24'(next_bi >>> 14);
                        bq <= 24'(next_bq >>> 14);
                    end
                end
            end
            SEND: if (m_ready) state <= IDLE;
            default: state <= IDLE;
        endcase
    end
endmodule
