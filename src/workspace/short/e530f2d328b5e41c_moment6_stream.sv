// Isolated six-channel integer moment reducer. No AXI/DMA or production use.
// Input packing: channel 0 in bits [15:0], channel 5 in bits [95:80].
// Output upper triangle order: (0,0),(0,1),...,(0,5),(1,1),...,(5,5).
module moment6_stream (
    input  logic                  clk,
    input  logic                  rst_n,
    input  logic                  valid_i,
    input  logic                  start_i,
    input  logic                  last_i,
    input  logic                  result_ready_i,
    input  logic signed [95:0]    sample_i,
    output logic                  ready_o,
    output logic                  result_valid_o,
    output logic [15:0]           count_o,
    output logic signed [287:0]   sums_o,
    output logic signed [1007:0]  cross_o
);
    logic [15:0] count_q;
    wire accept = valid_i && ready_o;
    assign ready_o = !result_valid_o || result_ready_i;
    assign count_o = count_q;

    always_ff @(posedge clk) begin
        if (!rst_n) begin
            count_q <= '0;
            result_valid_o <= 1'b0;
        end else begin
            if (result_valid_o && result_ready_i)
                result_valid_o <= 1'b0;
            if (accept && last_i)
                result_valid_o <= 1'b1;
            if (accept)
                count_q <= start_i ? 16'd1 : count_q + 16'd1;
        end
    end

    for (genvar c = 0; c < 6; c++) begin : g_sum
        logic signed [47:0] accum;
        wire signed [15:0] x = sample_i[16*c +: 16];
        wire signed [47:0] x_ext = {{32{x[15]}}, x};
        always_ff @(posedge clk) begin
            if (!rst_n) begin
                accum <= '0;
            end else if (accept) begin
                accum <= start_i ? x_ext : accum + x_ext;
            end
        end
        assign sums_o[48*c +: 48] = accum;
    end

    for (genvar i = 0; i < 6; i++) begin : g_row
        for (genvar j = i; j < 6; j++) begin : g_col
            localparam int INDEX = i * 6 - (i * (i - 1)) / 2 + j - i;
            logic signed [47:0] accum;
            wire signed [15:0] xi = sample_i[16*i +: 16];
            wire signed [15:0] xj = sample_i[16*j +: 16];
            wire signed [31:0] product = xi * xj;
            wire signed [47:0] product_ext = {{16{product[31]}}, product};
            always_ff @(posedge clk) begin
                if (!rst_n) begin
                    accum <= '0;
                end else if (accept) begin
                    accum <= start_i ? product_ext : accum + product_ext;
                end
            end
            assign cross_o[48*INDEX +: 48] = accum;
        end
    end
endmodule
