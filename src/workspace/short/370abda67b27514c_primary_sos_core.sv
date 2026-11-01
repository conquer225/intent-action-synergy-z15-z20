`timescale 1ns/1ps
// Isolated timing candidate: register each shared multiplier result before
// the unchanged DF-II-transposed accumulation/rounding operation.
module primary_sos_core (
    input wire clk,
    input wire rst,
    input wire in_valid,
    output wire in_ready,
    input wire [2:0] in_channel,
    input wire signed [39:0] in_data,
    output reg out_valid,
    input wire out_ready,
    output reg [2:0] out_channel,
    output reg signed [39:0] out_data,
    output reg overflow
);
    localparam IDLE=0, YM=1, Y=2, B1M=3, B1=4, A1M=5, A1=6,
               B2M=7, B2=8, A2M=9, A2=10, HOLD=11;
    reg [3:0] state;
    reg [2:0] stage_index;
    reg [2:0] channel;
    reg signed [39:0] x, y_value;
    reg signed [39:0] z1[0:39];
    reg signed [39:0] z2[0:39];
    reg signed [33:0] coeff[0:24];
    reg signed [75:0] partial;
    reg signed [75:0] mul_product;
    reg signed [39:0] mul_data;
    reg signed [33:0] mul_coeff;
    wire signed [73:0] product = mul_data * mul_coeff;
    wire signed [75:0] wide_product = {{2{product[73]}}, product};
    wire [5:0] slot = {stage_index, channel};
    wire signed [75:0] state1 = {{36{z1[slot][39]}}, z1[slot]};
    wire signed [75:0] state2 = {{36{z2[slot][39]}}, z2[slot]};
    reg signed [75:0] accumulator, rounded;
    localparam signed [75:0] HALF = 76'sd1073741824;
    localparam signed [75:0] MAX_DATA = 76'sd549755813887;
    localparam signed [75:0] MIN_DATA = -76'sd549755813888;
    wire clipped = (rounded > MAX_DATA) || (rounded < MIN_DATA);
    wire signed [39:0] narrowed = rounded > MAX_DATA ? 40'sh7fffffffff :
                                 rounded < MIN_DATA ? 40'sh8000000000 : rounded[39:0];
    assign in_ready = state == IDLE && !rst;
    integer k;
    initial $readmemh("coeff.hex", coeff);

    always @* begin
        mul_data = x;
        mul_coeff = coeff[stage_index*5];
        case (state)
            B1M: mul_coeff = coeff[stage_index*5+1];
            A1M: begin mul_coeff = coeff[stage_index*5+3]; mul_data = y_value; end
            B2M: mul_coeff = coeff[stage_index*5+2];
            A2M: begin mul_coeff = coeff[stage_index*5+4]; mul_data = y_value; end
            default: begin end
        endcase
        accumulator = 0;
        case (state)
            Y: accumulator = mul_product + (state1 <<< 31);
            A1: accumulator = partial - mul_product + (state2 <<< 31);
            A2: accumulator = partial - mul_product;
            default: begin end
        endcase
        if (accumulator < 0)
            rounded = -(((-accumulator) + HALF) >>> 31);
        else
            rounded = (accumulator + HALF) >>> 31;
    end

    always @(posedge clk) begin
        if (rst) begin
            state <= IDLE;
            stage_index <= 0;
            channel <= 0;
            x <= 0;
            y_value <= 0;
            partial <= 0;
            mul_product <= 0;
            out_valid <= 0;
            out_channel <= 0;
            out_data <= 0;
            overflow <= 0;
            for (k=0; k<40; k=k+1) begin z1[k] <= 0; z2[k] <= 0; end
        end else begin
            case (state)
                IDLE: if (in_valid) begin
                    channel <= in_channel;
                    x <= in_data;
                    stage_index <= 0;
                    state <= YM;
                end
                YM: begin mul_product <= wide_product; state <= Y; end
                Y: begin
                    y_value <= narrowed;
                    if (clipped) overflow <= 1;
                    state <= B1M;
                end
                B1M: begin mul_product <= wide_product; state <= B1; end
                B1: begin partial <= mul_product; state <= A1M; end
                A1M: begin mul_product <= wide_product; state <= A1; end
                A1: begin
                    z1[slot] <= narrowed;
                    if (clipped) overflow <= 1;
                    state <= B2M;
                end
                B2M: begin mul_product <= wide_product; state <= B2; end
                B2: begin partial <= mul_product; state <= A2M; end
                A2M: begin mul_product <= wide_product; state <= A2; end
                A2: begin
                    z2[slot] <= narrowed;
                    if (clipped) overflow <= 1;
                    if (stage_index == 4) begin
                        out_data <= y_value;
                        out_channel <= channel;
                        out_valid <= 1;
                        state <= HOLD;
                    end else begin
                        x <= y_value;
                        stage_index <= stage_index + 1;
                        state <= YM;
                    end
                end
                HOLD: if (out_ready) begin out_valid <= 0; state <= IDLE; end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
